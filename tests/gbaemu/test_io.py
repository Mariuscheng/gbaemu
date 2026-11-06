"""Phase 2：I/O 暫存器語意（GBATEK: GBA I/O Map）。"""

from __future__ import annotations

import pytest

from gbaemu import BootMode, EmulatorConfig
from gbaemu.bus.address_bus import AddressBus
from gbaemu.bus.io import IoRegisters
from gbaemu.memory.cartridge import RomCartridge

from .cpu_helpers import arm_words, program_rom


def _bus() -> AddressBus:
    return AddressBus(RomCartridge(bytes(0x400)))


def test_dispcnt_read_write_16_and_8bit():
    bus = _bus()
    bus.write_u16(0x04000000, 0x0403)
    assert bus.read_u16(0x04000000) == 0x0403
    bus.write_u8(0x04000001, 0x00)  # 只改高位 byte
    assert bus.read_u16(0x04000000) == 0x0003
    assert bus.read_u32(0x04000000) & 0xFFFF == 0x0003


def test_waitcnt_roundtrip_and_costs():
    bus = _bus()
    assert bus.waitcnt == 0
    bus.write_u16(0x04000204, 0x4317)
    assert bus.waitcnt == 0x4317
    assert bus.read_u16(0x04000204) == 0x4317


def test_ime_ie_if_latch_and_acknowledge():
    bus = _bus()
    bus.write_u16(0x04000208, 1)  # IME
    bus.write_u16(0x04000200, 0x0003)  # IE
    assert bus.read_u16(0x04000200) == 0x0003

    bus.io_registers.request_irq(0x0001)
    bus.io_registers.request_irq(0x0002)
    assert bus.read_u16(0x04000202) == 0x0003

    bus.write_u16(0x04000202, 0x0001)  # 寫 1 清除 bit0
    assert bus.read_u16(0x04000202) == 0x0002

    bus.write_u8(0x04000202, 0x02)  # byte 寫 1 清除 bit1
    assert bus.read_u16(0x04000202) == 0x0000


def test_vcount_is_zero_without_ppu():
    bus = _bus()
    assert bus.read_u16(0x04000006) == 0
    bus.write_u16(0x04000006, 0x1234)
    assert bus.read_u16(0x04000006) == 0  # 唯讀


def test_keyinput_active_low():
    class Keypad:
        keyinput_mask = 0x03FF

    bus = AddressBus(RomCartridge(bytes(0x400)), keypad=Keypad())
    assert bus.read_u16(0x04000130) == 0x03FF
    Keypad.keyinput_mask = 0x03FF & ~(1 << 0) & ~(1 << 3)  # A + START
    assert bus.read_u16(0x04000130) == 0x03FF & ~0x9
    assert bus.read_u8(0x04000130) == 0xF6


def test_input_port_maps_buttons_to_keyinput(tmp_path):
    from gbaemu import Button, Emulator

    path = tmp_path / "io.gba"
    path.write_bytes(program_rom(arm_words(0xEAFFFFFE)))
    emu = Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )

    assert emu.memory.read_u16(0x04000130) == 0x03FF
    emu.input.press(Button.A, Button.START)
    assert emu.memory.read_u16(0x04000130) == 0x03FF & ~0x9
    emu.input.clear()
    assert emu.memory.read_u16(0x04000130) == 0x03FF


def test_postflg_and_keycnt_storage():
    bus = _bus()
    bus.write_u16(0x04000300, 0x0001)
    assert bus.read_u16(0x04000300) == 0x0001
    bus.write_u16(0x04000132, 0x4307)
    assert bus.read_u16(0x04000132) == 0x4307


def test_io_reset_clears_registers():
    io = IoRegisters()
    io.write16(0x000, 0x0403)
    io.write16(0x200, 0x0003)
    io.request_irq(0x0001)
    io.write16(0x208, 1)
    io.reset()
    assert io.read16(0x000) == 0
    assert io.read16(0x200) == 0
    assert io.read16(0x202) == 0
    assert io.read16(0x208) == 0


def test_io_debug_write_sets_if_bits():
    io = IoRegisters()
    io.debug_write(0x202, 2, 0x0003)
    assert io.read16(0x202) == 0x0003


def test_io_rejects_unknown_width():
    io = IoRegisters()
    with pytest.raises(ValueError):
        io.read(0, 3)
    with pytest.raises(ValueError):
        io.write(0, 3, 0)

def test_hardware_waitcnt_write_changes_timed_cycles(tmp_path):
    from gbaemu import Emulator, TimingMode

    path = tmp_path / "waitcnt.gba"
    path.write_bytes(program_rom(arm_words(0xE1A00000, 0xEAFFFFFE)))
    emu = Emulator.from_rom(
        path,
        config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY, timing=TimingMode.TIMED),
    )
    assert emu._cpu.peek_cycles() == 8  # 預設 N32 = 5 + 3

    emu._bus.write_u16(0x04000204, (1 << 2) | (1 << 4))  # WS0 first=4、second=2
    assert emu._cpu.peek_cycles() == 6

def test_keycnt_irq_condition_and(tmp_path):
    from gbaemu import Button, Emulator

    path = tmp_path / "keyirq.gba"
    path.write_bytes(program_rom(arm_words(0xE1A00000, 0xEAFFFFFE)))
    emu = Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )
    emu.memory.write_u16(0x04000200, 0x1000)  # IE: keypad
    emu.memory.write_u16(0x04000208, 0x0001)  # IME
    emu.memory.write_u16(0x04000132, 0xC001)  # 啟用 IRQ、AND 模式、選 A

    emu.input.press(Button.A)
    emu.step_cycles(1)
    assert emu.memory.read_u16(0x04000202) & 0x1000


def test_keycnt_irq_or_condition(tmp_path):
    from gbaemu import Button, Emulator

    path = tmp_path / "keyirq2.gba"
    path.write_bytes(program_rom(arm_words(0xE1A00000, 0xEAFFFFFE)))
    emu = Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )
    emu.memory.write_u16(0x04000200, 0x1000)
    emu.memory.write_u16(0x04000208, 0x0001)
    emu.memory.write_u16(0x04000132, 0x4009)  # 啟用 IRQ、OR 模式、A 或 START

    emu.input.press(Button.START)
    emu.step_cycles(1)
    assert emu.memory.read_u16(0x04000202) & 0x1000
