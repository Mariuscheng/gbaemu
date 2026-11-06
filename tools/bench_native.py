"""G7 baseline：Python reference vs Rust native frame throughput。

用法（repo root）：

    .\\venv\\Scripts\\python.exe tools\\bench_native.py --frames 60

需要先 build native extension（見 tools/build_wheel.py）。
"""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from gbaemu import BootMode, Emulator, EmulatorConfig, NativeEmulator, VideoMode

ROOT = Path(__file__).resolve().parents[1]


def make_rom() -> bytes:
    rom = bytearray(0x4000)
    rom[0xB2] = 0x96
    rom[0:4] = (0xEAFFFFFE).to_bytes(4, "little")
    return bytes(rom)


def bench_python(path: Path, frames: int) -> tuple[float, int]:
    config = EmulatorConfig(
        boot_mode=BootMode.TEST_ROM_ONLY,
        video=VideoMode.FRAMEBUFFER,
    )
    emu = Emulator.from_rom(path, config=config)
    try:
        emu._bus.write_u16(0x0400_0000, 3)  # Mode 3
        for index in range(256):
            emu._bus.write_u16(0x0600_0000 + index * 2, (index * 37) & 0x7FFF)
        emu.step_frame(render=True)
        start = time.perf_counter()
        cycles = 0
        for _ in range(frames):
            cycles += emu.step_frame(render=True).cycles
        return time.perf_counter() - start, cycles
    finally:
        emu.close()


def bench_native(path: Path, frames: int) -> tuple[float, int]:
    config = EmulatorConfig(
        boot_mode=BootMode.TEST_ROM_ONLY,
        video=VideoMode.FRAMEBUFFER,
    )
    emu = NativeEmulator.from_rom(path, config)
    try:
        emu.write_u16(0x0400_0000, 3)
        for index in range(256):
            emu.write_u16(0x0600_0000 + index * 2, (index * 37) & 0x7FFF)
        emu.step_frame(render=True)
        start = time.perf_counter()
        cycles = 0
        for _ in range(frames):
            cycles += emu.step_frame(render=True).cycles
        return time.perf_counter() - start, cycles
    finally:
        emu.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=60)
    args = parser.parse_args()
    if args.frames < 1:
        parser.error("--frames 必須 >= 1")

    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "bench.gba"
        path.write_bytes(make_rom())

        py_seconds, py_cycles = bench_python(path, args.frames)
        rs_seconds, rs_cycles = bench_native(path, args.frames)

    py_fps = args.frames / py_seconds
    rs_fps = args.frames / rs_seconds
    print(f"frames={args.frames}")
    print(f"python : {py_seconds:.3f}s  {py_fps:8.1f} fps  cycles/frame={py_cycles / args.frames:.0f}")
    print(f"rust   : {rs_seconds:.3f}s  {rs_fps:8.1f} fps  cycles/frame={rs_cycles / args.frames:.0f}")
    print(f"speedup: {rs_fps / py_fps:.2f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
