from unittest import mock

import pytest
from django.core.cache import cache
from django.test import override_settings

from trips.services import geocoding, routing
from trips.services.http import UpstreamError
from trips.services.instructions import normalize_ref, road_label
from trips.services.places import get_index

from .helpers import CHICAGO, DALLAS, ST_LOUIS, coords, fixture, osrm_leg, osrm_response


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def fake_upstream(handlers):
    """Patch request_json; ``handlers`` maps a URL substring to a response or exception."""

    def handle(method, url, **kwargs):
        for fragment, outcome in handlers.items():
            if fragment in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        raise AssertionError(f"unexpected request to {url}")

    return handle


class TestOsrmParsing:
    def test_real_response_is_parsed(self):
        leg = routing.parse_osrm_leg(fixture("osrm_chicago_loop.json")["routes"][0]["legs"][0], "Grant Park", (41.8781, -87.6298), 29.06)
        assert leg.distance_miles == pytest.approx(985.9 / 1609.344, rel=0.01)
        assert leg.drive_minutes == 2
        instructions = [s.instruction for s in leg.steps]
        assert instructions[0] == "Head north on South Federal Street"
        assert instructions[1] == "Turn right onto US-66 Hist (West Jackson Boulevard)"
        assert instructions[2] == "Turn left onto South Dearborn Street"
        assert instructions[-1] == "Arrive at Grant Park, on the right" or instructions[-1].startswith("Arrive at Grant Park")
        assert leg.profile.points[0] == pytest.approx((41.878101, -87.629771))
        assert leg.profile.points[-1] == pytest.approx((41.882718, -87.624095))

    def test_highway_speed_is_capped_for_trucks(self):
        raw = osrm_leg(coords(CHICAGO), coords(ST_LOUIS), mph=80)
        leg = routing.parse_osrm_leg(raw, "St. Louis", coords(CHICAGO), max_mps=65 * 0.44704)
        highway_miles = raw["steps"][1]["distance"] / 1609.344
        assert leg.drive_minutes == pytest.approx(highway_miles / 65 * 60 + raw["steps"][0]["duration"] / 60, abs=1)

    def test_time_is_spread_along_geometry(self):
        # A 30 mph city step, then a 60 mph highway step: 1 mile per minute on the highway.
        leg = routing.parse_osrm_leg(osrm_leg(coords(CHICAGO), coords(ST_LOUIS), mph=60), "St. Louis", coords(CHICAGO), 40)
        on_highway = [leg.profile.miles_at(t) for t in (100, 160, 220)]
        assert on_highway[1] - on_highway[0] == pytest.approx(60, rel=0.01)
        assert on_highway[2] - on_highway[1] == pytest.approx(60, rel=0.01)
        city_miles = leg.distance_miles / 20
        assert leg.profile.minute_at_miles(city_miles) == pytest.approx(city_miles / 30 * 60, rel=0.02)
        lat, lon = leg.profile.point_at(leg.drive_minutes)
        assert (lat, lon) == pytest.approx(coords(ST_LOUIS), abs=1e-6)

    def test_road_lookup_for_remarks(self):
        leg = routing.parse_osrm_leg(osrm_leg(coords(CHICAGO), coords(ST_LOUIS)), "St. Louis", coords(CHICAGO), 40)
        assert leg.road_at(0.0) == "Main Street"
        assert leg.road_at(leg.distance_miles / 2) == "I-55"

    def test_reference_formatting(self):
        assert normalize_ref("I 55;US 66") == "I-55/US-66"
        assert road_label("Stevenson Expressway", "I 55") == "I-55 (Stevenson Expressway)"
        assert road_label("", "I 44") == "I-44"


class TestRouteProviders:
    points = [coords(CHICAGO), coords(ST_LOUIS), coords(DALLAS)]
    names = ["Chicago", "St. Louis", "Dallas"]

    def good_response(self):
        return 200, osrm_response(
            osrm_leg(coords(CHICAGO), coords(ST_LOUIS)), osrm_leg(coords(ST_LOUIS), coords(DALLAS), ref="I 44")
        )

    def test_primary_osrm_server(self):
        with mock.patch("trips.services.routing.request_json", side_effect=fake_upstream({"project-osrm": self.good_response()})):
            route = routing.get_route(self.points, self.names)
        assert route.provider == "OSRM (router.project-osrm.org)"
        assert not route.is_estimate and len(route.legs) == 2

    def test_falls_back_to_mirror(self):
        handlers = {"project-osrm": UpstreamError("down"), "openstreetmap.de": self.good_response()}
        with mock.patch("trips.services.routing.request_json", side_effect=fake_upstream(handlers)):
            route = routing.get_route(self.points, self.names)
        assert route.provider == "OSRM (routing.openstreetmap.de)"

    def test_falls_back_to_flagged_estimate(self):
        handlers = {"project-osrm": UpstreamError("down"), "openstreetmap.de": UpstreamError("down")}
        with mock.patch("trips.services.routing.request_json", side_effect=fake_upstream(handlers)):
            route = routing.get_route(self.points, self.names)
        assert route.is_estimate and route.warnings
        assert route.legs[0].distance_miles == pytest.approx(258 * 1.2, rel=0.05)

    @override_settings(ROUTING_ALLOW_ESTIMATE_FALLBACK=False)
    def test_outage_surfaces_when_estimates_disabled(self):
        handlers = {"project-osrm": UpstreamError("down"), "openstreetmap.de": UpstreamError("down")}
        with mock.patch("trips.services.routing.request_json", side_effect=fake_upstream(handlers)):
            with pytest.raises(UpstreamError):
                routing.get_route(self.points, self.names)

    def test_no_route_is_a_user_error_not_retried(self):
        calls = []

        def handle(method, url, **kwargs):
            calls.append(url)
            return 400, {"code": "NoRoute", "message": "Impossible route"}

        with mock.patch("trips.services.routing.request_json", side_effect=handle):
            with pytest.raises(routing.RoutingError):
                routing.get_route(self.points, self.names)
        assert len(calls) == 1

    def test_current_location_at_pickup_routes_once(self):
        response = 200, osrm_response(osrm_leg(coords(ST_LOUIS), coords(DALLAS)))
        with mock.patch("trips.services.routing.request_json", side_effect=fake_upstream({"project-osrm": response})) as call:
            route = routing.get_route([coords(ST_LOUIS), coords(ST_LOUIS), coords(DALLAS)], self.names)
        assert call.call_count == 1
        assert route.legs[0].distance_miles == 0 and route.legs[0].drive_minutes == 0
        assert route.legs[1].distance_miles > 0

    def test_routes_are_cached(self):
        with mock.patch("trips.services.routing.request_json", side_effect=fake_upstream({"project-osrm": self.good_response()})) as call:
            routing.get_route(self.points, self.names)
            routing.get_route(self.points, self.names)
        assert call.call_count == 1

    @override_settings(ROUTING_PROVIDER="ors", ORS_API_KEY="test-key")
    def test_openrouteservice_hgv_profile(self):
        coordinates = [[-87.63, 41.88], [-88.9, 40.3], [-90.2, 38.63], [-93.5, 35.7], [-96.8, 32.78]]
        body = {
            "features": [
                {
                    "geometry": {"coordinates": coordinates},
                    "properties": {
                        "way_points": [0, 2, 4],
                        "segments": [
                            {"steps": [
                                {"distance": 470000, "duration": 18000, "instruction": "Head south on I 55", "name": "I 55", "way_points": [0, 2], "type": 11},
                                {"distance": 0, "duration": 0, "instruction": "Arrive", "name": "-", "way_points": [2, 2], "type": 10},
                            ]},
                            {"steps": [
                                {"distance": 1000000, "duration": 40000, "instruction": "Head southwest on I 44", "name": "I 44", "way_points": [2, 4], "type": 11},
                            ]},
                        ],
                    },
                }
            ]
        }
        with mock.patch("trips.services.routing.request_json", side_effect=fake_upstream({"openrouteservice": (200, body)})):
            route = routing.get_route(self.points, self.names)
        assert route.provider == "OpenRouteService"
        assert route.legs[0].distance_miles == pytest.approx(470000 / 1609.344, rel=1e-3)
        assert route.legs[1].drive_minutes == round(40000 / 60)
        assert route.legs[1].steps[0].instruction == "Head southwest on I 44"
        assert route.legs[0].road_at(10) == "I 55"


class TestGeocoding:
    def test_photon_results_are_labelled_with_state_codes(self):
        response = (200, fixture("photon_springfield.json"))
        with mock.patch("trips.services.geocoding.request_json", return_value=response):
            results = geocoding.search("Springfield", limit=3)
        assert [r.label for r in results] == ["Springfield, MA", "Springfield, IL", "Springfield, MO"]
        assert results[1].lat == pytest.approx(39.799, abs=1e-3)
        assert all(r.source == "photon" for r in results)

    def test_offline_places_fill_in_when_photon_is_down(self):
        with mock.patch("trips.services.geocoding.request_json", side_effect=UpstreamError("down")):
            results = geocoding.search("Springfield, IL")
        assert results[0].label == "Springfield, IL" and results[0].source == "places"

    def test_reverse_geocode_formats_an_address(self):
        response = (200, fixture("photon_reverse_house.json"))
        with mock.patch("trips.services.geocoding.request_json", return_value=response):
            result = geocoding.reverse(39.7817, -89.6501)
        assert result.label == "1801 South 5th Street, Springfield, IL"

    @override_settings(GEOCODER="offline")
    def test_unknown_place_raises(self):
        with pytest.raises(geocoding.GeocodingError):
            geocoding.resolve("Qwertyzzz Nowhere")


class TestPlaces:
    @pytest.mark.parametrize(
        "query,expected",
        [
            ("Chicago", "Chicago, IL"),
            ("springfield mo", "Springfield, MO"),
            ("Dallas, Texas", "Dallas, TX"),
            ("albany new york", "Albany, NY"),
            ("Kansas City, MO", "Kansas City, MO"),
            ("Montreal", "Montréal, QC, Canada"),
            ("Monterrey, NL", "Monterrey, NL, Mexico"),
            ("Laredo, TX, USA", "Laredo, TX"),
        ],
    )
    def test_search(self, query, expected):
        assert get_index().search(query, 1)[0].full_label == expected

    @pytest.mark.parametrize(
        "lat,lon,road,expected",
        [
            (41.88, -87.63, None, "Chicago, IL"),  # downtown, not a neighbourhood
            (41.85, -87.75, None, "Cicero, IL"),  # the suburb, not the big city next door
            (37.8, -91.9, "I-44", "I-44, 10 mi S of Doolittle, MO"),
            (35.0, -115.5, "I-40", "I-40, 37 mi SE of Baker, CA"),
        ],
    )
    def test_describe(self, lat, lon, road, expected):
        assert get_index().describe(lat, lon, road).detail == expected
