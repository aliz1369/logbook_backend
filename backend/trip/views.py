from rest_framework import generics
from rest_framework.response import Response
from datetime import datetime, timedelta
from .models import Trip, DailyLog
from .serializers import TripSerializer, DailyLogSerializer
from rest_framework import status
from django.utils.timezone import make_aware


GRAPH_HOPPER_API_KEY = "40df3919-cb8f-4849-8828-7cadb3b3d05a"


class TripCreateView(generics.ListCreateAPIView):
    queryset = Trip.objects.all()
    serializer_class = TripSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        driver_name = data.get("driver_name")
        car_number = data.get("car_number")
        current_location = (data["current_location"],)
        pickup_location = (data["pickup_location"],)
        dropoff_location = (data["dropoff_location"],)
        date = (
            datetime.strptime(data.get("date"), "%Y-%m-%d").date()
            if "date" in data
            else datetime.today().date()
        )
        url = f"https://graphhopper.com/api/1/route?point={current_location['lat']},{current_location['lng']}&point={pickup_location['lat']},{pickup_location['lng']}&point={dropoff_location['lat']},{dropoff_location['lng']}&profile=truck&instructions=true&locale=en&calc_points=true&key={GRAPH_HOPPER_API_KEY}&points_encoded=false"

        response = request.get(url)
        if response.status.code != 200:
            return Response(
                {"error": "Failed to fetch route"}, status=status.HTTP_400_BAD_REQUEST
            )

        route_data = response.json()["paths"][0]
        distance_miles = route_data["distance"] / 1609
        duration_hours = route_data["time"] / 3_600_000
        trip = Trip.objects.create(
            driver_name=driver_name,
            car_number=car_number,
            date=date,
            current_location=current_location,
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            distance_miles=distance_miles,
            estimated_duration_hours=duration_hours,
        )

        self.generate_logs(trip, distance_miles)

        return Response(TripSerializer(trip).data, status=status.HTTP_201_CREATED)

    def generate_logs(self, trip, total_distance):

        start_datetime = make_aware(datetime.combine(trip.date, datetime.min.time()))
        logs = []
        hours_driven = 0
        miles_driven = 0
        fuel_stops = 0
        day_counter = 1

        logs.append(
            DailyLog(
                trip=trip,
                date=start_datetime.date(),
                start_time=start_datetime.time(),
                end_time=(start_datetime + timedelta(hours=1)).time(),
                status="onDuty",
                remarks="Pickup location - Loading cargo",
                day=day_counter,
            )
        )

        start_datetime += timedelta(hours=1)

        while miles_driven < total_distance:
            if hours_driven >= 11:
                logs.append(
                    DailyLog(
                        trip=trip,
                        date=start_datetime.date(),
                        start_time=start_datetime.time(),
                        end_time=(start_datetime + timedelta(hours=10)).time(),
                        status="sleeper",
                        remarks="Mandatory rest stop",
                        day=day_counter,
                    )
                )
            start_datetime += timedelta(hours=10)
            hours_driven = 0
            day_counter += 1
            continue

        if miles_driven > 0 and miles_driven % 1000 == 0:
            logs.append(
                DailyLog(
                    trip=trip,
                    date=start_datetime.date(),
                    start_time=start_datetime.time(),
                    end_time=(start_datetime + timedelta(minutes=30)).time(),
                    status="onDuty",
                    remarks="Fuel stop",
                    day=day_counter,
                )
            )
            start_datetime += timedelta(minutes=30)
            fuel_stops += 1

        drive_duration = min(11 - hours_driven, (total_distance - miles_driven) / 60)
        logs.append(
            DailyLog(
                trip=trip,
                date=start_datetime.date(),
                start_time=start_datetime.time(),
                end_time=(start_datetime + timedelta(hours=drive_duration)).time(),
                status="driving",
                remarks="Driving",
                day=day_counter,
            )
        )
        miles_driven += drive_duration * 60
        hours_driven += drive_duration
        start_datetime += timedelta(hours=drive_duration)

        logs.append(
            DailyLog(
                trip=trip,
                date=start_datetime.date(),
                start_time=start_datetime.time(),
                end_time=(start_datetime + timedelta(hours=1)).time(),
                status="onDuty",
                remarks="Drop-off location - Unloading cargo",
                day=day_counter,
            )
        )

        DailyLog.objects.bulk_create(logs)
