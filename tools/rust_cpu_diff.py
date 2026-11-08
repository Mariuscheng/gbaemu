"""G1 differential harness：Python reference CPU vs Rust `cpu_probe`。

用法（repo root）：

    cargo build --manifest-path crates/gbaemu-core/Cargo.toml --bin cpu_probe
    .\\venv\\Scripts\\python.exe tools/rust_cpu_diff.py

這不是 production backend；只是固定 instruction vector 的 G1 驗證。
"""

from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "crates" / "gbaemu-core" / "target" / "debug" / "cpu_probe.exe"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

import gbaemu  # noqa: E402

if Path(gbaemu.__file__).resolve().parent != ROOT:
    raise SystemExit(f"載入非 repo 的 gbaemu：{gbaemu.__file__}（預期 {ROOT}）")

from gbaemu import BootMode, Emulator, EmulatorConfig, TimingMode  # noqa: E402
from bus.access import access_cycles  # noqa: E402
from tests.gbaemu.cpu_helpers import arm_words, program_rom, thumb_words  # noqa: E402


@dataclass
class Case:
    name: str
    code: bytes
    thumb: bool = False
    cpsr: int = 0x1F
    regs: dict[int, int] = field(default_factory=dict)
    mem: list[tuple[int, int, int]] = field(default_factory=list)  # width, addr, value
    steps: int = 1
    checks: list[tuple[int, int]] = field(default_factory=list)  # width, addr
    exception: tuple[int, int, int] | None = None  # mode, vector, lr
    timing: bool = False  # True = TIMED，False = FUNCTIONAL


def _python_run(case: Case) -> tuple[dict[int, int], int, int, int, bool, dict[tuple[int, int], int]]:
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "program.gba"
        path.write_bytes(program_rom(case.code, size=0x400))
        timing = TimingMode.TIMED if case.timing else TimingMode.FUNCTIONAL
        emu = Emulator.from_rom(path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY, timing=timing))
        try:
            cpu = emu._cpu
            cpu.regs.cpsr = case.cpsr
            cpu.regs.pc = 0x0800_0000
            for index, value in case.regs.items():
                cpu.regs.r[index] = value
            for width, address, value in case.mem:
                if width == 8:
                    emu.memory.write_u8(address, value)
                elif width == 16:
                    emu.memory.write_u16(address, value)
                else:
                    emu.memory.write_u32(address, value)
            start_cycles = cpu.cycles
            if case.exception is not None:
                mode, vector, lr = case.exception
                cpu.enter_exception(mode, vector, lr - cpu.regs.pc)
            else:
                for _ in range(case.steps):
                    cpu.step()
            regs = {index: cpu.regs.r[index] for index in range(16)}
            cpsr = cpu.regs.cpsr
            spsr = cpu.regs.spsr
            halted = bool(cpu.core.halted)
            checks = {}
            for width, address in case.checks:
                if width == 8:
                    value = emu.memory.read_u8(address)
                elif width == 16:
                    value = emu.memory.read_u16(address)
                else:
                    value = emu.memory.read_u32(address)
                checks[(width, address)] = value
            return regs, cpsr, spsr, cpu.cycles - start_cycles, halted, checks
        finally:
            emu.close()


class Probe:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [str(PROBE)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def command(self, line: str) -> str:
        assert self.proc.stdin is not None
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        assert self.proc.stdout is not None
        output = self.proc.stdout.readline().strip()
        if not output:
            raise RuntimeError(f"probe closed after {line!r}")
        return output

    def close(self) -> None:
        try:
            self.command("quit")
        except Exception:
            pass
        self.proc.kill()


def _rust_run(probe: Probe, case: Case) -> tuple[dict[int, int], int, int, int, bool, dict[tuple[int, int], int]]:
    assert probe.command("reset") == "ok"
    assert probe.command(f"functional {0 if case.timing else 1}") == "ok"
    assert probe.command(f"mgba {1 if case.timing else 0}") == "ok"
    assert probe.command(f"cpsr {case.cpsr:08x}") == "ok"
    for index, value in case.regs.items():
        assert probe.command(f"reg {index} {value:08x}") == "ok"
    for offset in range(0, len(case.code), 4):
        word = case.code[offset : offset + 4].ljust(4, b"\0")
        value = struct.unpack("<I", word)[0]
        assert probe.command(f"rom32 {offset:x} {value:08x}") == "ok"
    for width, address, value in case.mem:
        assert probe.command(f"mem{width} {address:08x} {value:x}") == "ok"
    last = ""
    if case.exception is not None:
        mode, vector, lr = case.exception
        last = probe.command(f"exception {mode:02x} {vector:08x} {lr:08x}")
    else:
        for _ in range(case.steps):
            last = probe.command("step")
            if last.startswith("err "):
                raise AssertionError(f"{case.name}: Rust step failed: {last}")
    fields = dict(part.split("=", 1) for part in last.split()[1:])
    regs = {index: int(value, 16) for index, value in enumerate(fields["regs"].split(","))}
    cpsr = int(fields["cpsr"], 16)
    spsr = int(fields["spsr"], 16)
    cycles = int(fields["cycles"])
    halted = fields.get("halted") == "1"
    checks = {}
    for width, address in case.checks:
        result = probe.command(f"peek{width} {address:08x}")
        value = int(result.split("value=")[1], 16)
        checks[(width, address)] = value
    return regs, cpsr, spsr, cycles, halted, checks


def _compare(case: Case, python, rust) -> list[str]:
    py_regs, py_cpsr, py_spsr, py_cycles, py_halted, py_checks = python
    rs_regs, rs_cpsr, rs_spsr, rs_cycles, rs_halted, rs_checks = rust
    errors = []
    for index in range(16):
        if py_regs[index] != rs_regs[index]:
            errors.append(f"r{index}: py={py_regs[index]:08x} rust={rs_regs[index]:08x}")
    if py_cpsr != rs_cpsr:
        errors.append(f"cpsr: py={py_cpsr:08x} rust={rs_cpsr:08x}")
    if py_spsr != rs_spsr:
        errors.append(f"spsr: py={py_spsr:08x} rust={rs_spsr:08x}")
    if py_cycles != rs_cycles:
        errors.append(f"cycles: py={py_cycles} rust={rs_cycles}")
    if py_halted != rs_halted:
        errors.append(f"halted: py={py_halted} rust={rs_halted}")
    for key, value in py_checks.items():
        if rs_checks.get(key) != value:
            errors.append(f"mem{key[0]}[{key[1]:08x}]: py={value:x} rust={rs_checks.get(key, -1):x}")
    return errors


def main() -> int:
    if not PROBE.exists():
        print(f"missing probe: {PROBE}")
        print("run: cargo build --manifest-path crates/gbaemu-core/Cargo.toml --bin cpu_probe")
        return 2
    cases = [
        Case(
            "arm_data_processing",
            arm_words(0xE3A00005, 0xE3A01003, 0xE0502001),
            steps=3,
        ),
        Case(
            "arm_load_store",
            arm_words(0xE5801000, 0xE5902000),
            regs={0: 0x0200_0000, 1: 0x1234_5678},
            steps=2,
            checks=[(32, 0x0200_0000)],
        ),
        Case(
            "arm_ldr_str_immediate_bit4",
            arm_words(0xE5901054, 0xE5801054),  # ldr r1,[r0,#0x54]; str r1,[r0,#0x54]
            regs={0: 0x0200_0000},
            mem=[(32, 0x0200_0054, 0xCAFE_BABE)],
            steps=2,
            checks=[(32, 0x0200_0054)],
        ),
        Case(
            "arm_unaligned_ldrh_rotates",
            arm_words(0xE1D010B1),  # ldrh r1,[r0,#1]
            regs={0: 0x0200_0000},
            mem=[(16, 0x0200_0000, 0xBEEF)],
            steps=1,
        ),
        Case(
            "arm_unaligned_strh_rotates",
            arm_words(0xE1C020B1),  # strh r2,[r0,#1]
            regs={0: 0x0200_0000, 2: 0x1234},
            steps=1,
            checks=[(16, 0x0200_0000)],
        ),
        Case(
            "thumb_unaligned_ldrh_rotates",
            thumb_words(0x5A45),  # ldrh r5,[r0,r1]
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x0200_0000, 1: 1},
            mem=[(16, 0x0200_0000, 0xBEEF)],
            steps=1,
        ),
        Case(
            "arm_open_bus_load",
            arm_words(0xE5910000),  # ldr r0, [r1]
            regs={1: 0x1000_0000},
            steps=1,
            checks=[(32, 0x1000_0000)],
        ),
        Case(
            "arm_adds_carry_zero",
            arm_words(0xE3E00000, 0xE3A01001, 0xE0902001),  # mvn r0,#0; mov r1,#1; adds r2,r0,r1
            steps=3,
        ),
        Case(
            "arm_adcs_carry_in",
            arm_words(0xE3E00000, 0xE3A01000, 0xE0B02001),  # mvn; mov r1,#0; adcs r2,r0,r1
            cpsr=0x2000_001F,
            steps=3,
        ),
        Case(
            "arm_subs_borrow",
            arm_words(0xE3A00000, 0xE3A01001, 0xE0502001),  # mov r0,#0; mov r1,#1; subs r2,r0,r1
            steps=3,
        ),
        Case(
            "arm_sbcs_borrow",
            arm_words(0xE3A00000, 0xE3A01000, 0xE0D02001),  # mov r0,#0; mov r1,#0; sbcs r2,r0,r1
            steps=3,
        ),
        Case(
            "arm_lsl_immediate",
            arm_words(0xE1A02200),  # mov r2,r0,lsl #4
            regs={0: 0x8000_0001},
            steps=1,
        ),
        Case(
            "arm_add_register_shift",
            arm_words(0xE0802311),  # add r2,r0,r1,lsl r3
            regs={0: 0, 1: 1, 3: 4},
            steps=1,
        ),
        Case(
            "arm_lsr_32",
            arm_words(0xE1A02020),  # mov r2,r0,lsr #32
            regs={0: 0x8000_0000},
            steps=1,
        ),
        Case(
            "arm_asr_32",
            arm_words(0xE1A02040),  # mov r2,r0,asr #32
            regs={0: 0x8000_0000},
            steps=1,
        ),
        Case(
            "arm_rrx",
            arm_words(0xE1A02060),  # mov r2,r0,rrx
            cpsr=0x2000_001F,
            regs={0: 0},
            steps=1,
        ),
        Case(
            "arm_ror_register_zero",
            arm_words(0xE1A02170),  # mov r2,r0,ror r1
            cpsr=0x2000_001F,
            regs={0: 0x1234_5678, 1: 0},
            steps=1,
        ),
        Case(
            "arm_lsl_register_33",
            arm_words(0xE1A02110),  # mov r2,r0,lsl r1
            regs={0: 0xFFFF_FFFF, 1: 33},
            steps=1,
        ),
        Case(
            "arm_movs_shift_zero_preserves_carry",
            arm_words(0xE1B02000),  # movs r2,r0
            cpsr=0x2000_001F,
            regs={0: 0},
            steps=1,
        ),
        Case(
            "arm_pc_operand",
            arm_words(0xE28F0004),  # add r0,pc,#4
            steps=1,
        ),
        Case(
            "arm_str_pc",
            arm_words(0xE580F000),  # str pc,[r0]
            regs={0: 0x0200_0000},
            steps=1,
            checks=[(32, 0x0200_0000)],
        ),
        Case(
            "arm_pc_relative_ldr",
            arm_words(0xE59F0004, 0xE1A00000, 0x1234_5678),
            steps=1,
        ),
        Case(
            "arm_halfword_transfers",
            arm_words(0xE1C010B0, 0xE1D020B0),  # strh r1,[r0]; ldrh r2,[r0]
            regs={0: 0x0200_0000, 1: 0xBEEF},
            steps=2,
            checks=[(16, 0x0200_0000)],
        ),
        Case(
            "arm_ldrsb",
            arm_words(0xE1D020D0),  # ldrsb r2,[r0]
            regs={0: 0x0200_0000},
            mem=[(8, 0x0200_0000, 0x80)],
            steps=1,
        ),
        Case(
            "arm_ldrsh",
            arm_words(0xE1D030F0),  # ldrsh r3,[r0]
            regs={0: 0x0200_0000},
            mem=[(16, 0x0200_0000, 0x8001)],
            steps=1,
        ),
        Case(
            "arm_swap",
            arm_words(0xE1002091),  # swp r2,r1,[r0]
            regs={0: 0x0200_0000, 1: 0xAABB_CCDD},
            mem=[(32, 0x0200_0000, 0x1122_3344)],
            steps=1,
            checks=[(32, 0x0200_0000)],
        ),
        Case(
            "arm_mrs_cpsr",
            arm_words(0xE10F0000),  # mrs r0,cpsr
            cpsr=0x6000_001F,
            steps=1,
        ),
        Case(
            "arm_umull",
            arm_words(0xE0832190),  # umull r2,r3,r0,r1
            regs={0: 0xFFFF_FFFF, 1: 2},
            steps=1,
        ),
        Case(
            "arm_smull",
            arm_words(0xE0C32190),  # smull r2,r3,r0,r1
            regs={0: 0xFFFF_FFFF, 1: 2},
            steps=1,
        ),
        Case(
            "arm_mla",
            arm_words(0xE0232190),  # mla r3,r0,r1,r2
            regs={0: 7, 1: 6, 2: 5},
            steps=1,
        ),
        Case(
            "arm_conditional_skipped",
            arm_words(0xE1500001, 0x13A02007),  # cmp r0,r1; movne r2,#7
            regs={0: 5, 1: 5, 2: 0},
            steps=2,
        ),
        Case(
            "arm_branch_not_taken",
            arm_words(0xE1500001, 0x1A000000),  # cmp r0,r1; bne +0
            regs={0: 5, 1: 5},
            steps=2,
        ),
        Case(
            "arm_branch_taken",
            arm_words(0xE1500001, 0x0A000000),  # cmp r0,r1; beq +0
            regs={0: 5, 1: 5},
            steps=2,
        ),
        Case(
            "arm_branch_link",
            arm_words(0xEB000000, 0xE1A00000),
            steps=2,
        ),
        Case(
            "arm_ldm_stm",
            arm_words(0xE8A00006, 0xE8B00018),
            regs={0: 0x0200_0000, 1: 0x1111_1111, 2: 0x2222_2222},
            steps=2,
            checks=[(32, 0x0200_0000), (32, 0x0200_0004)],
        ),
        Case(
            "arm_stm_base_in_list_first",
            arm_words(0xE92D6000),  # stmdb sp!,{sp,lr}
            regs={13: 0x0300_7F00, 14: 0x1111_1111},
            steps=1,
            checks=[(32, 0x0300_7EF8), (32, 0x0300_7EFC)],
        ),
        Case(
            "arm_stm_base_in_list_not_first",
            arm_words(0xE92D2001),  # stmdb sp!,{r0,sp}
            regs={0: 0xAAAA_AAAA, 13: 0x0300_7F00},
            steps=1,
            checks=[(32, 0x0300_7EF8), (32, 0x0300_7EFC)],
        ),
        Case(
            "arm_ldm_base_in_list",
            arm_words(0xE8B00003),  # ldmia r0!,{r0,r1}
            regs={0: 0x0200_0000},
            mem=[(32, 0x0200_0000, 0x1111_1111), (32, 0x0200_0004, 0x2222_2222)],
            steps=1,
        ),
        Case(
            "arm_stm_empty_list",
            arm_words(0xE8A00000),  # stmia r0!,{}
            regs={0: 0x0200_0000},
            steps=1,
            checks=[(32, 0x0200_0000)],
        ),
        Case(
            "arm_ldm_empty_list",
            arm_words(0xE8B00000),  # ldmia r0!,{}
            regs={0: 0x0200_0000},
            mem=[(32, 0x0200_0000, 0x0800_0123)],
            steps=1,
        ),
        Case(
            "thumb_mov_add_branch",
            thumb_words(0x2001, 0x3002, 0xE000),
            thumb=True,
            cpsr=0x3F,
            steps=3,
        ),
        Case(
            "thumb_stmia_base_in_list",
            thumb_words(0xC006),  # stmia r0!,{r1,r2}
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x0200_0000, 1: 0x1111_1111, 2: 0x2222_2222},
            steps=1,
            checks=[(32, 0x0200_0000), (32, 0x0200_0004)],
        ),
        Case(
            "thumb_ldmia_writeback",
            thumb_words(0xC806),  # ldmia r0!,{r1,r2}
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x0200_0000},
            mem=[(32, 0x0200_0000, 0x1111_1111), (32, 0x0200_0004, 0x2222_2222)],
            steps=1,
        ),
        Case(
            "thumb_ldmia_writeback_base_r3",
            thumb_words(0xCB01),  # ldmia r3!,{r0}
            thumb=True,
            cpsr=0x3F,
            regs={3: 0x0200_0000},
            mem=[(32, 0x0200_0000, 0xCAFE_BABE)],
            steps=1,
        ),
        Case(
            "thumb_push_pop",
            thumb_words(0x2105, 0x4008, 0xB501, 0xBD01),
            thumb=True,
            cpsr=0x3F,
            regs={0: 1, 1: 3, 13: 0x0300_7F00},
            steps=4,
        ),
        Case(
            "thumb_alu",
            thumb_words(0x2105, 0x4008),
            thumb=True,
            cpsr=0x3F,
            regs={0: 1},
            steps=2,
        ),
        Case(
            "thumb_add_register",
            thumb_words(0x1840),  # add r0,r0,r1
            thumb=True,
            cpsr=0x3F,
            regs={0: 5, 1: 1},
            steps=1,
        ),
        Case(
            "thumb_mov_imm_preserves_carry",
            thumb_words(0x2000),  # mov r0,#0
            thumb=True,
            cpsr=0x2000_003F,
            regs={0: 5},
            steps=1,
        ),
        Case(
            "thumb_add_imm_flags",
            thumb_words(0x3001),  # add r0,#1
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x7FFF_FFFF},
            steps=1,
        ),
        Case(
            "thumb_swi_halt",
            thumb_words(0xDF02),  # swi 2 (Halt)
            thumb=True,
            cpsr=0x3F,
            steps=1,
        ),
        Case(
            "thumb_cmp_v_flag",
            thumb_words(0x4288),  # cmp r0,r1
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x8000_0000, 1: 1},
            steps=1,
        ),
        Case(
            "thumb_lsr_32",
            thumb_words(0x0800),  # lsr r0,r0,#0 == #32
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x8000_0000},
            steps=1,
        ),
        Case(
            "thumb_ror_multiple_of_32",
            thumb_words(0x41C8),  # ror r0,r1
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x8000_0000, 1: 32},
            steps=1,
        ),
        Case(
            "thumb_load_store_immediate",
            thumb_words(0x6048, 0x684A),
            thumb=True,
            cpsr=0x3F,
            regs={0: 0xCAFE, 1: 0x0200_0000},
            steps=2,
            checks=[(32, 0x0200_0004)],
        ),
        Case(
            "thumb_register_offset_loads",
            thumb_words(0x5042, 0x5843, 0x5244, 0x5A45, 0x5446, 0x5C47),
            # STR r2,[r0,r1]; LDR r3; STRH r4; LDRH r5; STRB r6; LDRB r7
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x0200_0000, 1: 4, 2: 0x89AB_CDEF, 4: 0x1234, 6: 0x5A},
            steps=6,
            checks=[(32, 0x0200_0004), (16, 0x0200_0004), (8, 0x0200_0004)],
        ),
        Case(
            "thumb_ldsb_register_offset",
            thumb_words(0x5642),  # LDSB r2,[r0,r1]
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x0200_0000, 1: 0},
            mem=[(8, 0x0200_0000, 0x80)],
            steps=1,
        ),
        Case(
            "thumb_ldsh_register_offset",
            thumb_words(0x5E43),  # LDSH r3,[r0,r1]
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x0200_0000, 1: 2},
            mem=[(16, 0x0200_0000, 0x8000)],
            steps=1,
        ),
        Case(
            "thumb_sp_relative",
            thumb_words(0x9000, 0x9800),
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x1234_5678, 13: 0x0300_7F00},
            steps=2,
            checks=[(32, 0x0300_7F00)],
        ),
        Case(
            "thumb_add_sp",
            thumb_words(0xB002),
            thumb=True,
            cpsr=0x3F,
            regs={13: 0x0300_7F00},
            steps=1,
        ),
        Case(
            "thumb_bl",
            thumb_words(0xF000, 0xF800),
            thumb=True,
            cpsr=0x3F,
            steps=1,
        ),
        Case(
            "thumb_bl_full",
            thumb_words(0xF000, 0xF800),
            thumb=True,
            cpsr=0x3F,
            steps=2,
        ),
        Case(
            "thumb_beq_taken",
            thumb_words(0xD001),
            thumb=True,
            cpsr=0x4000_003F,
            steps=1,
        ),
        Case(
            "thumb_ldrh",
            thumb_words(0x8802),  # ldrh r2,[r0]
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x0200_0000},
            mem=[(16, 0x0200_0000, 0xBEEF)],
            steps=1,
            checks=[(16, 0x0200_0000)],
        ),
        Case(
            "thumb_high_reg_add",
            thumb_words(0x4480),  # add r8,r0
            thumb=True,
            cpsr=0x3F,
            regs={0: 0x1234_5678},
            steps=1,
        ),
        Case(
            "arm_swi_div",
            arm_words(0xEF06_0000),
            regs={0: 0xFFFF_FFF9, 1: 2},
            steps=1,
        ),
        Case(
            "arm_swi_sqrt",
            arm_words(0xEF08_0000),
            regs={0: 81},
            steps=1,
        ),
        Case(
            "arm_swi_halt",
            arm_words(0xEF02_0000),
            regs={0: 0, 1: 0},
            steps=1,
        ),
        Case(
            "arm_swi_vblank_intrwait",
            arm_words(0xEF05_0000),
            regs={0: 0, 1: 0},
            steps=1,
        ),
        Case(
            "arm_swi_bios_checksum",
            arm_words(0xEF0D_0000),
            steps=1,
        ),
        Case(
            "arm_swi_midi_key",
            arm_words(0xEF1F_0000),
            regs={0: 0, 1: 69, 2: 0},
            steps=1,
        ),
        Case(
            "arm_swi_huffman",
            arm_words(0xEF13_0000),
            regs={0: 0x0200_0000, 1: 0x0200_0200},
            mem=[
                (32, 0x0200_0000, 0x0000_0408),
                (8, 0x0200_0004, 64),
                (8, 0x0200_0005, 0xFF),
                (16, 0x0200_0084, 0x4141),
                (8, 0x0200_0086, 0),
            ],
            steps=1,
            checks=[(32, 0x0200_0200)],
        ),
        Case(
            "arm_swi_bg_affine",
            arm_words(0xEF0E_0000),
            regs={0: 0x0200_0000, 1: 0x0200_0100, 2: 1},
            mem=[
                (32, 0x0200_0000, 0),
                (32, 0x0200_0004, 0),
                (16, 0x0200_0008, 0),
                (16, 0x0200_000A, 0),
                (16, 0x0200_000C, 256),
                (16, 0x0200_000E, 256),
                (16, 0x0200_0010, 0),
            ],
            steps=1,
            checks=[(32, 0x0200_0100), (32, 0x0200_0104)],
        ),
        Case(
            "arm_swi_bitunpack",
            arm_words(0xEF10_0000),
            regs={0: 0x0200_0000, 1: 0x0200_0100, 2: 0x0200_0010},
            mem=[
                (8, 0x0200_0000, 0x12),
                (8, 0x0200_0001, 0x34),
                (16, 0x0200_0010, 2),
                (8, 0x0200_0012, 4),
                (8, 0x0200_0013, 8),
                (32, 0x0200_0014, 0),
            ],
            steps=1,
            checks=[(32, 0x0200_0100)],
        ),
        Case(
            "arm_swi_diff8",
            arm_words(0xEF16_0000),
            regs={0: 0x0200_0000, 1: 0x0200_0100},
            mem=[
                (32, 0x0200_0000, 0x0000_0416),
                (32, 0x0200_0004, 0x0403_0201),
            ],
            steps=1,
            checks=[(32, 0x0200_0100)],
        ),
        Case(
            "arm_swi_diff16",
            arm_words(0xEF18_0000),
            regs={0: 0x0200_0000, 1: 0x0200_0100},
            mem=[
                (32, 0x0200_0000, 0x0000_0418),
                (32, 0x0200_0004, 0x0002_0001),
            ],
            steps=1,
            checks=[(32, 0x0200_0100)],
        ),
        Case(
            "arm_swi_lz77_wram",
            arm_words(0xEF11_0000),
            regs={0: 0x0200_0000, 1: 0x0200_0100},
            mem=[
                (32, 0x0200_0000, 0x0000_0410),
                (32, 0x0200_0004, 0x4342_4100),
                (32, 0x0200_0008, 0x0000_0044),
            ],
            steps=1,
            checks=[(32, 0x0200_0100)],
        ),
        Case(
            "arm_swi_rl_wram",
            arm_words(0xEF14_0000),
            regs={0: 0x0200_0000, 1: 0x0200_0100},
            mem=[
                (32, 0x0200_0000, 0x0000_0430),
                (32, 0x0200_0004, 0x4342_4103),
                (32, 0x0200_0008, 0x0000_0044),
            ],
            steps=1,
            checks=[(32, 0x0200_0100)],
        ),
        Case(
            "timed_arm_mov",
            arm_words(0xE3A0_0001),
            steps=1,
            timing=True,
        ),
        Case(
            "timed_arm_ldr",
            arm_words(0xE590_1000),
            regs={0: 0x0200_0000},
            steps=1,
            timing=True,
        ),
        Case(
            "timed_arm_str",
            arm_words(0xE580_1000),
            regs={0: 0x0200_0000},
            steps=1,
            timing=True,
        ),
        Case(
            "timed_arm_branch",
            arm_words(0xEA00_0000),
            steps=1,
            timing=True,
        ),
        Case(
            "timed_thumb_mov",
            thumb_words(0x2001),
            thumb=True,
            cpsr=0x3F,
            steps=1,
            timing=True,
        ),
        Case(
            "timed_thumb_ldr",
            thumb_words(0x680A),
            thumb=True,
            cpsr=0x3F,
            regs={1: 0x0200_0000},
            steps=1,
            timing=True,
        ),
        Case(
            "irq_exception",
            b"",
            cpsr=0x13,
            regs={13: 0x0300_7F00, 14: 0x1111_1111},
            exception=(0x12, 0x18, 0x0800_0004),
        ),
        Case(
            "fiq_exception",
            b"",
            cpsr=0x13,
            regs={8: 0xAAAA_AAAA, 13: 0x0300_7F00},
            exception=(0x11, 0x1C, 0x0800_0004),
        ),
        Case(
            "svc_exception",
            b"",
            cpsr=0x1F,
            regs={13: 0x0300_7F00},
            exception=(0x13, 0x08, 0x0800_0004),
        ),
    ]

    probe = Probe()
    failed = 0
    try:
        for case in cases:
            python = _python_run(case)
            rust = _rust_run(probe, case)
            errors = _compare(case, python, rust)
            if errors:
                failed += 1
                print(f"[FAIL] {case.name}")
                for error in errors:
                    print(f"  {error}")
            else:
                print(f"[ ok ] {case.name}")

        bus_cases = [
            (0x0000, 0x0800_0000, 4, False),
            (0x0000, 0x0800_0002, 2, True),
            (0x0000, 0x0A00_0000, 4, False),
            (0x0000, 0x0C00_0000, 1, True),
            (0x0014, 0x0800_0000, 4, False),
            (0x0014, 0x0800_0002, 2, True),
            (0x0001, 0x0E00_0000, 1, False),
            (0x0000, 0x0200_0000, 4, False),
            (0x0000, 0x0500_0000, 4, False),
            (0x0000, 0x0600_0000, 2, False),
            (0x0000, 0x0300_0000, 4, False),
        ]
        assert probe.command("functional 0") == "ok"
        for waitcnt, address, width, sequential in bus_cases:
            assert probe.command(f"waitcnt {waitcnt:04x}") == "ok"
            result = probe.command(f"cost {address:08x} {width} {int(sequential)}")
            rust_cost = int(result.split("cost=")[1])
            python_cost = access_cycles(address, width, sequential, waitcnt)
            if rust_cost != python_cost:
                failed += 1
                print(f"[FAIL] bus cost waitcnt={waitcnt:04x} addr={address:08x} width={width} seq={sequential}")
                print(f"  py={python_cost} rust={rust_cost}")
            else:
                print(f"[ ok ] bus cost waitcnt={waitcnt:04x} addr={address:08x} width={width} seq={sequential}")
    finally:
        probe.close()

    probe = Probe()
    cycle_cases = [
        ("mov", 0xE3A0_0001, {}),
        ("ldr", 0xE590_1000, {0: 0x0200_0000}),
        ("str", 0xE580_1000, {0: 0x0200_0000}),
        ("b", 0xEA00_0000, {}),
        ("mul", 0xE000_0190, {0: 7, 1: 6}),
        ("ldm", 0xE8B0_0018, {0: 0x0200_0000}),
        ("stm", 0xE8A0_0006, {0: 0x0200_0000}),
    ]
    for name, instr, initial_regs in cycle_cases:
        assert probe.command("reset") == "ok"
        assert probe.command("functional 1") == "ok"
        assert probe.command("cpsr 0000001f") == "ok"
        for index, value in initial_regs.items():
            assert probe.command(f"reg {index} {value:08x}") == "ok"
        rust_cost = int(probe.command(f"cycles {instr:08x}").split("cost=")[1])

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "program.gba"
            path.write_bytes(program_rom(b"\0" * 16, size=0x400))
            emu = Emulator.from_rom(path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY))
            try:
                cpu = emu._cpu
                cpu.bus.functional = True
                cpu.regs.cpsr = 0x1F
                cpu.regs.pc = 0x0800_0000
                for index, value in initial_regs.items():
                    cpu.regs.r[index] = value
                python_cost = cpu._arm_cycles(instr)
            finally:
                emu.close()
        if rust_cost != python_cost:
            failed += 1
            print(f"[FAIL] cycle {name}: py={python_cost} rust={rust_cost}")
        else:
            print(f"[ ok ] cycle {name}")


    thumb_cycle_cases = [
        ("thumb_mov", 0x2001, {}),
        ("thumb_b", 0xE000, {}),
        ("thumb_ldr", 0x680A, {1: 0x0200_0000}),
        ("thumb_str", 0x6048, {1: 0x0200_0000}),
    ]
    for name, instr, initial_regs in thumb_cycle_cases:
        assert probe.command("reset") == "ok"
        assert probe.command("functional 1") == "ok"
        assert probe.command("cpsr 0000003f") == "ok"
        for index, value in initial_regs.items():
            assert probe.command(f"reg {index} {value:08x}") == "ok"
        rust_cost = int(probe.command(f"cycles {instr:04x}").split("cost=")[1])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "program.gba"
            path.write_bytes(program_rom(b"\0" * 16, size=0x400))
            emu = Emulator.from_rom(path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY))
            try:
                cpu = emu._cpu
                cpu.bus.functional = True
                cpu.regs.cpsr = 0x3F
                cpu.regs.pc = 0x0800_0000
                for index, value in initial_regs.items():
                    cpu.regs.r[index] = value
                python_cost = cpu._thumb_cycles(instr)
            finally:
                emu.close()
        if rust_cost != python_cost:
            failed += 1
            print(f"[FAIL] cycle {name}: py={python_cost} rust={rust_cost}")
        else:
            print(f"[ ok ] cycle {name}")

    total = len(cases) + len(bus_cases) + len(cycle_cases) + len(thumb_cycle_cases)
    print(f"{total - failed}/{total} checks passed ({len(cases)} CPU cases, {len(bus_cases)} bus costs, {len(cycle_cases)+len(thumb_cycle_cases)} cycle cases)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
