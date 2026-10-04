"""Split a trip timeline into midnight-to-midnight driver's daily logs (49 CFR 395.8)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .models import ACTIVITY_LABELS, Activity, HOSRules, Segment, Status

MINUTES_PER_DAY = 24 * 60


@dataclass(frozen=True)
class Place:
    name: str  # short form for the grid, e.g. "Rolla, MO"
    detail: str  # remark form, e.g. "I-44, 12 mi SW of Rolla, MO"


@dataclass
class GridLine:
    status: Status
    start: int  # minute of the day, 0-1440
    end: int


@dataclass
class Remark:
    minute: int
    status: Status
    activity: Activity
    place: Place
    note: str


@dataclass
class Bracket:
    """A stationary period drawn under the grid, labelled with where it happened."""

    start: int
    end: int
    place: Place


@dataclass
class DailyLog:
    day: int
    date: date
    lines: list[GridLine]
    totals: dict[Status, int]
    miles: float
    start_place: Place
    end_place: Place
    remarks: list[Remark]
    brackets: list[Bracket]
    on_duty_today: int
    cycle_total: int  # on-duty minutes in the 70-hour/8-day window at the end of the day
    available_tomorrow: int
    restart_completed: bool
    legs: list[int] = field(default_factory=list)  # route legs driven this day


@dataclass(frozen=True)
class _Item:
    start: int  # absolute minute from midnight of the departure date
    end: int
    status: Status
    activity: Activity
    place: Place
    segment: Segment | None  # None for off-duty padding before/after the trip


def build_daily_logs(
    segments: list[Segment],
    places: list[Place],
    *,
    departure: datetime,
    origin: Place,
    destination: Place,
    cycle_used_minutes: int,
    rules: HOSRules | None = None,
) -> list[DailyLog]:
    """``places[i]`` is where ``segments[i]`` starts."""
    rules = rules or HOSRules()
    offset = departure.hour * 60 + departure.minute
    trip_end = offset + (segments[-1].end if segments else 0)
    day_count = max(1, math.ceil(trip_end / MINUTES_PER_DAY))
    sheet_end = day_count * MINUTES_PER_DAY

    items: list[_Item] = []
    if offset > 0:
        items.append(_Item(0, offset, Status.OFF, Activity.OFF_DUTY, origin, None))
    for seg, place in zip(segments, places):
        items.append(_Item(offset + seg.start, offset + seg.end, seg.status, seg.activity, place, seg))
    if trip_end < sheet_end:
        items.append(_Item(trip_end, sheet_end, Status.OFF, Activity.OFF_DUTY, destination, None))

    logs = []
    for day in range(day_count):
        day_start, day_end = day * MINUTES_PER_DAY, (day + 1) * MINUTES_PER_DAY
        todays = [i for i in items if i.start < day_end and i.end > day_start]
        lines = _grid_lines(todays, day_start, day_end)
        totals = {status: 0 for status in Status}
        for line in lines:
            totals[line.status] += line.end - line.start
        miles = sum(i.segment.miles for i in todays if i.segment is not None and i.status is Status.D)
        cycle_total = _cycle_at(segments, day_end - offset, cycle_used_minutes)
        logs.append(
            DailyLog(
                day=day + 1,
                date=departure.date() + timedelta(days=day),
                lines=lines,
                totals=totals,
                miles=miles,
                start_place=_place_at(items, day_start, origin),
                end_place=_place_at(items, day_end, destination),
                remarks=_remarks(todays, day_start, day_end),
                brackets=_brackets(todays, day_start, day_end),
                on_duty_today=totals[Status.D] + totals[Status.ON],
                cycle_total=cycle_total,
                available_tomorrow=max(0, rules.cycle_limit - cycle_total),
                restart_completed=any(
                    i.activity is Activity.RESTART and day_start < i.end <= day_end for i in todays
                ),
                legs=sorted({i.segment.leg for i in todays if i.segment and i.segment.leg is not None}),
            )
        )
    return logs


def _grid_lines(items: list[_Item], day_start: int, day_end: int) -> list[GridLine]:
    lines: list[GridLine] = []
    for item in items:
        start, end = max(item.start, day_start) - day_start, min(item.end, day_end) - day_start
        if end <= start:
            continue
        if lines and lines[-1].status is item.status and lines[-1].end == start:
            lines[-1].end = end
        else:
            lines.append(GridLine(item.status, start, end))
    return lines


def _remarks(items: list[_Item], day_start: int, day_end: int) -> list[Remark]:
    """One remark per change of duty status or activity, as 395.8(c) requires."""
    remarks = []
    for item in items:
        if not day_start <= item.start < day_end:
            continue  # continuation from the previous day
        if item.segment is None and item.start == 0:
            continue  # off-duty padding before departure on the first sheet
        note = ACTIVITY_LABELS[item.activity]
        if item.activity is Activity.OFF_DUTY:
            note = "Off duty - trip complete"
        elif item.activity is Activity.REST and item.status is Status.SB:
            note = "10-hour rest (sleeper berth)"
        remarks.append(Remark(item.start - day_start, item.status, item.activity, item.place, note))
    return remarks


def _brackets(items: list[_Item], day_start: int, day_end: int) -> list[Bracket]:
    """Group consecutive non-driving trip segments at one place into a single bracket."""
    brackets: list[Bracket] = []
    for item in items:
        if item.segment is None or item.status is Status.D:
            continue
        start, end = max(item.start, day_start) - day_start, min(item.end, day_end) - day_start
        if end <= start:
            continue
        previous = brackets[-1] if brackets else None
        if previous and previous.end == start and previous.place == item.place:
            previous.end = end
        else:
            brackets.append(Bracket(start, end, item.place))
    return brackets


def _place_at(items: list[_Item], minute: int, fallback: Place) -> Place:
    """Where the driver is at ``minute``. Drives are split at midnight, so an item covering a
    day boundary either starts exactly there or is stationary; both carry the right place."""
    for item in items:
        if item.start <= minute < item.end:
            return item.place
    return fallback


def _cycle_at(segments: list[Segment], minute: int, initial: int) -> int:
    """On-duty minutes in the 70-hour window at ``minute`` (trip-relative)."""
    value = initial
    for seg in segments:
        if seg.end <= minute:
            value = seg.cycle_after
            continue
        if seg.start < minute and seg.status.is_on_duty:
            value += minute - seg.start
        break
    return value
