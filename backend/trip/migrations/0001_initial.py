# Generated by Django 5.1.4 on 2025-03-08 20:16

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Driver",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("license_number", models.CharField(max_length=50, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name="Vehicle",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("car_number", models.CharField(max_length=50, unique=True)),
                ("make", models.CharField(blank=True, max_length=100, null=True)),
                ("model", models.CharField(blank=True, max_length=100, null=True)),
                ("year", models.IntegerField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="Trip",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("date", models.DateField(auto_now_add=True)),
                ("current_location", models.JSONField()),
                ("pickup_location", models.JSONField()),
                ("dropoff_location", models.JSONField()),
                ("distance_miles", models.FloatField(blank=True, null=True)),
                ("estimated_duration_hours", models.FloatField(blank=True, null=True)),
                (
                    "driver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trips",
                        to="trip.driver",
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trips",
                        to="trip.vehicle",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="DailyLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("date", models.DateField()),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("offDuty", "Off Duty"),
                            ("sleeper", "Sleeper"),
                            ("driving", "Driving"),
                            ("onDuty", "On Duty"),
                        ],
                        max_length=10,
                    ),
                ),
                ("remarks", models.TextField(blank=True, null=True)),
                ("day", models.IntegerField()),
                (
                    "trip",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logs",
                        to="trip.trip",
                    ),
                ),
            ],
        ),
    ]
