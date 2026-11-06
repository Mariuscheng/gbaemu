"""RL 層（規格 §5.8／§7）：Gymnasium 風格 ``GBAEnv`` 與 PyBoy 風格 facade。

型別的**唯一權威定義**在 :mod:`gbaemu.api_types`；本子套件只做匯出與行為。
"""

from __future__ import annotations

from ..api_types import ActionSpec, GBAEnvConfig, MemoryRange, ObservationConfig
from .env import GBAEnv
from .wrappers import GbaApp, Screen

__all__ = [
    "ActionSpec",
    "GBAEnvConfig",
    "MemoryRange",
    "ObservationConfig",
    "GBAEnv",
    "GbaApp",
    "Screen",
]
