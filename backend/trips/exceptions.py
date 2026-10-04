"""Maps domain failures to HTTP responses so every error has the same JSON shape:
``{"detail": "...", "field": "pickup_location" | null, "errors": {...} | null}``."""

import logging

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .hos import PlanningError
from .services.geocoding import GeocodingError
from .services.http import UpstreamError
from .services.routing import RoutingError

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    if isinstance(exc, (GeocodingError, RoutingError, PlanningError)):
        body = {"detail": str(exc), "field": getattr(exc, "field", None), "errors": None}
        return Response(body, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    if isinstance(exc, UpstreamError):
        detail = "A map service is temporarily unavailable. Please try again in a minute."
        return Response({"detail": detail, "field": None, "errors": None}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, ValidationError):
        errors = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
        field = next(iter(errors), None)
        return Response(
            {"detail": _first_message(errors), "field": field, "errors": errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled error while planning a trip", exc_info=exc)
        return Response(
            {"detail": "Something went wrong while planning this trip.", "field": None, "errors": None},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    detail = response.data.get("detail", "Request failed.") if isinstance(response.data, dict) else response.data
    response.data = {"detail": str(detail), "field": None, "errors": None}
    return response


def _first_message(errors) -> str:
    """Flatten DRF's nested error structure to one readable sentence."""
    if isinstance(errors, dict):
        for key, value in errors.items():
            message = _first_message(value)
            label = key.replace("_", " ").capitalize()
            return message if key == "non_field_errors" else f"{label}: {message}"
    if isinstance(errors, list) and errors:
        return _first_message(errors[0])
    return str(errors)
