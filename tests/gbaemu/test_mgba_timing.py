"""Python reference 的 mGBA 式 timing accounting（``CpuBus.mgba_timing``）。

數值係 hardware-derived（mgba-emu/suite "Timing tests" 的期望值），同時鎖住
Rust mgba 分支的逐指令成本；跨語言對照見 ``tools/mgba_cost_diff.py``。
"""

from __future__ import annotations

from gbaemu.bus.address_bus import AddressBus
from gbaemu.cpu.arm7tdmi import Arm7Tdmi
from gbaemu.memory.cartridge import RomCartridge

ROM_PC = 0x08000004  # 唔好落 128 KiB bank 邊界，否則 fetch 會強制 nonseq


def _cpu(*, thumb: bool = False, waitcnt: int = 0) -> Arm7Tdmi:
    rom = bytearray(0x4000)
    rom[0xB2] = 0x96
    bus = AddressBus(RomCartridge(bytes(rom)))
    cpu = Arm7Tdmi(bus, functional=False)
    bus.mgba_timing = True
    cpu.bus.mgba_timing = True
    cpu.regs.cpsr = 0x3F if thumb else 0x1F
    cpu.regs.r[0] = 0x12345678
    cpu.regs.r[1] = 0xFF
    cpu.regs.r[2] = 0xFF
    cpu.regs.r[13] = 0x03000000
    bus.write_u16(0x04000204, waitcnt)
    return cpu


def _cost(instr: int, *, thumb: bool = False, waitcnt: int = 0, pc: int = ROM_PC, **regs) -> int:
    cpu = _cpu(thumb=thumb, waitcnt=waitcnt)
    cpu.regs.r[15] = pc
    for name, value in regs.items():
        cpu.regs.r[int(name[1:])] = value
    cpu.bus.prefetch_last_pc = 0
    return cpu._thumb_cycles(instr) if thumb else cpu._arm_cycles(instr)


def test_rom_fetch_and_prefetch_off():
    # ARM nop：1 + seq32(5) = 6；prefetch 與否都一樣。
    assert _cost(0xE1A00000) == 6
    assert _cost(0xE1A00000, waitcnt=0x4000) == 6


def test_load_store_data_cost():
    # LDR [sp]：data = wait(0)+2、post-body N-S = 2。
    assert _cost(0xE59D2000) == 10
    assert _cost(0xE59D2000, waitcnt=0x4000) == 6
    # STRH：store 只 ++wait（比 load 少 1）。
    assert _cost(0xE1CD10B0) == 9
    assert _cost(0xE1CD10B0, waitcnt=0x4000) == 6


def test_ldm_per_register_and_overflow():
    assert _cost(0xE89D0004) == 10          # ldmia sp,{r2}
    # OAM→ROM 跨區：逐 register 重新計 nonseq，唔可以只用起始 region。
    assert _cost(0xE8B200F8, r2=0x07FFFFFC) == 36


def test_multiply_wait_table():
    # MUL：multiplier 0xFF → m=1；base 6 + stall 1 + post delta 2 = 9，
    # prefetch on 時 stall 吸收 → 6。
    assert _cost(0xE0000291) == 9
    assert _cost(0xE0000291, waitcnt=0x4000) == 6


def test_thumb_ldr_pc_relative():
    assert _cost(0x4800, thumb=True) == 14


def test_swi_hle_stall_enters_bios_vector():
    # SWI 6（Div，r0=0／r1=0 → stall 24）純 HLE profile：24 + profile 47
    # + return refill（IWRAM 2）= 342；同 Rust `hle_swi_profile` 一致。
    assert _cost(0xDF06, thumb=True) == 342


def test_legacy_model_unchanged_when_flag_off():
    rom = bytearray(0x4000)
    rom[0xB2] = 0x96
    bus = AddressBus(RomCartridge(bytes(rom)))
    cpu = Arm7Tdmi(bus, functional=False)
    cpu.regs.cpsr = 0x1F
    cpu.regs.r[15] = ROM_PC
    cpu._nseq_fetch = False
    # Legacy：ROM prefetch off 的 32-bit fetch = 6（與 mgba 相同），但 LDR 用 access_cost+?
    assert cpu._arm_cycles(0xE1A00000) == 6


def test_timed_mode_uses_mgba_model(tmp_path):
    from gbaemu import BootMode, Emulator, EmulatorConfig, TimingMode

    from .cpu_helpers import arm_words, program_rom

    path = tmp_path / "timing_mode.gba"
    path.write_bytes(program_rom(arm_words(0xE1A00000, 0xEAFFFFFE)))
    emu = Emulator.from_rom(
        path,
        config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY, timing=TimingMode.TIMED),
    )
    # TIMED／TRACE 預設用 mGBA accounting；FUNCTIONAL 保持近似模型。
    assert emu._cpu.bus.mgba_timing is True
    assert emu._cpu.bus.functional is False
    functional = Emulator.from_rom(
        path,
        config=EmulatorConfig(
            boot_mode=BootMode.TEST_ROM_ONLY, timing=TimingMode.FUNCTIONAL
        ),
    )
    assert functional._cpu.bus.mgba_timing is False
