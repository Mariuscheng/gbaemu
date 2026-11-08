"""32-bit GBA 位址匯流排（Phase 0 功能骨架）。

解碼與鏡像依 GBATEK「GBA Memory Map」與規格 3.1：

* EWRAM 256 KiB 在 16 MiB 視窗內重複；IWRAM 32 KiB 在 16 MiB 視窗內重複。
* Palette／OAM 1 KiB 重複；VRAM 96 KiB + 尾端 32 KiB 鏡像。
* Game Pak ROM 的三個 32 MiB 視窗互為鏡像。
* BIOS、ROM 唯讀；SRAM 只能 8-bit 存取。
* 8-bit 特殊寫入規則由 :mod:`gbaemu.memory` 各模組實作。

Phase 0 尚未實作 I/O 暫存器語意：硬體路徑的 I/O 讀寫會被計數並忽略
（不 silent 假裝成功），除錯路徑的 ``peek``/``debug_write`` 可直接看/改
raw 1 KiB I/O 空間。Phase 2 會以既有 ``pygba/core/bus.pyx`` 的暫存器語意
遷移取代這個 placeholder。
"""

from __future__ import annotations

import struct

from ..api_types import MemoryRegionInfo, MemoryRegionKind
from ..errors import ReadOnlyMemoryError
from ..hle.bios_read_protect import hle_bios_read
from ..memory.cartridge import Cartridge
from ..memory.oam import Oam
from ..memory.palette import PaletteRam
from ..memory.vram import Vram
from ..memory.wram import Ewram, Iwram
from ..audio.sound import SoundController
from ..devices.dma import DmaController
from ..devices.timers import Timers
from ..video.ppu import Ppu
from .access import align_address
from .io import IoRegisters
from .regions import (
    BIOS_BASE,
    BIOS_SIZE,
    EWRAM_BASE,
    IO_BASE,
    IO_SIZE,
    IWRAM_BASE,
    OAM_BASE,
    OAM_SIZE,
    PALETTE_BASE,
    PALETTE_SIZE,
    ROM_BASE,
    ROM_END,
    ROM_WINDOW_SIZE,
    SRAM_BASE,
    SRAM_SIZE,
    VRAM_BASE,
    VRAM_WINDOW_SIZE,
)

OPEN_BUS_VALUE = 0x00000000
_SRAM_ERASED = 0xFF


class AddressBus:
    """解碼 32-bit 位址並處理寬度、鏡像、唯讀與 open bus。"""

    def __init__(
        self,
        cartridge: Cartridge | None = None,
        *,
        bios: bytes | None = None,
        keypad=None,
        framebuffer=None,
        events=None,
        ppu=None,
    ) -> None:
        if bios is not None and len(bios) != BIOS_SIZE:
            raise ValueError(f"BIOS 必須是 {BIOS_SIZE} bytes，得到 {len(bios)}")
        self.cartridge = cartridge
        self._bios = bytes(bios) if bios is not None else None

        self.ewram = Ewram()
        self.iwram = Iwram()
        self.palette = PaletteRam()
        self.vram = Vram()
        self.oam = Oam()

        # Phase 0 placeholder：SRAM 由 bus 持有；Phase 3 改由 cartridge adapter 管理。
        self._sram = bytearray([_SRAM_ERASED]) * SRAM_SIZE
        self.ppu = ppu if ppu is not None else Ppu()
        self.dma = DmaController()
        self.timers = Timers()
        self.sound = SoundController()
        self.io_registers = IoRegisters(
            keypad=keypad,
            ppu=self.ppu,
            dma=self.dma,
            timers=self.timers,
            sound=self.sound,
        )
        self.ppu.bind_irq(self.io_registers.request_irq)
        self.ppu.bind_events(events)
        self.ppu.bind_output(self.vram, framebuffer, self.palette, self.oam)
        self.ppu.bind_dma(self.dma.on_ppu_event)
        self.dma.attach_bus(self)
        self.dma.bind_irq(self.io_registers.request_irq)
        self.timers.bind_irq(self.io_registers.request_irq)
        self.timers.bind_sound(self.sound.timer_overflow)
        self.sound.fifo_dma_request = self.dma.request_fifo

        self._io_reads = 0
        self._io_writes = 0
        self._open_bus_reads = 0
        self.open_bus = 0
        self._ignored_writes = 0

    # ------------------------------------------------------------------
    # 硬體存取路徑
    # ------------------------------------------------------------------
    def read_u8(self, address: int) -> int:
        return self._read(address, 1)

    def _eight_bit_bus(self, address: int) -> bool:
        """Game Pak SRAM／Flash 一帶（0x0E000000 以上）係 8-bit 匯流排：
        wide access 唔可以喺 bus 層先對齊（mGBA LOAD_SRAM／STORE_SRAM）。
        冇插卡時 SRAM window 都仍然行同一規則。"""
        return self._save_covers(address) or (
            SRAM_BASE <= address < SRAM_BASE + SRAM_SIZE
        )

    def read_u16(self, address: int) -> int:
        # 8-bit 匯流排：wide load 讀「原始位址」的 byte 再複製。
        if self._eight_bit_bus(address):
            return self._read(address, 2)
        return self._read(align_address(address, 2), 2)

    def read_u32(self, address: int) -> int:
        if self._eight_bit_bus(address):
            value = self._read(address, 4)
            self.open_bus = value & 0xFFFFFFFF
            return value
        value = self._read(align_address(address, 4), 4)
        # 資料匯流排會保留最後一次 32-bit 讀出的值，供 open bus 讀取使用
        # （GBATEK: Unmapped Memory；suite「ROM out-of-bounds load」）。
        self.open_bus = value & 0xFFFFFFFF
        return value

    def write_u8(self, address: int, value: int) -> None:
        self._write(address, 1, value)

    def write_u16(self, address: int, value: int) -> None:
        # 8-bit 匯流排：wide store 的 byte 由原始位址低 bit 決定，
        # 不能在 bus 層先對齊（GBATEK 12 章；legacy 實機測試 t006–t009）。
        if self._eight_bit_bus(address):
            self._write(address, 2, value)
            return
        self._write(align_address(address, 2), 2, value)

    def write_u32(self, address: int, value: int) -> None:
        if self._eight_bit_bus(address):
            self._write(address, 4, value)
            return
        self._write(align_address(address, 4), 4, value)

    def _read(self, address: int, width: int) -> int:
        address &= 0xFFFFFFFF

        save_value = self._save_read(address, width)
        if save_value is not None:
            return save_value

        if address < BIOS_SIZE:
            return self._read_bios(address, width)

        if EWRAM_BASE <= address < IWRAM_BASE:
            return self._read_region(self.ewram, address - EWRAM_BASE, width)

        if IWRAM_BASE <= address < IO_BASE:
            return self._read_region(self.iwram, address - IWRAM_BASE, width)

        if IO_BASE <= address < IO_BASE + IO_SIZE:
            self._io_reads += 1
            return self.io_registers.read(address - IO_BASE, width)

        if PALETTE_BASE <= address < PALETTE_BASE + PALETTE_SIZE * 2:
            return self._read_region(self.palette, address - PALETTE_BASE, width)

        if VRAM_BASE <= address < VRAM_BASE + VRAM_WINDOW_SIZE * 2:
            return self._read_region(self.vram, address - VRAM_BASE, width)

        if OAM_BASE <= address < OAM_BASE + OAM_SIZE * 2:
            return self._read_region(self.oam, address - OAM_BASE, width)

        if ROM_BASE <= address < ROM_END:
            return self._read_rom(address, width)

        if SRAM_BASE <= address < SRAM_BASE + SRAM_SIZE:
            return self._read_sram(address, width)

        self._open_bus_reads += 1
        if width == 1:
            return (self.open_bus >> ((address & 3) * 8)) & 0xFF
        if width == 2:
            return (self.open_bus >> ((address & 2) * 8)) & 0xFFFF
        return self.open_bus

    def _read_region(self, region, offset: int, width: int) -> int:
        if width == 1:
            return region.read_u8(offset)
        if width == 2:
            return region.read_u16(offset)
        return region.read_u32(offset)

    def _read_bios(self, address: int, width: int) -> int:
        if self._bios is None:
            # HLE：固定近似值；Phase 2 起改為 pc_in_bios/bios_prefetch 模型。
            return hle_bios_read(address, width)
        value = 0
        for index in range(width):
            value |= self._bios[(address + index) % BIOS_SIZE] << (index * 8)
        return value

    def _read_rom(self, address: int, width: int) -> int:
        rom = self.cartridge.rom_bytes if self.cartridge is not None else b""
        offset = (address - ROM_BASE) % ROM_WINDOW_SIZE
        value = 0
        missed = False
        for index in range(width):
            position = offset + index
            if position >= len(rom):
                # 超出卡匣大小的 ROM 讀取：硬體回傳位址衍生的固定樣式
                # （mGBA: Out of bounds ROM Load；suite「ROM out-of-bounds load」）。
                missed = True
                byte_address = address + index
                lane = ((byte_address >> 1) >> ((byte_address & 1) * 8)) & 0xFF
                value |= lane << (index * 8)
            else:
                value |= rom[position] << (index * 8)
        if missed:
            self._open_bus_reads += 1
        return value

    def _read_sram(self, address: int, width: int) -> int:
        # 8-bit 匯流排：16/32-bit load 讀原始位址的 byte，再複製到整個寬度
        # （mGBA LOAD_SRAM：value = Load8(address); value |= value << 8; ...）。
        byte = self._sram[address & (SRAM_SIZE - 1)]
        if width == 1:
            return byte
        value = byte
        for _ in range((width * 8) // 8 - 1):
            value |= value << 8
        return value & ((1 << (width * 8)) - 1)

    def _write(self, address: int, width: int, value: int) -> None:
        address &= 0xFFFFFFFF
        value &= (1 << (width * 8)) - 1

        if self._save_write(address, width, value):
            return

        if address < BIOS_SIZE:
            self._ignored_writes += 1  # BIOS 唯讀
            return

        if EWRAM_BASE <= address < IWRAM_BASE:
            self._write_region(self.ewram, address - EWRAM_BASE, width, value)
            return

        if IWRAM_BASE <= address < IO_BASE:
            self._write_region(self.iwram, address - IWRAM_BASE, width, value)
            return

        if IO_BASE <= address < IO_BASE + IO_SIZE:
            self._io_writes += 1
            self.io_registers.write(address - IO_BASE, width, value)
            return

        if PALETTE_BASE <= address < PALETTE_BASE + PALETTE_SIZE * 2:
            self._write_region(self.palette, address - PALETTE_BASE, width, value)
            self.ppu.dirty = True
            return

        if VRAM_BASE <= address < VRAM_BASE + VRAM_WINDOW_SIZE * 2:
            self._write_region(self.vram, address - VRAM_BASE, width, value)
            self.ppu.dirty = True
            return

        if OAM_BASE <= address < OAM_BASE + OAM_SIZE * 2:
            self._write_region(self.oam, address - OAM_BASE, width, value)
            self.ppu.dirty = True
            return

        if ROM_BASE <= address < ROM_END:
            self._ignored_writes += 1  # ROM 寫入忽略（寫保護）
            return

        if SRAM_BASE <= address < SRAM_BASE + SRAM_SIZE:
            lane = address & (width - 1) if width > 1 else 0
            self._sram[address & (SRAM_SIZE - 1)] = (value >> (8 * lane)) & 0xFF
            return

        self._ignored_writes += 1  # unmapped：寫入忽略

    def _write_region(self, region, offset: int, width: int, value: int) -> None:
        if width == 1:
            region.write_u8(offset, value)
        elif width == 2:
            region.write_u16(offset, value)
        else:
            region.write_u32(offset, value)

    # ------------------------------------------------------------------
    # 備份媒體（SRAM／Flash／EEPROM；GBATEK 12 章）
    # ------------------------------------------------------------------
    def _save_backend(self):
        return None if self.cartridge is None else self.cartridge.save

    def _save_covers(self, address: int) -> bool:
        save = self._save_backend()
        if save is None:
            return False
        if save.kind == "EEPROM":
            return 0x0D000000 <= address < 0x0E000000
        return 0x0E000000 <= address < 0x10000000

    def _save_read(self, address: int, width: int):
        save = self._save_backend()
        if save is None:
            return None
        if save.kind == "EEPROM":
            if 0x0D000000 <= address < 0x0E000000:
                return save.read_bit()
            return None
        if 0x0E000000 <= address < 0x10000000:
            offset = address & 0xFFFF
            if width == 1:
                return save.read8(offset)
            if width == 2:
                return save.read16(offset)
            return save.read32(offset)
        return None

    def _save_write(self, address: int, width: int, value: int) -> bool:
        save = self._save_backend()
        if save is None:
            return False
        if save.kind == "EEPROM":
            if 0x0D000000 <= address < 0x0E000000:
                save.write_bit(value & 1)
                return True
            return False
        if 0x0E000000 <= address < 0x10000000:
            offset = address & 0xFFFF
            if width == 1:
                save.write8(offset, value)
            elif width == 2:
                save.write16(offset, value)
            else:
                save.write32(offset, value)
            return True
        return False

    # ------------------------------------------------------------------
    # 除錯路徑（無硬體副作用、不計數、不消耗 cycle）
    # ------------------------------------------------------------------
    def fetch32(self, address: int) -> int:
        # 指令 prefetch 不更新 open bus：硬體 open bus 保留的是最後一次
        # 「資料」讀取的值（suite「ROM out-of-bounds load」驗證）。
        return self._read(align_address(address, 4), 4)

    def peek_u8(self, address: int) -> int:
        address &= 0xFFFFFFFF

        save = self._save_backend()
        if save is not None:
            if save.kind == "EEPROM":
                if 0x0D000000 <= address < 0x0E000000:
                    return 1  # EEPROM 閒置時回 Ready，不推進位元流
            elif 0x0E000000 <= address < 0x10000000:
                return save.read8(address & 0xFFFF)

        if address < BIOS_SIZE:
            if self._bios is None:
                return hle_bios_read(address, 1)
            return self._bios[address]

        if EWRAM_BASE <= address < IWRAM_BASE:
            return self.ewram.read_u8(address - EWRAM_BASE)
        if IWRAM_BASE <= address < IO_BASE:
            return self.iwram.read_u8(address - IWRAM_BASE)
        if IO_BASE <= address < IO_BASE + IO_SIZE:
            return self.io_registers.read8(address - IO_BASE)
        if PALETTE_BASE <= address < PALETTE_BASE + PALETTE_SIZE:
            return self.palette.read_u8(address - PALETTE_BASE)
        if VRAM_BASE <= address < VRAM_BASE + VRAM_WINDOW_SIZE * 2:
            return self.vram.read_u8(address - VRAM_BASE)
        if OAM_BASE <= address < OAM_BASE + OAM_SIZE:
            return self.oam.read_u8(address - OAM_BASE)
        if ROM_BASE <= address < ROM_END:
            if self.cartridge is None:
                return (self.open_bus >> ((address & 3) * 8)) & 0xFF
            return self.cartridge.read_rom(address)
        if SRAM_BASE <= address < SRAM_BASE + SRAM_SIZE:
            return self._sram[address & (SRAM_SIZE - 1)]
        return (self.open_bus >> ((address & 3) * 8)) & 0xFF

    def peek_u16(self, address: int) -> int:
        address &= 0xFFFFFFFF
        if IO_BASE <= address < IO_BASE + IO_SIZE:
            return self.io_registers.read16(address - IO_BASE)
        return self.peek_u8(address) | (self.peek_u8(address + 1) << 8)

    def peek_u32(self, address: int) -> int:
        address &= 0xFFFFFFFF
        if IO_BASE <= address < IO_BASE + IO_SIZE:
            return self.io_registers.read32(address - IO_BASE)
        return (
            self.peek_u8(address)
            | (self.peek_u8(address + 1) << 8)
            | (self.peek_u8(address + 2) << 16)
            | (self.peek_u8(address + 3) << 24)
        )

    def peek_block(self, address: int, size: int) -> bytes:
        if size < 0:
            raise ValueError("size 不可為負")
        return bytes(self.peek_u8(address + index) for index in range(size))

    def debug_write(self, address: int, value: int, size: int = 1) -> None:
        """除錯寫入：繞過硬體 8-bit 特殊規則，但仍禁止寫 ROM/BIOS/open bus。"""

        if size not in (1, 2, 4):
            raise ValueError(f"不支援的存取寬度：{size}")
        address &= 0xFFFFFFFF
        if IO_BASE <= address < IO_BASE + IO_SIZE:
            self.io_registers.debug_write(address - IO_BASE, size, value)
            return
        for index in range(size):
            self._debug_write_byte(address + index, (value >> (index * 8)) & 0xFF)

    def _debug_write_byte(self, address: int, value: int) -> None:
        if address < BIOS_SIZE or ROM_BASE <= address < ROM_END:
            raise ReadOnlyMemoryError(f"位址 0x{address:08X} 是唯讀區域")

        if EWRAM_BASE <= address < IWRAM_BASE:
            self.ewram.write_raw_u8(address - EWRAM_BASE, value)
        elif IWRAM_BASE <= address < IO_BASE:
            self.iwram.write_raw_u8(address - IWRAM_BASE, value)
        elif IO_BASE <= address < IO_BASE + IO_SIZE:
            self.io_registers.write8(address - IO_BASE, value)
        elif PALETTE_BASE <= address < PALETTE_BASE + PALETTE_SIZE:
            self.palette.write_raw_u8(address - PALETTE_BASE, value)
            self.ppu.dirty = True
        elif VRAM_BASE <= address < VRAM_BASE + VRAM_WINDOW_SIZE * 2:
            self.vram.write_raw_u8(address - VRAM_BASE, value)
            self.ppu.dirty = True
        elif OAM_BASE <= address < OAM_BASE + OAM_SIZE:
            self.oam.write_raw_u8(address - OAM_BASE, value)
            self.ppu.dirty = True
        elif SRAM_BASE <= address < SRAM_BASE + SRAM_SIZE:
            save = self._save_backend()
            if save is not None:
                save.write8(address & 0xFFFF, value)
            else:
                self._sram[address & (SRAM_SIZE - 1)] = value
        else:
            raise ReadOnlyMemoryError(f"位址 0x{address:08X} 無法除錯寫入（open bus）")

    def is_read_only(self, address: int) -> bool:
        address &= 0xFFFFFFFF
        return address < BIOS_SIZE or ROM_BASE <= address < ROM_END

    # ------------------------------------------------------------------
    # 區域觀測
    # ------------------------------------------------------------------
    def read_region(self, kind: MemoryRegionKind) -> bytes:
        if kind is MemoryRegionKind.BIOS:
            return bytes(self._bios) if self._bios is not None else bytes(BIOS_SIZE)
        if kind is MemoryRegionKind.EWRAM:
            return self.ewram.to_bytes()
        if kind is MemoryRegionKind.IWRAM:
            return self.iwram.to_bytes()
        if kind is MemoryRegionKind.IO:
            return bytes(self.io_registers.raw)
        if kind is MemoryRegionKind.PALETTE:
            return self.palette.to_bytes()
        if kind is MemoryRegionKind.VRAM:
            return self.vram.to_bytes()
        if kind is MemoryRegionKind.OAM:
            return self.oam.to_bytes()
        if kind is MemoryRegionKind.ROM:
            return self.cartridge.rom_bytes if self.cartridge is not None else b""
        if kind is MemoryRegionKind.SRAM:
            save = self._save_backend()
            return bytes(self._sram) if save is None else save.export()
        if kind is MemoryRegionKind.OPEN_BUS:
            return b""
        raise ValueError(f"未知的記憶體區域：{kind!r}")

    def region_info(self, kind: MemoryRegionKind) -> MemoryRegionInfo:
        if kind is MemoryRegionKind.BIOS:
            return MemoryRegionInfo(kind, BIOS_BASE, BIOS_SIZE, True)
        if kind is MemoryRegionKind.EWRAM:
            return self.ewram.info()
        if kind is MemoryRegionKind.IWRAM:
            return self.iwram.info()
        if kind is MemoryRegionKind.IO:
            return MemoryRegionInfo(kind, IO_BASE, IO_SIZE, False)
        if kind is MemoryRegionKind.PALETTE:
            return self.palette.info()
        if kind is MemoryRegionKind.VRAM:
            return self.vram.info()
        if kind is MemoryRegionKind.OAM:
            return self.oam.info()
        if kind is MemoryRegionKind.ROM:
            size = self.cartridge.rom_size if self.cartridge is not None else 0
            return MemoryRegionInfo(kind, ROM_BASE, size, True)
        if kind is MemoryRegionKind.SRAM:
            save = self._save_backend()
            size = len(save.export()) if save is not None else SRAM_SIZE
            return MemoryRegionInfo(kind, SRAM_BASE, size, False)
        if kind is MemoryRegionKind.OPEN_BUS:
            return MemoryRegionInfo(kind, 0, 0, True)
        raise ValueError(f"未知的記憶體區域：{kind!r}")

    # ------------------------------------------------------------------
    # Snapshot（規格 5.7 BUS 區段：EWRAM/IWRAM/VRAM/Palette/OAM/SRAM）
    # ------------------------------------------------------------------
    _LENGTH = struct.Struct("<I")

    def snapshot_state(self) -> bytes:
        save = self._save_backend()
        sram = save.export() if save is not None else bytes(self._sram)
        return (
            self._LENGTH.pack(len(sram))
            + self.ewram.to_bytes()
            + self.iwram.to_bytes()
            + self.palette.to_bytes()
            + self.vram.to_bytes()
            + self.oam.to_bytes()
            + sram
            + self.io_registers.export_state()
        )

    def restore_state(self, data: bytes) -> None:
        (sram_length,) = self._LENGTH.unpack_from(data, 0)
        offset = self._LENGTH.size
        for region in (self.ewram, self.iwram, self.palette, self.vram, self.oam):
            region.load(data[offset : offset + region.size])
            offset += region.size
        sram = data[offset : offset + sram_length]
        offset += sram_length
        save = self._save_backend()
        if save is not None:
            save.load(sram)
        else:
            self._sram[:] = sram[: len(self._sram)]
        self.io_registers.load_state(data[offset:])

    # ------------------------------------------------------------------
    # 狀態
    # ------------------------------------------------------------------
    def set_vram_bitmap_mode(self, bitmap_mode: bool) -> None:
        self.vram.bitmap_mode = bool(bitmap_mode)

    def tick(self, cycles: int) -> None:
        """推進周邊時間（目前只有 PPU；DMA/timer 於 Phase 3 接上）。"""

        self.ppu.advance(cycles)
        self.timers.tick(cycles)
        self.sound.tick(cycles)

    def reset(self) -> None:
        """回到 power-on 的零狀態（Phase 0 的決定性政策）。"""

        self.ewram.clear()
        self.iwram.clear()
        self.palette.clear()
        self.vram.clear()
        self.vram.bitmap_mode = False
        self.oam.clear()
        self._sram[:] = bytes([_SRAM_ERASED]) * SRAM_SIZE
        self.io_registers.reset()
        self.ppu.reset()
        self.dma.reset()
        self.timers.reset()
        self.sound.reset()
        self._io_reads = 0
        self._io_writes = 0
        self._open_bus_reads = 0
        self.open_bus = 0
        self._ignored_writes = 0

    @property
    def unsupported_io_reads(self) -> int:
        return self._io_reads

    @property
    def bios_present(self) -> bool:
        return self._bios is not None

    def video_wait(self, address: int, width: int) -> int:
        """CPU 存取 VRAM/OAM/Palette 時的 video contention（GBATEK 02 章）。

        顯示控制器同時使用記憶體時插入 1 clock waitstate；HBlank 期間
        VRAM/Palette 可自由存取，OAM 需 DISPCNT bit5（HBlank Interval Free）。
        """

        if address < 0x05000000 or address >= 0x07000400:
            return 0
        palette = 0x05000000 <= address < 0x05000400
        vram = 0x06000000 <= address < 0x06018000
        oam = 0x07000000 <= address < 0x07000400
        if not (palette or vram or oam):
            return 0
        if self.ppu is None:
            return 0
        dispcnt = self.ppu.dispcnt
        if dispcnt & 0x80:  # forced blank：PPU 不存取
            return 0
        if self.ppu.state.scanline >= 160:
            return 0
        if self.ppu.state.in_hblank:
            if oam and not (dispcnt & 0x20):
                return 1
            return 0
        return 1

    @property
    def unsupported_io_writes(self) -> int:
        return self._io_writes

    @property
    def open_bus_reads(self) -> int:
        return self._open_bus_reads

    @property
    def ignored_writes(self) -> int:
        return self._ignored_writes

    @property
    def waitcnt(self) -> int:
        """WAITCNT（0x04000204）目前值（供 bus/access 的存取成本使用）。"""

        return self.io_registers.waitcnt


__all__ = ["AddressBus", "OPEN_BUS_VALUE"]
