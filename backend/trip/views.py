from datetime import datetime, time, timedelta

import requests
from django.conf import settings
from django.utils.timezone import make_aware, now
from rest_framework import generics, status
from rest_framework.response import Response

from .models import DailyLog, Driver, Trip, Vehicle
from .serializers import DriverSerializer, TripSerializer, VehicleSerializer


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
            url = f"https://graphhopper.com/api/1/route?point={start['lat']},{start['lng']}&point={end['lat']},{end['lng']}&profile=car&instructions=true&locale=en&calc_points=true&key={settings.GRAPH_HOPPER_API_KEY}&points_encoded=false"
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                route = response.json()["paths"][0]
                return (
                    route["distance"] / 1609,
                    route["time"] / 3_600_000,
                    route["points"]["coordinates"],
                )
            except (requests.RequestException, KeyError, IndexError):
                return None, None, None

        distance_to_pickup, duration_to_pickup, waypoints_to_pickup = (
            get_route_distance_duration(current_location, pickup_location)
        )
        distance_to_dropoff, duration_to_dropoff, waypoints_to_dropoff = (
            get_route_distance_duration(pickup_location, dropoff_location)
        )

        if None in (distance_to_pickup, distance_to_dropoff):
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

        self.generate_logs(
            trip,
            distance_to_pickup,
            duration_to_pickup,
            waypoints_to_pickup,
            distance_to_dropoff,
            duration_to_dropoff,
            waypoints_to_dropoff,
        )

        return Response(TripSerializer(trip).data, status=status.HTTP_201_CREATED)

    def generate_logs(
        self,
        trip,
        distance_to_pickup,
        duration_to_pickup,
        waypoints_to_pickup,
        distance_to_dropoff,
        duration_to_dropoff,
        waypoints_to_dropoff,
    ):
        start_datetime = make_aware(datetime.combine(trip.date, datetime.now().time()))
        logs = []
        miles_driven = 0
        hours_driven = 0
        last_fuel_stop = 0
        day_counter = 1

        def get_closest_waypoint(progress_ratio, waypoints):
            if not waypoints:
                return {"lat": 0.0, "lng": 0.0}
            index = min(int(progress_ratio * len(waypoints)), len(waypoints) - 1)
            return {"lat": waypoints[index][1], "lng": waypoints[index][0]}

        def add_log_entry(start, duration, status, remarks, stop_location=None):
            nonlocal day_counter
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

                day_counter += 1
                logs.append(
                    DailyLog(
                        trip=trip,
                        date=new_start.date(),
                        start_time=time(0, 0, 0),
                        end_time=(new_start + remaining_duration).time(),
                        status=status,
                        remarks=f"{remarks} (after midnight)",
                        stop_location=stop_location,
                        day=day_counter,
                    )
                )

                return new_start + remaining_duration
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
                return end_time

        def handle_drive_segment(
            current_time, distance, segment_text, waypoints, is_off_duty=False
        ):
            nonlocal miles_driven, hours_driven, last_fuel_stop
            remaining_distance = distance
            last_rest_time = 0

            while remaining_distance > 5:
                miles_since_last_rest = miles_driven - last_rest_time
                miles_until_rest = (
                    max(0, (5 * 60) - miles_since_last_rest)
                    if miles_since_last_rest < (5 * 60)
                    else 0
                )
                miles_until_fuel = max(0, 1000 - (miles_driven - last_fuel_stop))
                miles_until_sleep = max(0, (11 * 60) - (hours_driven * 60))

                event_distances = [
                    miles_until_rest,
                    miles_until_fuel,
                    miles_until_sleep,
                    remaining_distance,
                ]
                next_event_miles = min([d for d in event_distances if d > 0])

                if hours_driven >= 11 and remaining_distance > 0:
                    stop_location = get_closest_waypoint(
                        1 - (remaining_distance / distance), waypoints
                    )
                    current_time = add_log_entry(
                        current_time,
                        timedelta(hours=10),
                        "sleeper",
                        f"Mandatory sleep {segment_text}",
                        stop_location,
                    )
                    hours_driven = 0
                    last_rest_time = miles_driven
                    remaining_distance -= next_event_miles
                    miles_driven += next_event_miles
                    continue

                log_status = "offDuty" if is_off_duty else "driving"
                log_activity = "Traveling" if is_off_duty else "Driving"
                drive_hours = next_event_miles / 60
                current_time = add_log_entry(
                    current_time,
                    timedelta(hours=drive_hours),
                    log_status,
                    f"{log_activity} {segment_text}",
                )

                miles_driven += next_event_miles
                remaining_distance -= next_event_miles
                hours_driven += drive_hours

                if next_event_miles == miles_until_rest:
                    stop_location = get_closest_waypoint(
                        1 - (remaining_distance / distance), waypoints
                    )
                    current_time = add_log_entry(
                        current_time,
                        timedelta(minutes=30),
                        "onDuty",
                        f"Mandatory rest {segment_text}",
                        stop_location,
                    )
                    last_rest_time = miles_driven

                elif next_event_miles == miles_until_fuel:
                    stop_location = get_closest_waypoint(
                        1 - (remaining_distance / distance), waypoints
                    )
                    last_fuel_stop = miles_driven
                    current_time = add_log_entry(
                        current_time,
                        timedelta(minutes=30),
                        "onDuty",
                        f"Fuel stop {segment_text}",
                        stop_location,
                    )

            return current_time

        current_datetime = handle_drive_segment(
            start_datetime,
            distance_to_pickup,
            "to pickup location",
            waypoints_to_pickup,
            is_off_duty=True,
        )
        current_datetime = add_log_entry(
            current_datetime,
            timedelta(hours=1),
            "onDuty",
            "Pickup location - Loading cargo",
            trip.pickup_location,
        )
        current_datetime = handle_drive_segment(
            current_datetime,
            distance_to_dropoff,
            "to dropoff location",
            waypoints_to_dropoff,
            is_off_duty=False,
        )
        current_datetime = add_log_entry(
            current_datetime,
            timedelta(hours=1),
            "onDuty",
            "Drop-off location - Unloading cargo",
            trip.dropoff_location,
        )
        current_datetime = add_log_entry(
            current_datetime, timedelta(minutes=15), "offDuty", "Finished"
        )

        trip.end_date = current_datetime.date()
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
