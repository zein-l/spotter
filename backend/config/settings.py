"""Django settings for the ELD trip planner API.

The API is stateless (every plan is computed from the request), so there is no database.
Configuration comes from environment variables; see README.md for the full list.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", default=False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or "insecure-dev-key-only-used-without-sessions"
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,.vercel.app")
# Vercel exposes the deployment, branch and production domains (including a custom one).
ALLOWED_HOSTS += [
    os.environ[name]
    for name in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL")
    if os.environ.get(name)
]

INSTALLED_APPS = [
    "corsheaders",
    "rest_framework",
    "trips",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {}
USE_TZ = False  # log times are "home terminal time" by regulation, not UTC instants
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
APPEND_SLASH = False

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# The frontend is served from the same origin on Vercel. These cover local development and
# a split deployment where the frontend lives on its own *.vercel.app domain.
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://[\w-]+\.vercel\.app$",
    r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
]
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    # Protects the free upstream routing/geocoding services from a runaway client.
    "DEFAULT_THROTTLE_RATES": {"plan": "30/min", "geocode": "120/min"},
    "EXCEPTION_HANDLER": "trips.exceptions.api_exception_handler",
}

# --- Upstream services ----------------------------------------------------------------
HTTP_USER_AGENT = os.environ.get(
    "HTTP_USER_AGENT", "eld-trip-planner/1.0 (+https://github.com/zein-l/spotter)"
)
HTTP_TIMEOUT = (4, 25)  # connect, read (seconds)

# "osrm" (default, keyless), "ors" (needs ORS_API_KEY, truck profile) or "estimate" (offline).
ROUTING_PROVIDER = os.environ.get("ROUTING_PROVIDER", "osrm")
OSRM_URLS = env_list(
    "OSRM_URLS", "https://router.project-osrm.org,https://routing.openstreetmap.de/routed-car"
)
ORS_API_KEY = os.environ.get("ORS_API_KEY", "")
# If every live router fails, plan on a straight-line estimate (clearly flagged) instead of
# failing the request.
ROUTING_ALLOW_ESTIMATE_FALLBACK = env_bool("ROUTING_ALLOW_ESTIMATE_FALLBACK", default=True)
TRUCK_MAX_SPEED_MPH = float(os.environ.get("TRUCK_MAX_SPEED_MPH", "65"))

# "photon" (default) or "offline" (built-in North American places index only).
GEOCODER = os.environ.get("GEOCODER", "photon")
PHOTON_URL = os.environ.get("PHOTON_URL", "https://photon.komoot.io")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
