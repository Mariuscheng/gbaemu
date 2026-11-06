"""RL 設定型別的匯出層（權威定義：``gbaemu.api_types``，規格 5.8）。"""

from __future__ import annotations

from ..api_types import ActionSpec, GBAEnvConfig, MemoryRange, ObservationConfig

# multi_binary / buttons 的固定 bit 順序（bit 0 = A；規格 5.8）。
BUTTON_ORDER = ActionSpec.button_order

__all__ = [
    "ActionSpec",
    "GBAEnvConfig",
    "MemoryRange",
    "ObservationConfig",
    "BUTTON_ORDER",
]
