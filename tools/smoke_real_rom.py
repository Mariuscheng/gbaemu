"""Real-ROM smoke：Python reference vs Rust native parity + throughput。

用法（repo root）：

    .\\venv\\Scripts\\python.exe tools\\smoke_real_rom.py --rom rom/rom.gba --frames 120
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from gbaemu import Emulator, EmulatorConfig, NativeEmulator


def fnv1a(data: bytes) -> int:
    value = 0xCBF29CE484222325
    for byte in data:
        value ^= byte
        value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return value


def run_python(rom: Path, frames: int) -> tuple[bytes, float]:
    emu = Emulator.from_rom(rom, config=EmulatorConfig())
    try:
        start = time.perf_counter()
        for _ in range(frames):
            emu.step_frame(render=True)
        return emu._framebuffer.read_frame(), time.perf_counter() - start
    finally:
        emu.close()


def run_native(rom: Path, frames: int) -> tuple[bytes, float]:
    emu = NativeEmulator.from_rom(rom, EmulatorConfig())
    try:
        start = time.perf_counter()
        for _ in range(frames):
            emu.step_frame()
        return emu.framebuffer(), time.perf_counter() - start
    finally:
        emu.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=Path("rom/rom.gba"))
    parser.add_argument("--frames", type=int, default=120)
    args = parser.parse_args()
    if not args.rom.exists():
        raise SystemExit(f"missing ROM: {args.rom}")
    if args.frames < 1:
        parser.error("--frames 必須 >= 1")

    py_frame, py_seconds = run_python(args.rom, args.frames)
    rs_frame, rs_seconds = run_native(args.rom, args.frames)
    py_fps = args.frames / py_seconds
    rs_fps = args.frames / rs_seconds
    print(f"rom={args.rom} frames={args.frames}")
    print(f"python : {py_seconds:.3f}s {py_fps:7.1f} fps hash={fnv1a(py_frame):016x}")
    print(f"rust   : {rs_seconds:.3f}s {rs_fps:7.1f} fps hash={fnv1a(rs_frame):016x}")
    print(f"match  : {py_frame == rs_frame}")
    print(f"speedup: {rs_fps / py_fps:.2f}x")
    return 0 if py_frame == rs_frame else 1


if __name__ == "__main__":
    raise SystemExit(main())
