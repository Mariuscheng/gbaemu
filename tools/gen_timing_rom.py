"""Generate minimal ROMs that mimic the mGBA test suite's timing harness.

The suite (``src/tests`` + ``include/macros.s``) measures an instruction with
TIMER0:

    START:  ldr r0,=TM0CNT ; ldr r1,=0x00800000 ; str r1,[r0]
    CODE:   <the instruction under test>
    END:    ldrh r2,[r0] ; strh r1,[r0,#2] ; store r2 to EWRAM

and subtracts a calibration run (empty CODE).  These ROMs reproduce a single
case so ``cycle_probe`` / ``mgba_cycle`` can report the same timer value the
suite would compare against.

Usage (repo root)::

    python tools/gen_timing_rom.py build/cal_empty.gba
    python tools/gen_timing_rom.py build/cal_mul.gba --code 0xE0030293
    cargo run --release --bin cycle_probe -- build/cal_mul.gba 30 4010 02000000

``--code`` may be repeated; each word is one ARM instruction placed inside the
measured window.  ROM header: entry branch to 0xC0, 0x96 at 0xB2.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

BASE = 0xC0
ENTRY_BRANCH = 0xEA00002E  # b 0x080000C0


def _ldr_literal(index: int, rd: int, target: int) -> int:
    address = BASE + index * 4
    offset = target - (address + 8)
    if not -4095 <= offset <= 4095:
        raise ValueError(f"literal offset out of range: {offset}")
    return 0xE59F0000 | (offset & 0xFFF) | (rd << 12)


def build(code: list[int], value: int = 0x12345678) -> bytes:
    instructions: list[int] = [
        None,  # 0: ldr r3,=0x12345678
        None,  # 1: ldr r0,=TM0CNT
        None,  # 2: ldr r1,=0x00800000
        0xE3A020FF,  # 3: mov r2,#0xFF
        0xE5801000,  # 4: str r1,[r0]      (START)
        *code,
        0xE1D020B0,  # END: ldrh r2,[r0]
        0xE1C010B2,  #      strh r1,[r0,#2]
        None,  # ldr r4,=0x02000000
        0xE5842000,  # str r2,[r4]
        0xEAFFFFFE,  # b .
    ]
    ldr4_index = len(instructions) - 3
    instructions[ldr4_index] = 0xE59F4000
    literals = [value, 0x04000100, 0x00800000, 0x02000000]
    literal_base = BASE + 4 * len(instructions)
    instructions[0] = _ldr_literal(0, 3, literal_base)
    instructions[1] = _ldr_literal(1, 0, literal_base + 4)
    instructions[2] = _ldr_literal(2, 1, literal_base + 8)
    instructions[ldr4_index] = _ldr_literal(ldr4_index, 4, literal_base + 12)

    rom = bytearray(0x20000)
    rom[0:4] = struct.pack("<I", ENTRY_BRANCH)
    for index, word in enumerate(instructions):
        rom[BASE + index * 4 : BASE + index * 4 + 4] = struct.pack("<I", word)
    for index, word in enumerate(literals):
        start = literal_base + index * 4
        rom[start : start + 4] = struct.pack("<I", word)
    rom[0xB2] = 0x96
    return bytes(rom)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument(
        "--value",
        type=lambda v: int(v, 0),
        default=0x12345678,
        help="r3 literal value for the multiply tests",
    )
    parser.add_argument(
        "--code",
        type=lambda value: int(value, 0),
        action="append",
        default=[],
        help="ARM instruction word(s) inside the measured window (repeatable)",
    )
    args = parser.parse_args()
    Path(args.output).write_bytes(build(args.code, args.value))
    print(f"wrote {args.output} ({len(args.code)} instruction(s) in window)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
