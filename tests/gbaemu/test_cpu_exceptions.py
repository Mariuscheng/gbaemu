"""Phase 1 驗收：例外入口（SWI／IRQ／UND）與 banking。"""

from __future__ import annotations

import pytest

from gbaemu import BootMode, EmulatorConfig
from gbaemu.errors import HleUnsupportedSwiError

from .cpu_helpers import arm_words, make_emu, thumb_words

MODE_IRQ = 0x12
MODE_SVC = 0x13
MODE_UND = 0x1B
CPSR_I = 1 << 7


def _lenient(tmp_path, code: bytes, thumb: bool) -> "object":
    from gbaemu import Emulator

    from .cpu_helpers import program_rom

    path = tmp_path / "program.gba"
    path.write_bytes(program_rom(code))
    emu = Emulator.from_rom(
        path,
        config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY, hle_strict=False),
    )
    if thumb:
        emu._cpu.regs.cpsr |= 0x20
        emu._cpu.regs.pc = 0x08000000
    return emu


def test_swi_enters_svc_and_raises_unsupported(tmp_path):
    emu = make_emu(tmp_path, arm_words(0xEF2B0000, 0xEAFFFFFE))  # SWI 0x2B（無效）
    with pytest.raises(HleUnsupportedSwiError):
        emu.step_cycles(10)

    state = emu.cpu.state()
    assert state.mode == MODE_SVC
    assert state.cpsr & CPSR_I
    assert state.regs[15] == 0x08  # SVC vector
    assert state.regs[14] == 0x08000004  # 下一個 ARM 指令
    assert state.spsr & 0x1F == 0x1F  # 進場前的 System mode


def test_swi_lenient_returns_to_next_instruction(tmp_path):
    emu = _lenient(tmp_path, arm_words(0xEF060000, 0xE3A00001, 0xEAFFFFFE), thumb=False)
    emu.step_cycles(4)
    assert emu.cpu.state().mode == 0x1F
    assert emu.cpu.read_register("r0") == 1
    assert emu.cpu.read_register("r15") == 0x08000008


def test_thumb_swi_lr_is_next_halfword(tmp_path):
    emu = make_emu(tmp_path, thumb_words(0xDF2B, 0xE7FE), thumb=True)
    with pytest.raises(HleUnsupportedSwiError):
        emu.step_cycles(10)
    assert emu.cpu.read_register("r14") == 0x08000002


def test_irq_entry(tmp_path):
    emu = make_emu(tmp_path, arm_words(0xE1A00000, 0xE1A00000, 0xEAFFFFFE))
    emu._cpu.regs.cpsr &= ~CPSR_I
    emu.memory.write_u8(0x04000200, 0x01)  # IE
    emu.memory.write_u8(0x04000202, 0x01)  # IF
    emu.memory.write_u8(0x04000208, 0x01)  # IME

    emu.step_cycles(1)  # arm 2-cycle pipeline 延遲
    assert emu.cpu.state().mode == 0x1F
    emu.step_cycles(3)  # NOP + B . → 延遲到點，進 IRQ
    state = emu.cpu.state()
    assert state.mode == MODE_IRQ
    # HLE BIOS stub：LR=0x138、PC=[03007FFC]（預設 0）
    assert state.regs[14] == 0x138
    assert state.regs[15] == 0
    assert state.spsr & 0x1F == 0x1F


def test_irq_masked_by_cpsr_i(tmp_path):
    emu = make_emu(tmp_path, arm_words(0xE1A00000, 0xEAFFFFFE))
    emu._cpu.regs.cpsr |= CPSR_I
    emu.memory.write_u8(0x04000200, 0x01)
    emu.memory.write_u8(0x04000202, 0x01)
    emu.memory.write_u8(0x04000208, 0x01)

    emu.step_cycles(10)
    assert emu.cpu.state().mode == 0x1F


def test_undefined_instruction_enters_und_mode(tmp_path):
    emu = make_emu(tmp_path, arm_words(0xE7F000F0, 0xEAFFFFFE))
    emu.step_cycles(4)  # 未定義指令的 fetch/例外成本為 4 cycles
    state = emu.cpu.state()
    assert state.mode == MODE_UND
    assert state.regs[15] == 0x04
    assert state.regs[14] == 0x08000004


def test_banked_stack_pointer_switches_with_mode(tmp_path):
    emu = make_emu(tmp_path, arm_words(0xEF2B0000, 0xEAFFFFFE))
    assert emu.cpu.read_register("r13") == 0x03007F00
    with pytest.raises(HleUnsupportedSwiError):
        emu.step_cycles(10)
    assert emu._cpu.core.bank_mode == MODE_SVC
    assert emu.cpu.read_register("r13") == 0  # SVC bank 尚未初始化
    assert emu._cpu.core.banked[0x1F] == (0x03007F00, 0)  # System bank 已保存
