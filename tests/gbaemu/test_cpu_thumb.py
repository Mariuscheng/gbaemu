"""Phase 1 驗收：THUMB 指令語意（GBATEK: ARM 16bit Instruction Set）。"""

from __future__ import annotations

from .cpu_helpers import make_emu, thumb_words

CPSR_N = 1 << 31
CPSR_Z = 1 << 30
CPSR_C = 1 << 29


def _run(tmp_path, *words):
    emu = make_emu(tmp_path, thumb_words(*words), thumb=True)
    emu.step_cycles(200)
    return emu


def test_thumb_alu_immediate(tmp_path):
    emu = _run(
        tmp_path,
        0x2005,  # MOVS r0,#5
        0x2103,  # MOVS r1,#3
        0x1842,  # ADDS r2,r0,r1
        0xE7FE,  # B .
    )
    assert emu.cpu.read_register("r0") == 5
    assert emu.cpu.read_register("r1") == 3
    assert emu.cpu.read_register("r2") == 8
    assert emu.cpu.state().thumb is True


def test_thumb_sub_flags(tmp_path):
    emu = _run(
        tmp_path,
        0x2000,  # MOVS r0,#0
        0x2101,  # MOVS r1,#1
        0x1A42,  # SUBS r2,r0,r1 → N=1, C=0
        0xE7FE,
    )
    cpsr = emu.cpu.read_register("cpsr")
    assert cpsr & CPSR_N
    assert not cpsr & CPSR_C
    assert not cpsr & CPSR_Z


def test_thumb_ldr_str_with_register_setup(tmp_path):
    emu = make_emu(
        tmp_path,
        thumb_words(
            0x2007,  # MOVS r0,#7
            0x6018,  # STR r0,[r3]
            0x6819,  # LDR r1,[r3]
            0xE7FE,
        ),
        thumb=True,
    )
    emu._cpu.regs.r[3] = 0x02000000
    emu.step_cycles(200)
    assert emu.memory.read_u32(0x02000000) == 7
    assert emu.cpu.read_register("r1") == 7


def test_thumb_push_pop(tmp_path):
    emu = make_emu(
        tmp_path,
        thumb_words(
            0x2011,  # MOVS r0,#0x11
            0x2112,  # MOVS r1,#0x12
            0xB403,  # PUSH {r0,r1}
            0xBC0C,  # POP {r2,r3}
            0xE7FE,
        ),
        thumb=True,
    )
    emu.step_cycles(200)
    assert emu.cpu.read_register("r2") == 0x11
    assert emu.cpu.read_register("r3") == 0x12
    assert emu.cpu.read_register("r13") == 0x03007F00


def test_thumb_conditional_branch_skips(tmp_path):
    emu = _run(
        tmp_path,
        0x2000,  # MOVS r0,#0 → Z=1
        0xD000,  # BEQ +0（PC+4 → 跳過下一條）
        0x2101,  # MOVS r1,#1（不執行）
        0x2102,  # MOVS r1,#2
        0xE7FE,
    )
    assert emu.cpu.read_register("r1") == 2
