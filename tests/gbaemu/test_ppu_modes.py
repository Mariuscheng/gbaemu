"""Phase 4：PPU Mode 0/1/2、tile/affine BG、sprites、alpha blending。"""

from __future__ import annotations

from gbaemu import BootMode, Emulator, EmulatorConfig

from .cpu_helpers import arm_words, program_rom

B_SELF = 0xEAFFFFFE
DISPCTRL = 0x04000000
BG0CNT = 0x04000008
BG2CNT = 0x0400000C
BG0HOFS = 0x04000010
BG2PA = 0x04000020
BG2PD = 0x04000026
BG2X = 0x04000028
BG2Y = 0x0400002C
BLDCNT = 0x04000050
BLDALPHA = 0x04000052
OAM_BASE = 0x07000000
PALETTE = 0x05000000
VRAM = 0x06000000


def _emu(tmp_path) -> Emulator:
    path = tmp_path / "ppu_modes.gba"
    path.write_bytes(program_rom(arm_words(B_SELF)))
    return Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )


def _render(emu: Emulator) -> bytes:
    emu._bus.ppu.render(emu._bus.vram, emu._framebuffer)
    return emu.video.read_frame()


def _pixel(frame: bytes, x: int, y: int) -> tuple[int, int, int]:
    offset = (y * 240 + x) * 3
    return tuple(frame[offset : offset + 3])


def _fill(emu: Emulator, address: int, value: int, count: int) -> None:
    for index in range(count):
        emu.memory.write_u8(address + index, value)


def test_mode0_text_bg_4bpp():
    pass


def test_mode0_text_bg_4bpp(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x0100)  # Mode 0 + BG0 enable
    emu.memory.write_u16(BG0CNT, 0x0004)  # char base 1 (0x4000)、screen base 0
    _fill(emu, VRAM + 0x4000, 0x11, 32)  # tile 0：所有 pixel = 1
    emu.memory.write_u16(VRAM, 0)  # map[0] = tile 0
    emu.memory.write_u16(PALETTE + 2, 0x001F)  # palette[1] 紅

    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (255, 0, 0)
    assert _pixel(frame, 7, 7) == (255, 0, 0)


def test_mode0_transparent_pixels_use_backdrop(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x0100)
    emu.memory.write_u16(BG0CNT, 0x0004)
    _fill(emu, VRAM + 0x4000, 0x00, 32)  # tile 0 全透明
    emu.memory.write_u16(VRAM, 0)
    emu.memory.write_u16(PALETTE, 0x03E0)  # 綠 backdrop

    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (0, 255, 0)


def test_mode0_text_bg_scroll(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x0100)
    emu.memory.write_u16(BG0CNT, 0x0004)
    _fill(emu, VRAM + 0x4000, 0x11, 32)  # tile 0 紅
    _fill(emu, VRAM + 0x4020, 0x22, 32)  # tile 1（palette 2）
    emu.memory.write_u16(VRAM, 0)  # (0,0) tile 0
    emu.memory.write_u16(VRAM + 2, 1)  # (1,0) tile 1
    emu.memory.write_u16(PALETTE + 2, 0x001F)
    emu.memory.write_u16(PALETTE + 4, 0x7C00)

    emu.memory.write_u16(BG0HOFS, 8)
    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (0, 0, 255)  # 捲動後看到 tile 1
    emu.memory.write_u16(BG0HOFS, 0)
    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (255, 0, 0)


def test_mode0_text_bg_8bpp(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x0100)
    emu.memory.write_u16(BG0CNT, 0x0084)  # 8bpp + char base 1
    _fill(emu, VRAM + 0x4000, 0x05, 64)
    emu.memory.write_u16(VRAM, 0)
    emu.memory.write_u16(PALETTE + 5 * 2, 0x7C00)

    frame = _render(emu)
    assert _pixel(frame, 3, 3) == (0, 0, 255)


def test_mode2_affine_bg(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x0002 | 0x0400)  # Mode 2 + BG2
    emu.memory.write_u16(BG2CNT, 0x0084)  # 8bpp + char base 1 + size 128
    _fill(emu, VRAM + 0x4000, 0x09, 64)
    emu.memory.write_u8(VRAM, 0)  # tile 0
    emu.memory.write_u16(BG2PA, 0x0100)
    emu.memory.write_u16(BG2PD, 0x0100)
    emu.memory.write_u32(BG2X, 0)
    emu.memory.write_u32(BG2Y, 0)
    emu.memory.write_u16(PALETTE + 9 * 2, 0x03E0)

    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (0, 255, 0)
    assert _pixel(frame, 100, 100) == (0, 255, 0)


def test_regular_sprite(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x1000)  # OBJ enable、Mode 0
    emu.memory.write_u16(OAM_BASE + 0, 0)  # y=0、regular、8x8
    emu.memory.write_u16(OAM_BASE + 2, 0)  # x=0、size 0
    emu.memory.write_u16(OAM_BASE + 4, 0)  # tile 0、priority 0、palette 0
    _fill(emu, VRAM + 0x10000, 0x22, 32)  # 4bpp tile：color 2
    emu.memory.write_u16(PALETTE + (0x100 + 2) * 2, 0x001F)  # OBJ palette red

    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (255, 0, 0)
    assert _pixel(frame, 7, 7) == (255, 0, 0)
    assert _pixel(frame, 8, 0) != (255, 0, 0)  # sprite 範圍外


def test_sprite_hflip(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x1000)
    emu.memory.write_u16(OAM_BASE + 0, 0)
    emu.memory.write_u16(OAM_BASE + 2, 0x1000)  # hflip
    emu.memory.write_u16(OAM_BASE + 4, 0)
    # tile：左半 color 2、右半 color 3
    for row in range(8):
        emu.memory.write_u8(VRAM + 0x10000 + row * 4 + 0, 0x22)
        emu.memory.write_u8(VRAM + 0x10000 + row * 4 + 1, 0x22)
        emu.memory.write_u8(VRAM + 0x10000 + row * 4 + 2, 0x33)
        emu.memory.write_u8(VRAM + 0x10000 + row * 4 + 3, 0x33)
    emu.memory.write_u16(PALETTE + (0x100 + 2) * 2, 0x001F)
    emu.memory.write_u16(PALETTE + (0x100 + 3) * 2, 0x7C00)

    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (0, 0, 255)  # hflip：原右半到左邊
    assert _pixel(frame, 7, 0) == (255, 0, 0)


def test_alpha_blend_bg_over_backdrop(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x0100 | 0x0040)  # Mode 0 + BG0 + alpha? bit6 is OBJ 1D
    emu.memory.write_u16(DISPCTRL, 0x0100)  # 確認 Mode 0 + BG0
    emu.memory.write_u16(BG0CNT, 0x0004)
    _fill(emu, VRAM + 0x4000, 0x11, 32)
    emu.memory.write_u16(VRAM, 0)
    emu.memory.write_u16(PALETTE + 2, 0x001F)  # red
    emu.memory.write_u16(PALETTE, 0x7C00)  # blue backdrop

    # GBATEK BLDCNT：bit6-7 = 效果模式（1=alpha）、bit8-13 = 2nd target。
    # BG0 為 1st target、backdrop 為 2nd target。
    emu.memory.write_u16(BLDCNT, 0x2000 | 0x0040 | 0x0001)
    emu.memory.write_u16(BLDALPHA, 0x0808)  # EVA=8、EVB=8

    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (123, 0, 123)


def test_force_blank_is_white(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x0080)
    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (255, 255, 255)
    assert _pixel(frame, 239, 159) == (255, 255, 255)


def test_window0_masks_bg_outside(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x0100 | 0x2000)  # BG0 + WIN0 enable
    emu.memory.write_u16(BG0CNT, 0x0004)
    _fill(emu, VRAM + 0x4000, 0x11, 32)
    emu.memory.write_u16(VRAM, 0)
    emu.memory.write_u16(PALETTE + 2, 0x001F)  # red BG
    emu.memory.write_u16(PALETTE, 0x03E0)  # green backdrop

    emu.memory.write_u16(0x04000040, 0x0008)  # WIN0H: X1=0, X2=8
    emu.memory.write_u16(0x04000044, 0x0008)  # WIN0V: Y1=0, Y2=8
    emu.memory.write_u16(0x04000048, 0x0001)  # WININ: BG0 on inside WIN0
    emu.memory.write_u16(0x0400004A, 0x0000)  # WINOUT: all off

    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (255, 0, 0)  # 窗內看得到 BG
    assert _pixel(frame, 7, 7) == (255, 0, 0)
    assert _pixel(frame, 8, 0) == (0, 255, 0)  # 窗外被遮成 backdrop


def test_window1_masks_bg_outside(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x0100 | 0x4000)  # BG0 + WIN1
    emu.memory.write_u16(BG0CNT, 0x0004)
    _fill(emu, VRAM + 0x4000, 0x11, 32)
    emu.memory.write_u16(VRAM, 0)
    emu.memory.write_u16(PALETTE + 2, 0x001F)
    emu.memory.write_u16(PALETTE, 0x03E0)

    emu.memory.write_u16(0x04000042, 0x0828)  # WIN1H: X1=8, X2=40
    emu.memory.write_u16(0x04000046, 0x0828)  # WIN1V: Y1=8, Y2=40
    emu.memory.write_u16(0x04000048, 0x0100)  # WININ: BG0 on inside WIN1
    emu.memory.write_u16(0x0400004A, 0x0000)

    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (0, 255, 0)
    assert _pixel(frame, 10, 10) == (255, 0, 0)


def test_window1_full_width_band(tmp_path):
    """WIN1 用 0x042/0x046；X1=0/X2=240 全寬、Y1=32/Y2=128 成一條橫帶。

    LeafGreen 開場廠商 logo 就是用這組設定，早前把 0x042 當成 WIN0V 會令
    整個窗變空、畫面全黑。
    """
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x0100 | 0x4000)  # BG0 + WIN1
    emu.memory.write_u16(BG0CNT, 0x0004)
    _fill(emu, VRAM + 0x4000, 0x11, 32)
    emu.memory.write_u16(VRAM, 0)
    emu.memory.write_u16(PALETTE + 2, 0x001F)  # red BG
    emu.memory.write_u16(PALETTE, 0x03E0)  # green backdrop

    emu.memory.write_u16(0x04000042, 0x00F0)  # WIN1H: X1=0, X2=240
    emu.memory.write_u16(0x04000046, 0x2080)  # WIN1V: Y1=32, Y2=128
    emu.memory.write_u16(0x04000048, 0x3F00)  # WININ: WIN1 內全部 layer
    emu.memory.write_u16(0x0400004A, 0x0000)  # 窗外全部隱藏

    frame = _render(emu)
    assert _pixel(frame, 120, 31) == (0, 255, 0)  # 帶外 backdrop
    assert _pixel(frame, 120, 32) == (255, 0, 0)  # 帶內看得到 BG
    assert _pixel(frame, 0, 80) == (255, 0, 0)  # 全寬（X1=0、X2=240）
    assert _pixel(frame, 239, 80) == (255, 0, 0)
    assert _pixel(frame, 120, 127) == (255, 0, 0)
    assert _pixel(frame, 120, 128) == (0, 255, 0)


def test_window_x1_greater_than_x2_clamps_to_edge(tmp_path):
    """GBATEK：X1>X2 當成 X2=240（不是繞回左邊）。"""
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x0100 | 0x2000)  # BG0 + WIN0
    emu.memory.write_u16(BG0CNT, 0x0004)
    _fill(emu, VRAM + 0x4000, 0x11, 32)
    emu.memory.write_u16(VRAM, 0)
    emu.memory.write_u16(PALETTE + 2, 0x001F)
    emu.memory.write_u16(PALETTE, 0x03E0)

    emu.memory.write_u16(0x04000040, 0x5000)  # WIN0H: X1=0x50、X2=0 → X2=240
    emu.memory.write_u16(0x04000044, 0x00A0)  # WIN0V: Y1=0、Y2=160
    emu.memory.write_u16(0x04000048, 0x003F)
    emu.memory.write_u16(0x0400004A, 0x0000)

    frame = _render(emu)
    assert _pixel(frame, 79, 0) == (0, 255, 0)  # X1 左邊唔顯示
    assert _pixel(frame, 80, 0) == (255, 0, 0)
    assert _pixel(frame, 239, 159) == (255, 0, 0)


def test_bg_mosaic_samples_block_origin(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x0100)
    emu.memory.write_u16(BG0CNT, 0x0004 | 0x0040)  # mosaic enable
    # tile byte 0 = 0x12 → pixel0 color 2、pixel1 color 1
    emu.memory.write_u8(VRAM + 0x4000, 0x12)
    _fill(emu, VRAM + 0x4001, 0, 31)
    emu.memory.write_u16(VRAM, 0)
    emu.memory.write_u16(PALETTE + 2 * 2, 0x001F)  # color2 red
    emu.memory.write_u16(PALETTE + 1 * 2, 0x7C00)  # color1 blue
    emu.memory.write_u16(0x0400004C, 0x0001)  # BG mosaic size 2

    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (255, 0, 0)
    assert _pixel(frame, 1, 0) == (255, 0, 0)  # 取 block 原點 → color2

    emu.memory.write_u16(BG0CNT, 0x0004)  # 關閉 mosaic
    frame = _render(emu)
    assert _pixel(frame, 1, 0) == (0, 0, 255)  # 恢復 color1


def test_obj_mosaic_samples_block_origin(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(DISPCTRL, 0x1000)  # OBJ
    emu.memory.write_u16(OAM_BASE + 0, 0x1000)  # y=0、regular、mosaic
    emu.memory.write_u16(OAM_BASE + 2, 0)  # x=0、size0
    emu.memory.write_u16(OAM_BASE + 4, 0)
    emu.memory.write_u8(VRAM + 0x10000, 0x12)  # px0=2、px1=1
    _fill(emu, VRAM + 0x10001, 0, 31)
    emu.memory.write_u16(PALETTE + (0x100 + 2) * 2, 0x001F)
    emu.memory.write_u16(PALETTE + (0x100 + 1) * 2, 0x7C00)
    emu.memory.write_u16(0x0400004C, 0x0010)  # OBJ mosaic size 2

    frame = _render(emu)
    assert _pixel(frame, 0, 0) == (255, 0, 0)
    assert _pixel(frame, 1, 0) == (255, 0, 0)  # 取 block 原點 → color2
