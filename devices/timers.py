"""Timers 0–3（規格 §3.4；GBATEK: GBA Timers）。

暫存器（每通道 4 bytes，0x04000100 起）：

* ``TMxCNT_L``（+0）：寫入只改 reload，讀取回目前 counter。
* ``TMxCNT_H``（+2）：prescaler 0-1（F/1、F/64、F/256、F/1024）、
  count-up 2（cascade，TM0 不支援）、IRQ 6、start 7。

counter 只在 overflow 或 start bit 0→1 時從 reload 重載；cascade 模式忽略
prescaler，由前一級 overflow 遞增。overflow 可拉 IF bit 3-6。

# GBATEK: GBA Timers - TMxCNT_L / TMxCNT_H；Prescaler、Count-up Timing、IRQ
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ..bus.io import IRQ_TIMER0

TIMER_BASE = 0x04000100
TIMER_STRIDE = 4

PRESCALERS = (1, 64, 256, 1024)


@dataclass(slots=True)
class TimerState:
    index: int  # 0-3
    counter: int  # 目前計數（0-65535）
    reload: int  # reload value（0-65535）
    control: int  # TMxCNT 原始值
    prescaler: int
    cascade: bool
    irq_enable: bool
    ticks_pending: int  # 週期累積（套用 prescaler 前）


class Timers:
    """四個 16-bit timer 的暫存器與計數。"""

    def __init__(self, *, irq=None) -> None:
        self.states = [
            TimerState(
                index=index,
                counter=0,
                reload=0,
                control=0,
                prescaler=1,
                cascade=False,
                irq_enable=False,
                ticks_pending=0,
            )
            for index in range(4)
        ]
        self.running = [False, False, False, False]
        # Timer 剛 enable：本條指令最後 2 cycles 唔計（hardware 喺 write
        # data phase 完成後才起動；suite Calibration 的 +2 offset）。
        self.start_pending = [0, 0, 0, 0]
        # 32-bit IO write（CNT_L+CNT_H 兩個 beat）期間為 True：timer 喺
        # 第二個 beat 才起動，start offset 係 2；16-bit CNT_H write 係 0。
        self.wide_write = False
        self._irq = irq
        # DMA Sound A/B 取樣：timer 0/1 每次溢位呼叫 `sound.timer_overflow(index)`。
        self._sound_overflow = None

    # ------------------------------------------------------------------
    # 接線
    # ------------------------------------------------------------------
    def bind_irq(self, callback) -> None:
        self._irq = callback

    def bind_sound(self, callback) -> None:
        """`callback(index)`：timer 0/1 溢位時推進 DMA Sound 取樣。"""

        self._sound_overflow = callback

    # ------------------------------------------------------------------
    # 暫存器存取（IoRegisters 委派）
    # ------------------------------------------------------------------
    def read16(self, offset: int) -> int:
        index, field = self._decode(offset)
        if index is None:
            return 0
        if field == "cnt_l":
            return (self.states[index].counter >> ((offset & 2) * 8)) & 0xFFFF
        return self.states[index].control

    def read32(self, offset: int) -> int:
        return self.read16(offset) | (self.read16(offset + 2) << 16)

    def write16(self, offset: int, value: int) -> None:
        index, field = self._decode(offset)
        if index is None:
            return
        value &= 0xFFFF
        if field == "cnt_l":
            self.states[index].reload = value
            return
        self._write_control(index, value)

    def write32(self, offset: int, value: int) -> None:
        # 先寫 reload、再寫 control：start 0→1 時 counter = 新 reload（GBATEK）。
        index, field = self._decode(offset)
        if index is None:
            return
        self.wide_write = True
        try:
            self.write16(offset, value & 0xFFFF)
            self.write16(offset + 2, (value >> 16) & 0xFFFF)
        finally:
            self.wide_write = False

    def _write_control(self, index: int, value: int) -> None:
        state = self.states[index]
        was_running = self.running[index]
        state.control = value
        state.prescaler = PRESCALERS[value & 0x3]
        state.cascade = bool(value & 0x04) and index > 0
        state.irq_enable = bool(value & 0x40)
        state.ticks_pending = 0
        running = bool(value & 0x80)
        self.running[index] = running
        if running and not was_running:
            state.counter = state.reload
            self.start_pending[index] = 2 if self.wide_write else 0
        elif not running and was_running:
            state.ticks_pending = 0
            self.start_pending[index] = 0

    # ------------------------------------------------------------------
    # 計數
    # ------------------------------------------------------------------
    def tick(self, cycles: int) -> None:
        if cycles < 0:
            raise ValueError("cycles 不可為負")
        for index in range(4):
            state = self.states[index]
            effective = cycles
            # 起動中的 timer 只計扣掉 offset 之後的 cycles。
            if self.start_pending[index]:
                skip = self.start_pending[index]
                self.start_pending[index] = 0
                effective = max(0, cycles - skip)
            if not self.running[index] or state.cascade:
                continue
            state.ticks_pending += effective
            increments, state.ticks_pending = divmod(state.ticks_pending, state.prescaler)
            if increments:
                self._add(index, increments)

    def next_irq_cycles(self, index: int) -> int | None:
        """下一個 overflow IRQ 還需多少 cycle；無法預測（cascade）回 None。"""

        state = self.states[index]
        if not self.running[index] or not state.irq_enable or state.cascade:
            return None
        ticks = 0x10000 - state.counter
        return max(1, ticks * state.prescaler - state.ticks_pending)

    def _add(self, index: int, increments: int) -> None:
        state = self.states[index]
        value = state.counter + increments
        overflows = 0
        while value > 0xFFFF:
            value = state.reload + (value - 0x10000)
            overflows += 1
        state.counter = value
        for _ in range(overflows):
            if state.irq_enable and self._irq is not None:
                self._irq(IRQ_TIMER0 << index)
            if self._sound_overflow is not None and index < 2:
                self._sound_overflow(index)
            self._cascade(index)

    def _cascade(self, index: int) -> None:
        next_index = index + 1
        if next_index >= 4:
            return
        if not self.running[next_index] or not self.states[next_index].cascade:
            return
        self._add(next_index, 1)

    # ------------------------------------------------------------------
    # Snapshot（規格 5.7 TMR 區段）
    # ------------------------------------------------------------------
    _SNAPSHOT = struct.Struct("<3IQIBBB")

    def snapshot_state(self) -> bytes:
        parts = []
        for index, state in enumerate(self.states):
            parts.append(
                self._SNAPSHOT.pack(
                    state.counter & 0xFFFF,
                    state.reload & 0xFFFF,
                    state.control & 0xFFFF,
                    state.ticks_pending,
                    state.prescaler,
                    1 if state.cascade else 0,
                    1 if state.irq_enable else 0,
                    1 if self.running[index] else 0,
                )
            )
        return b"".join(parts)

    def restore_state(self, data: bytes) -> None:
        offset = 0
        for index in range(4):
            (
                counter,
                reload,
                control,
                ticks_pending,
                prescaler,
                cascade,
                irq_enable,
                running,
            ) = self._SNAPSHOT.unpack_from(data, offset)
            offset += self._SNAPSHOT.size
            state = self.states[index]
            state.counter = counter
            state.reload = reload
            state.control = control
            state.ticks_pending = ticks_pending
            state.prescaler = prescaler
            state.cascade = bool(cascade)
            state.irq_enable = bool(irq_enable)
            self.running[index] = bool(running)

    # ------------------------------------------------------------------
    # 解碼
    # ------------------------------------------------------------------
    @staticmethod
    def _decode(offset: int) -> tuple[int | None, str | None]:
        relative = offset - TIMER_BASE if offset >= TIMER_BASE else offset - 0x100
        if relative < 0 or relative >= 4 * TIMER_STRIDE:
            return None, None
        index = relative // TIMER_STRIDE
        field_offset = relative % TIMER_STRIDE
        if field_offset < 2:
            return index, "cnt_l"
        return index, "cnt_h"

    # ------------------------------------------------------------------
    # 生命週期
    # ------------------------------------------------------------------
    def reset(self) -> None:
        for state in self.states:
            state.counter = 0
            state.reload = 0
            state.control = 0
            state.prescaler = 1
            state.cascade = False
            state.irq_enable = False
            state.ticks_pending = 0
        self.running = [False, False, False, False]


__all__ = ["TIMER_BASE", "TIMER_STRIDE", "PRESCALERS", "TimerState", "Timers"]
