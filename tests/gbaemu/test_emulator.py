"""Phase 0 驗收：ROM 載入、reset、HLE 狀態與對外 view。"""

from __future__ import annotations

import pytest

from gbaemu import (
    BootMode,
    Button,
    Emulator,
    EmulatorConfig,
    EventKind,
    MemoryRegionKind,
)
from gbaemu.errors import (
    BiosChecksumError,
    BiosMissingError,
    BreakpointError,
    GbaEmuError,
    InvalidConfigError,
    ReadOnlyMemoryError,
    RomInvalidError,
)

from .helpers import build_rom

FRAME_BYTES = 240 * 160 * 3


def test_from_rom_completes_hle_boot(rom_path, rom_bytes):
    emu = Emulator.from_rom(rom_path)
    state = emu.cpu.state()

    assert len(state.regs) == 16
    assert state.regs[13] == 0x03007F00
    assert state.regs[15] == 0x08000000
    assert state.mode == 0x1F
    assert state.thumb is False
    assert state.halted is False
    assert state.cycles == 0
    assert emu.cycles == 0
    assert emu.frame_index == 0
    assert emu.rom_path == rom_path

    first_word = int.from_bytes(rom_bytes[0:4], "little")
    assert emu.memory.read_u32(0x02000000) == first_word
    for index in range(0xC0):
        assert emu.memory.read_u8(0x02000000 + index) == rom_bytes[index]
    assert emu.memory.read_u32(0x03007FF8) == 0
    assert emu.memory.read_u32(0x03007FFC) == 0


def test_rom_header_is_parsed(rom_path):
    emu = Emulator.from_rom(rom_path)
    header = emu.rom_header
    assert header.title == "TESTGAME"
    assert header.game_code == "TEST"
    assert header.maker_code == "01"
    assert header.entry_point == 0x08000000
    assert header.fixed_value == 0x96
    assert header.fixed_value_ok is True
    assert header.complement_check_ok is True


def test_reset_clears_ram_and_restores_postboot(rom_path):
    emu = Emulator.from_rom(rom_path)
    emu.memory.write_u8(0x02000100, 0xAA)
    emu.memory.write_u8(0x03000000, 0xBB)
    emu.memory.write_u8(0x05000000, 0xCC)
    emu.memory.write_u8(0x06000000, 0xDD)
    emu.memory.write_u16(0x07000000, 0xABCD)
    emu.memory.write_u8(0x0E000000, 0xEE)
    emu.input.set_buttons(a=True)

    emu.reset()

    assert emu.memory.read_u8(0x02000100) == 0
    assert emu.memory.read_u8(0x03000000) == 0
    assert emu.memory.read_u8(0x05000000) == 0
    assert emu.memory.read_u8(0x06000000) == 0
    assert emu.memory.read_u16(0x07000000) == 0
    assert emu.memory.read_u8(0x0E000000) == 0xFF
    assert emu.input.pressed_buttons == frozenset()
    assert emu.events.poll() == ()
    assert emu.cpu.state().regs[15] == 0x08000000


def test_test_rom_only_starts_at_rom_base_without_header_copy(rom_path):
    emu = Emulator.from_rom(
        rom_path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )
    state = emu.cpu.state()
    assert state.regs[15] == 0x08000000
    assert state.mode == 0x1F
    assert emu.memory.read_u8(0x02000000) == 0


def test_require_bios_requires_path(rom_path):
    with pytest.raises(InvalidConfigError):
        Emulator.from_rom(
            rom_path, config=EmulatorConfig(boot_mode=BootMode.REQUIRE_BIOS)
        )


def test_require_bios_missing_file(rom_path, tmp_path):
    config = EmulatorConfig(
        boot_mode=BootMode.REQUIRE_BIOS, bios_path=tmp_path / "missing.bin"
    )
    with pytest.raises(BiosMissingError):
        Emulator.from_rom(rom_path, config=config)


def test_require_bios_wrong_size(rom_path, tmp_path):
    bios = tmp_path / "bios.bin"
    bios.write_bytes(b"\x00" * 0x100)
    config = EmulatorConfig(boot_mode=BootMode.REQUIRE_BIOS, bios_path=bios)
    with pytest.raises(BiosChecksumError):
        Emulator.from_rom(rom_path, config=config)


def test_require_bios_starts_at_reset_vector(rom_path, tmp_path):
    bios = tmp_path / "bios.bin"
    bios.write_bytes(b"\x00" * 0x4000)
    emu = Emulator.from_rom(
        rom_path, config=EmulatorConfig(boot_mode=BootMode.REQUIRE_BIOS, bios_path=bios)
    )
    state = emu.cpu.state()
    assert state.regs[15] == 0
    assert state.mode == 0x13
    assert emu.memory.read_u8(0x00000000) == 0
    assert emu.memory.read_u8(0x00003FFF) == 0


def test_invalid_rom_too_small(tmp_path):
    path = tmp_path / "bad.gba"
    path.write_bytes(b"\x00" * 8)
    with pytest.raises(RomInvalidError):
        Emulator.from_rom(path)


def test_missing_rom_file(tmp_path):
    with pytest.raises(RomInvalidError):
        Emulator.from_rom(tmp_path / "nope.gba")


def test_input_port_latches_buttons(rom_path):
    emu = Emulator.from_rom(rom_path)
    emu.input.set_buttons(a=True, start=True)
    assert emu.input.pressed_buttons == frozenset({Button.A, Button.START})
    emu.input.set_buttons(a=False)
    assert emu.input.pressed_buttons == frozenset({Button.START})

    emu.input.press(Button.B, Button.L)
    assert emu.input.is_pressed(Button.B)
    assert emu.input.is_pressed(Button.L)
    emu.input.release(Button.B)
    assert not emu.input.is_pressed(Button.B)
    emu.input.clear()
    assert emu.input.pressed_buttons == frozenset()

    with pytest.raises(ValueError):
        emu.input.set_buttons(nope=True)
    with pytest.raises(ValueError):
        emu.input.set_buttons(a=1)
    with pytest.raises(ValueError):
        emu.input.press("a")
    with pytest.raises(ValueError):
        emu.input.is_pressed("a")


def test_video_view_shape_and_scanlines(rom_path):
    emu = Emulator.from_rom(rom_path)
    frame = emu.video.read_frame()
    assert len(frame) == FRAME_BYTES
    assert frame == bytes(FRAME_BYTES)
    assert len(emu.video.read_frame(copy=False)) == FRAME_BYTES
    scanline = emu.video.read_scanline(0)
    assert len(scanline) == 240 * 3
    with pytest.raises(ValueError):
        emu.video.read_scanline(160)


def test_video_frame_array(rom_path):
    np = pytest.importorskip("numpy")
    emu = Emulator.from_rom(rom_path)
    array = emu.video.read_frame_array()
    assert array.shape == (160, 240, 3)
    assert array.dtype == np.uint8
    assert int(array.sum()) == 0


def test_memory_view_regions_and_readonly(rom_path, rom_bytes):
    emu = Emulator.from_rom(rom_path)
    assert emu.memory.read_region(MemoryRegionKind.EWRAM)[:0xC0] == rom_bytes[:0xC0]
    info = emu.memory.region_info(MemoryRegionKind.ROM)
    assert info.base == 0x08000000
    assert info.size == len(rom_bytes)
    assert info.read_only is True

    with pytest.raises(ReadOnlyMemoryError):
        emu.memory.write_u8(0x08000000, 0xFF)
    with pytest.raises(ReadOnlyMemoryError):
        emu.memory.write_u8(0x00000000, 0xFF)
    with pytest.raises(ReadOnlyMemoryError):
        emu.memory.write_u8(0x0F000000, 0xFF)


def test_breakpoints(rom_path):
    emu = Emulator.from_rom(rom_path)
    first = emu.cpu.set_breakpoint(0x08000000)
    second = emu.cpu.set_breakpoint(0x08000000, thumb=True)
    assert first != second
    emu.cpu.clear_breakpoint(first)
    emu.cpu.clear_breakpoint(second)
    with pytest.raises(BreakpointError):
        emu.cpu.clear_breakpoint(999)
    emu.cpu.set_breakpoint(0x08000010)
    with pytest.raises(ValueError):
        emu.cpu.set_breakpoint(-1)


def test_force_write_emits_watchpoint_event(rom_path):
    emu = Emulator.from_rom(rom_path)
    assert emu.events.poll() == ()
    emu.memory.force_write(0x02000100, 0x5A)
    assert emu.memory.read_u8(0x02000100) == 0x5A
    events = emu.events.poll()
    assert len(events) == 1
    event = events[0]
    assert event.kind is EventKind.WATCHPOINT_WRITE
    assert event.address == 0x02000100
    assert event.value == 0x5A
    assert event.cycle == 0
    assert event.frame_index == 0
    assert emu.events.poll() == ()


def test_close_is_idempotent_and_blocks_lifecycle(rom_path):
    emu = Emulator.from_rom(rom_path)
    emu.close()
    emu.close()
    assert emu.is_closed is True
    with pytest.raises(GbaEmuError):
        emu.reset()
    with pytest.raises(GbaEmuError):
        emu.step_cycles(1)


def test_unimplemented_phases_are_explicit(rom_path):
    emu = Emulator.from_rom(rom_path)
    # Phase 1/2 已實作 step_cycles／step_frame；其餘 Phase 仍明確 NotImplementedError。
    assert emu.step_cycles(1).cycles_executed == 1
    with pytest.raises(NotImplementedError):
        emu.run_until(EventKind.FRAME_BOUNDARY, max_cycles=10)
    with pytest.raises(GbaEmuError):
        emu.cartridge_flush_to_disk()  # 此 ROM 沒有 save 媒體


def test_determinism_same_rom_and_config(rom_path):
    first = Emulator.from_rom(rom_path)
    second = Emulator.from_rom(rom_path)
    assert first.cpu.state() == second.cpu.state()
    for kind in (
        MemoryRegionKind.EWRAM,
        MemoryRegionKind.IWRAM,
        MemoryRegionKind.PALETTE,
        MemoryRegionKind.VRAM,
        MemoryRegionKind.OAM,
        MemoryRegionKind.SRAM,
    ):
        assert first.memory.read_region(kind) == second.memory.read_region(kind)

    first.memory.force_write(0x02000100, 1)
    first.reset(seed=7)
    second.reset(seed=7)
    assert first.cpu.state() == second.cpu.state()
    assert first.memory.read_region(MemoryRegionKind.EWRAM) == second.memory.read_region(
        MemoryRegionKind.EWRAM
    )


def test_real_test_rom_boots(hello_rom_path):
    emu = Emulator.from_rom(hello_rom_path)
    assert emu.rom_header.title == "GBA Tests"
    assert emu.rom_header.game_code == "1337"
    assert emu.cpu.state().regs[15] == 0x08000000
    assert emu.memory.read_u8(0x02000000) == hello_rom_path.read_bytes()[0]


def test_checksum_failure_does_not_abort_boot(tmp_path):
    rom = build_rom(checksum_delta=1)
    path = tmp_path / "bad_checksum.gba"
    path.write_bytes(rom)
    emu = Emulator.from_rom(path)
    assert emu.rom_header.complement_check_ok is False
    assert emu.cpu.state().regs[15] == 0x08000000
