from django.conf import settings
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .serializers import TripPlanSerializer
from .services import geocoding, trip_planner


class HealthView(APIView):
    def get(self, request):
        return Response(
            {
                "status": "ok",
                "routing_provider": settings.ROUTING_PROVIDER,
                "geocoder": settings.GEOCODER,
            }
        )


class GeocodeView(APIView):
    """Location autocomplete: ``GET /api/geocode?q=dallas&limit=6``."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geocode"

    def get(self, request):
        query = request.query_params.get("q", "")
        limit = _bounded_int(request.query_params.get("limit"), default=6, low=1, high=10)
        results = geocoding.search(query, limit)
        return Response({"results": [r.as_dict() for r in results]})


class ReverseGeocodeView(APIView):
    """Names a coordinate, for "use my location": ``GET /api/reverse-geocode?lat=..&lon=..``."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geocode"

    class Params(serializers.Serializer):
        lat = serializers.FloatField(min_value=-90, max_value=90)
        lon = serializers.FloatField(min_value=-180, max_value=180)

    def get(self, request):
        params = self.Params(data=request.query_params)
        params.is_valid(raise_exception=True)
        result = geocoding.reverse(params.validated_data["lat"], params.validated_data["lon"])
        return Response({"result": result.as_dict()})


class PlanTripView(APIView):
    """``POST /api/trips/plan`` -> route, HOS-compliant schedule, stops and daily logs."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "plan"

    def post(self, request):
        serializer = TripPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(trip_planner.plan(serializer.to_trip_request()))


def _bounded_int(raw, *, default: int, low: int, high: int) -> int:
    try:
        return min(high, max(low, int(raw)))
    except (TypeError, ValueError):
        return default
