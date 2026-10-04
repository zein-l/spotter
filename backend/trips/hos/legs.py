"""Route legs parametrised by driving time, implementing the planner's ``DriveLeg`` protocol."""

from __future__ import annotations

from bisect import bisect_left, bisect_right

MIN_DRIVING_MILES = 0.05  # anything shorter is treated as "already there"


class PolylineLeg:
    """A leg as a polyline with cumulative miles and driving time at every vertex.

    Driving time is rounded to whole minutes (the planner's resolution) and the per-vertex
    times are rescaled so the leg ends exactly on that minute.
    """

    def __init__(
        self,
        points: list[tuple[float, float]],
        cum_miles: list[float],
        cum_seconds: list[float],
    ) -> None:
        if not points or len(points) != len(cum_miles) or len(points) != len(cum_seconds):
            raise ValueError("points, cum_miles and cum_seconds must be equal, non-empty lists")
        self.points = points
        self.cum_miles = cum_miles
        miles, seconds = cum_miles[-1], cum_seconds[-1]
        if miles < MIN_DRIVING_MILES or len(points) < 2:
            self._total_minutes, self._total_miles = 0, 0.0
            self.cum_minutes = [0.0] * len(points)
            return
        self._total_minutes = max(1, round(seconds / 60))
        self._total_miles = miles
        if seconds > 0:
            scale = self._total_minutes / seconds
            self.cum_minutes = [s * scale for s in cum_seconds]
        else:  # no timing data: spread time evenly by distance
            self.cum_minutes = [m / miles * self._total_minutes for m in cum_miles]

    @classmethod
    def straight(
        cls,
        start: tuple[float, float],
        end: tuple[float, float],
        miles: float,
        minutes: float,
        vertices: int = 50,
    ) -> PolylineLeg:
        """Uniform-speed straight leg; used by tests and the offline demo router."""
        steps = max(1, vertices)
        points, cum_miles, cum_seconds = [], [], []
        for i in range(steps + 1):
            f = i / steps
            points.append((start[0] + (end[0] - start[0]) * f, start[1] + (end[1] - start[1]) * f))
            cum_miles.append(miles * f)
            cum_seconds.append(minutes * 60 * f)
        return cls(points, cum_miles, cum_seconds)

    @property
    def total_minutes(self) -> int:
        return self._total_minutes

    @property
    def total_miles(self) -> float:
        return self._total_miles

    def miles_at(self, minute: float) -> float:
        if self._total_minutes == 0 or minute <= 0:
            return 0.0
        if minute >= self._total_minutes:
            return self._total_miles
        return _interpolate(self.cum_minutes, self.cum_miles, minute)

    def minute_at_miles(self, miles: float) -> float:
        if self._total_minutes == 0 or miles <= 0:
            return 0.0
        if miles >= self._total_miles:
            return float(self._total_minutes)
        return _interpolate(self.cum_miles, self.cum_minutes, miles)

    def point_at(self, minute: float) -> tuple[float, float]:
        if self._total_minutes == 0 or minute <= 0:
            return self.points[0]
        if minute >= self._total_minutes:
            return self.points[-1]
        i, f = _locate(self.cum_minutes, minute)
        (lat0, lon0), (lat1, lon1) = self.points[i], self.points[i + 1]
        return lat0 + (lat1 - lat0) * f, lon0 + (lon1 - lon0) * f


def _locate(xs: list[float], x: float) -> tuple[int, float]:
    """Index of the segment [xs[i], xs[i+1]] containing x, and the fraction along it."""
    i = bisect_right(xs, x) - 1
    i = min(max(i, 0), len(xs) - 2)
    # Skip zero-length segments so the fraction is well defined.
    while i < len(xs) - 2 and xs[i + 1] <= xs[i]:
        i += 1
    span = xs[i + 1] - xs[i]
    return i, 0.0 if span <= 0 else min(1.0, max(0.0, (x - xs[i]) / span))


def _interpolate(xs: list[float], ys: list[float], x: float) -> float:
    i = bisect_left(xs, x)
    if i <= 0:
        return ys[0]
    if i >= len(xs):
        return ys[-1]
    span = xs[i] - xs[i - 1]
    if span <= 0:
        return ys[i]
    return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / span
