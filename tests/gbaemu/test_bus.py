"""Phase 0 驗收：address bus、WRAM、鏡像與 8-bit 寫入規則。"""

from __future__ import annotations

import pytest

from gbaemu.api_types import MemoryRegionKind
from gbaemu.bus.access import (
    AccessWidth,
    align_address,
    rotate_right_32,
    unaligned_word_rotate,
)
from gbaemu.bus.address_bus import AddressBus
from gbaemu.memory.cartridge import RomCartridge


@pytest.fixture
def bus(rom_bytes):
    return AddressBus(RomCartridge(rom_bytes))


def test_ewram_and_iwram_roundtrip(bus):
    bus.write_u8(0x02000000, 0x12)
    assert bus.read_u8(0x02000000) == 0x12
    bus.write_u32(0x02000010, 0xDEADBEEF)
    assert bus.read_u32(0x02000010) == 0xDEADBEEF
    bus.write_u16(0x03000000, 0xABCD)
    assert bus.read_u16(0x03000000) == 0xABCD


def test_ewram_and_iwram_mirrors(bus):
    bus.write_u8(0x02000010, 0xAB)
    assert bus.read_u8(0x02040010) == 0xAB
    bus.write_u8(0x03000010, 0xCD)
    assert bus.read_u8(0x03008010) == 0xCD


def test_rom_reads_and_three_windows(rom_bytes):
    rom = bytearray(rom_bytes)
    rom[0xC0:0xC4] = b"\x11\x22\x33\x44"
    bus = AddressBus(RomCartridge(bytes(rom)))
    assert bus.read_u8(0x080000C0) == 0x11
    assert bus.read_u8(0x0A0000C0) == 0x11
    assert bus.read_u8(0x0C0000C0) == 0x11
    assert bus.read_u16(0x080000C0) == 0x2211
    assert bus.read_u32(0x080000C0) == 0x44332211


def test_rom_writes_are_ignored(bus):
    before = bus.read_u8(0x080000C0)
    bus.write_u8(0x080000C0, 0xFF)
    assert bus.read_u8(0x080000C0) == before
    assert bus.ignored_writes == 1


def test_palette_8bit_write_duplicates(bus):
    bus.write_u8(0x05000001, 0x12)
    assert bus.read_u16(0x05000000) == 0x1212
    assert bus.read_u8(0x05000000) == 0x12
    assert bus.read_u8(0x05000001) == 0x12

    # 16-bit 寫入不可被拆成兩次 8-bit 複製，否則第二個 byte 會覆蓋第一個。
    bus.write_u16(0x05000002, 0x3456)
    assert bus.read_u8(0x05000002) == 0x56
    assert bus.read_u8(0x05000003) == 0x34


def test_vram_tile_mode_8bit_rules(bus):
    bus.write_u8(0x06000001, 0x34)
    assert bus.read_u16(0x06000000) == 0x3434

    # OBJ VRAM（tile mode >= 0x06010000）忽略 8-bit 寫入
    bus.write_u8(0x06010001, 0x34)
    assert bus.read_u8(0x06010001) == 0x00

    # 16-bit 寫入則有效
    bus.write_u16(0x06010000, 0xABCD)
    assert bus.read_u16(0x06010000) == 0xABCD


def test_vram_bitmap_mode_boundary(bus):
    bus.set_vram_bitmap_mode(True)
    bus.write_u8(0x06010001, 0x56)
    assert bus.read_u16(0x06010000) == 0x5656
    bus.write_u8(0x06014001, 0x78)
    assert bus.read_u8(0x06014001) == 0x00


def test_vram_tail_mirror(bus):
    bus.write_u16(0x06010000, 0xABCD)
    assert bus.read_u16(0x06018000) == 0xABCD


def test_oam_8bit_write_ignored(bus):
    bus.write_u8(0x07000000, 0x12)
    assert bus.read_u8(0x07000000) == 0x00
    bus.write_u16(0x07000000, 0x3456)
    assert bus.read_u16(0x07000000) == 0x3456


def test_sram_is_8bit_bus_and_mirrored(bus):
    assert bus.read_u8(0x0E000000) == 0xFF
    bus.write_u8(0x0E000010, 0x5A)
    assert bus.read_u8(0x0E000010) == 0x5A
    # SRAM 視窗只有 64 KiB（0x0E000000-0x0E00FFFF）；再上去是 open bus。
    assert bus.read_u8(0x0E010010) == 0

    # 8-bit 匯流排：wide load 讀「原始位址」的 byte 再複製（mGBA LOAD_SRAM）。
    for k, value in enumerate((0x11, 0x22, 0x33, 0x44)):
        bus.write_u8(0x0E000020 + k, value)
    assert bus.read_u16(0x0E000020) == 0x1111
    assert bus.read_u16(0x0E000021) == 0x2222
    assert bus.read_u32(0x0E000022) == 0x33333333
    assert bus.read_u32(0x0E000023) == 0x44444444
    # wide store 只寫 1 個 byte，byte 由原始位址低 bit 揀（mGBA STORE_SRAM）。
    bus.write_u16(0x0E000020, 0x1234)      # lane 0 → 0x34
    bus.write_u16(0x0E000021, 0x1234)      # lane 1 → 0x12
    bus.write_u32(0x0E000022, 0xAABBCCDD)  # lane 2 → 0xBB
    bus.write_u32(0x0E000023, 0xAABBCCDD)  # lane 3 → 0xAA
    assert [bus.read_u8(0x0E000020 + k) for k in range(4)] == [0x34, 0x12, 0xBB, 0xAA]


def test_bios_readonly_and_hle_approximation(rom_bytes):
    cart = RomCartridge(rom_bytes)
    hle_bus = AddressBus(cart)
    assert hle_bus.read_u8(0x00000000) == 0
    hle_bus.write_u8(0x00000000, 0xFF)
    assert hle_bus.ignored_writes == 1

    bios_bus = AddressBus(cart, bios=bytes([0x11]) * 0x4000)
    assert bios_bus.read_u8(0x00000000) == 0x11
    assert bios_bus.read_u16(0x00000000) == 0x1111
    assert bios_bus.read_u32(0x00003FFE) == 0x11111111


def test_open_bus_and_io_registers_are_counted(bus):
    assert bus.read_u32(0x0F000000) == 0
    assert bus.open_bus_reads == 1

    assert bus.read_u8(0x04000000) == 0  # DISPCNT 初值
    assert bus.unsupported_io_reads == 1
    bus.write_u8(0x04000000, 0x80)
    assert bus.unsupported_io_writes == 1
    assert bus.peek_u8(0x04000000) == 0x80  # Phase 2：I/O 暫存器語意

    bus.debug_write(0x04000000, 0x00)
    assert bus.peek_u8(0x04000000) == 0x00
    assert bus.read_u8(0x04000000) == 0
    assert bus.unsupported_io_reads == 2


def test_open_bus_tracks_last_data_read(bus):
    """open bus 保留最後一次 32-bit 資料讀取的值，依位址 lane 與存取寬度選取。"""
    bus.write_u32(0x02000000, 0x11223344)
    assert bus.read_u32(0x02000000) == 0x11223344
    assert bus.open_bus == 0x11223344

    assert bus.read_u8(0x0F000000) == 0x44
    assert bus.read_u8(0x0F000001) == 0x33
    assert bus.read_u16(0x0F000002) == 0x1122
    assert bus.open_bus_reads == 3
    assert bus.peek_u32(0x0F000000) == 0x11223344
    assert bus.peek_u8(0x0F000003) == 0x11

    # 指令 prefetch 不改寫 open bus；只有資料讀取會更新。
    bus.fetch32(0x02000000)
    assert bus.open_bus == 0x11223344
    bus.read_u32(0x02000000)
    assert bus.open_bus == 0x11223344

    bus.write_u32(0x02000004, 0xAABBCCDD)
    bus.read_u32(0x02000004)
    assert bus.read_u8(0x0F000000) == 0xDD


def test_absent_cartridge_rom_reads_address_pattern():
    # 沒有卡匣時 ROM 區全部視為 out-of-bounds：硬體回傳位址衍生的樣式
    # （mGBA: Out of bounds ROM Load）。
    bus = AddressBus(None)

    assert bus.read_u8(0x08000001) == 0x00
    assert bus.read_u16(0x08000002) == 0x0001
    assert bus.read_u32(0x08000000) == 0x00010000
    assert bus.open_bus_reads == 3


def test_rom_out_of_bounds_reads_address_pattern(bus):
    # 測試 ROM 只有 0x200 bytes；0x08000200 之後是位址衍生樣式。
    assert bus.read_u8(0x08000200) == 0x00
    assert bus.read_u16(0x08000202) == 0x0101
    assert bus.read_u32(0x08000200) == 0x01010100


def test_peek_has_no_side_effects(bus):
    bus.read_u32(0x0F000000)
    bus.read_u8(0x04000000)
    open_before = bus.open_bus_reads
    io_before = bus.unsupported_io_reads
    bus.peek_u32(0x0F000000)
    bus.peek_u8(0x04000000)
    assert bus.open_bus_reads == open_before
    assert bus.unsupported_io_reads == io_before


def test_region_info_and_copy(bus):
    info = bus.region_info(MemoryRegionKind.EWRAM)
    assert (info.base, info.size, info.read_only) == (0x02000000, 0x40000, False)
    assert bus.region_info(MemoryRegionKind.BIOS).read_only is True
    assert bus.region_info(MemoryRegionKind.ROM).size == len(bus.cartridge.rom_bytes)

    bus.write_u8(0x02000000, 0x12)
    snapshot = bus.read_region(MemoryRegionKind.EWRAM)
    assert snapshot[0] == 0x12
    snapshot = bytearray(snapshot)
    snapshot[0] = 0xFF
    assert bus.read_u8(0x02000000) == 0x12


def test_reset_clears_writable_regions(bus):
    bus.write_u8(0x02000000, 0x12)
    bus.write_u8(0x03000000, 0x34)
    bus.write_u8(0x05000000, 0x56)
    bus.write_u8(0x06000000, 0x78)
    bus.write_u16(0x07000000, 0x9ABC)
    bus.write_u8(0x0E000000, 0xDE)
    bus.debug_write(0x04000000, 0xAD)
    bus.reset()

    assert bus.read_u8(0x02000000) == 0
    assert bus.read_u8(0x03000000) == 0
    assert bus.read_u8(0x05000000) == 0
    assert bus.read_u8(0x06000000) == 0
    assert bus.read_u16(0x07000000) == 0
    assert bus.read_u8(0x0E000000) == 0xFF
    assert bus.peek_u8(0x04000000) == 0
    assert bus.unsupported_io_reads == 0


def test_access_helpers():
    assert AccessWidth.BYTE.size == 1
    assert AccessWidth.HALFWORD.size == 2
    assert AccessWidth.WORD.size == 4
    assert align_address(0x101, 1) == 0x101
    assert align_address(0x101, 2) == 0x100
    assert align_address(0x103, 4) == 0x100
    assert rotate_right_32(0x11223344, 8) == 0x44112233
    assert rotate_right_32(0x11223344, 0) == 0x11223344
    assert unaligned_word_rotate(0x11223344, 0x08000001) == 0x44112233
    with pytest.raises(ValueError):
        align_address(0, 3)
