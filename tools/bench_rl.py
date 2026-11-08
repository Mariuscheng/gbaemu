"""RL observation 與多 process rollout benchmark（SPEC §11）。

用法：
    python tools/bench_rl.py --rom rom/Dr_Mario.gba --frames 120 --workers 4
    python tools/bench_rl.py --rom rom/Dr_Mario.gba --source memory \
        --memory-range 0x02000000:256 --frames 60

量度：
* observation throughput（screen／memory／hybrid）—— steps/s、frames/s。
* 單 instance 與 multi-process rollout —— GBA frame / host second，用
  ``gbaemu.rl.run_rollouts`` 的結果總 frame 數除以 wall-clock。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if (_ROOT / "__init__.py").exists():
    sys.path.insert(0, str(_ROOT.parent))

from gbaemu import EmulatorConfig, TimingMode  # noqa: E402
from gbaemu.api_types import MemoryRange  # noqa: E402
from gbaemu.rl import (  # noqa: E402
    ActionSpec,
    GBAEnv,
    GBAEnvConfig,
    ObservationConfig,
    run_rollouts,
)


def _memory_ranges(specs: list[str]) -> tuple[MemoryRange, ...]:
    ranges = []
    for spec in specs:
        address, _, size = spec.partition(":")
        ranges.append(MemoryRange(int(address, 0), int(size or "256", 0)))
    return tuple(ranges)


def _config(args: argparse.Namespace) -> GBAEnvConfig:
    observation = ObservationConfig(
        source=args.source,
        grayscale=True,
        resize=(args.resize, args.resize),
        memory_ranges=_memory_ranges(args.memory_range),
    )
    return GBAEnvConfig(
        observation=observation,
        action=ActionSpec(mode="multi_binary"),
        frame_skip=args.frame_skip,
        max_episode_steps=10_000,
    )


def _actions(steps: int) -> list[list[int]]:
    # 固定 pattern，確保 benchmark 可重現；A/B 交替。
    return [[1] + [0] * 9 if index % 2 == 0 else [0, 1] + [0] * 8 for index in range(steps)]


def _bench_single(args: argparse.Namespace, config: GBAEnvConfig) -> float:
    env = GBAEnv(args.rom, config, emulator_config=EmulatorConfig(timing=TimingMode.FUNCTIONAL))
    try:
        env.reset(seed=0)
        actions = _actions(args.steps)
        start = time.perf_counter()
        for action in actions:
            env.step(action)
        elapsed = time.perf_counter() - start
    finally:
        env.close()
    frames = args.steps * args.frame_skip
    print(
        f"single env source={args.source} steps={args.steps} frame_skip={args.frame_skip} "
        f"frames={frames} elapsed={elapsed:.3f}s "
        f"steps/s={args.steps / elapsed:.1f} frames/s={frames / elapsed:.1f}"
    )
    return elapsed


def _bench_pool(args: argparse.Namespace, config: GBAEnvConfig) -> None:
    if args.workers <= 1:
        return
    rollouts = [(_actions(args.steps), seed) for seed in range(args.workers)]
    start = time.perf_counter()
    run_rollouts(
        args.rom,
        rollouts,
        workers=args.workers,
        config=config,
        emulator_config=EmulatorConfig(timing=TimingMode.FUNCTIONAL),
    )
    elapsed = time.perf_counter() - start
    frames = args.workers * args.steps * args.frame_skip
    print(
        f"pool workers={args.workers} rollouts={args.workers} frames={frames} "
        f"elapsed={elapsed:.3f}s frames/s={frames / elapsed:.1f} "
        f"frames_per_worker_s={frames / elapsed / args.workers:.1f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", default=None)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--frame-skip", type=int, default=4)
    parser.add_argument("--workers", type=int, default=0, help="0/1 = 只量單 instance")
    parser.add_argument("--source", choices=("screen", "memory", "hybrid"), default="screen")
    parser.add_argument("--resize", type=int, default=84)
    parser.add_argument(
        "--memory-range",
        action="append",
        default=[],
        metavar="ADDR:SIZE",
        help="memory／hybrid observation 的範圍，可重複（例：0x02000000:256）",
    )
    args = parser.parse_args()
    if args.steps <= 0:
        parser.error("--steps 必須大於 0")
    if args.frame_skip <= 0:
        parser.error("--frame-skip 必須大於 0")
    if args.source in ("memory", "hybrid") and not args.memory_range:
        parser.error(f"--source {args.source} 需要至少一個 --memory-range")
    if args.rom is None:
        from gbaemu.cli import find_roms

        candidates = find_roms("rom")
        if len(candidates) != 1:
            parser.error("rom/ 入面要有唯一 .gba，或用 --rom 指定")
        args.rom = candidates[0]
    config = _config(args)
    _bench_single(args, config)
    _bench_pool(args, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
