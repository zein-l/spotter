"""Event-driven trip simulator that schedules a driver's day under the FMCSA HOS rules.

The driver works through a fixed task list (pre-trip, drive to pickup, load, drive to
drop-off, unload, post-trip). Before every stretch of driving the planner asks how long the
driver may legally keep driving and stops just before the first limit that would be broken:

* 70-hour/8-day cycle exhausted        -> 34-hour restart          (395.3(b), (c))
* 11 hours driving or 14-hour window   -> 10 consecutive hours off (395.3(a)(2), (a)(3))
* 1,000 miles since the last fuel      -> fuel stop (on duty)      (assessment assumption)
* 8 hours driving without a 30-min gap -> 30-minute break          (395.3(a)(3)(ii))

Any 30+ consecutive minutes not driving (pickup, fueling, ...) satisfy the 30-minute break,
exactly as the FMCSA guide describes. On-duty work after the 14th hour or past 70 hours is
legal (only *driving* is prohibited), but the planner still reserves time for the post-trip
inspection so a normal shift ends inside both limits.

When the 70-hour cycle will run out before the trip ends, every 10-hour rest is also a
chance to take the 34-hour restart early. The planner simulates both choices and keeps the
one that delivers sooner, so it never burns a 10-hour rest just to drive 30 more minutes.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from enum import Enum

from .models import Activity, DriveLeg, HOSRules, Segment, Status, TripSettings

MINUTES_PER_DAY = 24 * 60
MAX_ITERATIONS = 20_000
DEFAULT_BRANCH_DEPTH = 4


class PlanningError(Exception):
    pass


class _TaskType(Enum):
    START = "start"
    DRIVE = "drive"
    WORK = "work"


@dataclass(frozen=True)
class _Task:
    type: _TaskType
    leg: int | None = None
    activity: Activity | None = None
    minutes: int = 0


@dataclass
class _State:
    t: int = 0
    task: int = 0
    leg_minute: int = 0
    miles: float = 0.0
    miles_since_fuel: float = 0.0
    shift_start: int | None = None  # start of the current 14-hour window
    drive_in_shift: int = 0  # driving since the last 10-hour reset
    drive_since_break: int = 0  # driving since the last 30+ minute interruption
    non_drive_streak: int = 0  # consecutive minutes not driving
    off_streak: int = 0  # consecutive minutes off duty / sleeper berth
    cycle_used: int = 0  # on-duty minutes counted toward the 70-hour limit
    lat: float = 0.0
    lon: float = 0.0
    segments: list[Segment] = field(default_factory=list)
    branch_budget: int = 0


@dataclass(frozen=True)
class _Context:
    legs: tuple[DriveLeg, ...]
    tasks: tuple[_Task, ...]
    rules: HOSRules
    settings: TripSettings
    day_offset: int  # minutes after midnight at departure, used to split driving at midnight


def plan_trip(
    legs: list[DriveLeg],
    *,
    cycle_used_minutes: int,
    departure_minute_of_day: int,
    rules: HOSRules | None = None,
    settings: TripSettings | None = None,
    branch_depth: int = DEFAULT_BRANCH_DEPTH,
) -> list[Segment]:
    """Return the duty-status segments for current -> pickup -> drop-off.

    ``legs`` must be [current->pickup, pickup->drop-off]. The driver is assumed to start
    the trip rested (10+ hours off), with ``cycle_used_minutes`` already on the 70-hour clock.
    """
    rules = rules or HOSRules()
    settings = settings or TripSettings()
    if len(legs) != 2:
        raise PlanningError("Expected exactly two legs: current->pickup and pickup->drop-off.")
    if not 0 <= cycle_used_minutes <= rules.cycle_limit:
        raise PlanningError("Current cycle used must be between 0 and 70 hours.")
    _check_settings(rules, settings)

    tasks = (
        _Task(_TaskType.START),
        _Task(_TaskType.DRIVE, leg=0),
        _Task(_TaskType.WORK, activity=Activity.PICKUP, minutes=settings.pickup_minutes),
        _Task(_TaskType.DRIVE, leg=1),
        _Task(_TaskType.WORK, activity=Activity.DROPOFF, minutes=settings.dropoff_minutes),
        _Task(_TaskType.WORK, activity=Activity.POST_TRIP, minutes=settings.post_trip_minutes),
    )
    ctx = _Context(tuple(legs), tasks, rules, settings, departure_minute_of_day % MINUTES_PER_DAY)
    lat, lon = legs[0].point_at(0)
    state = _State(cycle_used=cycle_used_minutes, lat=lat, lon=lon, branch_budget=branch_depth)
    return _run(state, ctx).segments


def _check_settings(rules: HOSRules, s: TripSettings) -> None:
    if s.break_minutes < rules.min_break:
        raise PlanningError("The rest break must be at least 30 minutes to satisfy 395.3(a)(3)(ii).")
    if s.fuel_interval_miles <= 0:
        raise PlanningError("Fuel interval must be positive.")
    if s.pre_trip_minutes + s.post_trip_minutes + s.min_drive_minutes >= rules.duty_window:
        raise PlanningError("Inspection times leave no room to drive inside the 14-hour window.")


# --------------------------------------------------------------------------- main loop


def _run(state: _State, ctx: _Context) -> _State:
    """Advance until every task is done. Branch points return the best finished state."""
    for _ in range(MAX_ITERATIONS):
        if state.task >= len(ctx.tasks):
            return state
        task = ctx.tasks[state.task]
        if task.type is _TaskType.START:
            finished = _start(state, ctx)
        elif task.type is _TaskType.DRIVE:
            finished = _drive_step(state, ctx, task)
        else:
            finished = _work(state, ctx, task)
        if finished is not None:
            return finished
    raise PlanningError("Trip planning did not converge.")


def _start(state: _State, ctx: _Context) -> _State | None:
    state.task += 1
    if state.branch_budget > 0 and _restart_may_help(state, ctx):
        # Cycle hours won't cover the trip: compare starting now vs. restarting first.
        go_now = _clone(state)
        restart_first = _clone(state)
        _add(restart_first, ctx, Status.OFF, ctx.rules.restart_off_duty, Activity.RESTART)
        return _best(_run(go_now, ctx), _run(restart_first, ctx))
    return None


def _work(state: _State, ctx: _Context, task: _Task) -> None:
    if task.minutes > 0:
        if state.shift_start is None and task.activity is not Activity.POST_TRIP:
            _begin_shift(state, ctx)
        _add(state, ctx, Status.ON, task.minutes, task.activity)
    state.task += 1
    return None


def _drive_step(state: _State, ctx: _Context, task: _Task) -> _State | None:
    leg = ctx.legs[task.leg]
    remaining = leg.total_minutes - state.leg_minute
    if remaining <= 0:
        state.task += 1
        state.leg_minute = 0
        return None
    if state.shift_start is None:
        _begin_shift(state, ctx)
        return None

    rules, s = ctx.rules, ctx.settings
    # Minutes of driving left before each limit. Post-trip time is reserved inside the
    # 14-hour window and the 70-hour cycle so a shift ends cleanly within both.
    available = {
        "cycle": rules.cycle_limit - state.cycle_used - s.post_trip_minutes,
        "shift": min(
            rules.max_driving - state.drive_in_shift,
            rules.duty_window - (state.t - state.shift_start) - s.post_trip_minutes,
        ),
        "fuel": _minutes_until_fuel(state, leg, s),
        "break": rules.driving_before_break - state.drive_since_break,
    }
    # Highest-priority limit that stops us before the end of this leg: a 34-hour restart
    # also satisfies a 10-hour rest, which also satisfies a 30-minute break.
    threshold = max(1, s.min_drive_minutes)
    for limit in ("cycle", "shift", "fuel", "break"):
        if available[limit] < remaining and available[limit] < threshold:
            return _stop_for(limit, state, ctx)

    _drive(state, ctx, task.leg, leg, int(min(remaining, *available.values())))
    return None


def _stop_for(limit: str, state: _State, ctx: _Context) -> _State | None:
    s = ctx.settings
    if limit == "cycle":
        _end_shift(state, ctx, Activity.RESTART)
    elif limit == "shift":
        return _rest_or_restart(state, ctx)
    elif limit == "fuel":
        _fuel(state, ctx)
    elif _fuel_during_break(state, ctx):
        # Fueling is on-duty, not-driving time, so it also satisfies the 30-minute break.
        _fuel(state, ctx)
        if s.fuel_minutes < s.break_minutes:
            _add(state, ctx, Status.OFF, s.break_minutes - s.fuel_minutes, Activity.BREAK)
    else:
        _add(state, ctx, Status.OFF, s.break_minutes, Activity.BREAK)
    return None


def _fuel(state: _State, ctx: _Context) -> None:
    _add(state, ctx, Status.ON, ctx.settings.fuel_minutes, Activity.FUEL)
    state.miles_since_fuel = 0.0


def _fuel_during_break(state: _State, ctx: _Context) -> bool:
    """Fuel at a mandatory break when the tank is past half and another fuel stop is needed
    before arrival anyway; it replaces a later stop instead of adding one."""
    s = ctx.settings
    if state.miles_since_fuel < s.fuel_interval_miles / 2:
        return False
    range_left = s.fuel_interval_miles - state.miles_since_fuel
    return _remaining_miles(state, ctx) > range_left


def _rest_or_restart(state: _State, ctx: _Context) -> _State | None:
    if state.branch_budget > 0 and _restart_may_help(state, ctx):
        rest = _clone(state)
        _end_shift(rest, ctx, Activity.REST)
        restart = _clone(state)
        _end_shift(restart, ctx, Activity.RESTART)
        return _best(_run(rest, ctx), _run(restart, ctx))
    _end_shift(state, ctx, Activity.REST)
    return None


# --------------------------------------------------------------------------- primitives


def _begin_shift(state: _State, ctx: _Context) -> None:
    if ctx.settings.pre_trip_minutes > 0:
        _add(state, ctx, Status.ON, ctx.settings.pre_trip_minutes, Activity.PRE_TRIP)
    else:
        state.shift_start = state.t


def _end_shift(state: _State, ctx: _Context, activity: Activity) -> None:
    s, rules = ctx.settings, ctx.rules
    if state.shift_start is not None and s.post_trip_minutes > 0:
        _add(state, ctx, Status.ON, s.post_trip_minutes, Activity.POST_TRIP)
    if activity is Activity.RESTART:
        _add(state, ctx, Status.OFF, rules.restart_off_duty, Activity.RESTART)
    else:
        status = Status.SB if s.rest_in_sleeper else Status.OFF
        _add(state, ctx, status, rules.reset_off_duty, Activity.REST)


def _add(state: _State, ctx: _Context, status: Status, minutes: int, activity: Activity) -> None:
    """Append a stationary segment at the current position."""
    if minutes <= 0:
        return
    segment = Segment(
        status=status,
        activity=activity,
        start=state.t,
        end=state.t + minutes,
        lat=state.lat,
        lon=state.lon,
        end_lat=state.lat,
        end_lon=state.lon,
        miles_start=state.miles,
        miles_end=state.miles,
        cycle_after=0,
    )
    _record(state, ctx, segment)


def _drive(state: _State, ctx: _Context, leg_index: int, leg: DriveLeg, minutes: int) -> None:
    """Drive ``minutes`` along ``leg``, splitting at midnight so daily mileage is exact."""
    while minutes > 0:
        to_midnight = MINUTES_PER_DAY - (ctx.day_offset + state.t) % MINUTES_PER_DAY
        piece = min(minutes, to_midnight)
        start_minute, end_minute = state.leg_minute, state.leg_minute + piece
        miles = leg.miles_at(end_minute) - leg.miles_at(start_minute)
        end_lat, end_lon = leg.point_at(end_minute)
        segment = Segment(
            status=Status.D,
            activity=Activity.DRIVE,
            start=state.t,
            end=state.t + piece,
            lat=state.lat,
            lon=state.lon,
            end_lat=end_lat,
            end_lon=end_lon,
            miles_start=state.miles,
            miles_end=state.miles + miles,
            cycle_after=0,
            leg=leg_index,
        )
        _record(state, ctx, segment)
        state.leg_minute = end_minute
        state.miles += miles
        state.miles_since_fuel += miles
        state.lat, state.lon = end_lat, end_lon
        minutes -= piece


def _record(state: _State, ctx: _Context, segment: Segment) -> None:
    """Apply a segment to the HOS clocks."""
    rules, minutes = ctx.rules, segment.minutes
    state.t = segment.end
    if segment.status.is_on_duty:
        if state.shift_start is None:
            state.shift_start = segment.start
        state.cycle_used += minutes
        state.off_streak = 0
    else:
        state.off_streak += minutes
        if state.off_streak >= rules.reset_off_duty:
            state.shift_start = None
            state.drive_in_shift = 0
        if state.off_streak >= rules.restart_off_duty:
            state.cycle_used = 0

    if segment.status is Status.D:
        state.drive_in_shift += minutes
        state.drive_since_break += minutes
        state.non_drive_streak = 0
    else:
        state.non_drive_streak += minutes
        if state.non_drive_streak >= rules.min_break:
            state.drive_since_break = 0

    segment.cycle_after = state.cycle_used
    state.segments.append(segment)


def _minutes_until_fuel(state: _State, leg: DriveLeg, s: TripSettings) -> float:
    here = leg.miles_at(state.leg_minute)
    range_left = s.fuel_interval_miles - state.miles_since_fuel
    if here + range_left >= leg.total_miles - 1e-6:
        return math.inf
    # Floor so the stop lands at or before the 1,000-mile mark, never after it.
    return math.floor(leg.minute_at_miles(here + range_left)) - state.leg_minute


# --------------------------------------------------------------------------- 34-hour restart choice


def _remaining_miles(state: _State, ctx: _Context) -> float:
    miles = 0.0
    for index in range(state.task, len(ctx.tasks)):
        task = ctx.tasks[index]
        if task.type is _TaskType.DRIVE:
            leg = ctx.legs[task.leg]
            miles += leg.total_miles - leg.miles_at(state.leg_minute if index == state.task else 0)
    return miles


def _restart_may_help(state: _State, ctx: _Context) -> bool:
    cycle_left = ctx.rules.cycle_limit - state.cycle_used
    return cycle_left < _remaining_on_duty_estimate(state, ctx)


def _remaining_on_duty_estimate(state: _State, ctx: _Context) -> int:
    s = ctx.settings
    drive, work, miles = 0, 0, 0.0
    for index in range(state.task, len(ctx.tasks)):
        task = ctx.tasks[index]
        if task.type is _TaskType.DRIVE:
            leg = ctx.legs[task.leg]
            done = state.leg_minute if index == state.task else 0
            drive += leg.total_minutes - done
            miles += leg.total_miles - leg.miles_at(done)
        elif task.type is _TaskType.WORK:
            work += task.minutes
    range_left = s.fuel_interval_miles - state.miles_since_fuel
    fuel_stops = max(0, math.ceil((miles - range_left) / s.fuel_interval_miles))
    shifts = math.ceil(drive / ctx.rules.max_driving) if drive else 0
    return drive + work + fuel_stops * s.fuel_minutes + shifts * (s.pre_trip_minutes + s.post_trip_minutes)


def _clone(state: _State) -> _State:
    clone = copy.copy(state)
    clone.segments = list(state.segments)  # segments are never mutated after recording
    clone.branch_budget = state.branch_budget - 1
    return clone


def _best(a: _State, b: _State) -> _State:
    """Earliest delivery wins; ties go to the plan without the extra restart."""
    return a if a.t <= b.t else b
