"""Breakpoint 表（公開 API；供 ``CPUView.set_breakpoint`` 與執行迴圈使用）。

原本喺 ``debug/breakpoints.py``；公開 repo 唔再包含 ``debug/`` 資料夾，所以
搬入正式套件模組，行為不變。
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import BreakpointError


@dataclass(frozen=True, slots=True)
class Breakpoint:
    id: int
    address: int
    thumb: bool | None  # None = 兩種 state 都命中


class BreakpointTable:
    def __init__(self) -> None:
        self._next_id = 1
        self._items: dict[int, Breakpoint] = {}

    def set(self, address: int, *, thumb: bool | None = None) -> int:
        if not isinstance(address, int) or not 0 <= address <= 0xFFFFFFFF:
            raise ValueError(f"breakpoint 位址必須是 32-bit 整數，得到 {address!r}")
        if thumb is not None and not isinstance(thumb, bool):
            raise ValueError("thumb 必須是 True/False/None")
        breakpoint_id = self._next_id
        self._next_id += 1
        self._items[breakpoint_id] = Breakpoint(breakpoint_id, address, thumb)
        return breakpoint_id

    def clear(self, breakpoint_id: int) -> None:
        if breakpoint_id not in self._items:
            raise BreakpointError(f"breakpoint id {breakpoint_id} 不存在")
        del self._items[breakpoint_id]

    @property
    def active(self) -> bool:
        return bool(self._items)

    def match(self, address: int, thumb: bool) -> Breakpoint | None:
        candidates = [
            item
            for item in self._items.values()
            if item.address == address and item.thumb in (None, thumb)
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item.thumb is None, item.id))

    @property
    def items(self) -> tuple[Breakpoint, ...]:
        return tuple(self._items[key] for key in sorted(self._items))

    def __len__(self) -> int:
        return len(self._items)


__all__ = ["Breakpoint", "BreakpointTable"]
