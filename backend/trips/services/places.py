"""Offline index of ~33,500 North American towns (GeoNames cities500, CC BY 4.0).

Used to label stops along the route ("I-44, 12 mi SW of Rolla, MO") without calling a
rate-limited reverse geocoder for every stop, and as a geocoding fallback for city names.
"""

from __future__ import annotations

import gzip
import math
import re
import unicodedata
from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .geo import bearing_degrees, compass_point, haversine_miles

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "places_na.tsv.gz"
CELL_DEGREES = 0.5
MAX_SEARCH_RINGS = 8

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}
CA_PROVINCES = {
    "alberta": "AB", "british columbia": "BC", "manitoba": "MB", "new brunswick": "NB",
    "newfoundland and labrador": "NL", "nova scotia": "NS", "ontario": "ON",
    "prince edward island": "PE", "quebec": "QC", "saskatchewan": "SK", "yukon": "YT",
    "northwest territories": "NT", "nunavut": "NU",
}
MX_STATES = {
    "aguascalientes": "AGS", "baja california": "BC", "baja california sur": "BCS",
    "campeche": "CAMP", "chiapas": "CHIS", "chihuahua": "CHIH", "coahuila": "COAH",
    "colima": "COL", "ciudad de mexico": "CDMX", "mexico city": "CDMX", "durango": "DGO",
    "guanajuato": "GTO", "guerrero": "GRO", "hidalgo": "HGO", "jalisco": "JAL", "mexico": "MEX",
    "estado de mexico": "MEX", "michoacan": "MICH", "morelos": "MOR", "nayarit": "NAY",
    "nuevo leon": "NL", "oaxaca": "OAX", "puebla": "PUE", "queretaro": "QRO",
    "quintana roo": "QROO", "san luis potosi": "SLP", "sinaloa": "SIN", "sonora": "SON",
    "tabasco": "TAB", "tamaulipas": "TAMPS", "tlaxcala": "TLAX", "veracruz": "VER",
    "yucatan": "YUC", "zacatecas": "ZAC",
}
REGION_NAMES = {"US": US_STATES, "CA": CA_PROVINCES, "MX": MX_STATES}
COUNTRY_NAMES = {"US": "United States", "CA": "Canada", "MX": "Mexico"}
COUNTRY_ALIASES = {"usa", "us", "united states", "united states of america", "canada", "mexico"}


def fold(text: str) -> str:
    """Lowercase ASCII form for matching ("Montréal" -> "montreal")."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9, ]+", " ", text).strip()


def region_code(region_name: str | None, country_code: str | None) -> str | None:
    """'Illinois' -> 'IL' (US, Canada and Mexico); None when unknown."""
    if not region_name:
        return None
    folded = fold(region_name)
    tables = [REGION_NAMES[country_code]] if country_code in REGION_NAMES else REGION_NAMES.values()
    for table in tables:
        if folded in table:
            return table[folded]
    return None


@dataclass(frozen=True)
class Town:
    name: str
    region: str
    country: str
    lat: float
    lon: float
    population: int

    @property
    def label(self) -> str:
        return f"{self.name}, {self.region}"

    @property
    def full_label(self) -> str:
        return self.label if self.country == "US" else f"{self.label}, {COUNTRY_NAMES[self.country]}"

    @property
    def radius_miles(self) -> float:
        """Rough town radius from population (~4,000 people per square mile)."""
        return max(1.0, math.sqrt(self.population / (4000 * math.pi)))


@dataclass(frozen=True)
class PlaceLabel:
    short: str  # "Rolla, MO"
    detail: str  # "I-44, 12 mi SW of Rolla, MO"


class PlacesIndex:
    def __init__(self, towns: list[Town]) -> None:
        self.towns = towns
        self.grid: dict[tuple[int, int], list[int]] = {}
        for i, town in enumerate(towns):
            self.grid.setdefault(_cell(town.lat, town.lon), []).append(i)
        self._sorted_names = sorted((fold(t.name), i) for i, t in enumerate(towns))
        self._names = [name for name, _ in self._sorted_names]

    # -- reverse lookup -------------------------------------------------------------
    def nearest(self, lat: float, lon: float) -> tuple[Town, float] | None:
        ci, cj = _cell(lat, lon)
        point = (lat, lon)
        cell_miles = _cell_miles(lat)
        best: tuple[Town, float] | None = None
        for ring in range(MAX_SEARCH_RINGS + 1):
            for key in _ring(ci, cj, ring):
                for index in self.grid.get(key, ()):
                    town = self.towns[index]
                    miles = haversine_miles(point, (town.lat, town.lon))
                    if best is None or miles < best[1]:
                        best = (town, miles)
            # Anything in the next ring is at least `ring` cells away.
            if best is not None and best[1] <= ring * cell_miles:
                break
        return best

    def within(self, lat: float, lon: float, radius_miles: float) -> list[tuple[Town, float]]:
        ci, cj = _cell(lat, lon)
        rings = min(MAX_SEARCH_RINGS, math.ceil(radius_miles / _cell_miles(lat)))
        found = []
        for ring in range(rings + 1):
            for key in _ring(ci, cj, ring):
                for index in self.grid.get(key, ()):
                    town = self.towns[index]
                    miles = haversine_miles((lat, lon), (town.lat, town.lon))
                    if miles <= radius_miles:
                        found.append((town, miles))
        return found

    def describe(self, lat: float, lon: float, road: str | None = None) -> PlaceLabel:
        """Remark-style location per 395.8(c): the town, or the highway and nearest town."""
        # Inside a town's footprint: pick the one the point sits most centrally in, so
        # downtown Chicago reads "Chicago, IL" rather than a neighbourhood, while a suburb
        # (small radius, but much closer) still wins over the big city next door.
        inside = [(t, d) for t, d in self.within(lat, lon, 35) if d <= t.radius_miles]
        if inside:
            town = min(inside, key=lambda td: td[1] / td[0].radius_miles)[0]
            return PlaceLabel(town.label, town.label)
        found = self.nearest(lat, lon)
        if found is None:
            text = _format_coordinates(lat, lon)
            return PlaceLabel(text, f"{road}, {text}" if road else text)
        town, miles = found
        direction = compass_point(bearing_degrees((town.lat, town.lon), (lat, lon)))
        relative = f"{miles:.0f} mi {direction} of {town.label}"
        return PlaceLabel(town.label, f"{road}, {relative}" if road else relative)

    # -- forward search -------------------------------------------------------------
    def search(self, query: str, limit: int = 6) -> list[Town]:
        name, region = _parse_query(query)
        if not name:
            return []
        start = bisect_left(self._names, name)
        matches: list[int] = []
        for folded, index in self._sorted_names[start:]:
            if not folded.startswith(name):
                break
            matches.append(index)
        if len(matches) < limit:  # also match later words: "york" -> "New York City"
            needle, seen = " " + name, set(matches)
            matches += [i for folded, i in self._sorted_names if needle in folded and i not in seen]
        towns = [self.towns[i] for i in matches]
        if region:
            towns = [t for t in towns if t.region == region]
        towns.sort(key=lambda t: (fold(t.name) != name, -t.population))
        return towns[:limit]


def _parse_query(query: str) -> tuple[str, str | None]:
    """'Springfield, IL' / 'springfield illinois' -> ('springfield', 'IL')."""
    parts = [p.strip() for p in fold(query).split(",") if p.strip()]
    parts = [p for p in parts if p not in COUNTRY_ALIASES]
    if not parts:
        return "", None
    name, region = parts[0], None
    if len(parts) > 1:
        region = _region_from_text(parts[1])
    else:
        words = name.split()
        for size in (3, 2, 1):  # trailing region: "san antonio tx", "albany new york"
            if len(words) > size and (code := _region_from_text(" ".join(words[-size:]))):
                name, region = " ".join(words[:-size]), code
                break
    return name, region


def _region_from_text(text: str) -> str | None:
    upper = text.upper()
    for table in REGION_NAMES.values():
        if text in table:
            return table[text]
        if upper in table.values():
            return upper
    return None


def _cell_miles(lat: float) -> float:
    """Smallest side of a grid cell at this latitude."""
    return CELL_DEGREES * 69.0 * max(0.2, math.cos(math.radians(lat)))


def _cell(lat: float, lon: float) -> tuple[int, int]:
    return math.floor(lat / CELL_DEGREES), math.floor(lon / CELL_DEGREES)


def _ring(ci: int, cj: int, ring: int):
    if ring == 0:
        yield ci, cj
        return
    for di in range(-ring, ring + 1):
        for dj in (-ring, ring) if abs(di) != ring else range(-ring, ring + 1):
            yield ci + di, cj + dj


def _format_coordinates(lat: float, lon: float) -> str:
    return f"{abs(lat):.3f}°{'N' if lat >= 0 else 'S'}, {abs(lon):.3f}°{'W' if lon < 0 else 'E'}"


@lru_cache(maxsize=1)
def get_index() -> PlacesIndex:
    towns = []
    with gzip.open(DATA_FILE, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            name, region, country, lat, lon, population, _tz = line.rstrip("\n").split("\t")
            towns.append(Town(name, region, country, float(lat), float(lon), int(population)))
    return PlacesIndex(towns)
