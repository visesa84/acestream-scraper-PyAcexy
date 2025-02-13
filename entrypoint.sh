#!/bin/sh

# Run database migrations
cd /app
echo "Running database migrations..."
python manage.py upgrade

# Start ZeroNet in the background
cd /app/ZeroNet
echo "Starting ZeroNet..."
python3 zeronet.py --ui-ip '*' --ui-host '0.0.0.0' --ui-port 43110 main &
ZERONET_PID=$!

# Wait for ZeroNet to start
echo "Waiting for ZeroNet to initialize..."
sleep 10

# Start Flask app with Gunicorn
cd /app
echo "Starting Flask application..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 wsgi:app &
GUNICORN_PID=$!

# Monitor processes
echo "Services started. Monitoring processes..."
trap "kill $ZERONET_PID $GUNICORN_PID" EXIT
wait