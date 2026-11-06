"""Phase 2：frame 邊界、`step_frame()`、FrameResult 與 Mode 3 繪製。"""

from __future__ import annotations

from gbaemu import BootMode, Emulator, EmulatorConfig, VideoMode
from gbaemu.timing import PPU_FRAME_CYCLES, PPU_VBLANK_START

from .cpu_helpers import arm_words, program_rom

B_SELF = 0xEAFFFFFE
NOP = 0xE1A00000


def _emu(tmp_path, *, video=VideoMode.FRAMEBUFFER):
    path = tmp_path / "frame.gba"
    path.write_bytes(program_rom(arm_words(NOP, B_SELF)))
    return Emulator.from_rom(
        path,
        config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY, video=video),
    )


def test_step_frame_advances_one_frame(tmp_path):
    emu = _emu(tmp_path)
    result = emu.step_frame()

    assert result.frame_index == 1
    assert emu.frame_index == 1
    assert PPU_FRAME_CYCLES <= result.cycles <= PPU_FRAME_CYCLES + 4
    assert result.vblank_started is True
    assert result.halted is False

    kinds = [event.kind.value for event in result.events]
    assert "vblank_start" in kinds and "frame_boundary" in kinds
    vblank = next(e for e in result.events if e.kind.value == "vblank_start")
    boundary = next(e for e in result.events if e.kind.value == "frame_boundary")
    assert vblank.cycle == PPU_VBLANK_START
    assert boundary.cycle == PPU_FRAME_CYCLES


def test_second_frame_and_run_frames(tmp_path):
    emu = _emu(tmp_path)
    first = emu.step_frame()
    second = emu.step_frame()
    assert (first.frame_index, second.frame_index) == (1, 2)
    assert PPU_FRAME_CYCLES <= second.cycles <= PPU_FRAME_CYCLES + 4

    results = emu.run_frames(2, collect_results=True)
    assert [result.frame_index for result in results] == [3, 4]
    assert emu.run_frames(2) == []


def test_step_cycles_crosses_frame_boundary(tmp_path):
    emu = _emu(tmp_path)
    result = emu.step_cycles(PPU_FRAME_CYCLES + 4)
    assert emu.frame_index == 1
    kinds = [event.kind.value for event in result.events]
    assert "frame_boundary" in kinds


def test_mode3_renders_vram(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(0x04000000, 0x0003)  # DISPCNT: Mode 3、BG2 on
    emu.memory.write_u16(0x06000000, 0x001F)  # 紅（RGB555）
    emu.memory.write_u16(0x06000002, 0x03E0)  # 綠

    emu.step_frame()
    frame = emu.video.read_frame()
    assert frame[0:3] == bytes([0xFF, 0x00, 0x00])
    assert frame[3:6] == bytes([0x00, 0xFF, 0x00])


def test_force_blank_renders_white(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(0x04000000, 0x0083)  # force blank + Mode 3
    emu.step_frame()
    frame = emu.video.read_frame()
    assert frame[:3] == b"\xFF\xFF\xFF"
    assert set(frame) == {0xFF}


def test_non_mode3_leaves_framebuffer_untouched(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(0x04000000, 0x0000)  # Mode 0：Phase 4 才繪製
    emu.memory.write_u16(0x06000000, 0x7FFF)
    emu.step_frame()
    assert emu.video.read_frame() == bytes(240 * 160 * 3)


def test_render_false_skips_framebuffer(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(0x04000000, 0x0003)
    emu.memory.write_u16(0x06000000, 0x001F)
    emu.step_frame(render=False)
    assert emu.video.read_frame() == bytes(240 * 160 * 3)


def test_video_mode_off_disables_rendering(tmp_path):
    emu = _emu(tmp_path, video=VideoMode.OFF)
    emu.memory.write_u16(0x04000000, 0x0003)
    emu.memory.write_u16(0x06000000, 0x001F)
    emu.step_frame()
    assert emu.video.read_frame() == bytes(240 * 160 * 3)


def test_frame_result_irq_pending_reports_if(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(0x04000004, 0x0008)  # VBlank IRQ enable
    emu.memory.write_u16(0x04000200, 0x0001)  # IE: VBlank
    emu.memory.write_u16(0x04000208, 1)  # IME
    result = emu.step_frame()
    assert result.irq_pending & 0x0001

def test_dispcnt_mode_switches_vram_bitmap_boundary(tmp_path):
    emu = _emu(tmp_path)

    # Mode 0（tile）：0x06010100 屬於 OBJ VRAM，8-bit 寫入忽略
    emu.memory.write_u16(0x04000000, 0x0000)
    emu._bus.write_u8(0x06010100, 0x11)
    assert emu.memory.read_u8(0x06010100) == 0

    # Mode 3（bitmap）：BG 到 0x06014000，0x06010100 是 BG → 8-bit 複製
    emu.memory.write_u16(0x04000000, 0x0003)
    emu._bus.write_u8(0x06010100, 0x22)
    assert emu.memory.read_u8(0x06010100) == 0x22
    assert emu.memory.read_u8(0x06010101) == 0x22

    # 回到 tile：bitmap 設定要清掉
    emu.memory.write_u16(0x04000000, 0x0000)
    emu._bus.write_u8(0x06010100, 0x33)
    assert emu.memory.read_u8(0x06010100) == 0x22
