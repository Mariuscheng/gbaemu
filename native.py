"""Opt-in Rust backend facade（需要先 build ``gbaemu_native``）。

Python reference 仍是默認；這個模組只提供最小可用的 ``NativeEmulator``，
用來驗證 PyO3 boundary、frame、framebuffer 與 snapshot。完整 ``Emulator``
API（input／audio／breakpoints／RL）仍由 Python backend 提供。
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

from .api_types import (
    AudioMode,
    CPUState,
    EmulatorConfig,
    FrameResult,
    MemoryRegionInfo,
    MemoryRegionKind,
)
from .config import config_sha256
from .errors import GbaEmuError
from .state.snapshot import parse_snapshot

logger = logging.getLogger("gbaemu.native")


class NativeEmulator:
    """``Emulator`` 的 Rust backend；默認不啟用。"""

    def __init__(
        self,
        rom: bytes,
        config: EmulatorConfig | None = None,
        *,
        rom_path: str | Path | None = None,
    ) -> None:
        from . import _native as _ext  # lazy：未 build extension 時不影響 import
        from .memory.cartridge import RomCartridge

        self._config = config or EmulatorConfig()
        self._rom = rom
        self._rom_path = Path(rom_path) if rom_path is not None else None
        self._cartridge = RomCartridge(rom)
        self._rom_sha256 = hashlib.sha256(rom).digest()
        self._config_sha256 = config_sha256(self._config)
        self._core = _ext.NativeCore(rom, self._config_sha256)
        if self._config.bios_path is not None:
            bios_data = Path(self._config.bios_path).read_bytes()
            self._core.load_bios(bios_data)
        self._save_path = (
            Path(str(self._rom_path) + ".sav") if self._rom_path is not None else None
        )
        self._load_save_file()
        from .emulator import InputPort

        self.input = InputPort()
        self.cpu = _NativeCPU(self)
        self.memory = _NativeMemory(self)
        self.video = _NativeVideo(self)
        self.audio = _NativeAudio(self)
        self._core.set_sound_enabled(self._config.audio is AudioMode.BUFFERED)
        self._paused = False
        self._closed = False

    @classmethod
    def from_rom(cls, path: str | Path, config: EmulatorConfig | None = None) -> "NativeEmulator":
        rom_path = Path(path)
        return cls(rom_path.read_bytes(), config, rom_path=rom_path)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("NativeEmulator 已關閉")

    def step_frame(self, *, render: bool = True) -> FrameResult:
        del render  # Rust Core 目前固定 render=true
        self._ensure_open()
        self._core.set_keyinput(self.input.keyinput_mask)
        cycles, frame_index, halted, irq = self._core.run_frame()
        return FrameResult(
            frame_index=frame_index,
            cycles=cycles,
            vblank_started=True,
            irq_pending=irq,
            halted=halted,
            events=(),
        )

    def framebuffer(self) -> bytes:
        self._ensure_open()
        return bytes(self._core.framebuffer())

    def save_state(self) -> bytes:
        self._ensure_open()
        self._core.set_keyinput(self.input.keyinput_mask)
        return bytes(self._core.save_state())

    def read_u8(self, address: int) -> int:
        return self._core.read8(address)

    def read_u16(self, address: int) -> int:
        return self._core.read16(address)

    def read_u32(self, address: int) -> int:
        return self._core.read32(address)

    def write_u8(self, address: int, value: int) -> None:
        self._core.write8(address, value)

    def write_u16(self, address: int, value: int) -> None:
        self._core.write16(address, value)

    def write_u32(self, address: int, value: int) -> None:
        self._core.write32(address, value)

    def load_state(self, data: bytes) -> None:
        self._ensure_open()
        parse_snapshot(
            data,
            rom_sha256=self._rom_sha256,
            config_sha256=self._config_sha256,
        )
        self._core.load_state(data)

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

    def run_until(self, event, *, max_cycles: int):
        self._ensure_open()
        del event
        if max_cycles <= 0:
            raise ValueError("max_cycles 必須為正整數")
        raise NotImplementedError("NativeEmulator.run_until() 尚未實作")

    def pause(self) -> None:
        self._paused = True

    def cartridge_flush_to_disk(self) -> None:
        """把備份記憶體原子寫回 ``<rom>.sav``（規格 5.7：不自動寫回）。"""

        self._ensure_open()
        if self._core.save_kind() == "none":
            raise GbaEmuError("cartridge 沒有 save 媒體")
        if self._save_path is None:
            raise GbaEmuError("cartridge 沒有 ROM 路徑，無法寫回磁碟")
        temporary = self._save_path.with_name(self._save_path.name + ".tmp")
        temporary.write_bytes(bytes(self._core.save_ram()))
        os.replace(temporary, self._save_path)

    def _load_save_file(self) -> None:
        """若 ``<rom>.sav`` 存在且大小相符，載入備份記憶體。"""

        if self._save_path is None or not self._save_path.exists():
            return
        data = self._save_path.read_bytes()
        try:
            self._core.load_save_ram(data)
        except ValueError as exc:
            logger.warning("save 檔大小不符（%s），忽略 %s", exc, self._save_path)

    @property
    def save_path(self) -> Path | None:
        """電池存檔路徑（``<rom>.sav``）；無 ROM 路徑時為 ``None``。"""

        return self._save_path

    @property
    def save_kind(self) -> str:
        """備份媒體類型：``none``／``sram``／``flash64``／``flash128``／
        ``eeprom512``／``eeprom8k``。"""

        return self._core.save_kind()

    @property
    def config(self) -> EmulatorConfig:
        return self._config

    @property
    def rom_path(self) -> Path | None:
        return self._rom_path

    @property
    def rom_header(self):
        return self._cartridge.header

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def cycles(self) -> int:
        return self._core.cpu_cycles()

    @property
    def frame_index(self) -> int:
        return self._core.frame_index()

    @property
    def halted(self) -> bool:
        return bool(self._core.halted())

    @property
    def irq_pending(self) -> bool:
        return bool(self._core.irq_pending())

    @property
    def vcount(self) -> int:
        return int(self._core.vcount())

    def reset(self, *, seed: int | None = None) -> None:
        del seed
        self._ensure_open()
        self._core.reset()
        self.input.clear()

    def close(self) -> None:
        self._closed = True


class _NativeCPU:
    """CPU 觀測；breakpoint 尚未接進 Rust frame 迴圈。"""

    def __init__(self, emu: NativeEmulator) -> None:
        self._emu = emu

    def state(self) -> CPUState:
        core = self._emu._core
        cpsr = core.cpsr()
        return CPUState(
            regs=tuple(core.reg(index) for index in range(16)),
            cpsr=cpsr,
            spsr=core.spsr(),
            thumb=bool(cpsr & 0x20),
            mode=cpsr & 0x1F,
            halted=bool(core.halted()),
            cycles=core.cpu_cycles(),
        )

    def read_register(self, name: str) -> int:
        core = self._emu._core
        if name in {f"r{index}" for index in range(16)}:
            return core.reg(int(name[1:]))
        if name == "cpsr":
            return core.cpsr()
        if name == "spsr":
            return core.spsr()
        raise ValueError(f"未知的暫存器名稱：{name!r}")

    def set_breakpoint(self, address: int, *, thumb: bool | None = None) -> int:
        del address, thumb
        raise NotImplementedError("NativeEmulator 尚未支援 breakpoint")

    def clear_breakpoint(self, breakpoint_id: int) -> None:
        del breakpoint_id
        raise NotImplementedError("NativeEmulator 尚未支援 breakpoint")


class _NativeMemory:
    _BASES = {
        MemoryRegionKind.BIOS: 0x0000_0000,
        MemoryRegionKind.EWRAM: 0x0200_0000,
        MemoryRegionKind.IWRAM: 0x0300_0000,
        MemoryRegionKind.IO: 0x0400_0000,
        MemoryRegionKind.PALETTE: 0x0500_0000,
        MemoryRegionKind.VRAM: 0x0600_0000,
        MemoryRegionKind.OAM: 0x0700_0000,
        MemoryRegionKind.ROM: 0x0800_0000,
        MemoryRegionKind.SRAM: 0x0E00_0000,
        MemoryRegionKind.OPEN_BUS: 0,
    }

    def __init__(self, emu: NativeEmulator) -> None:
        self._emu = emu

    def read_u8(self, address: int) -> int:
        return self._emu._core.read8(address)

    def read_u16(self, address: int) -> int:
        return self._emu._core.read16(address)

    def read_u32(self, address: int) -> int:
        return self._emu._core.read32(address)

    def read(self, address: int, size: int) -> bytes:
        if size < 0:
            raise ValueError("size 不可為負")
        return bytes(self._emu._core.read8(address + index) for index in range(size))

    def write_u8(self, address: int, value: int) -> None:
        self._emu._core.write8(address, value & 0xFF)

    def write_u16(self, address: int, value: int) -> None:
        self._emu._core.write16(address, value & 0xFFFF)

    def write_u32(self, address: int, value: int) -> None:
        self._emu._core.write32(address, value & 0xFFFFFFFF)

    def force_write(self, address: int, value: int) -> None:
        self._emu._core.write8(address, value & 0xFF)

    def read_region(self, name: MemoryRegionKind) -> bytes:
        kind = MemoryRegionKind(name)
        if kind is MemoryRegionKind.OPEN_BUS:
            return b""
        return bytes(self._emu._core.region(kind.value))

    def region_info(self, name: MemoryRegionKind) -> MemoryRegionInfo:
        kind = MemoryRegionKind(name)
        data = self.read_region(kind)
        return MemoryRegionInfo(
            kind=kind,
            base=self._BASES[kind],
            size=len(data),
            read_only=kind in (MemoryRegionKind.BIOS, MemoryRegionKind.ROM, MemoryRegionKind.OPEN_BUS),
        )


class _NativeVideo:
    width = 240
    height = 160

    def __init__(self, emu: NativeEmulator) -> None:
        self._emu = emu

    def read_frame(self, *, copy: bool = True) -> bytes:
        del copy  # Rust framebuffer() 已回傳獨立 bytes
        return self._emu.framebuffer()

    def read_frame_array(self):
        import numpy as np

        return np.frombuffer(self._emu.framebuffer(), dtype=np.uint8).reshape(160, 240, 3).copy()

    def read_scanline(self, line: int) -> bytes:
        if not 0 <= line < 160:
            raise ValueError("scanline 必須在 0-159")
        start = line * 240 * 3
        return self._emu.framebuffer()[start : start + 240 * 3]


class _NativeAudio:
    def __init__(self, emu: NativeEmulator) -> None:
        self._emu = emu

    @property
    def sample_rate(self) -> int:
        return int(self._emu._core.audio_sample_rate())

    def read_buffer(self) -> bytes:
        return bytes(self._emu._core.take_audio())


__all__ = ["NativeEmulator", "open_emulator"]


def open_emulator(
    rom_path: str | Path, config: EmulatorConfig | None = None
) -> Any:
    """依 ``GBAEMU_BACKEND`` 選擇 backend；默認仍是 Python reference。"""

    backend = os.environ.get("GBAEMU_BACKEND", "python")
    if backend == "rust":
        return NativeEmulator.from_rom(rom_path, config)
    if backend == "python":
        from .emulator import Emulator

        return Emulator.from_rom(rom_path, config=config)
    raise ValueError(f"未知的 GBAEMU_BACKEND：{backend!r}")
