"""Phase 1 驗收：ARM 指令語意（GBATEK: ARM 32bit Instruction Set）。

每個 case 用最小 ROM 驅動 ``Emulator.step_cycles()``，只驗證指令語意、旗標與
記憶體副作用，不依賴 PPU／DMA／timer（Phase 2/3）。
"""

from __future__ import annotations

from gbaemu import BootMode, EmulatorConfig

from .cpu_helpers import arm_words, make_emu

CPSR_N = 1 << 31
CPSR_Z = 1 << 30
CPSR_C = 1 << 29
CPSR_V = 1 << 28


def _run(tmp_path, *words, cycles=None, thumb=False):
    emu = make_emu(tmp_path, arm_words(*words), thumb=thumb)
    emu.step_cycles(200 if cycles is None else cycles)
    return emu


def test_adds_cycle_cost_is_not_multiply_long(tmp_path):
    """ADDS 的 bit23=1 不可被乘加長指令的週期解碼誤判（回歸）。"""
    emu = make_emu(
        tmp_path,
        arm_words(0xE3E00000, 0xE3A01001, 0xE0902001, 0xEAFFFFFE),
    )
    emu.step_cycles(1)  # MVN r0,#0
    emu.step_cycles(1)  # MOV r1,#1
    result = emu.step_cycles(2)  # ADDS r2,r0,r1：1S
    assert result.cycles_executed == 1
    assert emu.cpu.read_register("r2") == 0


def test_data_processing_and_flags(tmp_path):
    emu = _run(
        tmp_path,
        0xE3A00005,  # MOV r0,#5
        0xE3A01003,  # MOV r1,#3
        0xE0502001,  # SUBS r2,r0,r1
        0xEAFFFFFE,  # B .
    )
    assert emu.cpu.read_register("r2") == 2
    cpsr = emu.cpu.read_register("cpsr")
    assert not cpsr & CPSR_N
    assert not cpsr & CPSR_Z
    assert cpsr & CPSR_C  # 無借位 → C=1
    assert not cpsr & CPSR_V


def test_zero_and_negative_flags(tmp_path):
    emu = _run(
        tmp_path,
        0xE3A00000,  # MOV r0,#0
        0xE3A01000,  # MOV r1,#0
        0xE0502001,  # SUBS r2,r0,r1 → Z=1, C=1
        0xEAFFFFFE,  # B .
    )
    cpsr = emu.cpu.read_register("cpsr")
    assert cpsr & CPSR_Z
    assert cpsr & CPSR_C
    assert not cpsr & CPSR_N

    emu = _run(
        tmp_path,
        0xE3A00001,  # MOV r0,#1
        0xE3500002,  # CMP r0,#2 → 1-2 = -1 → N=1, C=0（借位）
        0xEAFFFFFE,
    )
    cpsr = emu.cpu.read_register("cpsr")
    assert cpsr & CPSR_N
    assert not cpsr & CPSR_C
    assert not cpsr & CPSR_Z


def test_ldr_str_and_unaligned_rotation(tmp_path):
    emu = _run(
        tmp_path,
        0xE3A03402,  # MOV r3,#0x02000000
        0xE3A00078,  # MOV r0,#0x78
        0xE5830000,  # STR r0,[r3]
        0xE5930000,  # LDR r0,[r3]
        0xE5931001,  # LDR r1,[r3,#1]（未對齊 → ROR 8）
        0xEAFFFFFE,
    )
    assert emu.memory.read_u32(0x02000000) == 0x78
    assert emu.cpu.read_register("r0") == 0x78
    assert emu.cpu.read_register("r1") == 0x78000000


def test_block_transfer_stack(tmp_path):
    emu = _run(
        tmp_path,
        0xE3A00011,  # MOV r0,#0x11
        0xE3A01022,  # MOV r1,#0x22
        0xE92D0003,  # STMFD sp!,{r0,r1}
        0xE8BD000C,  # LDMFD sp!,{r2,r3}
        0xEAFFFFFE,
    )
    assert emu.cpu.read_register("r2") == 0x11
    assert emu.cpu.read_register("r3") == 0x22
    assert emu.cpu.read_register("r13") == 0x03007F00
    assert emu.memory.read_u32(0x03007EF8) == 0x11


def test_multiply(tmp_path):
    emu = _run(
        tmp_path,
        0xE3A00007,  # MOV r0,#7
        0xE3A01006,  # MOV r1,#6
        0xE0020190,  # MUL r2,r0,r1
        0xEAFFFFFE,
    )
    assert emu.cpu.read_register("r2") == 42


def test_branch_and_link(tmp_path):
    emu = _run(
        tmp_path,
        0xEB000000,  # BL +0（跳過下一個 word，目標 = pc+8）
        0xEAFFFFFE,  # B .（不會執行）
        0xE3A00001,  # MOV r0,#1
        0xEAFFFFFE,  # B .
    )
    assert emu.cpu.read_register("r0") == 1
    assert emu.cpu.read_register("r14") == 0x08000004


def test_condition_code_not_taken(tmp_path):
    emu = _run(
        tmp_path,
        0xE3A00000,  # MOV r0,#0（Z=0）
        0x03A01001,  # MOVEQ r1,#1（不執行）
        0x13A01002,  # MOVNE r1,#2（執行）
        0xEAFFFFFE,
    )
    assert emu.cpu.read_register("r1") == 2


def test_pc_read_pipeline_offset(tmp_path):
    emu = _run(
        tmp_path,
        0xE59F0000,  # LDR r0,[pc]  → 讀 0x08000008
        0xEAFFFFFE,  # B .
        0xDEADBEEF,  # 常數
    )
    assert emu.cpu.read_register("r0") == 0xDEADBEEF


def test_step_result_matches_executed_instructions(tmp_path):
    emu = make_emu(tmp_path, arm_words(0xE1A00000, 0xE1A00000, 0xE1A00000, 0xEAFFFFFE))
    result = emu.step_cycles(3)
    assert result.cycles_executed == 3
    assert result.cycles_remaining == 0
    assert result.halted is False
    assert result.breakpoint_hit is None
    assert emu.cycles == 3


def test_test_rom_only_config_keeps_arm_state(tmp_path):
    emu = make_emu(tmp_path, arm_words(0xEAFFFFFE))
    state = emu.cpu.state()
    assert state.mode == 0x1F
    assert state.thumb is False
    assert EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY).boot_mode is BootMode.TEST_ROM_ONLY


def test_register_shift_by_zero_is_noop(tmp_path):
    """暫存器移位量 0：值與 C 都不變（只有立即數編碼的 0 才代表 32）。

    對應 ARMWrestler ARM ALU「MOV」頁的 ASR r0 測試。
    """

    emu = _run(
        tmp_path,
        0xE3A04001,  # MOV r4,#1
        0xE3A02000,  # MOV r2,#0
        0xE1540002,  # CMP r4,r2 → C=1
        0xE1B03254,  # MOVS r3,r4,ASR r2（r2=0）→ r3=1、C 不變
        0xEAFFFFFE,  # B .
    )
    assert emu.cpu.read_register("r3") == 1
    cpsr = emu.cpu.read_register("cpsr")
    assert cpsr & CPSR_C
    assert not cpsr & CPSR_Z


def test_register_shift_reads_pc_plus_12(tmp_path):
    """暫存器移位時 R15 讀到 PC+12（ARM7TDMI；立即數移位是 PC+8）。

    對應 ARMWrestler ARM ALU「MOV」頁的 MOVS r4,r15,LSL r3 測試。
    """

    emu = _run(
        tmp_path,
        0xE3A03000,  # MOV r3,#0（0x08000000）
        0xE1B0431F,  # MOVS r4,r15,LSL r3（0x08000004）→ r4 = 0x08000010
        0xEAFFFFFE,  # B .
    )
    assert emu.cpu.read_register("r4") == 0x08000010


def test_ldr_register_offset_rrx(tmp_path):
    """LDR 的暫存器 offset：ROR #0 編碼是 RRX（C 進 bit31）。

    對應 ARMWrestler ARM LOAD TESTS PART 1 的 +R / -R / ]+R 頁。
    """

    emu = make_emu(
        tmp_path,
        arm_words(
            0xE3A00402,  # MOV r0,#0x02000000
            0xE2800004,  # ADD r0,r0,#4
            0xE3E02003,  # MVN r2,#3          → r2 = 0xFFFFFFFC
            0xE0924002,  # ADDS r4,r2,r2      → C=1
            0xE7901062,  # LDR r1,[r0,r2,rrx] → offset 0xFFFFFFFE
            0xEAFFFFFE,  # B .
        ),
    )
    emu.memory.write_u32(0x02000000, 0x11223344)
    emu.step_cycles(200)
    # addr = 0x02000004 - 2 = 0x02000002 → 對齊字 ROR 16
    assert emu.cpu.read_register("r1") == 0x33441122
