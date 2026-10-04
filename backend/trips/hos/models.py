"""Domain types for the hours-of-service engine.

All times inside the engine are integer minutes measured from the planned departure,
which keeps every limit comparison exact (no floating-point drift at the 11:00 mark).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Status(str, Enum):
    """The four duty-status lines of the record of duty status (49 CFR 395.8)."""

    OFF = "OFF"  # Line 1: off duty
    SB = "SB"  # Line 2: sleeper berth
    D = "D"  # Line 3: driving
    ON = "ON"  # Line 4: on duty, not driving

    @property
    def is_on_duty(self) -> bool:
        return self in (Status.D, Status.ON)

    @property
    def is_off_duty(self) -> bool:
        return self in (Status.OFF, Status.SB)


class Activity(str, Enum):
    """What the driver is doing during a segment; drives remarks and map markers."""

    OFF_DUTY = "off_duty"  # time on the sheet before departure / after the trip ends
    PRE_TRIP = "pre_trip"
    DRIVE = "drive"
    PICKUP = "pickup"
    DROPOFF = "dropoff"
    FUEL = "fuel"
    BREAK = "break"  # 30-minute break required after 8 hours of driving
    REST = "rest"  # 10 consecutive hours off duty (sleeper berth)
    RESTART = "restart"  # 34 consecutive hours off duty, resets the 70-hour cycle
    POST_TRIP = "post_trip"


ACTIVITY_LABELS = {
    Activity.OFF_DUTY: "Off duty",
    Activity.PRE_TRIP: "Pre-trip inspection",
    Activity.DRIVE: "Driving",
    Activity.PICKUP: "Pickup (loading)",
    Activity.DROPOFF: "Drop-off (unloading)",
    Activity.FUEL: "Fueling",
    Activity.BREAK: "30-minute break",
    Activity.REST: "10-hour rest",
    Activity.RESTART: "34-hour restart",
    Activity.POST_TRIP: "Post-trip inspection",
}


@dataclass(frozen=True)
class HOSRules:
    """Property-carrying driver limits, 70-hour/8-day schedule (49 CFR 395.3)."""

    max_driving: int = 11 * 60  # 395.3(a)(3): 11 hours driving after 10 off
    duty_window: int = 14 * 60  # 395.3(a)(2): no driving after the 14th hour on duty
    driving_before_break: int = 8 * 60  # 395.3(a)(3)(ii): 30-min break after 8h driving
    min_break: int = 30
    reset_off_duty: int = 10 * 60  # 10 consecutive hours off resets 11/14
    cycle_limit: int = 70 * 60  # 395.3(b): 70 hours on duty in 8 days
    restart_off_duty: int = 34 * 60  # 395.3(c): 34-hour restart


@dataclass(frozen=True)
class TripSettings:
    """Assumptions from the assessment plus operational defaults (all overridable)."""

    pickup_minutes: int = 60
    dropoff_minutes: int = 60
    fuel_interval_miles: float = 1000.0
    fuel_minutes: int = 30
    pre_trip_minutes: int = 30
    post_trip_minutes: int = 15
    break_minutes: int = 30
    rest_in_sleeper: bool = True  # log 10-hour rests on line 2 (sleeper berth)
    # Don't start a drive shorter than this right before a mandatory stop; stop now instead.
    min_drive_minutes: int = 15


class DriveLeg(Protocol):
    """A drivable leg reduced to what the planner needs: time <-> distance <-> position."""

    @property
    def total_minutes(self) -> int: ...

    @property
    def total_miles(self) -> float: ...

    def miles_at(self, minute: float) -> float: ...

    def minute_at_miles(self, miles: float) -> float: ...

    def point_at(self, minute: float) -> tuple[float, float]: ...


@dataclass
class Segment:
    """A contiguous stretch of one duty status / activity."""

    status: Status
    activity: Activity
    start: int  # minutes since departure
    end: int
    lat: float
    lon: float
    end_lat: float
    end_lon: float
    miles_start: float  # cumulative trip miles
    miles_end: float
    cycle_after: int  # on-duty minutes counted in the 70-hour window when the segment ends
    leg: int | None = None  # 0 = to pickup, 1 = to drop-off

    @property
    def minutes(self) -> int:
        return self.end - self.start

    @property
    def miles(self) -> float:
        return self.miles_end - self.miles_start
