from django.urls import re_path

from trips import views

# Every route lives under /api/: on Vercel the frontend owns every other path.
urlpatterns = [
    re_path(r"^api/health/?$", views.HealthView.as_view(), name="health"),
    re_path(r"^api/geocode/?$", views.GeocodeView.as_view(), name="geocode"),
    re_path(r"^api/reverse-geocode/?$", views.ReverseGeocodeView.as_view(), name="reverse-geocode"),
    re_path(r"^api/trips/plan/?$", views.PlanTripView.as_view(), name="plan-trip"),
]
