"""對外高階控制器（規格第 6 章）。

Phase 0 提供：ROM 載入、reset、HLE post-boot、記憶體/CPU/畫面/輸入的觀測，
以及 ``inspect-rom`` 所需的 header 資訊。CPU 執行、PPU frame、snapshot
payload 分別在 Phase 1/2/3 接上；尚未實作的方法明確 raise ``NotImplementedError``，
不回傳假結果。
"""

from __future__ import annotations

import os

import hashlib
import os
import random
import struct
from pathlib import Path
from typing import ClassVar

from .api_types import (
    Button,
    BootMode,
    CPUState,
    EmulatorConfig,
    EmulatorEvent,
    EventKind,
    FrameResult,
    MemoryRegionInfo,
    MemoryRegionKind,
    StepResult,
    TimingMode,
    AudioMode,
    VideoMode,
)
from .bus.address_bus import AddressBus
from .bus.io import IRQ_KEYPAD, IRQ_TIMER0
from .bus.regions import BIOS_SIZE
from .config import config_sha256, validate_config
from .cpu.arm7tdmi import Arm7Tdmi
from .cpu.registers import CPSR_F, CPSR_I, MODE_SVC, MODE_SYS
from .breakpoints import BreakpointTable
from .errors import BiosChecksumError, BiosMissingError, GbaEmuError
from .events import EventStream
from .hle.postboot import PostBootState, apply_post_boot
from .hle.swi_impl import build_handlers
from .hle.swi_table import SwiTable
from .log import get_logger
from .memory.cartridge import RomCartridge, RomHeader, load_rom_file
from .memory.savedata import legacy_save_path_for, save_path_for
from .state.snapshot import (
    SECTION_BUS,
    SECTION_CPU,
    SECTION_CRT,
    SECTION_DMA,
    SECTION_IRQ,
    SECTION_KEY,
    SECTION_PPU,
    SECTION_SCH,
    SECTION_TMR,
    SNAPSHOT_HEADER_SIZE,
    build_snapshot_header,
    pack_sections,
    parse_snapshot,
    require_sections,
    unpack_sections,
)
from .timing import Scheduler
from .video.framebuffer import HEIGHT, WIDTH, Framebuffer

logger = get_logger("emulator")

_PHASE1 = "step_cycles() 於 Phase 1 實作（ARM/THUMB 指令執行）"
_PHASE3 = "snapshot payload 於 Phase 3 實作"


class Emulator:
    """一個 GBA 模擬器 instance（Phase 1：CPU 執行 + 觀測）。"""

    def __init__(
        self,
        rom: bytes,
        *,
        config: EmulatorConfig,
        rom_path: Path | None = None,
    ) -> None:
        validate_config(config)
        self._config = config
        self._rom_path = rom_path
        self._cartridge = RomCartridge(rom)
        self._rom_sha256 = hashlib.sha256(self._cartridge.rom_bytes).digest()
        if rom_path is not None:
            self._load_save_file(Path(rom_path))
        self._save_baseline = (
            self._cartridge.save.export() if self._cartridge.save is not None else None
        )
        self._bios_bytes = self._load_bios(config)

        # HLE 模式仍然可以載入真實 BIOS 內容（config 允許 HLE + bios_path），
        # 只係開機流程用 HLE；BIOS 視窗讀值就係真資料（suite「BIOS load」）。
        bus_bios = self._bios_bytes
        self.events = EventStream()
        self._framebuffer = Framebuffer()
        self.input = InputPort()  # KEYINPUT 由 bus 的 I/O 暫存器讀取
        self._bus = AddressBus(
            self._cartridge,
            bios=bus_bios,
            keypad=self.input,
            framebuffer=self._framebuffer,
            events=self.events,
        )
        self._cpu = Arm7Tdmi(
            self._bus, functional=config.timing is TimingMode.FUNCTIONAL
        )
        # TIMED／TRACE 用 mGBA 式 active-region accounting（FUNCTIONAL 保持近似）。
        self._cpu.bus.mgba_timing = config.timing is not TimingMode.FUNCTIONAL
        self._scheduler = Scheduler()
        self._breakpoints = BreakpointTable()
        self._swi_table = SwiTable(
            strict=config.hle_strict, handlers=build_handlers(self._cpu)
        )
        self._cpu.swi_table = self._swi_table
        self._bus.ppu.render_enabled = config.video is VideoMode.FRAMEBUFFER
        self._bus.sound.enabled = config.audio is AudioMode.BUFFERED
        self._bus.dma.functional = config.timing is TimingMode.FUNCTIONAL
        self._rng = random.Random(config.seed)

        self._frame_index = 0
        self._paused = False
        self._closed = False

        # 對外 view / port。
        self.cpu = CPUView(self)
        self.memory = MemoryView(self)
        self.video = VideoView(self)
        self.audio = AudioView(self)

        self._boot()

    # ------------------------------------------------------------------
    # 建構 / 生命週期（規格 6.1）
    # ------------------------------------------------------------------
    @classmethod
    def from_rom(
        cls, rom_path: str | Path, *, config: EmulatorConfig | None = None
    ) -> "Emulator":
        if os.environ.get("GBAEMU_BACKEND", "python") == "rust":
            from .native import NativeEmulator

            return NativeEmulator.from_rom(rom_path, config)  # type: ignore[return-value]
        effective = config if config is not None else EmulatorConfig()
        effective.validate()
        rom = load_rom_file(rom_path)
        return cls(rom, config=effective, rom_path=Path(rom_path))

    def reset(self, *, seed: int | None = None) -> None:
        self._ensure_open()
        self._rng.seed(self._config.seed if seed is None else seed)
        self.input.clear()
        self._paused = False
        self._boot()

    def step_cycles(self, cycles: int) -> StepResult:
        self._ensure_open()
        if isinstance(cycles, bool) or not isinstance(cycles, int):
            raise ValueError("cycles 必須是整數")
        if cycles < 0:
            raise ValueError("cycles 不可為負")
        if cycles == 0:
            return StepResult(0, 0, self._cpu.core.halted, None, ())

        executed = 0
        breakpoint_hit: int | None = None
        core = self._cpu.core
        while executed < cycles:
            hit = self._breakpoints.match(core.regs[15], bool(core.cpsr & 0x20))
            if hit is not None:
                breakpoint_hit = hit.id
                break
            chunk = self._halted_chunk()
            if chunk:
                chunk = min(chunk, cycles - executed)
                self._cpu.cycles += chunk
                self._bus.tick(chunk)
                executed += chunk
                executed += self._service_dma()
                self._bus.io_registers.poll_keypad()
                self._cpu.arm_irq()
                continue
            cost = self._cpu.peek_cycles()
            if executed + cost > cycles:
                break  # 不得超出請求的 cycle 數（規格 5.3）
            executed += self._cpu.step()
            self._bus.tick(cost)
            if self._bus.dma.startup > 0:
                self._bus.dma.startup = max(0, self._bus.dma.startup - cost)
            if self._bus.dma.startup == 0:
                executed += self._service_dma()
            self._bus.io_registers.poll_keypad()
            self._cpu.arm_irq()

        return StepResult(
            cycles_executed=executed,
            cycles_remaining=cycles - executed,
            halted=core.halted,
            breakpoint_hit=breakpoint_hit,
            events=tuple(self.events.poll()),
        )

    def _halted_chunk(self) -> int:
        """CPU 在 Halt 且沒有 IE&IF 可喚醒時，直接跳到下一個可能的 IRQ 事件。

        原本固定 64-cycle chunk 會讓 halted frame 產生數千次 Python 呼叫；這裡
        依 PPU DISPSTAT IRQ、timer overflow、keypad IRQ 計算下一個喚醒點，沒有
        事件時就直接跳到 frame 邊界。TIMED 模式保留逐 cycle 以維持精度。
        """

        if not self._cpu.core.halted:
            return 0
        if self._config.timing is not TimingMode.FUNCTIONAL:
            return 0
        ime, ie, flags = self._bus.io_registers.interrupts
        del ime
        if ie & flags:
            return 0

        ppu = self._bus.ppu
        limit = ppu.next_irq_cycle() - ppu.total_cycles
        if ie & IRQ_KEYPAD:
            limit = min(limit, 64)
        if ie & (IRQ_KEYPAD | IRQ_TIMER0 | (IRQ_TIMER0 << 1) | (IRQ_TIMER0 << 2) | (IRQ_TIMER0 << 3)):
            for index in range(4):
                if not (ie & (IRQ_TIMER0 << index)):
                    continue
                cycles = self._bus.timers.next_irq_cycles(index)
                if cycles is not None:
                    limit = min(limit, cycles)
        return max(1, limit)

    def _service_dma(self) -> int:
        """執行待處理的 DMA；DMA 佔用的 cycle 計入 CPU 與 PPU 時間。"""

        cycles = self._bus.dma.service()
        if cycles:
            self._bus.tick(cycles)
            self._cpu.cycles += cycles
        return cycles

    def step_frame(self, *, render: bool = True) -> FrameResult:
        """推進到下一個 frame 邊界（規格 5.3；280,896 cycles 為一 frame）。"""

        self._ensure_open()
        self._bus.ppu.render_enabled = (
            bool(render) and self._config.video is VideoMode.FRAMEBUFFER
        )
        start_cycles = self._cpu.cycles
        start_frame = self._bus.ppu.frame_index
        core = self._cpu.core

        while self._bus.ppu.frame_index == start_frame:
            hit = self._breakpoints.match(core.regs[15], bool(core.cpsr & 0x20))
            if hit is not None:
                self.events.emit(
                    EmulatorEvent(
                        kind=EventKind.BREAKPOINT,
                        cycle=self._cpu.cycles,
                        frame_index=self._bus.ppu.frame_index,
                        scanline=self._bus.ppu.vcount,
                        channel=None,
                        address=core.regs[15],
                        value=None,
                    )
                )
                break
            chunk = self._halted_chunk()
            if chunk:
                self._cpu.cycles += chunk
                self._bus.tick(chunk)
                self._service_dma()
                self._bus.io_registers.poll_keypad()
                self._cpu.arm_irq()
                continue
            cost = self._cpu.step()
            self._bus.tick(cost)
            if self._bus.dma.startup > 0:
                self._bus.dma.startup = max(0, self._bus.dma.startup - cost)
            if self._bus.dma.startup == 0:
                self._service_dma()
            self._bus.io_registers.poll_keypad()
            self._cpu.arm_irq()

        events = tuple(self.events.poll())
        ime, ie, flags = self._bus.io_registers.interrupts
        del ime, ie
        return FrameResult(
            frame_index=self._bus.ppu.frame_index,
            cycles=self._cpu.cycles - start_cycles,
            vblank_started=any(event.kind is EventKind.VBLANK_START for event in events),
            irq_pending=flags,
            halted=core.halted,
            events=events,
        )

    def run_frames(
        self,
        count: int,
        *,
        render: bool = False,
        collect_results: bool = False,
    ) -> list[FrameResult]:
        self._ensure_open()
        if count < 0:
            raise ValueError("count 不可為負")
        results = []
        for _ in range(count):
            result = self.step_frame(render=render)
            if collect_results:
                results.append(result)
        return results

    def run_until(self, event: EventKind, *, max_cycles: int) -> StepResult:
        """執行到下一個 ``event`` 或 ``max_cycles`` 為止（規格 6.1）。

        同 ``step_cycles()`` 一樣以完整指令為單位，唔會超額執行；事件由
        PPU／DMA／timer 喺 ``bus.tick()`` 期間 emit，逐條指令 poll，所以
        回傳的 ``events`` 會包含觸發停止嘅事件（以及之前同批事件）。
        """

        self._ensure_open()
        if not isinstance(event, EventKind):
            raise ValueError("event 必須是 EventKind")
        if isinstance(max_cycles, bool) or not isinstance(max_cycles, int):
            raise ValueError("max_cycles 必須是整數")
        if max_cycles <= 0:
            raise ValueError("max_cycles 必須為正整數")

        executed = 0
        breakpoint_hit: int | None = None
        collected: list[EmulatorEvent] = []
        core = self._cpu.core
        while executed < max_cycles:
            hit = self._breakpoints.match(core.regs[15], bool(core.cpsr & 0x20))
            if hit is not None:
                breakpoint_hit = hit.id
                break
            chunk = self._halted_chunk()
            if chunk:
                chunk = min(chunk, max_cycles - executed)
                self._cpu.cycles += chunk
                self._bus.tick(chunk)
                executed += chunk
                executed += self._service_dma()
                self._bus.io_registers.poll_keypad()
            else:
                cost = self._cpu.peek_cycles()
                if executed + cost > max_cycles:
                    break
                executed += self._cpu.step()
                self._bus.tick(cost)
                if self._bus.dma.startup > 0:
                    self._bus.dma.startup = max(0, self._bus.dma.startup - cost)
                if self._bus.dma.startup == 0:
                    executed += self._service_dma()
                self._bus.io_registers.poll_keypad()

            events = self.events.poll()
            if events:
                collected.extend(events)
                if any(item.kind is event for item in events):
                    break

        return StepResult(
            cycles_executed=executed,
            cycles_remaining=max_cycles - executed,
            halted=core.halted,
            breakpoint_hit=breakpoint_hit,
            events=tuple(collected),
        )

    def game_area(
        self, layer: int | None = None, *, include_attributes: bool = False
    ):
        """回傳 BG tile map（PyBoy ``game_area()`` 風格）。

        ``layer=None`` 會揀第一個 enabled 嘅 BG；回傳 numpy ``uint16`` array，
        shape 係該 BG 嘅 tile map 大小（通常 32x32）。
        """

        from .video.tilemap import read_game_area

        return read_game_area(
            self, layer=layer, include_attributes=include_attributes
        )

    def pause(self) -> None:
        self._paused = True

    def close(self) -> None:
        self._closed = True

    # ------------------------------------------------------------------
    # Snapshot（Phase 3）
    # ------------------------------------------------------------------
    def save_state(self) -> bytes:
        """序列化完整機器狀態（規格 5.7 九段 payload＋header）。"""

        self._ensure_open()
        ime, ie, interrupts = self._bus.io_registers.interrupts
        sections = {
            SECTION_CPU: self._cpu.snapshot_state(),
            SECTION_BUS: self._bus.snapshot_state(),
            SECTION_PPU: self._bus.ppu.snapshot_state(),
            SECTION_DMA: self._bus.dma.snapshot_state(),
            SECTION_TMR: self._bus.timers.snapshot_state(),
            SECTION_IRQ: struct.pack("<III", ime, ie, interrupts),
            SECTION_KEY: struct.pack(
                "<IH", self._bus.io_registers.keycnt, self.input.keyinput_mask
            ),
            SECTION_CRT: self._cartridge.snapshot(),
            SECTION_SCH: struct.pack("<QI", self._cpu.cycles, self._bus.ppu.frame_index),
        }
        payload = pack_sections(sections)
        return build_snapshot_header(
            payload,
            rom_sha256=self._rom_sha256,
            config_sha256=config_sha256(self._config),
        )

    def load_state(self, data: bytes) -> None:
        """驗證並還原 snapshot（不自動寫回 .sav）。"""

        self._ensure_open()
        parse_snapshot(
            data,
            rom_sha256=self._rom_sha256,
            config_sha256=config_sha256(self._config),
        )
        payload = data[SNAPSHOT_HEADER_SIZE:]
        sections = unpack_sections(payload)
        require_sections(sections)
        self._cpu.restore_state(sections[SECTION_CPU])
        self._bus.restore_state(sections[SECTION_BUS])
        self._bus.ppu.restore_state(sections[SECTION_PPU])
        self._bus.dma.restore_state(sections[SECTION_DMA])
        self._bus.timers.restore_state(sections[SECTION_TMR])
        ime, ie, interrupts = struct.unpack("<III", sections[SECTION_IRQ])
        self._bus.io_registers.load_interrupts(ime, ie, interrupts)
        self._cartridge.restore(sections[SECTION_CRT])
        self._cpu.cycles, frame = struct.unpack("<QI", sections[SECTION_SCH])
        self._bus.ppu.state.frame = frame
        self._bus.ppu.total_cycles = self._cpu.cycles
        self.events.clear()

    def cartridge_flush_to_disk(self) -> None:
        """把備份記憶體原子寫回 ``<rom stem>.sav``（規格 5.7：不自動寫回）。"""

        self._ensure_open()
        if self._cartridge.save is None:
            raise GbaEmuError("cartridge 沒有 save 媒體")
        if self._rom_path is None:
            raise GbaEmuError("cartridge 沒有 ROM 路徑，無法寫回磁碟")
        target = save_path_for(self._rom_path)
        temporary = target.with_name(target.name + ".tmp")
        data = self._cartridge.save.export()
        temporary.write_bytes(data)
        os.replace(temporary, target)
        self._save_baseline = data

    @property
    def battery_dirty(self) -> bool:
        """備份記憶體自載入／上次寫回後有無被遊戲寫過。"""

        if self._cartridge.save is None:
            return False
        return self._cartridge.save.export() != self._save_baseline

    # ------------------------------------------------------------------
    # 狀態
    # ------------------------------------------------------------------
    @property
    def config(self) -> EmulatorConfig:
        return self._config

    @property
    def rom_path(self) -> Path | None:
        return self._rom_path

    @property
    def rom_header(self) -> RomHeader:
        return self._cartridge.header

    @property
    def cycles(self) -> int:
        return self._cpu.cycles

    @property
    def frame_index(self) -> int:
        return self._bus.ppu.frame_index

    @property
    def halted(self) -> bool:
        return bool(self._cpu.core.halted)

    @property
    def irq_pending(self) -> bool:
        _, ie, flags = self._bus.io_registers.interrupts
        return bool(ie & flags)

    @property
    def vcount(self) -> int:
        return self._bus.ppu.vcount

    @property
    def is_closed(self) -> bool:
        return self._closed

    # ------------------------------------------------------------------
    # 內部
    # ------------------------------------------------------------------
    def _load_save_file(self, rom_path: Path) -> None:
        """先讀 ``<rom stem>.sav``，冇就退回舊式 ``<rom 全名>.sav``。"""

        save = self._cartridge.save
        if save is None:
            return
        for path in (save_path_for(rom_path), legacy_save_path_for(rom_path)):
            if not path.exists():
                continue
            data = path.read_bytes()
            if len(data) != len(save.export()):
                logger.warning(
                    "save 檔大小不符（%d != %d），忽略 %s",
                    len(data),
                    len(save.export()),
                    path,
                )
                continue
            save.load(data)
            return

    def _load_bios(self, config: EmulatorConfig) -> bytes | None:
        if config.bios_path is None:
            return None
        try:
            data = Path(config.bios_path).read_bytes()
        except OSError as exc:
            raise BiosMissingError(f"無法讀取 BIOS '{config.bios_path}': {exc}") from exc
        if len(data) != BIOS_SIZE:
            raise BiosChecksumError(
                f"BIOS 必須是 {BIOS_SIZE} bytes（16 KiB），得到 {len(data)}"
            )
        return data

    def _boot(self) -> None:
        self._bus.reset()
        self.events.clear()
        self._scheduler = Scheduler()
        self._framebuffer.clear()
        self._cpu.reset()
        self._frame_index = 0
        logger.debug(
            "boot mode=%s rom=%s", self._config.boot_mode.value, self._rom_path
        )

        if self._config.boot_mode is BootMode.HLE_ADVANCED:
            apply_post_boot(PostBootState(), self._cpu, self._bus)
        elif self._config.boot_mode is BootMode.TEST_ROM_ONLY:
            # 最小驗證路徑：不做 BIOS 流程，PC 直接指向 ROM 起點。
            # header 第 0-3 bytes 是 ARM branch opcode，不是位址。
            self._cpu.apply_bare_reset(
                0x08000000,
                mode=MODE_SYS,
                sp=0x03007F00,
            )
        else:  # REQUIRE_BIOS：停在上電 reset vector，由 Phase 1 的 CPU 執行 BIOS。
            self._cpu.apply_bare_reset(
                0x00000000,
                mode=MODE_SVC,
                sp=0x03007FE0,
                flags=CPSR_I | CPSR_F,
            )
        # bus.reset() 會關閉輸出；boot 完成後依 config 重新套用。
        self._bus.ppu.render_enabled = self._config.video is VideoMode.FRAMEBUFFER
        self._bus.sound.enabled = self._config.audio is AudioMode.BUFFERED

    def _ensure_open(self) -> None:
        if self._closed:
            raise GbaEmuError("Emulator 已關閉")


class CPUView:
    """唯讀 CPU 觀測 + breakpoint 管理（規格 6.2）。"""

    def __init__(self, emulator: Emulator) -> None:
        self._emu = emulator

    def state(self) -> CPUState:
        return self._emu._cpu.view()

    def read_register(self, name: str) -> int:
        return self._emu._cpu.read_register(name)

    def set_breakpoint(self, address: int, *, thumb: bool | None = None) -> int:
        return self._emu._breakpoints.set(address, thumb=thumb)

    def clear_breakpoint(self, breakpoint_id: int) -> None:
        self._emu._breakpoints.clear(breakpoint_id)


class MemoryView:
    """除錯用 memory peek/poke；不消耗 cycle、不觸發硬體副作用（規格 6.2）。

    ``write_*`` 是 silent debugger write；需要留下 ``WATCHPOINT_WRITE`` trace
    event 時走 ``force_write()``。
    """

    def __init__(self, emulator: Emulator) -> None:
        self._emu = emulator

    def read_u8(self, address: int) -> int:
        return self._emu._bus.peek_u8(address)

    def read_u16(self, address: int) -> int:
        return self._emu._bus.peek_u16(address)

    def read_u32(self, address: int) -> int:
        return self._emu._bus.peek_u32(address)

    def read(self, address: int, size: int) -> bytes:
        return self._emu._bus.peek_block(address, size)

    def write_u8(self, address: int, value: int) -> None:
        self._emu._bus.debug_write(address, value, 1)

    def write_u16(self, address: int, value: int) -> None:
        self._emu._bus.debug_write(address, value, 2)

    def write_u32(self, address: int, value: int) -> None:
        self._emu._bus.debug_write(address, value, 4)

    def read_region(self, name: MemoryRegionKind) -> bytes:
        return self._emu._bus.read_region(name)

    def region_info(self, name: MemoryRegionKind) -> MemoryRegionInfo:
        return self._emu._bus.region_info(name)

    def force_write(self, address: int, value: int) -> None:
        self._emu._bus.debug_write(address, value, 1)
        self._emu.events.emit(
            EmulatorEvent(
                kind=EventKind.WATCHPOINT_WRITE,
                cycle=self._emu.cycles,
                frame_index=self._emu.frame_index,
                scanline=None,
                channel=None,
                address=address & 0xFFFFFFFF,
                value=value & 0xFF,
            )
        )


class AudioView:
    """PCM 觀測（規格 3.5）：BUFFERED 模式才有資料，讀取後清空。"""

    def __init__(self, emulator: Emulator) -> None:
        self._emu = emulator

    @property
    def sample_rate(self) -> int:
        return self._emu._bus.sound.sample_rate

    def read_buffer(self) -> bytes:
        return self._emu._bus.sound.take_pcm()


class VideoView:
    """Framebuffer 觀測（規格 6.3）。Phase 0 畫面為全零。"""

    width: ClassVar[int] = WIDTH
    height: ClassVar[int] = HEIGHT

    def __init__(self, emulator: Emulator) -> None:
        self._emu = emulator

    def read_frame(self, *, copy: bool = True) -> bytes:
        return self._emu._framebuffer.read_frame(copy=copy)

    def read_scanline(self, line: int) -> bytes:
        return self._emu._framebuffer.read_scanline(line)

    def read_frame_array(self):
        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover - 開發環境有 numpy
            raise ImportError("read_frame_array() 需要 numpy") from exc
        frame = self._emu._framebuffer.read_frame()
        return np.frombuffer(frame, dtype=np.uint8).reshape((HEIGHT, WIDTH, 3)).copy()


class InputPort:
    """按鍵狀態與 KEYINPUT（active-low）對應（規格 §3.4）。

    ``set_buttons`` 只更新有具名傳入的按鍵；未提及的按鍵維持原狀。RL 的
    「每個 action 完整替換」語意由 Phase 5 的 ``GBAEnv`` 負責，不在這個低階
    port 上強制。

    # GBATEK: GBA Keypad Input - KEYINPUT active-low（按下 = 0）
    """

    _BUTTONS_BY_NAME = {button.value: button for button in Button}
    _KEY_BITS = {
        Button.A: 0,
        Button.B: 1,
        Button.SELECT: 2,
        Button.START: 3,
        Button.RIGHT: 4,
        Button.LEFT: 5,
        Button.UP: 6,
        Button.DOWN: 7,
        Button.R: 8,
        Button.L: 9,
    }

    def __init__(self) -> None:
        self._pressed: set[Button] = set()

    @property
    def keyinput_mask(self) -> int:
        """KEYINPUT 的低 10 位（active-low；未按 = 1）。"""

        value = 0x03FF
        for button in self._pressed:
            value &= ~(1 << self._KEY_BITS[button])
        return value

    def set_buttons(self, **buttons: bool) -> None:
        for name, pressed in buttons.items():
            button = self._BUTTONS_BY_NAME.get(name)
            if button is None:
                raise ValueError(f"未知的按鍵名稱：{name!r}")
            if not isinstance(pressed, bool):
                raise ValueError(f"按鍵 {name!r} 的狀態必須是 bool")
            if pressed:
                self._pressed.add(button)
            else:
                self._pressed.discard(button)

    def press(self, *buttons: Button) -> None:
        for button in buttons:
            self._pressed.add(self._require_button(button))

    def release(self, *buttons: Button) -> None:
        for button in buttons:
            self._pressed.discard(self._require_button(button))

    def clear(self) -> None:
        self._pressed.clear()

    @property
    def pressed_buttons(self) -> frozenset[Button]:
        return frozenset(self._pressed)

    def is_pressed(self, button: Button) -> bool:
        return self._require_button(button) in self._pressed

    @staticmethod
    def _require_button(button: Button) -> Button:
        if not isinstance(button, Button):
            raise ValueError(f"必須是 Button enum，得到 {button!r}")
        return button


__all__ = ["Emulator", "CPUView", "MemoryView", "VideoView", "InputPort"]
