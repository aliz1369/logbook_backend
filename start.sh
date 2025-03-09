#!/bin/bash

# Apply database migrations
echo "Applying database migrations..."
python manage.py makemigrations
python manage.py migrate


# Start the Django server
echo "Starting Django application..."
gunicorn backend.wsgi:application --bind 0.0.0.0:$PORT