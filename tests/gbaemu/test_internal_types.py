"""內部狀態 dataclass 與小工具的契約。"""

from __future__ import annotations

import pytest

from gbaemu.cpu.registers import (
    MODE_IRQ,
    Arm7CoreState,
    is_thumb,
    mode_of,
    new_core_state,
)
from gbaemu.debug.breakpoints import BreakpointTable
from gbaemu.devices.dma import DmaChannelState
from gbaemu.devices.interrupts import InterruptState
from gbaemu.devices.keypad import KeypadState
from gbaemu.devices.timers import TimerState
from gbaemu.errors import BreakpointError
from gbaemu.video.framebuffer import FRAME_SIZE, Framebuffer
from gbaemu.video.ppu import PpuState


def test_core_state_defaults_and_helpers():
    core = new_core_state()
    assert core.regs == [0] * 16
    assert core.cpsr == 0x1F
    assert core.banked == {}
    assert core.pipeline == []
    assert core.halted is False
    assert mode_of(0x1F | 0x80) == 0x1F
    assert is_thumb(0x20) is True
    assert is_thumb(0x1F) is False
    core.regs[13] = 0x03007F00
    assert isinstance(core, Arm7CoreState)


def test_device_state_fields_are_mutable():
    dma = DmaChannelState(
        channel=3,
        source=0x08000000,
        dest=0x02000000,
        word_count=16,
        control=0x8400,
        active=True,
        irq_enable=False,
    )
    assert dma.channel == 3
    dma.active = False

    timer = TimerState(
        index=0,
        counter=0xFFFF,
        reload=0x1234,
        control=0xC0,
        prescaler=1024,
        cascade=False,
        irq_enable=True,
        ticks_pending=0,
    )
    assert timer.reload == 0x1234

    interrupt = InterruptState(ime=1, ie=0x0001, _if=0, irqs_pending_mask=0)
    assert interrupt._if == 0
    interrupt._if = 1

    keypad = KeypadState(
        keyinput=0x03FF,
        keycnt=0,
        keycnt_irq_enable=False,
        keycnt_condition_all=True,
    )
    assert keypad.keyinput == 0x03FF

    ppu = PpuState(
        dispstat=0,
        vcount=0,
        dispcnt=0x0080,
        scanline=0,
        in_vblank=False,
        in_hblank=False,
        frame=0,
    )
    assert ppu.scanline == 0
    ppu.scanline = 160


def test_breakpoint_table_prefers_exact_thumb_match():
    table = BreakpointTable()
    generic = table.set(0x08000000)
    thumb = table.set(0x08000000, thumb=True)
    arm = table.set(0x08000000, thumb=False)

    assert table.match(0x08000000, True).id == thumb
    assert table.match(0x08000000, False).id == arm
    assert table.match(0x08000004, True) is None

    table.clear(generic)
    assert len(table) == 2
    assert [item.id for item in table.items] == [thumb, arm]
    with pytest.raises(BreakpointError):
        table.clear(generic)


def test_framebuffer_contract():
    framebuffer = Framebuffer()
    assert len(framebuffer.read_frame()) == FRAME_SIZE
    assert framebuffer.read_scanline(159) == bytes(240 * 3)
    with pytest.raises(ValueError):
        framebuffer.read_scanline(-1)
    with pytest.raises(ValueError):
        framebuffer.read_scanline(160)

    data = bytes([0x11, 0x22, 0x33]) * (240 * 160)
    framebuffer.write_rgb888(data)
    assert framebuffer.read_scanline(0)[:3] == b"\x11\x22\x33"
    with pytest.raises(ValueError):
        framebuffer.write_rgb888(b"\x00")


def test_arm7_core_state_has_slots():
    core = new_core_state()
    assert not hasattr(core, "__dict__")
    with pytest.raises(AttributeError):
        core.unknown_field = 1  # type: ignore[attr-defined]
