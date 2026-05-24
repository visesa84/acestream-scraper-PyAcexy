#!/bin/bash

# Create logs directory
LOG_DIR="/app/logs"
mkdir -p $LOG_DIR

# Configure log rotation - hourly rotation, keep 1 day of logs
cat > /etc/logrotate.d/acestream-services << EOF
$LOG_DIR/*.log {
    hourly
    rotate 7
    compress
    missingok
    notifempty
    create 0644 root root
}
EOF

echo "Starting cron daemon..."
cron || true

# Run logrotate once to ensure config is valid
logrotate /etc/logrotate.d/acestream-services --debug || true

# Preparamos las variables de control de procesos
ACESTREAM_PID=""
PYACEXY_PID=""
ZERONET_PID=""
GUNICORN_PID=""

# TRAP POSICIONADO AL PRINCIPIO: Asegura una salida limpia de TODOS los servicios
cleanup() {
    echo "Stopping all services cleanly..."
    # Matamos solo los PIDs que se hayan llegado a inicializar
    kill -TERM $GUNICORN_PID $ZERONET_PID $PYACEXY_PID $ACESTREAM_PID 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM EXIT

# Initialize WARP if enabled
if [ "${ENABLE_WARP}" = "true" ]; then
    echo "Initializing Cloudflare WARP..."
    /app/warp-setup.sh
fi

# Set ENABLE_ACESTREAM_ENGINE to match ENABLE_ACEXY if not explicitly set
if [ -z "${ENABLE_ACESTREAM_ENGINE+x}" ]; then
    export ENABLE_ACESTREAM_ENGINE=$ENABLE_ACEXY
    echo "ENABLE_ACESTREAM_ENGINE not set, using ENABLE_ACEXY value: $ENABLE_ACESTREAM_ENGINE"
fi
# Update ACESTREAM_HTTP_HOST to use the actual value of ACEXY_HOST
if [ "$ACESTREAM_HTTP_HOST" = "ACEXY_HOST" ]; then
    export ACESTREAM_HTTP_HOST="$ACEXY_HOST"
    echo "Setting ACESTREAM_HTTP_HOST to $ACEXY_HOST"
fi

# Setup ZeroNet config if not exists
ZERONET_CONFIG="/app/config/zeronet.conf"
if [ ! -f "$ZERONET_CONFIG" ]; then
    echo "Creating default ZeroNet config..."
    cat > "$ZERONET_CONFIG" << EOF
[global]
ui_ip = *
ui_host =
 0.0.0.0
 localhost
ui_port = 43110
EOF
fi

# Create symlink to config
ln -sf "$ZERONET_CONFIG" /app/ZeroNet/zeronet.conf

# Start Tor if enabled
if [ "$ENABLE_TOR" = "true" ]; then
    echo "Starting Tor service..."
    service tor start >> "$LOG_DIR/tor.log" 2>&1
    # Add a brief pause to ensure Tor has time to start
    sleep 3
    echo "Tor service logs available at $LOG_DIR/tor.log"
fi

# Start Acestream Engine if enabled
if [ "$ENABLE_ACESTREAM_ENGINE" = "true" ]; then
    echo "Starting Acestream engine..."
	# Limpiar posibles comillas literales que hayan quedado en la variable
	EXTRA_FLAGS=$(echo $EXTRA_FLAGS | sed 's/"//g')
    /opt/acestream/start-engine --client-console --http-port $ACESTREAM_HTTP_PORT $EXTRA_FLAGS --live-buffer $ACEXY_BUFFER_SIZE >> "$LOG_DIR/acestream.log" 2>&1 & 
	ACESTREAM_PID=$!	
    sleep 3 # Brief pause to allow Acestream engine to start
    echo "Acestream engine logs available at $LOG_DIR/acestream.log"
fi

# Start PyAcexy if enabled
if [ "$ENABLE_ACEXY" = "true" ]; then
    if [ "$ENABLE_ACESTREAM_ENGINE" = "false" ] && [ "$ACEXY_HOST" = "localhost" ] && [ "$ACEXY_PORT" = "6878" ]; then
        echo "ERROR: When Acestream Engine is disabled, you must specify ACEXY_HOST and ACEXY_PORT other than localhost to connect to an external Acestream Engine instance"
        exit 1
    fi
    
    echo "Starting PyAcexy proxy..."
    export ACEXY_HOST
    export ACEXY_PORT
    python /usr/local/bin/pyacexy >> "$LOG_DIR/pyacexy.log" 2>&1 &
	PYACEXY_PID=$!
    echo "PyAcexy proxy logs available at $LOG_DIR/pyacexy.log"
else
    echo "PyAcexy is disabled."
fi

# Start ZeroNet in the background
cd /app/ZeroNet
echo "Starting ZeroNet..."
python3 zeronet.py main >> "$LOG_DIR/zeronet.log" 2>&1 &
ZERONET_PID=$!
echo "ZeroNet logs available at $LOG_DIR/zeronet.log"

# Wait for ZeroNet to start
echo "Waiting for ZeroNet to initialize..."
sleep 10

# Start Flask app with Gunicorn
cd /app
echo "Starting Flask application on port $FLASK_PORT..."
gunicorn --bind "0.0.0.0:$FLASK_PORT" \
    --workers 4 \
    --threads 4 \
    --worker-class gthread \
    --timeout 300 \
    --keep-alive 5 \
    --log-level info \
    --forwarded-allow-ips="*" \
    "wsgi:app" &
GUNICORN_PID=$!

echo "Services started. Monitoring processes..."

# Mantenemos el contenedor vivo monitorizando gunicorn
wait $GUNICORN_PID