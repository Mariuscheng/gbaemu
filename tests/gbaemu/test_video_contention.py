"""Phase 4：video contention（VRAM/OAM/Palette waitstate）與 prefetch disable bug。"""

from __future__ import annotations

from gbaemu import BootMode, Emulator, EmulatorConfig, TimingMode, VideoMode
from gbaemu.bus.access import access_cycles
from gbaemu.timing import PPU_VBLANK_START

from .cpu_helpers import arm_words, program_rom

B_SELF = 0xEAFFFFFE
VRAM = 0x06000000
PALETTE = 0x05000000
OAM = 0x07000000
ROM = 0x08000100


def _emu(tmp_path, *, timing: TimingMode = TimingMode.TIMED) -> Emulator:
    path = tmp_path / "contention.gba"
    path.write_bytes(program_rom(arm_words(B_SELF)))
    return Emulator.from_rom(
        path,
        config=EmulatorConfig(
            boot_mode=BootMode.TEST_ROM_ONLY,
            timing=timing,
            video=VideoMode.OFF,
        ),
    )


def test_visible_line_adds_one_wait(tmp_path):
    bus = _emu(tmp_path)._bus
    assert bus.ppu.state.scanline == 0
    assert not bus.ppu.state.in_hblank

    assert bus.video_wait(VRAM, 2) == 1
    assert bus.video_wait(PALETTE, 2) == 1
    assert bus.video_wait(OAM, 2) == 1
    assert bus.video_wait(0x02000000, 2) == 0  # EWRAM 不受影響


def test_hblank_allows_vram_and_palette(tmp_path):
    bus = _emu(tmp_path)._bus
    bus.ppu.advance(1006)
    assert bus.ppu.state.in_hblank

    assert bus.video_wait(VRAM, 2) == 0
    assert bus.video_wait(PALETTE, 2) == 0
    assert bus.video_wait(OAM, 2) == 1  # 未設 DISPCNT bit5

    bus.write_u16(0x04000000, 0x20)  # H-Blank Interval Free
    assert bus.video_wait(OAM, 2) == 0


def test_vblank_and_forced_blank_have_no_wait(tmp_path):
    bus = _emu(tmp_path)._bus
    bus.ppu.advance(PPU_VBLANK_START)
    assert bus.ppu.state.scanline >= 160
    assert bus.video_wait(VRAM, 2) == 0
    assert bus.video_wait(OAM, 2) == 0

    other = _emu(tmp_path)._bus
    other.write_u16(0x04000000, 0x0080)  # forced blank
    assert other.video_wait(VRAM, 2) == 0
    assert other.video_wait(OAM, 2) == 0


def test_cpu_and_dma_costs_include_contention(tmp_path):
    emu = _emu(tmp_path)
    bus = emu._bus
    cpu_bus = emu._cpu.bus

    base = access_cycles(VRAM, 2, False, bus.waitcnt)
    assert cpu_bus.access_cost(VRAM, 2, False) == base + 1
    assert bus.dma._cost(VRAM, 2, False) == base + 1

    bus.ppu.advance(PPU_VBLANK_START)
    assert cpu_bus.access_cost(VRAM, 2, False) == base


def test_prefetch_disable_bug_uses_n_cycle_for_internal_opcodes(tmp_path):
    emu = _emu(tmp_path)
    cpu = emu._cpu
    # WAITCNT 預設 0：prefetch off、WS0 = 4/2 → N=5、S=3
    assert (cpu.bus.io[0x205] >> 6) & 1 == 0

    plain = cpu._fetch(ROM, 2, False)
    internal = cpu._fetch(ROM, 2, True)
    assert plain == cpu.bus.access_cost(ROM, 2, 1) == 3
    assert internal == cpu.bus.access_cost(ROM, 2, 0) == 5


def test_prefetch_enabled_sequential_fetch_is_one_cycle(tmp_path):
    emu = _emu(tmp_path)
    cpu = emu._cpu
    cpu.bus.io[0x205] |= 1 << 6  # WAITCNT bit14：prefetch on

    assert cpu._fetch(ROM, 2, False) == 1
    assert cpu._fetch(ROM, 2, True) == 1


def test_functional_mode_ignores_contention(tmp_path):
    emu = _emu(tmp_path, timing=TimingMode.FUNCTIONAL)
    cpu_bus = emu._cpu.bus
    assert cpu_bus.access_cost(VRAM, 2, False) == 1
