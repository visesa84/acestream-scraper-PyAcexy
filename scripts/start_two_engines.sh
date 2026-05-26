#!/usr/bin/env bash
set -euo pipefail
# Script to compile LD_PRELOAD remapper and start two acestreamengine instances
# First instance will bind normally to 8621.
# Second instance will have LD_PRELOAD which remaps bind 8621->8622.


# Directory helpers
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR=${LOG_DIR:-/app/logs}

mkdir -p "$LOG_DIR" || true
# Prefer a prebuilt .so in /usr/local/lib if present (built at image build time)
DEFAULT_SO="/usr/local/lib/bind_remap.so"
SO="$ROOT_DIR/bind_remap.so"
C_SRC="$ROOT_DIR/bind_remap.c"

if [ -f "$DEFAULT_SO" ]; then
	echo "Using prebuilt bind remap: $DEFAULT_SO"
	SO="$DEFAULT_SO"
elif [ -f "$C_SRC" ]; then
	echo "Compiling bind remap from source..."
	gcc -fPIC -shared -o "$SO" "$C_SRC" -ldl
else
	echo "Warning: bind_remap.so not found and source not available. Second engine may fail to remap port."
	SO=""
fi

## Build engine flags from environment (fallbacks)
ACE_PORT=${ACESTREAM_HTTP_PORT:-6878}
ACE_BUFF=${ACEXY_BUFFER_SIZE:-10}
EXTRA_FLAGS_SANITIZED=$(echo ${EXTRA_FLAGS:-} | sed 's/"//g')
ENGINE_BIN="/opt/acestream/start-engine"
ENGINE_FLAGS="--client-console --http-port ${ACE_PORT} ${EXTRA_FLAGS_SANITIZED} --live-buffer ${ACE_BUFF}"
ENGINE_FLAGS_BACKGROUND="--client-console --http-port 6879 ${EXTRA_FLAGS_SANITIZED} --live-buffer ${ACE_BUFF}"

MODE=${1:-both}

echo "Using engine binary: $ENGINE_BIN (mode=$MODE)"
if [ ! -x "$ENGINE_BIN" ]; then
	echo "ERROR: $ENGINE_BIN not found or not executable"
	exit 1
fi
if [ "$MODE" = "main-only" ] || [ "$MODE" = "both" ]; then
	echo "Starting Acestream engine on 127.0.0.1:${ACE_PORT}"
	"${ENGINE_BIN}" ${ENGINE_FLAGS} >> "$LOG_DIR/acestream_main.log" 2>&1 &
	PID1=$!
	sleep 3
fi


if [ "$MODE" = "both" ]; then
	echo "Starting Background Acestream engine (remapped to 6879)"
	# Force P2P remap to avoid 8621 collision (default remap 8621->8622)
	export ACE_BIND_REMAP_FROM_P2P=8621
	export ACE_BIND_REMAP_TO_P2P=8622

	# Set HTTP remap so background binds to 6879 internally
	export ACE_BIND_REMAP_FROM=${ACE_PORT}
	export ACE_BIND_REMAP_TO=6879

	if [ -n "$SO" ]; then
		export ACE_BIND_REMAP=1
		export LD_PRELOAD="$SO"
	else
		echo "Warning: LD_PRELOAD remapper not available, background engine will attempt to bind directly to 6879 and P2P remap will not be applied"
	fi

	"${ENGINE_BIN}" ${ENGINE_FLAGS_BACKGROUND} >> "$LOG_DIR/acestream_background.log" 2>&1 &
	PID2=$!
fi

echo "Acestream engine: http://127.0.0.1:${ACE_PORT}"
echo "Background Acestream engine: http://127.0.0.1:6879"

# Wait only for the engines that were actually started
PIDS_TO_WAIT=()
[ -n "${PID1:-}" ] && PIDS_TO_WAIT+=("$PID1")
[ -n "${PID2:-}" ] && PIDS_TO_WAIT+=("$PID2")
[ "${#PIDS_TO_WAIT[@]}" -gt 0 ] && wait "${PIDS_TO_WAIT[@]}" || true
