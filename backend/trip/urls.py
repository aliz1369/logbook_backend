from django.urls import path

from .views import (
    DriverHoursView,
    DriverListCreateView,
    TripCreateView,
    TripDetailView,
    VehicleListCreateView,
)

urlpatterns = [
    path("drivers/", DriverListCreateView.as_view(), name="driver-list-create"),
    path("drivers/<int:pk>/hours/", DriverHoursView.as_view(), name="driver-hours"),
    path("vehicles/", VehicleListCreateView.as_view(), name="vehicle-list-create"),
    path("trips/", TripCreateView.as_view(), name="trip-list-create"),
    path("trips/<int:pk>/", TripDetailView.as_view(), name="trip-detail"),
]
