"""Location search: Photon (OpenStreetMap, keyless) with the offline places index as backup."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass

from django.conf import settings
from django.core.cache import cache

from .http import UpstreamError, request_json
from .places import COUNTRY_NAMES, get_index, region_code

logger = logging.getLogger(__name__)

NORTH_AMERICA_BBOX = "-170,14,-50,72"  # minLon,minLat,maxLon,maxLat
PHOTON_TIMEOUT = (3, 4)
CACHE_SECONDS = 24 * 3600
TOWN_TYPES = {"city", "town", "village", "hamlet", "locality", "district", "county"}


class GeocodingError(Exception):
    """A location could not be found (user-facing)."""


@dataclass(frozen=True)
class GeoResult:
    label: str  # "Chicago, IL" / "1200 W Fulton Market, Chicago, IL"
    lat: float
    lon: float
    kind: str  # city | address | street | place | region
    source: str  # photon | places

    def as_dict(self) -> dict:
        return asdict(self)


def search(query: str, limit: int = 6) -> list[GeoResult]:
    query = " ".join(query.split())[:200]
    if len(query) < 2:
        return []
    raw_key = f"{settings.GEOCODER}:{limit}:{query.lower()}"
    key = "geocode:v1:" + hashlib.sha256(raw_key.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached

    results: list[GeoResult] = []
    if settings.GEOCODER == "photon":
        try:
            results = _photon_search(query, limit)
        except UpstreamError as exc:
            logger.warning("Photon search failed, using offline places: %s", exc)
    labels = {r.label.lower() for r in results}
    for town in get_index().search(query, limit):
        if len(results) >= limit:
            break
        if town.full_label.lower() not in labels:
            results.append(GeoResult(town.full_label, town.lat, town.lon, "city", "places"))
    cache.set(key, results, CACHE_SECONDS)
    return results


def resolve(query: str) -> GeoResult:
    """Best single match for free text the user didn't pick from the suggestions."""
    results = search(query, limit=1)
    if not results:
        raise GeocodingError(f'Could not find "{query}". Try a city and state, e.g. "Dallas, TX".')
    return results[0]


def reverse(lat: float, lon: float) -> GeoResult:
    if settings.GEOCODER == "photon":
        try:
            status, data = request_json(
                "GET",
                f"{settings.PHOTON_URL}/reverse",
                params={"lat": lat, "lon": lon, "limit": 1, "lang": "en"},
                timeout=PHOTON_TIMEOUT,
            )
            features = data.get("features", []) if status == 200 else []
            if features and (result := _from_photon(features[0])):
                return GeoResult(result.label, lat, lon, result.kind, "photon")
        except UpstreamError as exc:
            logger.warning("Photon reverse failed, using offline places: %s", exc)
    place = get_index().describe(lat, lon)
    return GeoResult(place.detail, lat, lon, "city", "places")


def _photon_search(query: str, limit: int) -> list[GeoResult]:
    status, data = request_json(
        "GET",
        f"{settings.PHOTON_URL}/api/",
        params={"q": query, "limit": limit + 2, "lang": "en", "bbox": NORTH_AMERICA_BBOX},
        timeout=PHOTON_TIMEOUT,
    )
    if status != 200 or not isinstance(data, dict):
        raise UpstreamError(f"Photon returned HTTP {status}")
    results, seen = [], set()
    for feature in data.get("features", []):
        result = _from_photon(feature)
        if result and result.label.lower() not in seen:
            seen.add(result.label.lower())
            results.append(result)
    return results[:limit]


def _from_photon(feature: dict) -> GeoResult | None:
    props = feature.get("properties", {})
    coords = (feature.get("geometry") or {}).get("coordinates")
    if not coords:
        return None
    country = props.get("countrycode")
    region = region_code(props.get("state"), country) or props.get("state")
    place_type = props.get("type", "")
    name = props.get("name", "")
    city = props.get("city") or props.get("town") or props.get("village") or props.get("county")

    if props.get("housenumber") and props.get("street"):
        head, kind = f"{props['housenumber']} {props['street']}", "address"
    elif place_type == "street":
        head, kind = name, "street"
    elif place_type in TOWN_TYPES:
        head, kind, city = name, "city", None
    elif place_type == "state":
        head, kind, region, city = name, "region", None, None
    elif place_type == "country":
        return None
    else:
        head, kind = name, "place"

    parts = [head, city if city and city != head else None, region]
    if country and country != "US":
        parts.append(COUNTRY_NAMES.get(country, props.get("country")))
    label = ", ".join(p for p in parts if p)
    if not label:
        return None
    return GeoResult(label, float(coords[1]), float(coords[0]), kind, "photon")
