"""Scheduler 與 EventStream 的確定性契約。"""

from __future__ import annotations

import pytest

from gbaemu.api_types import EmulatorEvent, EventKind
from gbaemu.events import EventStream
from gbaemu.timing import ScheduledEvent, Scheduler


def test_scheduler_orders_by_cycle_then_insertion():
    scheduler = Scheduler()
    scheduler.schedule(5, "five")
    first_three = scheduler.schedule(3, "three-a")
    second_three = scheduler.schedule(3, "three-b")
    assert first_three.sequence < second_three.sequence

    due = scheduler.advance_to(3)
    assert [event.action for event in due] == ["three-a", "three-b"]
    assert scheduler.now == 3
    assert [event.action for event in scheduler.advance_to(5)] == ["five"]
    assert scheduler.now == 5


def test_scheduler_zero_delay_and_pending():
    scheduler = Scheduler(cycle=10)
    event = scheduler.schedule(0, "now")
    assert event.cycle == 10
    assert scheduler.peek() == event
    assert scheduler.pending() == (event,)
    assert scheduler.advance(0) == (event,)
    assert scheduler.peek() is None


def test_scheduler_rejects_time_travel():
    scheduler = Scheduler(5)
    with pytest.raises(ValueError):
        scheduler.schedule(-1, "past")
    with pytest.raises(ValueError):
        scheduler.schedule_at(4, "past")
    with pytest.raises(ValueError):
        scheduler.advance_to(4)
    with pytest.raises(ValueError):
        scheduler.advance(-1)


def test_scheduled_event_is_comparable():
    early = ScheduledEvent(cycle=1, sequence=2, action="a")
    late = ScheduledEvent(cycle=2, sequence=0, action="b")
    assert early < late
    assert not late < early


def _event(kind: EventKind, cycle: int) -> EmulatorEvent:
    return EmulatorEvent(
        kind=kind,
        cycle=cycle,
        frame_index=0,
        scanline=None,
        channel=None,
        address=None,
        value=None,
    )


def test_event_stream_sorts_and_clears():
    stream = EventStream()
    first = _event(EventKind.HALT, 5)
    second = _event(EventKind.VBLANK_START, 3)
    third = _event(EventKind.IRQ, 3)
    stream.emit(first)
    stream.emit(second)
    stream.emit(third)
    assert len(stream) == 3

    events = stream.poll()
    assert [event.kind for event in events] == [
        EventKind.VBLANK_START,
        EventKind.IRQ,
        EventKind.HALT,
    ]
    assert stream.poll() == ()
    assert len(stream) == 0


def test_event_stream_clear_and_type_check():
    stream = EventStream()
    stream.emit(_event(EventKind.FRAME_BOUNDARY, 1))
    stream.clear()
    assert stream.poll() == ()
    with pytest.raises(TypeError):
        stream.emit("not an event")  # type: ignore[arg-type]
