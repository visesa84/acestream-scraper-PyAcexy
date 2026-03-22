# --- STAGE 0: Compilación de BoringTun Estable ---
FROM rust:1.82-slim AS builder
RUN apt-get update && apt-get install -y pkg-config libssl-dev git && \
    # Clonamos el repo oficial
    git clone https://github.com/cloudflare/boringtun.git /src

WORKDIR /src

# Usa las versiones exactas que Cloudflare probó
RUN cargo install --locked --path boringtun-cli

# --- STAGE 1: Base image con todas las dependencias (Alpine 3.21) ---
FROM --platform=linux/arm64 python:3.10-slim AS base

LABEL maintainer="visesa" \
      description="Acestream channel scraper with ZeroNet support" \
      version="2.7"

WORKDIR /app
RUN mkdir -p /app/config

# Copiamos el binario de BoringTun y preparamos el bridge
COPY --from=builder /usr/local/cargo/bin/boringtun-cli /usr/local/bin/boringtun-real
RUN echo -e '#!/bin/bash\n/usr/local/bin/boringtun-real --disable-drop-privileges "$@"' > /usr/local/bin/boringtun && \
    chmod +x /usr/local/bin/boringtun /usr/local/bin/boringtun-real

# Instalar dependencias del sistema + herramientas de WireGuard
RUN apt-get update && apt-get install -y \
    wget curl gnupg gcc python3-dev build-essential \
    tor git lsb-release apt-transport-https ca-certificates \
    wireguard-tools iproute2 ffmpeg \
	openresolv unzip binutils \
    && rm -rf /var/lib/apt/lists/*

# Configuración de TOR
RUN echo "ControlPort 9051" >> /etc/tor/torrc && \
    echo "CookieAuthentication 1" >> /etc/tor/torrc

# 1. Instalar librerías de Python
RUN pip install --no-cache-dir \
    "msgpack-python" "gevent==22.10.2" "PySocks" "gevent-websocket" \
    "python-bitcoinlib" "bencode.py" "merkletools" "pysha3" \
    "cgi-tools" "urllib3<2.0.0" "rich" "requests" "pyaes" \
    "coincurve" "base58" "defusedxml" "rsa" "psutil"

# --- INSTALACIÓN DE PYACEXY ---
RUN git clone https://github.com/wafy80/pyacexy /opt/pyacexy && \
    cd /opt/pyacexy && \
    pip install --no-cache-dir --break-system-packages -r requirements.txt

RUN cp /opt/pyacexy/pyacexy/proxy.py /usr/local/bin/pyacexy && \
    cp /opt/pyacexy/pyacexy/aceid.py /usr/local/bin/aceid.py && \
    cp /opt/pyacexy/pyacexy/copier.py /usr/local/bin/copier.py && \
    sed -i '4i import sys' /usr/local/bin/pyacexy && \
    sed -i '9i sys.path.append(os.path.dirname(os.path.realpath(__file__)))' /usr/local/bin/pyacexy && \
    sed -i 's/from \.aceid/from aceid/g' /usr/local/bin/pyacexy && \
    sed -i 's/from \.copier/from copier/g' /usr/local/bin/pyacexy && \
    sed -i '/async def start_server/i \    async def handle_status(self, request: web.Request) -> web.Response:\n        status_data = {"total_active_streams": len(self.streams), "streams": []}\n        async with self.streams_lock:\n            for key, ongoing in self.streams.items():\n                status_data["streams"].append({"id": key, "clients": len(ongoing.clients), "is_stopping": ongoing.stopping})\n        return web.json_response(status_data)\n' /usr/local/bin/pyacexy

# Descargar e instalar ZeroNet
RUN mkdir -p ZeroNet && \
    wget https://github.com/zeronet-conservancy/zeronet-conservancy/archive/refs/heads/master.tar.gz -O ZeroNet.tar.gz && \
    tar xvf ZeroNet.tar.gz && \
    mv zeronet-conservancy-master/* ZeroNet/ && \
    rm -rf ZeroNet.tar.gz zeronet-conservancy-master

# Permisos de ejecución
RUN chmod +x /usr/local/bin/pyacexy /usr/local/bin/aceid.py /usr/local/bin/copier.py

# --- ETAPA FINAL ---
# Usamos la base que acabamos de construir para mantener las dependencias
FROM base

# Copiar archivos de aplicación (Asegúrate de ejecutar el build desde el nivel correcto)
COPY --chmod=0755 /arm/arm64/entrypoint.sh healthcheck.sh warp-setup.sh ./
COPY --chmod=0755 /arm/arm64/wgcf /usr/local/bin/wgcf
COPY requirements.txt requirements-prod.txt ./
COPY migrations/ ./migrations/
COPY migrations_app.py manage.py wsgi.py ./
COPY app/ ./app/

# Instalación de dependencias de la app
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-prod.txt

# Instalación del motor Acestream (Archivos ZIP)
COPY /arm/arm64/ace-arm64-v8a.zip /arm/arm64/system.zip /
RUN unzip /ace-arm64-v8a.zip -d /acestream && \
    unzip /system.zip -d / && \
    rm /ace-arm64-v8a.zip /system.zip && \
    chmod -R +x /system/bin /acestream/python/bin

ADD /arm/arm64/main.py /arm/arm64/dnsproxyd.py /arm/arm64/app_bridge.py /acestream/

# Variables de entorno Acestream
ENV DOCKER_ENV=true
ENV TZ='Europe/Madrid'
ENV ENABLE_TOR=false
ENV ENABLE_ACEXY=true
ENV ENABLE_ACESTREAM_ENGINE=true
ENV WG_QUICK_USERSPACE_IMPLEMENTATION=boringtun
ENV WG_THREADS=4
ENV ENABLE_WARP=false
ENV CONTAINER_NETWORK_MODE=host
ENV WARP_LICENSE_KEY=
ENV ACESTREAM_HTTP_PORT=6878
ENV ACESTREAM_HTTP_HOST=ACEXY_HOST
ENV FLASK_PORT=8040
ENV ACEXY_LISTEN_ADDR=":8080"
ENV ACEXY_HOST="localhost"
ENV ACEXY_PORT=6878
ENV ALLOW_REMOTE_ACCESS="no"
ENV ACEXY_BUFFER_SIZE=10
ENV EXTRA_FLAGS="--cache-dir /tmp --cache-limit 2 --log-stderr --log-stderr-level error --max-connections 300 --max-peers 50 --core-dlrate-helper 0 --stats-report-interval 10 --live-cache-type memory --live-cache-size 209715200"
	
# Puertos, Volúmenes y Salud
EXPOSE 8040 43110 43111 26552 8080 6878 8621/tcp 8621/udp
VOLUME ["/app/ZeroNet/data", "/app/config", "/app/config/recordings"]

RUN chmod -R 755 /app
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s CMD /app/healthcheck.sh

ENTRYPOINT ["/app/entrypoint.sh"]
