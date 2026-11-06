"""對外事件流（規格 5.4）。"""

from __future__ import annotations

from .api_types import EmulatorEvent


class EventStream:
    """累積對外事件，``poll()`` 依 cycle 排序後清空。"""

    def __init__(self) -> None:
        self._pending: list[EmulatorEvent] = []

    def emit(self, event: EmulatorEvent) -> None:
        if not isinstance(event, EmulatorEvent):
            raise TypeError(f"event 必須是 EmulatorEvent，得到 {type(event).__name__}")
        self._pending.append(event)

    def poll(self) -> tuple[EmulatorEvent, ...]:
        # Python sort 穩定：同 cycle 事件保留 emit 順序。
        events = tuple(sorted(self._pending, key=lambda event: event.cycle))
        self._pending.clear()
        return events

    def clear(self) -> None:
        self._pending.clear()

    def __len__(self) -> int:
        return len(self._pending)


__all__ = ["EventStream"]
