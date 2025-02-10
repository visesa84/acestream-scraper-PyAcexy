#!/bin/sh

# Wait for any dependent services to start
sleep 5

# Start ZeroNet in the background
cd /app/ZeroNet
./ZeroNet.sh --ui_ip '*' &

# Run the Flask application with Gunicorn
cd /app
exec gunicorn --bind 0.0.0.0:8000 --workers 3 wsgi:app
