"""Independent compliance audit of a finished duty-status timeline.

The planner decides when to stop; this module re-derives every HOS clock from the final
segments without sharing any of the planner's bookkeeping, so a planner bug shows up as a
failed check instead of a silently illegal log.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Activity, HOSRules, Segment, Status, TripSettings


@dataclass(frozen=True)
class Check:
    id: str
    label: str
    limit: float  # minutes, or miles for distance checks
    actual: float
    unit: str  # "minutes" | "miles"
    passed: bool
    detail: str

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "limit": round(self.limit, 1),
            "actual": round(self.actual, 1),
            "unit": self.unit,
            "passed": self.passed,
            "detail": self.detail,
        }


def validate_plan(
    segments: list[Segment],
    *,
    cycle_used_minutes: int,
    rules: HOSRules | None = None,
    settings: TripSettings | None = None,
) -> list[Check]:
    rules = rules or HOSRules()
    settings = settings or TripSettings()

    gaps = 0
    expected_start = segments[0].start if segments else 0
    for seg in segments:
        if seg.start != expected_start or seg.end < seg.start:
            gaps += 1
        expected_start = seg.end

    window_start: int | None = None
    off_run = non_driving_run = 0
    shift_driving = driving_since_break = 0
    cycle = cycle_used_minutes
    worst_shift_driving = worst_window = worst_since_break = worst_cycle = 0
    for seg in segments:
        minutes = seg.minutes
        if seg.status.is_off_duty:
            off_run += minutes
            non_driving_run += minutes
            if off_run >= rules.reset_off_duty:
                window_start, shift_driving = None, 0
            if off_run >= rules.restart_off_duty:
                cycle = 0
        else:
            off_run = 0
            if window_start is None:
                window_start = seg.start
            cycle += minutes
            if seg.status is Status.ON:
                non_driving_run += minutes
            else:
                non_driving_run = 0
                shift_driving += minutes
                driving_since_break += minutes
                worst_shift_driving = max(worst_shift_driving, shift_driving)
                worst_window = max(worst_window, seg.end - window_start)
                worst_since_break = max(worst_since_break, driving_since_break)
                worst_cycle = max(worst_cycle, cycle)
        if non_driving_run >= rules.min_break:
            driving_since_break = 0

    fuel_points = [0.0]
    fuel_points += [s.miles_start for s in segments if s.activity is Activity.FUEL]
    fuel_points.append(segments[-1].miles_end if segments else 0.0)
    worst_fuel_gap = max(b - a for a, b in zip(fuel_points, fuel_points[1:]))

    pickups = [s for s in segments if s.activity is Activity.PICKUP]
    dropoffs = [s for s in segments if s.activity is Activity.DROPOFF]
    stops_ok = (
        len(pickups) == 1
        and len(dropoffs) == 1
        and pickups[0].minutes >= settings.pickup_minutes
        and dropoffs[0].minutes >= settings.dropoff_minutes
        and pickups[0].end <= dropoffs[0].start
    )

    return [
        Check(
            "driving_limit",
            "11-hour driving limit",
            rules.max_driving,
            worst_shift_driving,
            "minutes",
            worst_shift_driving <= rules.max_driving,
            "Most driving between 10-hour rests.",
        ),
        Check(
            "duty_window",
            "14-hour duty window",
            rules.duty_window,
            worst_window,
            "minutes",
            worst_window <= rules.duty_window,
            "Latest point a driving period ends, measured from the start of its duty window.",
        ),
        Check(
            "rest_break",
            "30-minute break after 8 hours driving",
            rules.driving_before_break,
            worst_since_break,
            "minutes",
            worst_since_break <= rules.driving_before_break,
            "Most driving without a 30-minute interruption (on duty, off duty or sleeper).",
        ),
        Check(
            "cycle_limit",
            "70-hour / 8-day limit",
            rules.cycle_limit,
            worst_cycle,
            "minutes",
            worst_cycle <= rules.cycle_limit,
            "Highest on-duty total in the cycle at any moment of driving.",
        ),
        Check(
            "fuel_interval",
            f"Fuel at least every {settings.fuel_interval_miles:,.0f} miles",
            settings.fuel_interval_miles,
            worst_fuel_gap,
            "miles",
            worst_fuel_gap <= settings.fuel_interval_miles + 0.5,
            "Longest distance driven between fuel stops.",
        ),
        Check(
            "stops",
            "Pickup and drop-off (1 hour each)",
            settings.pickup_minutes + settings.dropoff_minutes,
            sum(s.minutes for s in pickups + dropoffs),
            "minutes",
            stops_ok,
            "One pickup before one drop-off, each at least the configured duration.",
        ),
        Check(
            "continuity",
            "Continuous 24-hour record",
            0,
            gaps,
            "gaps",
            gaps == 0,
            "Every minute of the trip is assigned exactly one duty status.",
        ),
    ]
