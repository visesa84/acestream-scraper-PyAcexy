# --- STAGE 0: Compilación de BoringTun Estable ---
FROM rust:1.85-slim AS builder
RUN apt-get update && apt-get install -y pkg-config libssl-dev git && \
    # Clonamos el repo oficial
    git clone https://github.com/cloudflare/boringtun.git /src

WORKDIR /src

# Forzamos las versiones compatibles de 'time' en el archivo de configuración del proyecto
RUN sed -i 's/\[dependencies\]/\[dependencies\]\ntime = "=0.3.36"\ntime-core = "=0.1.2"/' boringtun-cli/Cargo.toml

RUN cargo install --path boringtun-cli

# --- STAGE 1: Base image con todas las dependencias ---
FROM --platform=linux/arm/v7 python:3.10-slim AS base

LABEL maintainer="visesa" \
      description="Acestream channel scraper with ZeroNet support" \
      version="3.6"

WORKDIR /app
RUN mkdir -p /app/config

# Copiamos el binario de BoringTun y preparamos el bridge
COPY --from=builder /usr/local/cargo/bin/boringtun-cli /usr/local/bin/boringtun-real
RUN echo -e '#!/bin/bash\n/usr/local/bin/boringtun-real --disable-drop-privileges "$@"' > /usr/local/bin/boringtun && \
    chmod +x /usr/local/bin/boringtun /usr/local/bin/boringtun-real
	
# Instalar dependencias del sistema + herramientas de WireGuard
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg gcc python3-dev build-essential \
    tor git lsb-release apt-transport-https ca-certificates \
    wireguard-tools iproute2 ffmpeg \
    openresolv unzip binutils \
    libssl-dev libffi-dev \
    libsecp256k1-dev libtool autoconf automake pkg-config \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    gfortran libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# Configuración de TOR
RUN echo "ControlPort 9051" >> /etc/tor/torrc && \
    echo "CookieAuthentication 1" >> /etc/tor/torrc

# Forzar Cython antiguo
RUN pip install --no-cache-dir "setuptools<61.0.0" "wheel" "Cython<3.0" "cffi>=1.15.0"
RUN pip install --no-cache-dir --no-build-isolation \
    "gevent==22.10.2" \
    "pysha3"

# Asegúrate de tener cffi instalado antes
RUN pip install --no-cache-dir "cffi>=1.15.0"

# Instalar coincurve
RUN COINCURVE_IGNORE_SYSTEM_LIB=0 \
    pip install --no-cache-dir --no-build-isolation "coincurve==18.0.0"
	
# Instalar librerías de Python
RUN pip install --no-cache-dir \
    "msgpack-python" "PySocks" "gevent-websocket" \
    "python-bitcoinlib" "bencode.py" "merkletools" "pysha3" \
    "cgi-tools" "urllib3<2.0.0" "rich" "requests" "pyaes" \
    "base58" "defusedxml" "rsa" "psutil" "opencv-python-headless"

# --- INSTALACIÓN DE PYACEXY ---
COPY pyacexy/ /opt/pyacexy/

RUN cp /opt/pyacexy/proxy.py /usr/local/bin/pyacexy && \
    cp /opt/pyacexy/aceid.py /usr/local/bin/aceid.py && \
    cp /opt/pyacexy/copier.py /usr/local/bin/copier.py && \
	cd /opt/pyacexy && \
    pip install --no-cache-dir -r requirements.txt

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
COPY --chmod=0755 /arm/arm32/entrypoint.sh healthcheck.sh warp-setup.sh ./
COPY --chmod=0755 /arm/arm32/wgcf /usr/local/bin/wgcf
COPY requirements.txt requirements-prod.txt ./
COPY migrations/ ./migrations/
COPY migrations_app.py manage.py wsgi.py ./
COPY app/ ./app/

# Instalación de dependencias de la app
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-prod.txt

# Instalación del motor Acestream (Archivos ZIP)
COPY /arm/arm32/ace-armeabi-v7a.zip /arm/arm32/system.zip /
RUN unzip /ace-armeabi-v7a.zip -d /acestream && \
    unzip /system.zip -d / && \
    rm /ace-armeabi-v7a.zip /system.zip && \
    chmod -R +x /system/bin /acestream/python/bin

ADD /arm/arm32/main.py /arm/arm32/dnsproxyd.py /arm/arm32/app_bridge.py /acestream/

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
