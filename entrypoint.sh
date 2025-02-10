#!/bin/sh

# Wait for any dependent services to start
sleep 5

# Start ZeroNet in the background with the correct options
cd /app/ZeroNet
./ZeroNet.sh --ui_ip '*' --ui_restrict '' &
ZERO_NET_PID=$!

# Run the Flask application with Gunicorn
cd /app
exec gunicorn --bind 0.0.0.0:8000 --workers 3 wsgi:app

# Stop ZeroNet when the script exits
trap "kill $ZERO_NET_PID" EXIT
