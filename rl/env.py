"""Gymnasium 風格的 GBA RL environment（規格 §5.8、§7）。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import ClassVar

from ..api_types import (
    Button,
    EmulatorConfig,
    GBAEnvConfig,
    VideoMode,
)
from ..emulator import Emulator

try:  # gymnasium 是選配；有安裝時才能通過 check_env
    import gymnasium as _gymnasium

    _ENV_BASE = _gymnasium.Env
except ImportError:  # pragma: no cover - 依環境
    _ENV_BASE = object


class GBAEnv(_ENV_BASE):
    """GBA 的通用 RL wrapper；reward 預設 0、terminated 預設 False。"""

    metadata: ClassVar[dict] = {"render_modes": []}

    def __init__(
        self,
        rom: str | Path,
        config: GBAEnvConfig | None = None,
        *,
        emulator_config: EmulatorConfig | None = None,
    ) -> None:
        self.config = config or GBAEnvConfig()
        observation = self.config.observation
        if observation.source not in ("screen", "memory", "hybrid"):
            raise ValueError(f"未知的 observation source：{observation.source!r}")
        if observation.source == "memory" and not observation.memory_ranges:
            raise ValueError("memory observation 需要 memory_ranges")
        if observation.source == "hybrid" and not observation.memory_ranges:
            raise ValueError("hybrid observation 需要 memory_ranges")
        if self.config.frame_skip < 1:
            raise ValueError("frame_skip 必須 >= 1")
        if self.config.max_episode_steps < 1:
            raise ValueError("max_episode_steps 必須 >= 1")

        base = emulator_config or EmulatorConfig()
        if observation.source in ("screen", "hybrid"):
            base = replace(base, video=VideoMode.FRAMEBUFFER)
        base = replace(base, hle_strict=False)
        self.emu = Emulator.from_rom(rom, config=base)
        self.render_mode = None
        self._steps = 0
        self._buttons: frozenset[Button] = frozenset()

    # ------------------------------------------------------------------
    # Gymnasium API
    # ------------------------------------------------------------------
    def reset(self, *, seed: int | None = None, options=None, **kwargs):
        del options, kwargs
        if _ENV_BASE is not object:
            super().reset(seed=seed)
        self.emu.reset(seed=seed)
        self._steps = 0
        self._buttons = frozenset()
        return self._observation(), self._info(frames_rendered=0)

    def step(self, action):
        buttons = self._parse_action(action)
        self._buttons = buttons
        self.emu.input.clear()
        if buttons:
            self.emu.input.set_buttons(**{button.value: True for button in buttons})

        render = self.config.observation.source in ("screen", "hybrid")
        frames = self.config.frame_skip
        for index in range(frames):
            self.emu.step_frame(render=render and index == frames - 1)

        self._steps += 1
        reward = 0.0
        terminated = False
        truncated = self._steps >= self.config.max_episode_steps
        info = self._info(frames_rendered=frames)
        return self._observation(), reward, terminated, truncated, info

    def close(self) -> None:
        self.emu.close()

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------
    def save_state(self) -> bytes:
        return self.emu.save_state()

    def load_state(self, data: bytes) -> None:
        self.emu.load_state(data)

    # ------------------------------------------------------------------
    # Action / observation
    # ------------------------------------------------------------------
    def _parse_action(self, action) -> frozenset[Button]:
        spec = self.config.action
        if spec.mode == "buttons":
            if isinstance(action, dict):
                pressed = []
                for button, value in action.items():
                    if not value:
                        continue
                    pressed.append(button if isinstance(button, Button) else Button(button))
                return frozenset(pressed)
            raise ValueError("buttons 模式需要 dict[Button, bool]")
        if spec.mode == "multi_binary":
            values = list(action)
            if len(values) != len(spec.button_order):
                raise ValueError(
                    f"multi_binary 長度必須是 {len(spec.button_order)}，得到 {len(values)}"
                )
            return frozenset(
                button for button, value in zip(spec.button_order, values) if bool(value)
            )
        if isinstance(action, bool) or not isinstance(action, int):
            raise ValueError("discrete 模式需要整數索引")
        if not 0 <= action < len(spec.discrete_sets):
            raise ValueError(f"discrete 索引超出範圍：{action}")
        return frozenset(spec.discrete_sets[action])

    def _observation(self):
        import numpy as np

        config = self.config.observation
        memory = None
        if config.source in ("memory", "hybrid"):
            parts = [
                self.emu.memory.read(item.address, item.size)
                for item in config.memory_ranges
            ]
            memory = np.frombuffer(b"".join(parts), dtype=np.uint8).copy()

        if config.source == "memory":
            return memory

        frame = self.emu.video.read_frame_array()  # (160, 240, 3)
        if config.grayscale:
            gray = (
                frame[:, :, 0].astype(np.uint16) * 77
                + frame[:, :, 1].astype(np.uint16) * 150
                + frame[:, :, 2].astype(np.uint16) * 29
            ) >> 8
            image = gray.astype(np.uint8)
        else:
            image = frame
        if config.resize is not None:
            height, width = config.resize
            ys = (np.arange(height) * image.shape[0] // height).astype(np.intp)
            xs = (np.arange(width) * image.shape[1] // width).astype(np.intp)
            image = image[ys][:, xs]
        if config.source == "hybrid":
            return np.concatenate([image.reshape(-1), memory])
        return image

    def _info(self, *, frames_rendered: int) -> dict:
        return {
            "frame_index": self.emu.frame_index,
            "frames_rendered": frames_rendered,
            "vcount": self.emu.vcount,
            "irq_pending": self.emu.irq_pending,
            "halted": self.emu.halted,
            "buttons": tuple(sorted(button.value for button in self._buttons)),
        }

    # -- Gymnasium spaces（需安裝 gymnasium 才提供） ---------------------
    @property
    def action_space(self):
        if _ENV_BASE is object:
            return None
        from gymnasium import spaces

        if self.config.action.mode == "multi_binary":
            return spaces.MultiBinary(len(self.config.action.button_order))
        if self.config.action.mode == "discrete":
            return spaces.Discrete(len(self.config.action.discrete_sets))
        return spaces.Dict({button: spaces.Discrete(2) for button in Button})

    @property
    def observation_space(self):
        if _ENV_BASE is object:
            return None
        import numpy as np
        from gymnasium import spaces

        config = self.config.observation
        if config.source == "memory":
            size = sum(item.size for item in config.memory_ranges)
            return spaces.Box(0, 255, shape=(size,), dtype=np.uint8)
        height, width = config.resize or (160, 240)
        if config.source == "hybrid":
            size = sum(item.size for item in config.memory_ranges)
            return spaces.Box(0, 255, shape=(height * width + size,), dtype=np.uint8)
        channels = () if config.grayscale else (3,)
        return spaces.Box(0, 255, shape=(height, width, *channels), dtype=np.uint8)


__all__ = ["GBAEnv"]
