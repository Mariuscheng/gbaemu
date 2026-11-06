"""Phase 2 前置：timing 基礎（規格 §3.6）。

涵蓋：時鐘／frame 常數、``access_cycles`` 的區域成本與 WAITCNT、ARM／THUMB
每條指令的 cycle 數（FUNCTIONAL／TIMED）、``step_cycles`` 不超出預算。
"""

from __future__ import annotations

import pytest

from gbaemu import BootMode, EmulatorConfig, TimingMode
from gbaemu.bus.access import access_cycles, waitcnt_from_io
from gbaemu.timing import (
    PPU_FRAME_CYCLES,
    PPU_HBLANK_START,
    PPU_LINE_CYCLES,
    PPU_TOTAL_LINES,
    PPU_VBLANK_START,
    PPU_VISIBLE_LINES,
    SYSTEM_CLOCK,
)

from .cpu_helpers import arm_words, program_rom, thumb_words


def _emu(tmp_path, code, *, thumb=False, timing=TimingMode.FUNCTIONAL):
    from gbaemu import Emulator

    path = tmp_path / "timing.gba"
    path.write_bytes(program_rom(code))
    emu = Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY, timing=timing)
    )
    if thumb:
        emu._cpu.regs.cpsr |= 0x20
        emu._cpu.regs.pc = 0x08000000
    return emu


def test_clock_and_frame_constants():
    assert SYSTEM_CLOCK == 16 * 1024 * 1024
    assert PPU_LINE_CYCLES == 1232
    assert PPU_VISIBLE_LINES == 160
    assert PPU_TOTAL_LINES == 228
    assert PPU_FRAME_CYCLES == 228 * 1232 == 280_896
    assert PPU_VBLANK_START == 160 * 1232 == 197_120
    assert PPU_HBLANK_START == 1006
    assert PPU_FRAME_CYCLES == 280896


def test_access_cycles_regions():
    assert access_cycles(0x03000000, 4, False) == 1  # IWRAM
    assert access_cycles(0x02000000, 2, False) == 3  # EWRAM 16-bit
    assert access_cycles(0x02000000, 4, False) == 6  # EWRAM 32-bit
    assert access_cycles(0x05000000, 2, False) == 1  # Palette
    assert access_cycles(0x06000000, 4, False) == 2  # VRAM 32-bit
    assert access_cycles(0x04000000, 2, False) == 1  # I/O
    assert access_cycles(0x00000000, 4, False) == 1  # BIOS


def test_access_cycles_rom_waitcnt_default_and_override():
    # WAITCNT=0：WS0 first=5、second=3；32-bit N+S=8
    assert access_cycles(0x08000000, 2, False, 0x0000) == 5
    assert access_cycles(0x08000002, 2, True, 0x0000) == 3
    assert access_cycles(0x08000000, 4, False, 0x0000) == 8
    assert access_cycles(0x08000004, 4, True, 0x0000) == 6  # S32 = 2S（非邊界）

    # WS0 first 欄位=1（4 cycles）、second 欄位=1（2 cycles）
    waitcnt = (1 << 2) | (1 << 4)
    assert access_cycles(0x08000000, 2, False, waitcnt) == 4
    assert access_cycles(0x08000002, 2, True, waitcnt) == 2


def test_access_cycles_128k_boundary_forces_sequential():
    waitcnt = (1 << 2) | (1 << 4)  # N=4、S=2
    assert access_cycles(0x08000000, 2, True, waitcnt) == 4  # 0x08000000 是邊界
    assert access_cycles(0x0A000000, 2, True, waitcnt) == 5  # WS1 邊界（WS1 預設 N）
    assert access_cycles(0x08000002, 2, True, waitcnt) == 2


def test_access_cycles_sram_and_waitcnt_io_decode():
    assert access_cycles(0x0E000000, 1, False, 0x0000) == 5
    assert access_cycles(0x0E000000, 1, False, 0x0003) == 9
    io = bytearray(0x400)
    io[0x204] = 0x14
    io[0x205] = 0x40
    assert waitcnt_from_io(io) == 0x4014


def test_arm_functional_instruction_costs(tmp_path):
    cases = {
        "MOV": (0xE3A00001, 1),
        "NOP": (0xE1A00000, 1),
        "LDR": (0xE5930000, 3),
        "STR": (0xE5830000, 2),
        "LDM2": (0xE8BD000C, 5),
        "STM2": (0xE92D0003, 4),
        "B": (0xEAFFFFFE, 2),
        "SWI": (0xEF060000, 3),
        "MUL": (0xE0020190, 2),
        "ADDshift": (0xE0800311, 2),  # ADD r2,r0,r1,lsl r3（暫存器移位 +1I）
    }
    for name, (instr, expected) in cases.items():
        emu = _emu(tmp_path, arm_words(instr, 0xEAFFFFFE))
        emu._cpu.regs.r[3] = 0x02000000
        assert emu._cpu.peek_cycles() == expected, name


def test_thumb_functional_instruction_costs(tmp_path):
    cases = {
        "MOV": (0x2001, 1),
        "ADD": (0x1842, 1),
        "LDR": (0x6818, 3),
        "STR": (0x6018, 2),
        "PUSH": (0xB403, 4),
        "POP": (0xBC0C, 5),
        "B": (0xE7FE, 2),
    }
    for name, (instr, expected) in cases.items():
        emu = _emu(tmp_path, thumb_words(instr, 0xE7FE), thumb=True)
        emu._cpu.regs.r[3] = 0x02000000
        assert emu._cpu.peek_cycles() == expected, name


def test_timed_mode_uses_bus_wait_states(tmp_path):
    # 程式從 0x08000000 起（128 KiB 邊界）→ 首個 fetch 強制 N32 = 8（5+3）
    # LDR = 8(fetch) + 6(EWRAM data) + 1(I) = 15
    emu = _emu(tmp_path, arm_words(0xE5930000, 0xEAFFFFFE), timing=TimingMode.TIMED)
    emu._cpu.regs.r[3] = 0x02000000
    assert emu._cpu.peek_cycles() == 15

    emu = _emu(tmp_path, arm_words(0xE3A00001, 0xEAFFFFFE), timing=TimingMode.TIMED)
    assert emu._cpu.peek_cycles() == 8


def test_step_cycles_never_exceeds_budget(tmp_path):
    # LDR 在 FUNCTIONAL 要 3 cycles；預算 2 → 不執行
    emu = _emu(tmp_path, arm_words(0xE5930000, 0xEAFFFFFE))
    emu._cpu.regs.r[3] = 0x02000000
    result = emu.step_cycles(2)
    assert result.cycles_executed == 0
    assert result.cycles_remaining == 2
    assert emu.cpu.read_register("r15") == 0x08000000

    result = emu.step_cycles(3)
    assert result.cycles_executed == 3
    assert result.cycles_remaining == 0


def test_cycle_counts_are_deterministic(tmp_path):
    code = arm_words(0xE3A00001, 0xE5930000, 0xE5830000, 0xEAFFFFFE)
    first = _emu(tmp_path, code)
    second = _emu(tmp_path, code)
    for _ in range(6):
        assert first._cpu.peek_cycles() == second._cpu.peek_cycles()
        first._cpu.step()
        second._cpu.step()
    assert first.cycles == second.cycles
