#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Apply database migrations
echo "Applying database migrations..."
python manage.py makemigrations --noinput
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Set default port if not defined
PORT=${PORT:-8000}

# Start Gunicorn
echo "Starting Django application on port $PORT..."
gunicorn backend.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 120
