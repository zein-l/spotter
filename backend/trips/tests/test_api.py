from unittest import mock

import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from trips.services.http import UpstreamError

from .helpers import CHICAGO, DALLAS, ST_LOUIS, coords, osrm_leg, osrm_response


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def osrm():
    response = 200, osrm_response(
        osrm_leg(coords(CHICAGO), coords(ST_LOUIS), mph=55, ref="I 55", summary="I 55"),
        osrm_leg(coords(ST_LOUIS), coords(DALLAS), mph=55, ref="I 44", summary="I 44"),
    )
    with mock.patch("trips.services.routing.request_json", return_value=response) as patched:
        yield patched


def trip(**overrides):
    body = {
        "current_location": CHICAGO,
        "pickup_location": ST_LOUIS,
        "dropoff_location": DALLAS,
        "current_cycle_used": 12,
        "departure": "2026-10-05T06:00",
    }
    body.update(overrides)
    return body


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_plan_returns_route_schedule_and_logs(client, osrm):
    response = client.post("/api/trips/plan", trip(), format="json")
    assert response.status_code == 200, response.json()
    data = response.json()
    assert set(data) == {
        "locations", "route", "summary", "timeline", "stops", "daily_logs", "compliance", "assumptions", "warnings",
    }
    assert data["compliance"]["passed"]
    assert len(data["route"]["legs"]) == 2 and data["route"]["legs"][1]["summary"] == "I-44"
    assert data["route"]["legs"][0]["geometry"][0] == pytest.approx([CHICAGO["lon"], CHICAGO["lat"]], abs=1e-4)
    assert data["summary"]["departure"] == "2026-10-05T06:00"
    assert data["summary"]["log_days"] == len(data["daily_logs"]) >= 2
    stop_types = [s["type"] for s in data["stops"]]
    assert stop_types[0] == "start" and "pickup" in stop_types and stop_types[-1] == "dropoff"
    assert "rest" in stop_types
    for log in data["daily_logs"]:
        assert sum(log["totals"].values()) == 1440
        assert log["lines"][0]["start"] == 0 and log["lines"][-1]["end"] == 1440
    total_miles = sum(log["miles"] for log in data["daily_logs"])
    assert total_miles == pytest.approx(data["route"]["distance_miles"], abs=0.5)


def test_stops_along_the_route_get_highway_remarks(client, osrm):
    data = client.post("/api/trips/plan", trip(), format="json").json()
    rest = next(s for s in data["stops"] if s["type"] == "rest")
    assert rest["place_detail"].startswith("I-44, ") or ", " in rest["place_detail"]
    assert rest["waypoint"] is None


def test_waypoint_labels_come_from_the_request(client, osrm):
    data = client.post("/api/trips/plan", trip(), format="json").json()
    pickup = next(s for s in data["stops"] if s["type"] == "pickup")
    assert pickup["place"] == "St. Louis, MO" and pickup["waypoint"] == "pickup"
    assert data["daily_logs"][0]["remarks"][0]["place"] == "Chicago, IL"


def test_options_change_the_plan(client, osrm):
    data = client.post(
        "/api/trips/plan",
        trip(options={"pre_trip_minutes": 0, "post_trip_minutes": 0, "rest_in_sleeper": False}),
        format="json",
    ).json()
    activities = {t["activity"] for t in data["timeline"]}
    assert "pre_trip" not in activities and "post_trip" not in activities
    assert all(t["status"] == "OFF" for t in data["timeline"] if t["activity"] == "rest")


def test_high_cycle_triggers_restart(client, osrm):
    data = client.post("/api/trips/plan", trip(current_cycle_used=69), format="json").json()
    assert data["summary"]["restarts"] == 1
    assert data["compliance"]["passed"]


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"current_cycle_used": 71}, "current_cycle_used"),
        ({"current_cycle_used": -1}, "current_cycle_used"),
        ({"pickup_location": {"label": ""}}, "pickup_location"),
        ({"dropoff_location": {"label": "Dallas", "lat": 32.7}}, "dropoff_location"),
        ({"departure": "next tuesday"}, "departure"),
    ],
)
def test_validation_errors_name_the_field(client, overrides, field):
    response = client.post("/api/trips/plan", trip(**overrides), format="json")
    assert response.status_code == 400
    body = response.json()
    assert body["field"] == field and body["detail"]


def test_pickup_and_dropoff_must_differ(client):
    response = client.post("/api/trips/plan", trip(dropoff_location=ST_LOUIS), format="json")
    assert response.status_code == 422
    assert response.json()["field"] == "dropoff_location"


@override_settings(GEOCODER="offline")
def test_unknown_place_is_a_422_on_that_field(client):
    response = client.post("/api/trips/plan", trip(pickup_location={"label": "Qwertyzzz Nowhere"}), format="json")
    assert response.status_code == 422
    assert response.json()["field"] == "pickup_location"


@override_settings(GEOCODER="offline")
def test_free_text_locations_are_geocoded(client, osrm):
    body = trip(current_location={"label": "Chicago, IL"}, pickup_location={"label": "St. Louis, MO"})
    data = client.post("/api/trips/plan", body, format="json").json()
    assert data["locations"]["current"]["source"] == "places"
    assert data["locations"]["pickup"]["label"] == "St. Louis, MO"


@override_settings(ROUTING_ALLOW_ESTIMATE_FALLBACK=False)
def test_routing_outage_is_a_503(client):
    with mock.patch("trips.services.routing.request_json", side_effect=UpstreamError("down")):
        response = client.post("/api/trips/plan", trip(), format="json")
    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]


def test_routing_outage_degrades_to_an_estimate(client):
    with mock.patch("trips.services.routing.request_json", side_effect=UpstreamError("down")):
        data = client.post("/api/trips/plan", trip(), format="json").json()
    assert data["route"]["is_estimate"] and data["warnings"]
    assert data["compliance"]["passed"]


@override_settings(GEOCODER="offline")
def test_geocode_autocomplete(client):
    results = client.get("/api/geocode", {"q": "Dallas"}).json()["results"]
    assert results[0]["label"] == "Dallas, TX"
    assert client.get("/api/geocode", {"q": "D"}).json()["results"] == []


@override_settings(GEOCODER="offline")
def test_reverse_geocode(client):
    assert client.get("/api/reverse-geocode", {"lat": 32.78, "lon": -96.80}).json()["result"]["label"] == "Dallas, TX"
    assert client.get("/api/reverse-geocode", {"lat": 200, "lon": 0}).status_code == 400


def test_zero_minute_stops_are_rejected_not_a_500(client, osrm):
    response = client.post("/api/trips/plan", trip(options={"pickup_minutes": 0, "dropoff_minutes": 0}), format="json")
    assert response.status_code == 400
    assert response.json()["field"] == "options"


def test_shortest_allowed_stops_plan(client, osrm):
    data = client.post("/api/trips/plan", trip(options={"pickup_minutes": 15, "dropoff_minutes": 15}), format="json").json()
    assert data["compliance"]["passed"]
