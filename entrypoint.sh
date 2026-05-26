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

# Start Acestream Engine(s) if enabled
if [ "$ENABLE_ACESTREAM_ENGINE" = "true" ]; then
    # Sanitize EXTRA_FLAGS and ensure buffer size
    export EXTRA_FLAGS=$(echo ${EXTRA_FLAGS:-} | sed 's/"//g')
    export ACEXY_BUFFER_SIZE=${ACEXY_BUFFER_SIZE:-10}
    # Use ACESTREAM_HTTP_PORT from env (set in Dockerfile, default: 6878)
    export ACESTREAM_HTTP_PORT=${ACESTREAM_HTTP_PORT:-6878}

    # Determine whether ACEXY_HOST points to an external engine (not local)
    SKIP_ALL_ENGINES=0
    if [ -n "${ACEXY_HOST:-}" ] && [ "$ACEXY_HOST" != "localhost" ] && [ "$ACEXY_HOST" != "127.0.0.1" ]; then
        echo "ACEXY_HOST points to external host ($ACEXY_HOST); will not start any internal engine."
        SKIP_ALL_ENGINES=1
        # Stream checks always use localhost:6879 — disable them when engine is external
        export CHECKSTATUS_ENABLED=false
        echo "ACEXY_HOST is external; stream status checks disabled (CHECKSTATUS_ENABLED=false)."
    fi

    # Decide startup mode based on CHECKSTATUS_ENABLED env var (default: true)
    if [ -z "${CHECKSTATUS_ENABLED:-}" ]; then
        CHECKSTATUS_ENABLED=true
    fi
    echo "checkstatus_enabled = $CHECKSTATUS_ENABLED"

    if [ "$CHECKSTATUS_ENABLED" = "false" ] || [ "$CHECKSTATUS_ENABLED" = "0" ]; then
        START_MODE="main-only"
    else
        START_MODE="both"
    fi

    # Locate bind_remap.so for direct fallback use (in case start_two_engines.sh is absent)
    SO=""
    for _so_path in /usr/local/lib/bind_remap.so /app/scripts/bind_remap.so; do
        [ -f "$_so_path" ] && SO="$_so_path" && break
    done

    # Start the helper script in appropriate mode
    if [ "$SKIP_ALL_ENGINES" -eq 1 ]; then
        echo "Skipping internal Acestream engine startup because configuration points to external engine."
    else
        if [ -x "/app/scripts/start_two_engines.sh" ]; then
            if [ "$START_MODE" = "main-only" ]; then
                /app/scripts/start_two_engines.sh main-only >> "$LOG_DIR/acestream.log" 2>&1 &
            else
                /app/scripts/start_two_engines.sh both >> "$LOG_DIR/acestream.log" 2>&1 &
            fi
        else
            echo "start_two_engines.sh not found or not executable; attempting direct start"
            if [ "$START_MODE" = "main-only" ]; then
                /opt/acestream/start-engine --client-console --http-port $ACESTREAM_HTTP_PORT $EXTRA_FLAGS --live-buffer $ACEXY_BUFFER_SIZE >> "$LOG_DIR/acestream.log" 2>&1 &
                ACESTREAM_PID=$!
            else
                # fallback: start two engines manually if we can't use the helper
                # Main engine starts normally (no remap needed)
                /opt/acestream/start-engine --client-console --http-port $ACESTREAM_HTTP_PORT $EXTRA_FLAGS --live-buffer $ACEXY_BUFFER_SIZE >> "$LOG_DIR/acestream_main.log" 2>&1 &
                PID_MAIN=$!
                # Background engine starts in a subshell with remap env vars so the
                # parent process (and gunicorn/pyacexy started later) are NOT affected
                (
                    if [ -n "$SO" ]; then
                        export ACE_BIND_REMAP=1
                        export ACE_BIND_REMAP_FROM=${ACESTREAM_HTTP_PORT}
                        export ACE_BIND_REMAP_TO=6879
                        export ACE_BIND_REMAP_FROM_P2P=8621
                        export ACE_BIND_REMAP_TO_P2P=8622
                        export LD_PRELOAD="$SO"
                    fi
                    exec /opt/acestream/start-engine --client-console --http-port 6879 $EXTRA_FLAGS --live-buffer $ACEXY_BUFFER_SIZE >> "$LOG_DIR/acestream_background.log" 2>&1
                ) &
                PID_BG=$!
                ACESTREAM_PID=$PID_MAIN
            fi
        fi
    fi
    sleep 3
    echo "Acestream engine startup log: $LOG_DIR/acestream.log"
fi

# If Acestream Engine is disabled, background engine on :6879 won't exist —
# force stream status checks off so the app doesn't waste time on failed checks.
if [ "$ENABLE_ACESTREAM_ENGINE" = "false" ]; then
    export CHECKSTATUS_ENABLED=false
    echo "ENABLE_ACESTREAM_ENGINE is disabled; stream status checks disabled (CHECKSTATUS_ENABLED=false)."
fi

# Start PyAcexy if enabled
if [ "$ENABLE_ACEXY" = "true" ]; then
    if [ "$ENABLE_ACESTREAM_ENGINE" = "false" ] && [ "$ACEXY_HOST" = "localhost" ] && [ "$ACEXY_PORT" = "6878" ]; then
        echo "WARNING: Acestream Engine is disabled and ACEXY_HOST is set to localhost:6878 — pyacexy will try to connect to localhost inside the container which may not be correct. Continuing startup."
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

# Run database migrations before starting the app
cd /app
echo "Running database migrations..."
python manage.py upgrade >> "$LOG_DIR/migrations.log" 2>&1
if [ $? -ne 0 ]; then
    echo "WARNING: Database migration failed — check $LOG_DIR/migrations.log"
else
    echo "Database migrations completed successfully."
fi

# Start Flask app with Gunicorn
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