from rest_framework import serializers

from .models import DailyLog, Driver, Trip, Vehicle


class DailyLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyLog
        fields = "__all__"


class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = "__all__"


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = "__all__"


class TripSerializer(serializers.ModelSerializer):
    driver = DriverSerializer(read_only=True)
    vehicle = VehicleSerializer(read_only=True)
    logs = DailyLogSerializer(many=True, read_only=True)

    class Meta:
        model = Trip
        fields = "__all__"
