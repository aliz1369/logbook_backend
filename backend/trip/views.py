from datetime import datetime, time, timedelta

import requests
from django.utils.timezone import make_aware
from rest_framework import generics, status
from rest_framework.response import Response

from .models import DailyLog, Driver, Trip, Vehicle
from .serializers import DriverSerializer, TripSerializer, VehicleSerializer

GRAPH_HOPPER_API_KEY = "40df3919-cb8f-4849-8828-7cadb3b3d05a"


class TripCreateView(generics.ListCreateAPIView):
    queryset = (
        Trip.objects.all().select_related("driver", "vehicle").prefetch_related("logs")
    )
    serializer_class = TripSerializer

    def create(self, request, *args, **kwargs):
        data = request.data

        provided_date = data.get("date")
        trip_date = (
            datetime.strptime(provided_date, "%Y-%m-%d").date()
            if provided_date
            else datetime.today().date()
        )

        driver = Driver.objects.get(id=data["driver_id"])
        available_hours = driver.get_available_hours(trip_date)

        if available_hours <= 0:
            return Response(
                {"error": "Driver has reached the 70-hour limit for 8 days."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vehicle = Vehicle.objects.get(id=data["vehicle_id"])
        current_location = data["current_location"]
        pickup_location = data["pickup_location"]
        dropoff_location = data["dropoff_location"]

        def get_route_distance_duration(start, end):
            url = f"https://graphhopper.com/api/1/route?point={start['lat']},{start['lng']}&point={end['lat']},{end['lng']}&profile=truck&instructions=true&locale=en&calc_points=true&key={GRAPH_HOPPER_API_KEY}&points_encoded=false"
            response = requests.get(url)
            if response.status_code != 200:
                return None, None
            route = response.json()["paths"][0]
            return (
                route["distance"] / 1609,
                route["time"] / 3_600_000,
            )

        distance_to_pickup, duration_to_pickup = get_route_distance_duration(
            current_location, pickup_location
        )
        distance_to_dropoff, duration_to_dropoff = get_route_distance_duration(
            pickup_location, dropoff_location
        )

        if distance_to_pickup is None or distance_to_dropoff is None:
            return Response(
                {"error": "Failed to fetch route"}, status=status.HTTP_400_BAD_REQUEST
            )

        total_distance = distance_to_pickup + distance_to_dropoff
        total_duration = duration_to_pickup + duration_to_dropoff

        if total_duration > available_hours:
            return Response(
                {"error": "Trip duration exceeds available hours."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        end_date = trip_date + timedelta(days=int(total_duration // 24))

        trip = Trip.objects.create(
            driver=driver,
            vehicle=vehicle,
            current_location=current_location,
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            distance_miles=total_distance,
            estimated_duration_hours=total_duration,
            end_date=end_date,
            date=trip_date,
        )

        self.generate_logs(trip, duration_to_pickup, duration_to_dropoff)
        return Response(TripSerializer(trip).data, status=status.HTTP_201_CREATED)

    def generate_logs(self, trip, duration_to_pickup, duration_to_dropoff):
        start_datetime = make_aware(datetime.combine(trip.date, datetime.now().time()))
        logs = []
        miles_driven = 0
        hours_driven = 0
        last_fuel_stop = 0
        day_counter = 1

        def get_stop_location(progress_ratio):
            return {
                "lat": trip.current_location["lat"]
                + progress_ratio
                * (trip.dropoff_location["lat"] - trip.current_location["lat"]),
                "lng": trip.current_location["lng"]
                + progress_ratio
                * (trip.dropoff_location["lng"] - trip.current_location["lng"]),
            }

        def add_log_entry(start, duration, status, remarks, stop_location=None):
            end_time = start + duration
            if end_time.date() > start.date():
                end_before_midnight = make_aware(
                    datetime.combine(start.date(), time(23, 59, 59))
                )

                logs.append(
                    DailyLog(
                        trip=trip,
                        date=start.date(),
                        start_time=start.time(),
                        end_time=end_before_midnight.time(),
                        status=status,
                        remarks=f"{remarks} (before midnight)",
                        stop_location=stop_location,
                        day=day_counter,
                    )
                )

                next_day = start.date() + timedelta(days=1)
                new_start = make_aware(datetime.combine(next_day, time(0, 0, 0)))
                remaining_duration = duration - (end_before_midnight - start)

                logs.append(
                    DailyLog(
                        trip=trip,
                        date=new_start.date(),
                        start_time=new_start.time(),
                        end_time=(new_start + remaining_duration).time(),
                        status=status,
                        remarks=f"{remarks} (after midnight)",
                        stop_location=stop_location,
                        day=day_counter + 1,
                    )
                )

                return new_start + remaining_duration, day_counter + 1
            else:
                logs.append(
                    DailyLog(
                        trip=trip,
                        date=start.date(),
                        start_time=start.time(),
                        end_time=end_time.time(),
                        status=status,
                        remarks=remarks,
                        stop_location=stop_location,
                        day=day_counter,
                    )
                )
                return end_time, day_counter

        start_datetime, day_counter = add_log_entry(
            start_datetime,
            timedelta(hours=duration_to_pickup),
            "offDuty",
            "Traveling to pickup location",
            stop_location=trip.current_location,
        )

        start_datetime, day_counter = add_log_entry(
            start_datetime,
            timedelta(hours=1),
            "onDuty",
            "Pickup location - Loading cargo",
            stop_location=trip.pickup_location,
        )

        while miles_driven < trip.distance_miles:
            if hours_driven >= 6:
                start_datetime, day_counter = add_log_entry(
                    start_datetime,
                    timedelta(minutes=30),
                    "onDuty",
                    "Mandatory 30-min rest",
                    stop_location=get_stop_location(miles_driven / trip.distance_miles),
                )

            if hours_driven >= 11:
                start_datetime, day_counter = add_log_entry(
                    start_datetime,
                    timedelta(hours=10),
                    "sleeper",
                    "Mandatory 10-hour sleep",
                    stop_location=get_stop_location(miles_driven / trip.distance_miles),
                )
                hours_driven = 0
                continue

            if miles_driven - last_fuel_stop >= 1000:
                last_fuel_stop = miles_driven
                start_datetime, day_counter = add_log_entry(
                    start_datetime,
                    timedelta(minutes=30),
                    "onDuty",
                    "Fuel stop",
                    stop_location=get_stop_location(miles_driven / trip.distance_miles),
                )

            drive_duration = min(
                11 - hours_driven, (trip.distance_miles - miles_driven) / 60
            )
            start_datetime, day_counter = add_log_entry(
                start_datetime, timedelta(hours=drive_duration), "driving", "Driving"
            )

            miles_driven += drive_duration * 60
            hours_driven += drive_duration

        start_datetime, day_counter = add_log_entry(
            start_datetime,
            timedelta(hours=1),
            "onDuty",
            "Drop-off location - Unloading cargo",
            stop_location=trip.dropoff_location,
        )

        start_datetime, day_counter = add_log_entry(
            start_datetime,
            timedelta(minutes=15),
            "offDuty",
            "Finished",
            stop_location=trip.dropoff_location,
        )

        trip.end_date = start_datetime.date()
        trip.save()

        DailyLog.objects.bulk_create(logs)


class DriverListCreateView(generics.ListCreateAPIView):
    queryset = Driver.objects.all()
    serializer_class = DriverSerializer


class VehicleListCreateView(generics.ListCreateAPIView):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer


class DriverHoursView(generics.RetrieveAPIView):

    queryset = Driver.objects.all()
    serializer_class = DriverSerializer

    def retrieve(self, request, *args, **kwargs):
        driver = self.get_object()
        reference_date_str = request.query_params.get("reference_date")
        try:
            reference_date = (
                datetime.strptime(reference_date_str, "%Y-%m-%d").date()
                if reference_date_str
                else now().date()
            )
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD HH:MM:SS"}, status=400
            )

        available_hours = driver.get_available_hours(reference_date)

        return Response(
            {"driver_name": driver.name, "available_hours": available_hours}
        )


class TripDetailView(generics.RetrieveAPIView):

    queryset = Trip.objects.all()
    serializer_class = TripSerializer
