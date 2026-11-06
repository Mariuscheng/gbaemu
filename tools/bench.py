"""量測 gbaemu 的 frame throughput（模擬 GBA frame / host second）。

用法（從 repo root 或安裝後皆可）：
    python tools/bench.py --rom rom/rom.gba --frames 120
    python tools/bench.py --rom rom/rom.gba --frames 30 --render
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# 開發樹：repo root 的上一層才是 gbaemu package 的父目錄。
if (_ROOT / "__init__.py").exists():
    sys.path.insert(0, str(_ROOT.parent))

from gbaemu import BootMode, Emulator, EmulatorConfig, TimingMode, VideoMode  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", default="rom/rom.gba")
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--timing", choices=("functional", "timed"), default="functional")
    args = parser.parse_args()
    if args.frames <= 0:
        parser.error("--frames 必須大於 0")

    config = EmulatorConfig(
        boot_mode=BootMode.HLE_ADVANCED,
        video=VideoMode.FRAMEBUFFER,
        timing=TimingMode.FUNCTIONAL if args.timing == "functional" else TimingMode.TIMED,
        hle_strict=False,
    )
    emu = Emulator.from_rom(args.rom, config=config)
    for _ in range(5):  # warm-up
        emu.step_frame(render=False)

    start = time.perf_counter()
    for _ in range(args.frames):
        emu.step_frame(render=args.render)
    elapsed = time.perf_counter() - start
    fps = args.frames / elapsed
    cycles_per_second = fps * 280_896
    print(
        f"rom={args.rom} frames={args.frames} render={args.render} "
        f"elapsed={elapsed:.3f}s fps={fps:.1f} cycles/s={cycles_per_second:,.0f}"
    )
    emu.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
