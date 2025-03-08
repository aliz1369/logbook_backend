from django.db import models


class Trip(models.Model):
    driver_name = models.CharField(max_length=255)
    car_number = models.CharField(max_length=50)
    date = models.DateField(auto_now_add=True)

    current_location = models.JSONField()
    pickup_location = models.JSONField()
    dropoff_location = models.JSONField()
    distance_miles = models.FloatField(null=True, blank=True)
    estimated_duration_hours = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.driver_name} - {self.car_number} - {self.date}"


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
    day = models.IntegerField()

    def __str__(self):
        return f"Log for {self.trip.driver_name} on {self.date} ({self.status})"
