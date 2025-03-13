from datetime import datetime

from django.db import models
from django.utils.timezone import now, timedelta


class Driver(models.Model):
    name = models.CharField(max_length=255)
    license_number = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return f"{self.name} ({self.license_number})"

    def get_hours_last_8_days(self, reference_date=None):
        if reference_date is None:
            reference_date = now().date()
        elif isinstance(reference_date, str):
            reference_date = datetime.strptime(reference_date, "%Y-%m-%d").date()

        last_8_days = reference_date - timedelta(days=8)
        logs = DailyLog.objects.filter(
            trip__driver=self, date__gte=last_8_days, date__lte=reference_date
        )

        total_seconds = sum(
            (
                datetime.combine(log.date, log.end_time)
                - datetime.combine(log.date, log.start_time)
            ).total_seconds()
            for log in logs
            if log.status in ["driving", "onDuty"]
        )

        total_hours = total_seconds / 3600
        return total_hours

    def get_available_hours(self, reference_date=None):
        used_hours = self.get_hours_last_8_days(reference_date)
        return max(0, 70 - used_hours)


class Vehicle(models.Model):
    car_number = models.CharField(max_length=50, unique=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.car_number} - {self.make} {self.model}"


class Trip(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name="trips")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="trips")
    date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    current_location = models.JSONField()
    pickup_location = models.JSONField()
    dropoff_location = models.JSONField()
    distance_miles = models.FloatField(null=True, blank=True)
    estimated_duration_hours = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Trip {self.id} - {self.driver.name} - {self.vehicle.car_number} - {self.date}"


class DailyLog(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="logs")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(
        max_length=10,
        choices=[
            ("offDuty", "Off Duty"),
            ("sleeper", "Sleeper"),
            ("driving", "Driving"),
            ("onDuty", "On Duty"),
        ],
    )
    remarks = models.TextField(blank=True, null=True)
    stop_location = models.JSONField(blank=True, null=True)
    day = models.IntegerField()

    def __str__(self):
        return f"Log for {self.trip.driver.name} on {self.date} ({self.status})"
