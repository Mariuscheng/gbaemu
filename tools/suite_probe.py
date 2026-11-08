"""用 Python reference 跑 ``rom/suite.gba`` 其中一個 suite，統計 pass／fail。

對應 Rust 的 ``suite_probe``；主要用嚟驗證 Python 的 mGBA timing accounting
同 Rust 一致（Timing tests 做 gate）。

用法（repo root）：

    python tools/suite_probe.py --suite 2            # mGBA accounting（預設）
    python tools/suite_probe.py --suite 2 --legacy   # legacy timed model
    python tools/suite_probe.py --suite 3 --frames 400
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

import gbaemu  # noqa: E402
from gbaemu import BootMode, Emulator, EmulatorConfig, MemoryRegionKind, TimingMode  # noqa: E402

SUITE_NAMES = [
    "Memory tests",
    "I/O read tests",
    "Timing tests",
    "Timer count-up tests",
    "Timer IRQ tests",
    "Shifter tests",
    "Carry tests",
    "Multiply long tests",
    "BIOS math tests",
    "DMA tests",
    "SIO register R/W tests",
    "SIO timing tests",
    "Misc. edge case tests",
    "Video tests",
]


def read_u32(rom: bytes, address: int) -> int:
    offset = address - 0x08000000
    return int.from_bytes(rom[offset : offset + 4], "little")


def find_suite(rom: bytes, name: str) -> int | None:
    needle = (name + "\0").encode()
    position = rom.find(needle)
    if position < 0:
        return None
    name_address = 0x08000000 + position
    pattern = name_address.to_bytes(4, "little")
    cursor = 0
    while True:
        found = rom.find(pattern, cursor)
        if found < 0:
            return None
        candidate = 0x08000000 + found
        run = read_u32(rom, candidate + 0x04)
        n_tests = read_u32(rom, candidate + 0x10)
        passes = read_u32(rom, candidate + 0x14)
        total = read_u32(rom, candidate + 0x18)
        if (
            1 <= n_tests <= 5000
            and passes != 0
            and total != 0
            and (run == 0 or 0x08000000 <= run < 0x0A000000)
        ):
            return candidate
        cursor = found + 1


def press(emu: Emulator, buttons: dict[str, bool], frames: int) -> None:
    emu.input.set_buttons(**buttons)
    emu.run_frames(frames)
    emu.input.set_buttons(**{name: False for name in buttons})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", default=str(ROOT / "rom" / "suite.gba"))
    parser.add_argument("--suite", type=int, default=0)
    parser.add_argument("--frames", type=int, default=900)
    parser.add_argument("--legacy", action="store_true", help="退回 legacy timed model")
    parser.add_argument("--mgba", action="store_true", help="alias（預設已是 mgba）")
    parser.add_argument("--functional", action="store_true")
    args = parser.parse_args()

    rom = Path(args.rom).read_bytes()
    name = SUITE_NAMES[args.suite]
    suite = find_suite(rom, name)
    if suite is None:
        raise SystemExit(f"找唔到 suite: {name}")
    run = read_u32(rom, suite + 0x04)
    n_tests = read_u32(rom, suite + 0x10)
    passes_pointer = read_u32(rom, suite + 0x14)
    total_pointer = read_u32(rom, suite + 0x18)
    if run == 0:
        print(f"suite={name} 係互動式（run=NULL），probe 唔跑。")
        return

    config = EmulatorConfig(
        boot_mode=BootMode.HLE_ADVANCED,
        timing=TimingMode.FUNCTIONAL if args.functional else TimingMode.TIMED,
    )
    emu = Emulator.from_rom(args.rom, config=config)
    if args.legacy:
        emu._cpu.bus.mgba_timing = False

    for _ in range(120):
        emu.run_frames(1)
    for _ in range(args.suite):
        press(emu, {"down": True}, 1)
        emu.run_frames(12)
    press(emu, {"a": True}, 1)
    emu.run_frames(12)

    last_total = 0
    stable = 0
    frames = 0
    while frames < args.frames:
        emu.run_frames(1)
        frames += 1
        total = emu.memory.read_u32(total_pointer)
        if total > 0 and total == last_total:
            stable += 1
            if stable >= 3:
                break
        else:
            stable = 0
        last_total = total

    passes = emu.memory.read_u32(passes_pointer)
    total = emu.memory.read_u32(total_pointer)
    print(f"suite={name} frames={frames} passes={passes} total={total} expected={n_tests}")

    sram = emu.memory.read_region(MemoryRegionKind.SRAM)
    log = sram.split(b"\0", 1)[0].decode("latin-1")
    print("---- SRAM log ----")
    print(log)
    emu.close()


if __name__ == "__main__":
    main()
