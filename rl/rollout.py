"""Multi-process rollout 與 trace replay（SPEC §9 Phase 4、§11）。

呢個模組係 RL scale-out 的入口：

* :func:`run_rollout` —— 單 process 由 reset 開始跑一串 action，
  記錄逐步 observation hash 同最終 state hash，可完全重現。
* :func:`replay_trace` —— 用 :class:`RolloutResult.trace` 重放同一串
  按鍵（frame → buttons），用嚟驗證確定性。
* :func:`run_rollouts` —— 用 ``ProcessPoolExecutor`` 平行跑多條
  rollout；每條 rollout 有獨立 seed，結果同單 process 版本逐 byte 一致。

Observation hash 係 SHA-256（observation 的 raw bytes），state hash 係
``Emulator.save_state()`` 的 SHA-256；兩者都係穩定、跨 process 一致的
識別碼，適合 CI 對照。
"""

from __future__ import annotations

import hashlib
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..api_types import Button, GBAEnvConfig
from .env import GBAEnv


def hash_bytes(data: bytes) -> str:
    """回傳 bytes 的 SHA-256 hex digest。"""

    return hashlib.sha256(data).hexdigest()


def hash_observation(observation: Any) -> str:
    """回傳 observation 的 SHA-256（支援 numpy array 或 bytes）。"""

    if isinstance(observation, (bytes, bytearray, memoryview)):
        return hash_bytes(bytes(observation))
    tobytes = getattr(observation, "tobytes", None)
    if callable(tobytes):
        return hash_bytes(tobytes())
    return hash_bytes(repr(observation).encode("utf-8"))


def _pressed_names(env: GBAEnv, action: Any) -> tuple[str, ...]:
    """把 action 轉做排序好的按鍵名稱（順序固定 = 重播穩定）。"""

    pressed = env._parse_action(action)
    order = env.config.action.button_order
    return tuple(button.value for button in order if button in pressed)


@dataclass(frozen=True, slots=True)
class RolloutResult:
    """一條 rollout 的可重現結果。"""

    seed: int
    steps: int
    observation_hashes: tuple[str, ...]
    final_state_hash: str
    total_reward: float
    truncated: bool
    trace: tuple[tuple[str, ...], ...]


def _run_rollout(
    rom_path: str | Path,
    actions: Iterable[Any],
    *,
    seed: int,
    config: GBAEnvConfig | None,
    emulator_config: Any,
) -> RolloutResult:
    env = GBAEnv(rom_path, config, emulator_config=emulator_config)
    try:
        observation, _info = env.reset(seed=seed)
        hashes = [hash_observation(observation)]
        trace: list[tuple[str, ...]] = []
        total_reward = 0.0
        truncated = False
        steps = 0
        for action in actions:
            trace.append(_pressed_names(env, action))
            observation, reward, terminated, truncated, _info = env.step(action)
            hashes.append(hash_observation(observation))
            total_reward += float(reward)
            steps += 1
            if terminated or truncated:
                break
        return RolloutResult(
            seed=seed,
            steps=steps,
            observation_hashes=tuple(hashes),
            final_state_hash=hash_bytes(env.save_state()),
            total_reward=total_reward,
            truncated=truncated,
            trace=tuple(trace),
        )
    finally:
        env.close()


def run_rollout(
    rom_path: str | Path,
    actions: Iterable[Any],
    *,
    seed: int = 0,
    config: GBAEnvConfig | None = None,
    emulator_config: Any = None,
) -> RolloutResult:
    """跑一條 rollout；同 seed／actions 必定得到同一個結果。"""

    return _run_rollout(
        rom_path,
        actions,
        seed=seed,
        config=config,
        emulator_config=emulator_config,
    )


def replay_trace(
    rom_path: str | Path,
    trace: Sequence[Sequence[str]],
    *,
    seed: int = 0,
    config: GBAEnvConfig | None = None,
    emulator_config: Any = None,
) -> RolloutResult:
    """重放按鍵 trace（``trace[i]`` = 第 i 個 step 按住的按鍵名稱）。

    用 ``multi_binary`` 或 ``discrete`` action spec 都可以；按鍵名稱會先
    轉返 action spec 要求的形式。回傳的 ``RolloutResult.trace`` 會等於
    輸入 trace。
    """

    spec = (config or GBAEnvConfig()).action
    order = spec.button_order
    actions: list[Any] = []
    for names in trace:
        pressed = {str(name) for name in names}
        unknown = pressed.difference(button.value for button in order)
        if unknown:
            raise ValueError(f"trace 有未知按鍵：{sorted(unknown)}")
        if spec.mode == "multi_binary":
            actions.append(tuple(button.value in pressed for button in order))
        elif spec.mode == "buttons":
            actions.append({button: (button.value in pressed) for button in order})
        else:
            actions.append(_discrete_index_for(spec, pressed))
    return _run_rollout(
        rom_path,
        actions,
        seed=seed,
        config=config,
        emulator_config=emulator_config,
    )


def _discrete_index_for(spec: Any, pressed: set[str]) -> int:
    wanted = frozenset(pressed)
    for index, buttons in enumerate(spec.discrete_sets):
        if frozenset(button.value for button in buttons) == wanted:
            return index
    raise ValueError(f"discrete_sets 冇對應 {sorted(pressed)} 的 action")


def _pool_worker(payload: tuple[str, tuple[Any, ...], int, Any, Any]) -> RolloutResult:
    rom_path, actions, seed, config, emulator_config = payload
    return _run_rollout(
        rom_path,
        actions,
        seed=seed,
        config=config,
        emulator_config=emulator_config,
    )


def run_rollouts(
    rom_path: str | Path,
    rollouts: Sequence[tuple[Sequence[Any], int]],
    *,
    workers: int | None = None,
    config: GBAEnvConfig | None = None,
    emulator_config: Any = None,
) -> list[RolloutResult]:
    """平行跑多條 rollout；``rollouts`` = [(actions, seed), ...]。

    ``workers`` 為 0／1／None 時用單 process（方便 debug）；大於 1 時用
    ``ProcessPoolExecutor``。無論行幾多 process，每條 rollout 的結果都
    同 ``run_rollout`` 一樣。
    """

    payloads = [
        (str(rom_path), tuple(actions), seed, config, emulator_config)
        for actions, seed in rollouts
    ]
    if not payloads:
        return []
    if workers is None or workers <= 1:
        return [_pool_worker(payload) for payload in payloads]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_pool_worker, payloads))


__all__ = [
    "RolloutResult",
    "hash_bytes",
    "hash_observation",
    "replay_trace",
    "run_rollout",
    "run_rollouts",
]
