from datetime import datetime, timedelta

from rest_framework import serializers

from .hos import TripSettings
from .services.trip_planner import LocationInput, TripRequest


class NaiveDateTimeField(serializers.Field):
    """Wall-clock departure time in home-terminal time. Any UTC offset is ignored on purpose:
    driver logs record terminal time, not instants."""

    def to_internal_value(self, value):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "")).replace(tzinfo=None)
        except ValueError as exc:
            raise serializers.ValidationError("Use ISO format, e.g. 2026-10-05T06:00.") from exc

    def to_representation(self, value):
        return value.isoformat(timespec="minutes")


class LocationSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=200, trim_whitespace=True)
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False, allow_null=True)
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False, allow_null=True)

    def validate(self, attrs):
        if (attrs.get("lat") is None) != (attrs.get("lon") is None):
            raise serializers.ValidationError("Provide both lat and lon, or neither.")
        return attrs


class TripOptionsSerializer(serializers.Serializer):
    pickup_minutes = serializers.IntegerField(min_value=0, max_value=12 * 60, default=60)
    dropoff_minutes = serializers.IntegerField(min_value=0, max_value=12 * 60, default=60)
    fuel_interval_miles = serializers.FloatField(min_value=100, max_value=3000, default=1000)
    fuel_minutes = serializers.IntegerField(min_value=5, max_value=120, default=30)
    pre_trip_minutes = serializers.IntegerField(min_value=0, max_value=120, default=30)
    post_trip_minutes = serializers.IntegerField(min_value=0, max_value=120, default=15)
    rest_in_sleeper = serializers.BooleanField(default=True)


class TripPlanSerializer(serializers.Serializer):
    current_location = LocationSerializer()
    pickup_location = LocationSerializer()
    dropoff_location = LocationSerializer()
    current_cycle_used = serializers.FloatField(
        min_value=0,
        max_value=70,
        help_text="On-duty hours already used in the current 70-hour/8-day cycle.",
    )
    departure = NaiveDateTimeField(required=False)
    options = TripOptionsSerializer(required=False)

    def to_trip_request(self) -> TripRequest:
        data = self.validated_data
        options = data.get("options") or TripOptionsSerializer().to_internal_value({})
        departure = data.get("departure") or _next_quarter_hour(datetime.now())
        return TripRequest(
            current=LocationInput(**data["current_location"]),
            pickup=LocationInput(**data["pickup_location"]),
            dropoff=LocationInput(**data["dropoff_location"]),
            cycle_used_hours=data["current_cycle_used"],
            departure=departure,
            settings=TripSettings(**options),
        )


def _next_quarter_hour(moment: datetime) -> datetime:
    moment = moment.replace(second=0, microsecond=0)
    return moment + timedelta(minutes=(15 - moment.minute % 15) % 15)
