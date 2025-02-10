#!/bin/sh
export MOUNTED_DIR=${MOUNTED_DIR:-/app/config}
exec gunicorn -w 4 -b 0.0.0.0:${HOST_PORT:-8000} wsgi:app &
cd ZeroNet-master && exec python zeronet.py --ui_ip 0.0.0.0
