"""整數 cycle 時鐘、PPU 時序常數與事件排程器。

確定性契約（規格第 8 章）：模擬時間只能是整數 cycle；不得用 wall clock、
``time.sleep`` 或背景 thread 推進硬體。同 cycle 事件以插入順序
（``sequence``）打破平手，heap 排序因此穩定且可重現。

# GBATEK: GBA LCD Video Controller - LCD Dimensions and Timings
# (16.78MHz; 1232 cycles/line; 228 lines; 280896 cycles/frame)

數值依規格 §3.6.1，其他模組一律引用這裡的常數，不得重複寫死。
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass

# -- 系統時鐘與 PPU 時序（規格 §3.6.1）-------------------------------------
SYSTEM_CLOCK = 16 * 1024 * 1024  # 16,777,216 Hz（16.78 MHz）
CYCLE_NS = 59.59  # 一個 cycle 約 59.59 ns

PPU_LINE_CYCLES = 1232  # 308 dots：visible 960 + HBlank 272
PPU_VISIBLE_LINES = 160
PPU_TOTAL_LINES = 228  # visible 160 + VBlank 68
PPU_FRAME_CYCLES = PPU_TOTAL_LINES * PPU_LINE_CYCLES  # 280,896
PPU_VBLANK_START = PPU_VISIBLE_LINES * PPU_LINE_CYCLES  # 197,120
PPU_HBLANK_START = 1006  # DISPSTAT HBlank flag 於此 cycle 設起
PPU_VISIBLE_CYCLES = 960  # 240 dots × 4 cycles


def scanline_of(cycle: int) -> int:
    """回傳該絕對 cycle 所在的 scanline（0..227）。"""

    return (cycle % PPU_FRAME_CYCLES) // PPU_LINE_CYCLES


def frame_of(cycle: int) -> int:
    """回傳該絕對 cycle 屬於第幾個 frame（從 0 起算）。"""

    return cycle // PPU_FRAME_CYCLES


def cycle_in_line(cycle: int) -> int:
    """回傳該 cycle 在 scanline 內的偏移（0..1231）。"""

    return cycle % PPU_LINE_CYCLES


@dataclass(frozen=True, slots=True)
class ScheduledEvent:
    """內部排程事件；不得出現在對外 ``EventStream.poll()``。"""

    cycle: int  # 觸發的絕對 cycle 數
    sequence: int  # 同 cycle 的穩定排序用序號
    action: str  # 內部事件識別碼（由 scheduler 解析）

    def __lt__(self, other: "ScheduledEvent") -> bool:
        return (self.cycle, self.sequence) < (other.cycle, other.sequence)


class Scheduler:
    """單一、可重現的事件佇列。"""

    def __init__(self, cycle: int = 0) -> None:
        if cycle < 0:
            raise ValueError("cycle 不可為負")
        self._now = cycle
        self._sequence = 0
        self._queue: list[ScheduledEvent] = []

    @property
    def now(self) -> int:
        return self._now

    def schedule(self, delay: int, action: str) -> ScheduledEvent:
        if delay < 0:
            raise ValueError("delay 不可為負")
        return self.schedule_at(self._now + delay, action)

    def schedule_at(self, cycle: int, action: str) -> ScheduledEvent:
        if cycle < self._now:
            raise ValueError(f"不可排程到過去的 cycle：{cycle} < {self._now}")
        event = ScheduledEvent(cycle=cycle, sequence=self._sequence, action=action)
        self._sequence += 1
        heapq.heappush(self._queue, event)
        return event

    def peek(self) -> ScheduledEvent | None:
        return self._queue[0] if self._queue else None

    def advance_to(self, cycle: int) -> tuple[ScheduledEvent, ...]:
        """推進到 ``cycle``，回傳所有到期事件（含 cycle 邊界）。"""

        if cycle < self._now:
            raise ValueError(f"時間不可倒退：{cycle} < {self._now}")
        due: list[ScheduledEvent] = []
        while self._queue and self._queue[0].cycle <= cycle:
            due.append(heapq.heappop(self._queue))
        self._now = cycle
        return tuple(due)

    def advance(self, cycles: int) -> tuple[ScheduledEvent, ...]:
        if cycles < 0:
            raise ValueError("cycles 不可為負")
        return self.advance_to(self._now + cycles)

    def pending(self) -> tuple[ScheduledEvent, ...]:
        return tuple(sorted(self._queue))

    def clear(self) -> None:
        self._queue.clear()
        self._sequence = 0

    def __len__(self) -> int:
        return len(self._queue)


__all__ = [
    "SYSTEM_CLOCK",
    "CYCLE_NS",
    "PPU_LINE_CYCLES",
    "PPU_VISIBLE_LINES",
    "PPU_TOTAL_LINES",
    "PPU_FRAME_CYCLES",
    "PPU_VBLANK_START",
    "PPU_HBLANK_START",
    "PPU_VISIBLE_CYCLES",
    "scanline_of",
    "frame_of",
    "cycle_in_line",
    "ScheduledEvent",
    "Scheduler",
]
