"""Phase 3：SWI 0x00–0x2A HLE 實作（GBATEK: BIOS Functions）。"""

from __future__ import annotations

import pytest

from gbaemu import BootMode, Emulator, EmulatorConfig
from gbaemu.errors import HleUnsupportedSwiError
from gbaemu.hle.swi_math import biosatan2_parts, biostan_parts, midi_val

from .cpu_helpers import arm_words, program_rom

SWI = 0xEF000000


def _emu(tmp_path, code=None) -> Emulator:
    code = code if code is not None else arm_words(0xEAFFFFFE)
    path = tmp_path / "swi.gba"
    path.write_bytes(program_rom(code))
    return Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )


def _call(emu: Emulator, number: int) -> None:
    emu._swi_table.dispatch(number)


def _reg(emu: Emulator, index: int) -> int:
    return emu._cpu.regs.r[index]


def _set(emu: Emulator, index: int, value: int) -> None:
    emu._cpu.regs.r[index] = value & 0xFFFFFFFF


def test_div_and_divarm(tmp_path):
    emu = _emu(tmp_path)
    _set(emu, 0, -1234)
    _set(emu, 1, 10)
    _call(emu, 0x06)
    assert _reg(emu, 0) == -123 & 0xFFFFFFFF
    assert _reg(emu, 1) == -4 & 0xFFFFFFFF
    assert _reg(emu, 3) == 123

    _set(emu, 0, 10)  # DivArm：r0=分母、r1=分子
    _set(emu, 1, -1234)
    _call(emu, 0x07)
    assert _reg(emu, 0) == -123 & 0xFFFFFFFF
    assert _reg(emu, 1) == -4 & 0xFFFFFFFF

    # BIOS 除以零的保護值：商 = sign(numerator)，餘數 = numerator，r3=1
    _set(emu, 0, 0)
    _set(emu, 1, 0)
    _call(emu, 0x06)
    assert (_reg(emu, 0), _reg(emu, 1), _reg(emu, 3)) == (1, 0, 1)
    _set(emu, 0, 0xFFFFFFFF)
    _call(emu, 0x06)
    assert (_reg(emu, 0), _reg(emu, 1), _reg(emu, 3)) == (0xFFFFFFFF, 0xFFFFFFFF, 1)


def test_sqrt_arctan_arctan2_checksum(tmp_path):
    emu = _emu(tmp_path)
    _set(emu, 0, 144)
    _call(emu, 0x08)
    assert _reg(emu, 0) == 12

    _set(emu, 0, 0x00001234)
    expected, expected_r1, expected_r3 = biostan_parts(0x00001234)
    _call(emu, 0x09)
    assert _reg(emu, 0) == expected
    assert _reg(emu, 1) == expected_r1
    assert _reg(emu, 3) == expected_r3

    _set(emu, 0, 0x00001234)
    _set(emu, 1, 0x00005678)
    expected2, expected2_r1 = biosatan2_parts(0x00001234, 0x00005678)
    _call(emu, 0x0A)
    assert _reg(emu, 0) == expected2
    assert _reg(emu, 1) == expected2_r1
    assert _reg(emu, 3) == 0x170

    _call(emu, 0x0D)
    assert _reg(emu, 0) == 0xBAAE187F


def test_cpu_set_copy_and_fill(tmp_path):
    emu = _emu(tmp_path)
    for index in range(4):
        emu.memory.write_u16(0x02000000 + index * 2, 0x1000 + index)
    _set(emu, 0, 0x02000000)
    _set(emu, 1, 0x02000100)
    _set(emu, 2, 4)  # 16-bit、count=4、copy
    _call(emu, 0x0B)
    for index in range(4):
        assert emu.memory.read_u16(0x02000100 + index * 2) == 0x1000 + index

    _set(emu, 1, 0x02000200)
    _set(emu, 2, (1 << 24) | 4)  # fill
    _call(emu, 0x0B)
    for index in range(4):
        assert emu.memory.read_u16(0x02000200 + index * 2) == 0x1000


def test_cpu_set_unaligned_source(tmp_path):
    emu = _emu(tmp_path)
    for index, value in enumerate((0x0D, 0xF0, 0x0D, 0x90)):
        emu.memory.write_u8(0x02000000 + index, value)
    _set(emu, 0, 0x02000001)
    _set(emu, 1, 0x02000100)
    _set(emu, 2, 4)
    _call(emu, 0x0B)
    assert emu.memory.read_u32(0x02000100) == 0x0090_00F0

    _set(emu, 0, 0x02000001)
    _set(emu, 1, 0x02000200)
    _set(emu, 2, 2 | (1 << 26))
    _call(emu, 0x0B)
    assert emu.memory.read_u32(0x02000200) == 0x900D_F00D


def test_cpu_fast_set_rounds_up_to_eight_words(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u32(0x02000000, 0xCAFEBABE)
    _set(emu, 0, 0x02000000)
    _set(emu, 1, 0x02000100)
    _set(emu, 2, (1 << 24) | 5)  # fill、5 words → 向上取整 8
    _call(emu, 0x0C)
    for index in range(8):
        assert emu.memory.read_u32(0x02000100 + index * 4) == 0xCAFEBABE


def test_bit_unpack(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u8(0x02000000, 0b10101010)
    info = 0x02000100
    emu.memory.write_u16(info, 1)  # 來源長度 1 byte
    emu.memory.write_u8(info + 2, 1)  # 來源 1 bit
    emu.memory.write_u8(info + 3, 4)  # 目的 4 bit
    emu.memory.write_u32(info + 4, 0)

    _set(emu, 0, 0x02000000)
    _set(emu, 1, 0x02000200)
    _set(emu, 2, info)
    _call(emu, 0x10)
    # LSB 起：0,1,0,1,... → 4bit 單位交錯 → 0x11111110
    assert emu.memory.read_u32(0x02000200) == 0x10101010


def _write_bytes(emu, address: int, data: bytes) -> None:
    for index, value in enumerate(data):
        emu.memory.write_u8(address + index, value)


def test_lz77_decompress(tmp_path):
    emu = _emu(tmp_path)
    # header：type=1、解壓長度 4；flag=0x00（8 個 literal）
    header = 1 << 4 | 4 << 8
    data = header.to_bytes(4, "little") + bytes([0x00, ord("A"), ord("B"), ord("C"), ord("D")])
    _write_bytes(emu, 0x02000000, data)
    _set(emu, 0, 0x02000000)
    _set(emu, 1, 0x02001000)
    _call(emu, 0x11)
    assert bytes(emu.memory.read_u8(0x02001000 + i) for i in range(4)) == b"ABCD"


def test_lz77_back_reference(tmp_path):
    emu = _emu(tmp_path)
    # 先輸出 "AB"，再從 dest-1 複製（disp=1）3 bytes → "ABBBB"
    header = (1 << 4) | (5 << 8)
    stream = header.to_bytes(4, "little")
    stream += bytes(
        [
            0b0010_0000,  # flag：第二個 block 是壓縮
            ord("A"),
            ord("B"),
            0x00,  # disp=0 → 從 dest-1 複製；count=(0>>4)+3=3
            0x00,
        ]
    )
    _write_bytes(emu, 0x02000000, stream)
    _set(emu, 0, 0x02000000)
    _set(emu, 1, 0x02001000)
    _call(emu, 0x11)
    out = bytes(emu.memory.read_u8(0x02001000 + i) for i in range(5))
    assert out == b"ABBBB"


def test_huffman_variable_length_codes(tmp_path):
    emu = _emu(tmp_path)
    # Codes: 0 -> 0x11, 10 -> 0x22, 11 -> 0x33。
    # 8 symbols = 14 bits，但輸出仍是兩個 32-bit words；壓縮碼是變長的，
    # 不能固定每個 word 只解 4 個 symbol。
    data = bytes(
        [
            0x08, 0x08, 0x00, 0x00,  # header: 8 bytes、8-bit symbols
            0x03,                    # tree size -> 7 bytes（bitstream 4-byte 對齊）
            0x80, 0x11, 0xC0, 0x22, 0x33, 0x00, 0x00,
            0x00, 0x00, 0xD0, 0x5A,  # 0101101011010000（word MSB 起）
        ]
    )
    _write_bytes(emu, 0x02000000, data)
    _set(emu, 0, 0x02000000)
    _set(emu, 1, 0x02001000)
    _call(emu, 0x13)
    assert emu.memory.read_u32(0x02001000) == 0x1133_2211
    assert emu.memory.read_u32(0x02001004) == 0x2211_3322
    assert _reg(emu, 1) == 0x02001008


def test_rl_decompress(tmp_path):
    emu = _emu(tmp_path)
    header = (2 << 4) | (6 << 8)  # type=2、解壓 6 bytes
    stream = header.to_bytes(4, "little") + bytes([0x80 | 3, 0xAA])  # 重複 6 次
    _write_bytes(emu, 0x02000000, stream)
    _set(emu, 0, 0x02000000)
    _set(emu, 1, 0x02001000)
    _call(emu, 0x14)
    assert bytes(emu.memory.read_u8(0x02001000 + i) for i in range(6)) == bytes([0xAA]) * 6


def test_diff8_and_diff16(tmp_path):
    emu = _emu(tmp_path)
    header8 = (8 << 4) | (4 << 8)
    stream = header8.to_bytes(4, "little") + bytes([1, 2, 3, 4])
    _write_bytes(emu, 0x02000000, stream)
    _set(emu, 0, 0x02000000)
    _set(emu, 1, 0x02001000)
    _call(emu, 0x16)
    assert bytes(emu.memory.read_u8(0x02001000 + i) for i in range(4)) == bytes([1, 3, 6, 10])

    header16 = (8 << 4) | (4 << 8)
    stream16 = header16.to_bytes(4, "little") + (1).to_bytes(2, "little") + (2).to_bytes(2, "little")
    _write_bytes(emu, 0x02000000, stream16)
    _set(emu, 0, 0x02000000)
    _set(emu, 1, 0x02002000)
    _call(emu, 0x18)
    assert emu.memory.read_u16(0x02002000) == 1
    assert emu.memory.read_u16(0x02002002) == 3


def test_sound_bias_and_midi(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(0x04000088, 0x4000 | 0x0300)
    _set(emu, 0, 0x200)
    _call(emu, 0x19)
    assert emu.memory.read_u16(0x04000088) & 0x3FF == 0x200
    assert emu.memory.read_u16(0x04000088) & 0xFC00 == 0x4000

    _set(emu, 0, 0)
    _set(emu, 1, 60)
    _set(emu, 2, 0)
    _call(emu, 0x1F)
    assert _reg(emu, 0) == midi_val(60)


def test_register_ram_reset(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u8(0x02000010, 0xAA)
    emu.memory.write_u8(0x05000000, 0xBB)
    _set(emu, 0, 0x01 | 0x04)  # EWRAM + Palette
    _call(emu, 0x01)
    assert emu.memory.read_u8(0x02000010) == 0
    assert emu.memory.read_u8(0x05000000) == 0
    assert emu.memory.read_u16(0x04000000) == 0x0080  # forced blank


def test_register_ram_reset_sets_affine_identity(tmp_path):
    """BIOS 的 IO 復位值：BG2/BG3 affine matrix = identity（PA=PD=0x0100）。

    LeafGreen 開機用 SWI 0x01（flags 0x80）重設 IO，之後靠呢個預設用 BG2
    畫 Professor Oak；之前我哋清零 affine register → BG2 只剩一個透明 texel。
    """

    emu = _emu(tmp_path)
    emu.memory.write_u16(0x04000020, 0)  # 先破壞 identity
    emu.memory.write_u16(0x04000026, 0)
    _set(emu, 0, 0x80)
    _call(emu, 0x01)

    # 用 render 驗證：mode 2 + BG2（128x128 affine），唔寫 BG2PA/PD。
    emu.memory.write_u16(0x04000000, 0x0002 | 0x0400)  # Mode 2 + BG2
    emu.memory.write_u16(0x0400000C, 0x0084)  # BG2CNT: 8bpp + char base 1
    for offset in range(0x40):
        emu.memory.write_u8(0x06004000 + offset, 0x09)
    emu.memory.write_u8(0x06000000, 0)  # tile 0
    emu.memory.write_u16(0x05000000 + 9 * 2, 0x03E0)
    emu._bus.ppu.render(emu._bus.vram, emu._framebuffer)
    frame = emu.video.read_frame()
    assert frame[:3] == bytes((0, 255, 0))
    assert frame[(100 * 240 + 100) * 3 : (100 * 240 + 100) * 3 + 3] == bytes((0, 255, 0))


def test_halt_and_intr_wait(tmp_path):
    emu = _emu(tmp_path)
    _call(emu, 0x02)
    assert emu._cpu.core.halted is True

    emu.memory.write_u16(0x04000200, 0x0001)  # IE
    emu.memory.write_u16(0x04000202, 0x0001)  # IF
    emu.step_cycles(1)
    assert emu._cpu.core.halted is False

    emu.memory.write_u16(0x04000202, 0x0000)
    _set(emu, 0, 0)
    _set(emu, 1, 0x0002)
    _call(emu, 0x04)
    assert emu._cpu.core.halted is True
    assert emu._cpu.wait_irq == 0x0002

    emu.memory.write_u16(0x04000202, 0x0002)
    emu.step_cycles(1)
    assert emu._cpu.core.halted is False
    assert emu._cpu.wait_irq == 0


def test_unknown_swi_raises_in_strict_mode(tmp_path):
    emu = _emu(tmp_path)
    with pytest.raises(HleUnsupportedSwiError):
        _call(emu, 0x20)  # SoundWhatever0：未實作


def test_div_via_cpu_swi_instruction(tmp_path):
    emu = _emu(tmp_path, arm_words(SWI | (0x06 << 16), 0xE1A00000, 0xEAFFFFFE))
    _set(emu, 0, -1234)
    _set(emu, 1, 10)
    emu.step_cycles(10)
    assert _reg(emu, 0) == -123 & 0xFFFFFFFF
    assert _reg(emu, 1) == -4 & 0xFFFFFFFF
    assert emu.cpu.state().mode == 0x1F
    assert emu.cpu.read_register("r15") == 0x08000008  # 已回到 B . 迴圈
