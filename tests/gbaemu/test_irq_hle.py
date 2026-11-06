"""Phase 3：IRQ 2-cycle pipeline 延遲與 HLE BIOS IRQ stub（GBATEK 10/16 章）。"""

from __future__ import annotations

from gbaemu import Button, Emulator
from gbaemu.api_types import BootMode
from gbaemu.emulator import Emulator as Emu

from .cpu_helpers import arm_words, program_rom

NOP = 0xE1A00000
B_SELF = 0xEAFFFFFE
BX_LR = 0xE12FFF1E

CPSR_I = 1 << 7
HANDLER = 0x0800000C


def _hle_emu(tmp_path, code: bytes) -> Emu:
    """HLE 啟動（有合法的 IRQ/SVC bank SP）＋自訂程式碼。"""

    path = tmp_path / "irq.gba"
    path.write_bytes(program_rom(code))
    return Emulator.from_rom(path)


def _enable_irq(emu: Emu) -> None:
    emu._cpu.regs.cpsr &= ~CPSR_I
    emu.memory.write_u16(0x04000200, 0x0001)  # IE: VBlank
    emu.memory.write_u16(0x04000202, 0x0001)  # IF
    emu.memory.write_u16(0x04000208, 0x0001)  # IME


def test_pipeline_delay_is_two_cycles(tmp_path):
    emu = _hle_emu(tmp_path, arm_words(NOP, NOP, NOP, B_SELF))
    _enable_irq(emu)

    emu.step_cycles(1)  # 第 1 條：arm 延遲
    assert emu.cpu.state().mode == 0x1F
    emu.step_cycles(1)  # 第 2 條：倒數 1
    assert emu.cpu.state().mode == 0x1F
    emu.step_cycles(1)  # 第 3 條：倒數到 0 → 進場
    assert emu.cpu.state().mode == 0x12


def test_hle_stub_saves_registers_and_jumps_to_handler(tmp_path):
    emu = _hle_emu(tmp_path, arm_words(NOP, NOP, B_SELF))
    _enable_irq(emu)
    emu.memory.write_u32(0x03007FFC, HANDLER)
    for index in range(4):
        emu._cpu.regs.r[index] = 0x1000 + index
    emu._cpu.regs.r[12] = 0x1200

    emu.step_cycles(4)  # 2 條 NOP + B .（延遲到點）

    state = emu.cpu.state()
    assert state.mode == 0x12
    assert state.regs[15] == HANDLER  # [03007FFC]
    assert state.regs[14] == 0x138  # BIOS return stub
    assert state.regs[13] == 0x03007FA0 - 24  # IRQ stack

    sp = state.regs[13]
    assert emu.memory.read_u32(sp + 0) == 0x1000
    assert emu.memory.read_u32(sp + 4) == 0x1001
    assert emu.memory.read_u32(sp + 12) == 0x1003
    assert emu.memory.read_u32(sp + 16) == 0x1200
    assert emu.memory.read_u32(sp + 20) == 0x0800000C  # 被中斷的下一條 + 4


def test_hle_stub_return_restores_state(tmp_path):
    # 0x08000000: NOP, NOP, B .（0x08）；0x0800000C: BX LR（handler）
    emu = _hle_emu(tmp_path, arm_words(NOP, NOP, B_SELF, BX_LR))
    _enable_irq(emu)
    emu.memory.write_u32(0x03007FFC, HANDLER)
    emu._cpu.regs.r[0] = 0xDEADBEEF

    emu.step_cycles(4)  # 進入 IRQ（PC=handler）
    assert emu.cpu.state().mode == 0x12
    assert emu.cpu.read_register("r15") == HANDLER

    emu.step_cycles(2)  # BX LR（2 cycles）→ PC=0x138
    assert emu.cpu.read_register("r15") == 0x138
    assert emu.cpu.state().mode == 0x12

    emu.step_cycles(4)  # BIOS return stub：LDM + SUBS PC,LR,#4（3 cycles）
    state = emu.cpu.state()
    assert state.mode == 0x1F
    assert state.regs[15] == 0x08000008  # 回到 B .
    assert state.regs[13] == 0x03007F00  # 回到 System bank 的 SP
    assert state.regs[0] == 0xDEADBEEF
    assert not (state.cpsr & CPSR_I)


def test_real_bios_mode_skips_hle_stub(tmp_path):
    # REQUIRE_BIOS：CPU 停在 reset vector，IRQ 進場後不套 HLE stub。
    path = tmp_path / "bios.gba"
    path.write_bytes(program_rom(arm_words(B_SELF)))
    bios = tmp_path / "bios.bin"
    bios.write_bytes(bytes([0x00, 0x00, 0x00, 0xEA]) + bytes(0x4000 - 4))
    from gbaemu import EmulatorConfig

    emu = Emulator.from_rom(
        path,
        config=EmulatorConfig(boot_mode=BootMode.REQUIRE_BIOS, bios_path=bios),
    )
    _enable_irq(emu)
    emu.step_cycles(2)  # BIOS B 0x08（2 cycles）→ arm 延遲
    emu.step_cycles(2)  # 兩條 zero opcode（延遲到點）→ 進 IRQ vector
    state = emu.cpu.state()
    assert state.mode == 0x12
    assert state.regs[15] == 0x18  # 直接進 IRQ vector，不跳 handler
    assert state.regs[14] == 0x00000014
