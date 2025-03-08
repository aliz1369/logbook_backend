#!/bin/bash

# Apply database migrations
echo "Applying database migrations..."
python manage.py makemigrations
python manage.py migrate

# Create superuser (Optional: Only runs if not already created)
echo "Creating superuser if not exists..."
python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
username = "admin"
email = "admin@example.com"
password = "adminpassword"

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, email, password)
    print("Superuser created successfully!")
else:
    print("Superuser already exists.")
EOF

# Start the Django server
echo "Starting Django application..."
gunicorn backend.wsgi:application --bind 0.0.0.0:$PORT