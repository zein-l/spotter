"""Builders for upstream API payloads used across tests."""

import json
from pathlib import Path

from trips.services.geo import METERS_PER_MILE, haversine_miles

FIXTURES = Path(__file__).parent / "fixtures"

CHICAGO = {"label": "Chicago, IL", "lat": 41.8781, "lon": -87.6298}
ST_LOUIS = {"label": "St. Louis, MO", "lat": 38.6270, "lon": -90.1994}
DALLAS = {"label": "Dallas, TX", "lat": 32.7767, "lon": -96.7970}


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def osrm_step(points, mph, name="", ref="", kind="continue", modifier="straight"):
    """One OSRM step along ``points`` [(lat, lon), ...] driven at ``mph``."""
    miles = sum(haversine_miles(a, b) for a, b in zip(points, points[1:]))
    return {
        "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in points]},
        "maneuver": {"type": kind, "modifier": modifier, "location": [points[0][1], points[0][0]], "bearing_after": 180},
        "name": name,
        "ref": ref,
        "distance": miles * METERS_PER_MILE,
        "duration": miles / mph * 3600 if mph else 0,
    }


def osrm_leg(start, end, mph=60, ref="I 55", pieces=20, summary="I 55"):
    """A leg from start to end as depart + highway + arrive steps."""
    points = [
        (start[0] + (end[0] - start[0]) * i / pieces, start[1] + (end[1] - start[1]) * i / pieces)
        for i in range(pieces + 1)
    ]
    steps = [
        osrm_step(points[:2], 30, name="Main Street", kind="depart", modifier=""),
        osrm_step(points[1:], mph, name="", ref=ref, kind="on ramp", modifier="slight right"),
        osrm_step([points[-1], points[-1]], 0, kind="arrive", modifier="right"),
    ]
    return {"steps": steps, "summary": summary, "distance": sum(s["distance"] for s in steps)}


def osrm_response(*legs):
    return {"code": "Ok", "routes": [{"legs": list(legs)}], "waypoints": []}


def coords(place):
    return place["lat"], place["lon"]
