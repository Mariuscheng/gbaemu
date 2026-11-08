"""中斷控制器狀態（規格 3.4；snapshot 必須完整保存）。

Phase 3 才實作 IME/IE/IF latch 與 acknowledge；欄位先依規格固定。
"""

# GBATEK: GBA Interrupt Control - IME/IE/IF，以及 BIOS interrupt handling 的
# 進入順序（IF latch 需由 CPU acknowledge 清除）。
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class InterruptState:
    ime: int
    ie: int
    _if: int  # IF latch
    irqs_pending_mask: int  # 裝置已拉起、尚未被 CPU acknowledge 的位元


__all__ = ["InterruptState"]
