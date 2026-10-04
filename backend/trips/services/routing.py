"""Truck routing.

Providers, tried in order:
  1. OpenRouteService ``driving-hgv`` (heavy-goods-vehicle profile) when ORS_API_KEY is set
     and ROUTING_PROVIDER=ors.
  2. OSRM: the public demo server, then the FOSSGIS mirror. Keyless.
  3. A straight-line estimate, flagged in the response, so an upstream outage degrades the
     plan instead of failing it (disable with ROUTING_ALLOW_ESTIMATE_FALLBACK=0).

Every leg is reduced to a ``PolylineLeg``: geometry with cumulative miles and driving time
at each vertex. OSRM's public profile is a car profile, so each step is slowed to at most
TRUCK_MAX_SPEED_MPH (a typical governed truck speed) before its time is spread over its
geometry.
"""

from __future__ import annotations

import hashlib
import logging
from bisect import bisect_right
from dataclasses import dataclass, field

from django.conf import settings
from django.core.cache import cache

from ..hos import PolylineLeg
from .geo import METERS_PER_MILE, bearing_degrees, haversine_miles, simplify_to_budget
from .http import UpstreamError, request_json
from .instructions import DIRECTIONS, normalize_ref, osrm_instruction, road_label, short_road

logger = logging.getLogger(__name__)

MPH_TO_MPS = 0.44704
ESTIMATE_CIRCUITY = 1.2  # road distance is ~1.2x great-circle distance in the US
ESTIMATE_SPEED_MPH = 55.0
GEOMETRY_POINT_BUDGET = 2500  # per leg, for the map
SAME_PLACE_MILES = 0.03
ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"
CACHE_SECONDS = 6 * 3600


class RoutingError(Exception):
    """No drivable route exists between the requested places (a user-facing problem)."""


@dataclass
class RouteStep:
    instruction: str
    road: str
    distance_miles: float
    duration_minutes: float
    lat: float
    lon: float
    maneuver: str


@dataclass
class RouteLeg:
    profile: PolylineLeg
    steps: list[RouteStep]
    summary: str
    step_start_miles: list[float] = field(default_factory=list)
    step_roads: list[str] = field(default_factory=list)

    @property
    def distance_miles(self) -> float:
        return self.profile.total_miles

    @property
    def drive_minutes(self) -> int:
        return self.profile.total_minutes

    def road_at(self, miles: float) -> str:
        """Short road name (e.g. 'I-44') being driven ``miles`` into the leg."""
        if not self.step_roads:
            return ""
        index = max(0, bisect_right(self.step_start_miles, miles) - 1)
        for road in reversed(self.step_roads[: index + 1]):  # fall back to the last named road
            if road:
                return road
        return ""

    def geometry(self) -> list[list[float]]:
        points = simplify_to_budget(self.profile.points, GEOMETRY_POINT_BUDGET)
        return [[round(lon, 5), round(lat, 5)] for lat, lon in points]


@dataclass
class Route:
    legs: list[RouteLeg]
    provider: str
    profile: str
    is_estimate: bool = False
    warnings: list[str] = field(default_factory=list)


def get_route(points: list[tuple[float, float]], names: list[str]) -> Route:
    """Route through ``points`` (lat, lon) in order; ``names`` label them in directions."""
    raw_key = "|".join(f"{lat:.5f},{lon:.5f},{name}" for (lat, lon), name in zip(points, names))
    key = "route:v1:" + hashlib.sha256(f"{settings.ROUTING_PROVIDER}|{raw_key}".encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached

    # Route only between distinct places; a zero-length leg (current location == pickup)
    # becomes an empty leg instead of a request some providers reject.
    distinct = [0] + [i for i in range(1, len(points)) if not _same_place(points[i - 1], points[i])]
    route = _compute([points[i] for i in distinct], [names[i] for i in distinct])
    legs = iter(route.legs)
    route.legs = [
        next(legs) if i in distinct else _empty_leg(points[i], names[i]) for i in range(1, len(points))
    ]
    if not route.is_estimate:
        cache.set(key, route, CACHE_SECONDS)
    return route


def _compute(points: list[tuple[float, float]], names: list[str]) -> Route:
    if len(points) < 2:
        return Route([], provider="none", profile="none")
    if settings.ROUTING_PROVIDER == "estimate":
        return estimate_route(points, names)
    failures = []
    if settings.ROUTING_PROVIDER == "ors" and settings.ORS_API_KEY:
        try:
            return ors_route(points, names)
        except UpstreamError as exc:
            failures.append(str(exc))
    for base in settings.OSRM_URLS:
        try:
            return osrm_route(base, points, names)
        except UpstreamError as exc:
            failures.append(str(exc))
    logger.error("All routing providers failed: %s", failures)
    if settings.ROUTING_ALLOW_ESTIMATE_FALLBACK:
        route = estimate_route(points, names)
        route.warnings.append(
            "Live road routing is temporarily unavailable, so distances are estimated "
            f"(straight line x {ESTIMATE_CIRCUITY}) at {ESTIMATE_SPEED_MPH:.0f} mph. "
            "Re-plan in a minute for the road route."
        )
        return route
    raise UpstreamError("Routing services are unavailable: " + "; ".join(failures))


# --------------------------------------------------------------------------- OSRM


def osrm_route(base_url: str, points: list[tuple[float, float]], names: list[str]) -> Route:
    coordinates = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    status, data = request_json(
        "GET",
        f"{base_url.rstrip('/')}/route/v1/driving/{coordinates}",
        params={"overview": "false", "steps": "true", "geometries": "geojson", "alternatives": "false"},
    )
    code = data.get("code") if isinstance(data, dict) else None
    if code == "Ok" and data.get("routes"):
        max_mps = settings.TRUCK_MAX_SPEED_MPH * MPH_TO_MPS
        legs = [
            parse_osrm_leg(leg, names[i + 1], points[i], max_mps)
            for i, leg in enumerate(data["routes"][0]["legs"])
        ]
        host = base_url.split("//")[-1].split("/")[0]
        return Route(legs, provider=f"OSRM ({host})", profile="road network, truck-speed capped")
    if code in ("NoRoute", "NoSegment"):
        raise RoutingError(
            "No drivable route connects these locations. Check that each one is reachable by road."
        )
    raise UpstreamError(f"OSRM returned {code or status}: {data.get('message', '') if isinstance(data, dict) else ''}")


def parse_osrm_leg(leg: dict, destination: str, origin: tuple[float, float], max_mps: float) -> RouteLeg:
    points: list[tuple[float, float]] = []
    cum_meters: list[float] = []
    cum_seconds: list[float] = []
    steps, step_start_miles, step_roads = [], [], []
    meters = seconds = 0.0
    for raw in leg.get("steps", []):
        distance = float(raw.get("distance", 0.0))
        duration = float(raw.get("duration", 0.0))
        if distance > 0:
            duration = max(duration, distance / max_mps)
        lon, lat = raw.get("maneuver", {}).get("location", (origin[1], origin[0]))
        steps.append(
            RouteStep(
                instruction=osrm_instruction(raw, destination),
                road=road_label(raw.get("name"), raw.get("ref")),
                distance_miles=distance / METERS_PER_MILE,
                duration_minutes=duration / 60,
                lat=lat,
                lon=lon,
                maneuver=raw.get("maneuver", {}).get("type", ""),
            )
        )
        step_start_miles.append(meters / METERS_PER_MILE)
        step_roads.append(short_road(raw.get("name"), raw.get("ref")))
        geometry = [(c[1], c[0]) for c in (raw.get("geometry") or {}).get("coordinates", [])]
        meters, seconds = _append_geometry(
            geometry, distance, duration, points, cum_meters, cum_seconds, meters, seconds
        )
    if not points:
        points, cum_meters, cum_seconds = [origin], [0.0], [0.0]
    profile = PolylineLeg(points, [m / METERS_PER_MILE for m in cum_meters], cum_seconds)
    summary = ", ".join(normalize_ref(part) for part in (leg.get("summary") or "").split(", ") if part)
    return RouteLeg(profile, steps, summary, step_start_miles, step_roads)


def _append_geometry(geometry, distance, duration, points, cum_meters, cum_seconds, meters, seconds):
    """Add a step's vertices, spreading its distance and time in proportion to length."""
    if not geometry:
        return meters, seconds
    if not points:
        points.append(geometry[0])
        cum_meters.append(meters)
        cum_seconds.append(seconds)
    lengths = [haversine_miles(a, b) for a, b in zip(geometry, geometry[1:])]
    total = sum(lengths)
    if total <= 0:
        if distance > 0:
            meters, seconds = meters + distance, seconds + duration
            points.append(geometry[-1])
            cum_meters.append(meters)
            cum_seconds.append(seconds)
        return meters, seconds
    for point, length in zip(geometry[1:], lengths):
        meters += distance * length / total
        seconds += duration * length / total
        points.append(point)
        cum_meters.append(meters)
        cum_seconds.append(seconds)
    return meters, seconds


# --------------------------------------------------------------------------- OpenRouteService


def ors_route(points: list[tuple[float, float]], names: list[str]) -> Route:
    status, data = request_json(
        "POST",
        ORS_URL,
        json={
            "coordinates": [[lon, lat] for lat, lon in points],
            "instructions": True,
            "geometry_simplify": False,
            "units": "m",
            "language": "en",
        },
        headers={"Authorization": settings.ORS_API_KEY, "Accept": "application/geo+json"},
    )
    if status != 200:
        error = data.get("error", {}) if isinstance(data, dict) else {}
        code = error.get("code") if isinstance(error, dict) else None
        if code in (2009, 2010):  # route not found / point not routable
            raise RoutingError("No truck route connects these locations.")
        raise UpstreamError(f"OpenRouteService returned HTTP {status}: {error}")
    feature = data["features"][0]
    coordinates = [(c[1], c[0]) for c in feature["geometry"]["coordinates"]]
    props = feature["properties"]
    way_points = props["way_points"]
    max_mps = settings.TRUCK_MAX_SPEED_MPH * MPH_TO_MPS
    legs = []
    for i, segment in enumerate(props["segments"]):
        pts: list[tuple[float, float]] = []
        cum_meters: list[float] = []
        cum_seconds: list[float] = []
        steps, step_start_miles, step_roads = [], [], []
        meters = seconds = 0.0
        for raw in segment.get("steps", []):
            distance = float(raw.get("distance", 0.0))
            duration = float(raw.get("duration", 0.0))
            if distance > 0:
                duration = max(duration, distance / max_mps)
            first, last = raw["way_points"]
            lat, lon = coordinates[first]
            name = raw.get("name", "") if raw.get("name") != "-" else ""
            steps.append(
                RouteStep(
                    instruction=raw.get("instruction", "Continue"),
                    road=name,
                    distance_miles=distance / METERS_PER_MILE,
                    duration_minutes=duration / 60,
                    lat=lat,
                    lon=lon,
                    maneuver=str(raw.get("type", "")),
                )
            )
            step_start_miles.append(meters / METERS_PER_MILE)
            step_roads.append(name)
            meters, seconds = _append_geometry(
                coordinates[first : last + 1], distance, duration, pts, cum_meters, cum_seconds, meters, seconds
            )
        if not pts:
            pts, cum_meters, cum_seconds = [coordinates[way_points[i]]], [0.0], [0.0]
        profile = PolylineLeg(pts, [m / METERS_PER_MILE for m in cum_meters], cum_seconds)
        legs.append(RouteLeg(profile, steps, "", step_start_miles, step_roads))
    return Route(legs, provider="OpenRouteService", profile="heavy goods vehicle (driving-hgv)")


# --------------------------------------------------------------------------- fallbacks


def estimate_route(points: list[tuple[float, float]], names: list[str]) -> Route:
    legs = []
    for (start, end), destination in zip(zip(points, points[1:]), names[1:]):
        miles = haversine_miles(start, end) * ESTIMATE_CIRCUITY
        minutes = miles / ESTIMATE_SPEED_MPH * 60
        profile = PolylineLeg.straight(start, end, miles, minutes, vertices=max(2, int(miles / 5)))
        heading = DIRECTIONS[round(bearing_degrees(start, end) / 45) % 8]
        steps = [
            RouteStep(f"Head {heading} toward {destination}", "", miles, minutes, start[0], start[1], "depart"),
            RouteStep(f"Arrive at {destination}", "", 0.0, 0.0, end[0], end[1], "arrive"),
        ]
        legs.append(RouteLeg(profile, steps, "", [0.0, miles], ["", ""]))
    return Route(legs, provider="Straight-line estimate", profile="estimate", is_estimate=True)


def _empty_leg(point: tuple[float, float], name: str) -> RouteLeg:
    profile = PolylineLeg([point], [0.0], [0.0])
    return RouteLeg(profile, [RouteStep(f"Already at {name}", "", 0.0, 0.0, point[0], point[1], "arrive")], "")


def _same_place(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return haversine_miles(a, b) <= SAME_PLACE_MILES
