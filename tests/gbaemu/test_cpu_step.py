"""Phase 1 驗收：``step_cycles()``、``StepResult``、breakpoint 與確定性。"""

from __future__ import annotations

import pytest

from gbaemu.errors import GbaEmuError

from .cpu_helpers import arm_words, make_emu

NOP = 0xE1A00000
B_SELF = 0xEAFFFFFE


def _emu(tmp_path, count: int = 4):
    return make_emu(tmp_path, arm_words(*([NOP] * count + [B_SELF])))


def test_step_cycles_zero(tmp_path):
    emu = _emu(tmp_path)
    result = emu.step_cycles(0)
    assert result.cycles_executed == 0
    assert result.cycles_remaining == 0
    assert result.halted is False
    assert result.breakpoint_hit is None
    assert result.events == ()
    assert emu.cycles == 0


def test_step_cycles_accumulates_and_reports(tmp_path):
    emu = _emu(tmp_path)
    first = emu.step_cycles(3)
    assert first.cycles_executed == 3
    assert first.cycles_remaining == 0
    assert emu.cycles == 3
    assert emu.cpu.read_register("r15") == 0x0800000C

    second = emu.step_cycles(2)  # B . 一次要 2 cycles，放不下
    assert second.cycles_executed == 1
    assert second.cycles_remaining == 1
    assert emu.cycles == 4
    assert emu.cpu.read_register("r15") == 0x08000010  # 第 4 條 NOP 之後


def test_step_cycles_rejects_invalid_arguments(tmp_path):
    emu = _emu(tmp_path)
    with pytest.raises(ValueError):
        emu.step_cycles(-1)
    with pytest.raises(ValueError):
        emu.step_cycles(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        emu.step_cycles(1.5)  # type: ignore[arg-type]
    with pytest.raises(GbaEmuError):
        emu.close()
        emu.step_cycles(1)


def test_breakpoint_stops_before_execution(tmp_path):
    emu = _emu(tmp_path, count=4)
    breakpoint_id = emu.cpu.set_breakpoint(0x08000008)

    result = emu.step_cycles(10)
    assert result.breakpoint_hit == breakpoint_id
    assert result.cycles_executed == 2
    assert result.cycles_remaining == 8
    assert emu.cpu.read_register("r15") == 0x08000008

    emu.cpu.clear_breakpoint(breakpoint_id)
    resumed = emu.step_cycles(1)
    assert resumed.breakpoint_hit is None
    assert resumed.cycles_executed == 1
    assert emu.cpu.read_register("r15") == 0x0800000C


def test_breakpoint_with_thumb_flag(tmp_path):
    emu = make_emu(tmp_path, arm_words(NOP, B_SELF))
    generic = emu.cpu.set_breakpoint(0x08000004)
    thumb = emu.cpu.set_breakpoint(0x08000004, thumb=True)

    result = emu.step_cycles(4)
    assert result.breakpoint_hit == generic  # ARM state 命中 generic
    emu.cpu.clear_breakpoint(generic)
    emu._cpu.regs.cpsr |= 0x20  # 切到 Thumb
    emu._cpu.regs.pc = 0x08000004
    result = emu.step_cycles(2)
    assert result.breakpoint_hit == thumb


def test_halted_cpu_burns_cycles(tmp_path):
    emu = _emu(tmp_path)
    emu._cpu.halted = True
    result = emu.step_cycles(4)
    assert result.cycles_executed == 4
    assert result.halted is True
    assert emu.cycles == 4
    assert emu.cpu.read_register("r15") == 0x08000000


def test_determinism_same_rom_and_config(tmp_path):
    first = _emu(tmp_path, count=8)
    second = _emu(tmp_path, count=8)
    first.step_cycles(30)
    second.step_cycles(30)
    assert first.cpu.state() == second.cpu.state()
    assert first.cycles == second.cycles == 30
    for kind in ("EWRAM", "IWRAM", "PALETTE", "VRAM", "OAM", "SRAM"):
        from gbaemu.api_types import MemoryRegionKind

        region = MemoryRegionKind[kind]
        assert first.memory.read_region(region) == second.memory.read_region(region)


def test_reset_restores_cpu_state(tmp_path):
    emu = _emu(tmp_path, count=2)
    emu.step_cycles(2)
    assert emu.cycles == 2
    emu.reset()
    assert emu.cycles == 0
    assert emu.cpu.read_register("r15") == 0x08000000
    assert emu.cpu.read_register("r0") == 0
