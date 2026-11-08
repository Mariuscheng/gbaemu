"""Rust `--mgba` accounting 同 Python reference 的逐指令成本對照。

用法（repo root，先 build cpu_probe）：

    cargo build --release --bin cpu_probe --manifest-path crates/gbaemu-core/Cargo.toml
    python tools/mgba_cost_diff.py

Mismatch 會以非 0 exit code 結束，可當 differential gate。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from gbaemu import BootMode, Emulator, EmulatorConfig, TimingMode  # noqa: E402


def make_rom() -> bytes:
    rom = bytearray(0x4000)
    rom[0xB2] = 0x96
    return bytes(rom)


CASES = [
    # (thumb, pc, instr, extra regs)
    (False, 0x08000000, 0xE89D0004, {"r13": 0x03000000}),       # ldmia sp,{r2}
    (False, 0x03000000, 0xE89D0004, {"r13": 0x03000000}),
    (False, 0x08000000, 0xE1CD10B0, {"r13": 0x03000000}),       # strh r1,[sp]
    (False, 0x08000000, 0xE59D2000, {"r13": 0x03000000}),       # ldr r2,[sp]
    (False, 0x08000000, 0xE59F2000, {}),                        # ldr r2,[pc]
    (False, 0x08000000, 0xE0000291, {"r1": 0x12345678, "r2": 0xFF}),   # mul
    (False, 0x08000000, 0xE0820091, {"r1": 0x12345678, "r2": 0xFF}),   # mla
    (False, 0x08000000, 0xE0C10290, {"r1": 0xFF, "r2": 0x12345678}),   # smull
    (False, 0x08000000, 0xE0810290, {"r1": 0xFFFFFFFF, "r2": 0xFFFFFFFF}),  # umull
    (False, 0x08000000, 0xE0A10290, {"r1": 0xFFFFFFFF, "r2": 0xFFFFFFFF}),  # umlal
    (False, 0x08000000, 0xE0E10290, {"r1": 0xFFFFFFFF, "r2": 0xFFFFFFFF}),  # smlal
    (False, 0x08000000, 0xE8B200F8, {"r2": 0x07FFFFFC}),        # ldmia r2!,{r3-r7}
    (False, 0x08000000, 0xE8B200F8, {"r2": 0x07FFFFEC}),
    (False, 0x08000000, 0xE92D40F0, {"r13": 0x03000100}),       # push {r4-r7,lr}
    (False, 0x08000000, 0xE92D00F0, {"r13": 0x03000100}),
    (False, 0x08000000, 0xEF060000, {"r0": 0x12345678, "r1": 0xFF}),   # swi 6
    (False, 0x08000000, 0xEF080000, {"r0": 0xFF}),                     # swi 8
    (True, 0x08000000, 0x4800, {}),                             # ldr r0,[pc]
    (True, 0x08000000, 0xB500, {"r13": 0x03000100}),            # push {lr}
    (True, 0x08000000, 0xBD00, {"r13": 0x03000100}),            # pop {pc}
    (True, 0x08000000, 0xC800, {"r0": 0x03000000}),             # ldmia r0!,{r3}
    (True, 0x08000000, 0xC000, {"r0": 0x03000000}),             # stmia r0!,{r3}
    (True, 0x08000000, 0x4348, {"r0": 0x12345678, "r1": 0xFF}), # mul r0,r1
    (True, 0x08000000, 0xE000, {}),                             # b
    (True, 0x08000000, 0xDF06, {"r0": 0x12345678, "r1": 0xFF}), # swi 6
    (True, 0x03000000, 0xC800, {"r0": 0x03000000}),
    (True, 0x03000000, 0x4800, {}),
]

WAITCNTS = [0x0000, 0x4000, 0x0004, 0x0010, 0x0014]


def probe_costs() -> dict[tuple[int, int, int], int]:
    exe = ROOT / "crates" / "gbaemu-core" / "target" / "release" / "cpu_probe.exe"
    commands = ["reset", "mgba 1", "functional 0"]
    keys = []
    for waitcnt in WAITCNTS:
        for thumb, pc, instr, regs in CASES:
            keys.append((waitcnt, pc, instr))
            commands += [
                "reset",
                "mgba 1",
                "functional 0",
                f"waitcnt {waitcnt:x}",
                f"reg 15 {pc:x}",
                "reg 0 12345678",
                "reg 1 ff",
                "reg 2 ffffffff",
                "reg 3 1000",
                "reg 13 03000000",
                "reg 14 08000010",
            ]
            for name, value in regs.items():
                index = int(name[1:])
                commands.append(f"reg {index} {value:x}")
            if thumb:
                commands.append("cpsr 3f")
            else:
                commands.append("cpsr 1f")
            commands.append(f"cycles {instr:x}")
    commands.append("quit")
    output = subprocess.run(
        [str(exe)], input="\n".join(commands) + "\n", capture_output=True, text=True, check=True
    ).stdout.splitlines()
    costs = []
    for line in output:
        if line.startswith("ok cost="):
            costs.append(int(line.split("=")[1]))
    if len(costs) != len(keys):
        raise SystemExit(f"cpu_probe 回應數量不符：{len(costs)} vs {len(keys)}")
    return dict(zip(keys, costs, strict=True))


def python_costs() -> dict[tuple[int, int, int], int]:
    emu = Emulator(
        make_rom(),
        config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY, timing=TimingMode.TIMED),
    )
    cpu = emu._cpu
    cpu.bus.mgba_timing = True
    costs = {}
    for waitcnt in WAITCNTS:
        for thumb, pc, instr, regs in CASES:
            cpu.bus.prefetch_last_pc = 0
            cpu.regs.r[0] = 0x12345678
            cpu.regs.r[1] = 0xFF
            cpu.regs.r[2] = 0xFFFFFFFF
            cpu.regs.r[3] = 0x1000
            cpu.regs.r[13] = 0x03000000
            cpu.regs.r[14] = 0x08000010
            for name, value in regs.items():
                cpu.regs.r[int(name[1:])] = value
            cpu.regs.r[15] = pc
            cpu.regs.cpsr = 0x3F if thumb else 0x1F
            emu.memory.write_u16(0x04000204, waitcnt)
            cost = cpu._thumb_cycles(instr) if thumb else cpu._arm_cycles(instr)
            costs[(waitcnt, pc, instr)] = cost
    return costs


def main() -> None:
    rust = probe_costs()
    py = python_costs()
    bad = 0
    for key in rust:
        if rust[key] != py[key]:
            bad += 1
            print(f"MISMATCH waitcnt={key[0]:04x} pc={key[1]:08x} instr={key[2]:08x} rust={rust[key]} py={py[key]}")
    print(f"checked {len(rust)} cases, mismatches={bad}")
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
