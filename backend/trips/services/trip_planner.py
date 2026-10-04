"""Turns a trip request into a full plan: route, HOS schedule, stops, daily logs, audit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..hos import (
    ACTIVITY_LABELS,
    Activity,
    HOSRules,
    Place,
    Segment,
    Status,
    TripSettings,
    build_daily_logs,
    plan_trip,
    validate_plan,
)
from . import geocoding
from .places import get_index
from .routing import Route, get_route

WAYPOINT_KEYS = ("current", "pickup", "dropoff")
STOP_PRIORITY = (
    (Activity.PICKUP, "pickup", "Pickup"),
    (Activity.DROPOFF, "dropoff", "Drop-off"),
    (Activity.RESTART, "restart", "34-hour restart"),
    (Activity.REST, "rest", "10-hour rest"),
    (Activity.FUEL, "fuel", "Fuel stop"),
    (Activity.BREAK, "break", "30-minute break"),
    (Activity.PRE_TRIP, "start", "Pre-trip inspection"),
    (Activity.POST_TRIP, "end", "Post-trip inspection"),
)


@dataclass(frozen=True)
class LocationInput:
    label: str
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True)
class TripRequest:
    current: LocationInput
    pickup: LocationInput
    dropoff: LocationInput
    cycle_used_hours: float
    departure: datetime
    settings: TripSettings


def plan(request: TripRequest) -> dict:
    locations = {
        key: _resolve(location, key)
        for key, location in zip(WAYPOINT_KEYS, (request.current, request.pickup, request.dropoff))
    }
    names = [locations[key].label for key in WAYPOINT_KEYS]
    route = get_route([(locations[k].lat, locations[k].lon) for k in WAYPOINT_KEYS], names)

    rules, settings = HOSRules(), request.settings
    cycle_minutes = round(request.cycle_used_hours * 60)
    departure = request.departure.replace(second=0, microsecond=0)
    segments = plan_trip(
        [leg.profile for leg in route.legs],
        cycle_used_minutes=cycle_minutes,
        departure_minute_of_day=departure.hour * 60 + departure.minute,
        rules=rules,
        settings=settings,
    )
    checks = validate_plan(segments, cycle_used_minutes=cycle_minutes, rules=rules, settings=settings)
    labeler = _Labeler(route, names)
    places = [labeler.place_for(seg) for seg in segments]
    logs = build_daily_logs(
        segments,
        places,
        departure=departure,
        origin=Place(names[0], names[0]),
        destination=Place(names[2], names[2]),
        cycle_used_minutes=cycle_minutes,
        rules=rules,
    )

    at = lambda minute: (departure + timedelta(minutes=minute)).isoformat(timespec="minutes")  # noqa: E731
    return {
        "locations": {key: _location_json(locations[key]) for key in WAYPOINT_KEYS},
        "route": _route_json(route, names),
        "summary": _summary_json(segments, logs, route, cycle_minutes, departure, at),
        "timeline": [_segment_json(s, p, labeler, at) for s, p in zip(segments, places)],
        "stops": _stops_json(segments, places, labeler, at),
        "daily_logs": [_log_json(log) for log in logs],
        "compliance": {"passed": all(c.passed for c in checks), "checks": [c.as_dict() for c in checks]},
        "assumptions": _assumptions(settings, request.cycle_used_hours, route),
        "warnings": list(route.warnings),
    }


def _resolve(location: LocationInput, field: str) -> geocoding.GeoResult:
    if location.lat is not None and location.lon is not None:
        return geocoding.GeoResult(location.label, location.lat, location.lon, "point", "client")
    try:
        return geocoding.resolve(location.label)
    except geocoding.GeocodingError as exc:
        exc.field = f"{field}_location"
        raise


class _Labeler:
    """Names the place where each segment starts, for remarks and markers."""

    def __init__(self, route: Route, names: list[str]) -> None:
        self.route, self.names = route, names
        self.leg_miles = [leg.distance_miles for leg in route.legs]
        self.total = sum(self.leg_miles)
        self._cache: dict[tuple[float, float], Place] = {}

    def waypoint(self, miles: float) -> str | None:
        """Which of current / pickup / drop-off the driver is at, by trip mileage."""
        if miles <= 0.01:
            return "current" if self.leg_miles[0] > 0.01 else "pickup"
        if abs(miles - self.leg_miles[0]) <= 0.01:
            return "pickup"
        if abs(miles - self.total) <= 0.01:
            return "dropoff"
        return None

    def place_for(self, segment: Segment) -> Place:
        waypoint = self.waypoint(segment.miles_start)
        if waypoint is not None:
            name = self.names[WAYPOINT_KEYS.index(waypoint)]
            return Place(name, name)
        key = (round(segment.lat, 4), round(segment.lon, 4))
        if key not in self._cache:
            on_first_leg = segment.miles_start < self.leg_miles[0]
            leg = self.route.legs[0 if on_first_leg else 1]
            road = leg.road_at(segment.miles_start - (0 if on_first_leg else self.leg_miles[0]))
            label = get_index().describe(segment.lat, segment.lon, road or None)
            self._cache[key] = Place(label.short, label.detail)
        return self._cache[key]


# --------------------------------------------------------------------------- serialization


def _location_json(location: geocoding.GeoResult) -> dict:
    return {"label": location.label, "lat": location.lat, "lon": location.lon, "source": location.source}


def _route_json(route: Route, names: list[str]) -> dict:
    legs = []
    for i, leg in enumerate(route.legs):
        legs.append(
            {
                "from": names[i],
                "to": names[i + 1],
                "distance_miles": round(leg.distance_miles, 1),
                "drive_minutes": leg.drive_minutes,
                "summary": leg.summary,
                "geometry": leg.geometry(),
                "steps": [
                    {
                        "instruction": step.instruction,
                        "road": step.road,
                        "distance_miles": round(step.distance_miles, 2),
                        "duration_minutes": round(step.duration_minutes, 1),
                        "lat": round(step.lat, 5),
                        "lon": round(step.lon, 5),
                        "maneuver": step.maneuver,
                    }
                    for step in leg.steps
                ],
            }
        )
    return {
        "provider": route.provider,
        "profile": route.profile,
        "is_estimate": route.is_estimate,
        "distance_miles": round(sum(leg.distance_miles for leg in route.legs), 1),
        "drive_minutes": sum(leg.drive_minutes for leg in route.legs),
        "legs": legs,
    }


def _summary_json(segments, logs, route, cycle_minutes, departure, at) -> dict:
    minutes = {status: sum(s.minutes for s in segments if s.status is status) for status in Status}
    count = lambda activity: sum(1 for s in segments if s.activity is activity)  # noqa: E731
    dropoff = next(s for s in segments if s.activity is Activity.DROPOFF)
    pickup = next(s for s in segments if s.activity is Activity.PICKUP)
    driving_hours = minutes[Status.D] / 60
    miles = segments[-1].miles_end if segments else 0.0
    return {
        "departure": at(0),
        "pickup_arrival": at(pickup.start),
        "dropoff_arrival": at(dropoff.start),
        "trip_end": at(segments[-1].end),
        "total_minutes": segments[-1].end,
        "total_miles": round(miles, 1),
        "driving_minutes": minutes[Status.D],
        "on_duty_minutes": minutes[Status.ON],
        "off_duty_minutes": minutes[Status.OFF],
        "sleeper_minutes": minutes[Status.SB],
        "average_speed_mph": round(miles / driving_hours, 1) if driving_hours else 0.0,
        "log_days": len(logs),
        "fuel_stops": count(Activity.FUEL),
        "breaks": count(Activity.BREAK),
        "rests": count(Activity.REST),
        "restarts": count(Activity.RESTART),
        "cycle_used_start_minutes": cycle_minutes,
        "cycle_used_end_minutes": segments[-1].cycle_after,
        "cycle_available_end_minutes": max(0, HOSRules().cycle_limit - segments[-1].cycle_after),
    }


def _segment_json(segment: Segment, place: Place, labeler: _Labeler, at) -> dict:
    return {
        "status": segment.status.value,
        "activity": segment.activity.value,
        "label": ACTIVITY_LABELS[segment.activity],
        "start": at(segment.start),
        "end": at(segment.end),
        "offset_minutes": segment.start,
        "minutes": segment.minutes,
        "place": place.name,
        "place_detail": place.detail,
        "waypoint": labeler.waypoint(segment.miles_start),
        "lat": round(segment.lat, 5),
        "lon": round(segment.lon, 5),
        "end_lat": round(segment.end_lat, 5),
        "end_lon": round(segment.end_lon, 5),
        "miles_start": round(segment.miles_start, 1),
        "miles_end": round(segment.miles_end, 1),
        "cycle_after_minutes": segment.cycle_after,
        "leg": segment.leg,
    }


def _stops_json(segments: list[Segment], places: list[Place], labeler: _Labeler, at) -> list[dict]:
    """Consecutive non-driving segments at one spot form a stop (e.g. post-trip + rest + pre-trip)."""
    stops, group = [], []
    for segment, place in zip(segments + [None], places + [None]):
        if segment is not None and segment.status is not Status.D:
            group.append((segment, place))
            continue
        if group:
            stops.append(_stop_json(len(stops), group, labeler, at))
            group = []
    return stops


def _stop_json(index: int, group: list[tuple[Segment, Place]], labeler: _Labeler, at) -> dict:
    activities = {segment.activity for segment, _ in group}
    kind, title = next((k, t) for activity, k, t in STOP_PRIORITY if activity in activities)
    first, place = group[0]
    last = group[-1][0]
    return {
        "index": index,
        "type": kind,
        "title": title,
        "place": place.name,
        "place_detail": place.detail,
        "waypoint": labeler.waypoint(first.miles_start),
        "lat": round(first.lat, 5),
        "lon": round(first.lon, 5),
        "arrival": at(first.start),
        "departure": at(last.end),
        "minutes": last.end - first.start,
        "miles_from_start": round(first.miles_start, 1),
        "activities": [
            {
                "activity": segment.activity.value,
                "label": ACTIVITY_LABELS[segment.activity],
                "status": segment.status.value,
                "start": at(segment.start),
                "end": at(segment.end),
                "minutes": segment.minutes,
            }
            for segment, _ in group
        ],
    }


def _log_json(log) -> dict:
    place = lambda p: {"name": p.name, "detail": p.detail}  # noqa: E731
    return {
        "day": log.day,
        "date": log.date.isoformat(),
        "lines": [{"status": line.status.value, "start": line.start, "end": line.end} for line in log.lines],
        "totals": {status.value: minutes for status, minutes in log.totals.items()},
        "miles": round(log.miles, 1),
        "from": place(log.start_place),
        "to": place(log.end_place),
        "remarks": [
            {
                "minute": r.minute,
                "status": r.status.value,
                "activity": r.activity.value,
                "note": r.note,
                "place": r.place.name,
                "place_detail": r.place.detail,
            }
            for r in log.remarks
        ],
        "brackets": [{"start": b.start, "end": b.end, "place": b.place.name} for b in log.brackets],
        "recap": {
            "on_duty_today_minutes": log.on_duty_today,
            "cycle_total_minutes": log.cycle_total,
            "available_tomorrow_minutes": log.available_tomorrow,
            "restart_completed": log.restart_completed,
        },
        "legs": log.legs,
    }


def _assumptions(settings: TripSettings, cycle_hours: float, route: Route) -> list[str]:
    rest_line = "sleeper berth" if settings.rest_in_sleeper else "off duty"
    return [
        "Property-carrying driver on the 70-hour/8-day schedule; no adverse driving conditions.",
        f"Driver starts rested (10+ hours off) with {cycle_hours:g} h already used in the cycle. "
        "Those prior hours are kept in the 8-day window for the whole trip (conservative: we "
        "don't know which days they fell on).",
        f"Pickup {settings.pickup_minutes} min and drop-off {settings.dropoff_minutes} min, on duty (not driving).",
        f"Fuel at least every {settings.fuel_interval_miles:,.0f} miles; {settings.fuel_minutes} min on duty per stop.",
        f"{settings.pre_trip_minutes}-min pre-trip and {settings.post_trip_minutes}-min post-trip "
        "inspection each duty day (on duty).",
        f"10-hour rests logged in the {rest_line}; 34-hour restarts off duty; 30-minute breaks off duty.",
        f"Drive times: {route.provider}, {route.profile}.",
        "All times are home-terminal time, starting from the departure time entered.",
    ]
