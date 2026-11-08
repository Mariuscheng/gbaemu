"""量測 gbaemu 的 frame throughput（模擬 GBA frame / host second）。

用法（從 repo root 或安裝後皆可）：
    python tools/bench.py --rom rom/Dr_Mario.gba --frames 120
    python tools/bench.py --rom rom/Dr_Mario.gba --frames 30 --render

唔畀 ``--rom`` 時會用 ``rom/`` 入面唯一的 ``.gba``。
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
    parser.add_argument("--rom", default=None, help="ROM 路徑；預設 rom/ 入面唯一的 .gba")
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--render", action="store_true")
    parser.add_argument(
        "--render-every",
        type=int,
        default=0,
        help="每 N 個 frame render 一次（0 = 完全唔 render；--render 等於 1）",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="另外量 snapshot save/restore throughput",
    )
    parser.add_argument("--timing", choices=("functional", "timed"), default="functional")
    args = parser.parse_args()
    if args.frames <= 0:
        parser.error("--frames 必須大於 0")
    if args.rom is None:
        from gbaemu.cli import find_roms

        candidates = find_roms("rom")
        if len(candidates) != 1:
            parser.error("rom/ 入面要有唯一 .gba，或用 --rom 指定")
        args.rom = candidates[0]

    config = EmulatorConfig(
        boot_mode=BootMode.HLE_ADVANCED,
        video=VideoMode.FRAMEBUFFER,
        timing=TimingMode.FUNCTIONAL if args.timing == "functional" else TimingMode.TIMED,
        hle_strict=False,
    )
    emu = Emulator.from_rom(args.rom, config=config)
    for _ in range(5):  # warm-up
        emu.step_frame(render=False)

    render_every = 1 if args.render else max(0, args.render_every)
    start = time.perf_counter()
    for index in range(args.frames):
        render = render_every > 0 and index % render_every == 0
        emu.step_frame(render=render)
    elapsed = time.perf_counter() - start
    fps = args.frames / elapsed
    cycles_per_second = fps * 280_896
    print(
        f"rom={args.rom} frames={args.frames} render_every={render_every} "
        f"elapsed={elapsed:.3f}s fps={fps:.1f} cycles/s={cycles_per_second:,.0f}"
    )

    if args.snapshot:
        count = min(args.frames, 100)
        data = emu.save_state()
        start = time.perf_counter()
        for _ in range(count):
            emu.save_state()
        save_elapsed = time.perf_counter() - start
        start = time.perf_counter()
        for _ in range(count):
            emu.load_state(data)
        load_elapsed = time.perf_counter() - start
        print(
            f"snapshot bytes={len(data)} count={count} "
            f"save/s={count / save_elapsed:.1f} load/s={count / load_elapsed:.1f} "
            f"save_MB/s={count * len(data) / save_elapsed / 1e6:.1f} "
            f"load_MB/s={count * len(data) / load_elapsed / 1e6:.1f}"
        )
    emu.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
