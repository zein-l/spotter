"""Small geodesy helpers. Coordinates are (lat, lon) in degrees unless noted."""

from __future__ import annotations

import math

EARTH_RADIUS_MILES = 3958.7613
METERS_PER_MILE = 1609.344
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(h)))


def bearing_degrees(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Initial bearing from a to b, 0 = north, clockwise."""
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass_point(bearing: float) -> str:
    return COMPASS[round(bearing / 45) % 8]


def simplify(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Douglas-Peucker in degree space (iterative, so long routes can't hit recursion limits)."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    tol2 = tolerance * tolerance
    while stack:
        first, last = stack.pop()
        (ay, ax), (by, bx) = points[first], points[last]
        dx, dy = bx - ax, by - ay
        norm = dx * dx + dy * dy
        worst, worst_d2 = -1, tol2
        for i in range(first + 1, last):
            py, px = points[i]
            if norm == 0:
                d2 = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / norm))
                d2 = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d2 > worst_d2:
                worst, worst_d2 = i, d2
        if worst > 0:
            keep[worst] = True
            stack.append((first, worst))
            stack.append((worst, last))
    return [p for p, k in zip(points, keep) if k]


def simplify_to_budget(points: list[tuple[float, float]], max_points: int) -> list[tuple[float, float]]:
    """Simplify until the line fits in ``max_points`` (keeps response payloads small)."""
    tolerance = 0.00005  # ~5 m
    simplified = simplify(points, tolerance)
    while len(simplified) > max_points:
        tolerance *= 2
        simplified = simplify(points, tolerance)
    return simplified
