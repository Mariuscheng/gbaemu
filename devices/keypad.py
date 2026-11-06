"""Keypad 狀態（規格 3.4；snapshot 必須完整保存）。

GBATEK: GBA Keypad Input - KEYINPUT 為 active-low。Phase 2 才把
``InputPort`` 的按鍵 latch 接到 KEYINPUT；Phase 0 只固定狀態欄位。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class KeypadState:
    keyinput: int  # 反映目前按鍵（active-low）
    keycnt: int
    keycnt_irq_enable: bool
    keycnt_condition_all: bool  # True = AND 邏輯，False = OR 邏輯


__all__ = ["KeypadState"]
