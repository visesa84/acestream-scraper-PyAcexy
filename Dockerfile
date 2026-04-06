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
FROM python:3.10-slim AS base

LABEL maintainer="visesa" \
      description="Base image for Acestream channel scraper with pyacexy" \
      version="3.6"

WORKDIR /app
RUN mkdir -p /app/config

# Copiamos el binario de BoringTun desde la etapa anterior
COPY --from=builder /usr/local/cargo/bin/boringtun-cli /usr/local/bin/boringtun
RUN chmod +x /usr/local/bin/boringtun

# Renombramos el binario real
RUN mv /usr/local/bin/boringtun /usr/local/bin/boringtun-real

# Creamos un script que haga de "puente" y fuerce las opciones
RUN echo '#!/bin/bash\n/usr/local/bin/boringtun-real --disable-drop-privileges "$@"' > /usr/local/bin/boringtun && \
    chmod +x /usr/local/bin/boringtun

# Instalar dependencias del sistema + herramientas de WireGuard
RUN apt-get update && apt-get install -y \
    wget curl gnupg gcc python3-dev build-essential \
    tor git lsb-release apt-transport-https ca-certificates \
    wireguard-tools iproute2 \
	openresolv \
	libsm6 libxext6 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Configuración de TOR
RUN echo "ControlPort 9051" >> /etc/tor/torrc && \
    echo "CookieAuthentication 1" >> /etc/tor/torrc

# 1. Actualizar herramientas de construcción
RUN pip install --no-cache-dir \
    "msgpack-python" \
    "gevent==22.10.2" \
    "PySocks" \
    "gevent-websocket" \
    "python-bitcoinlib" \
    "bencode.py" \
    "merkletools" \
    "pysha3" \
    "cgi-tools" \
    "urllib3<2.0.0" \
    "rich" \
    "requests" \
    "pyaes" \
    "coincurve" \
    "base58" \
    "defusedxml" \
    "rsa" \
	"opencv-python-headless" \
	"psutil"

# --- INSTALACIÓN DE PYACEXY ---
COPY pyacexy/ /opt/pyacexy/

RUN cp /opt/pyacexy/proxy.py /usr/local/bin/pyacexy && \
    cp /opt/pyacexy/aceid.py /usr/local/bin/aceid.py && \
    cp /opt/pyacexy/copier.py /usr/local/bin/copier.py && \
	cd /opt/pyacexy && \
    pip install --no-cache-dir -r requirements.txt

# Permisos de ejecución
RUN chmod +x /usr/local/bin/pyacexy /usr/local/bin/aceid.py /usr/local/bin/copier.py

# Descargar e instalar ZeroNet
RUN mkdir -p ZeroNet && \
    wget https://github.com/zeronet-conservancy/zeronet-conservancy/archive/refs/heads/master.tar.gz -O ZeroNet.tar.gz && \
    tar xvf ZeroNet.tar.gz && \
    mv zeronet-conservancy-master/* ZeroNet/ && \
    rm -rf ZeroNet.tar.gz zeronet-conservancy-master

# Install Acestream Engine
ENV ACESTREAM_VERSION="3.2.11_ubuntu_22.04_x86_64_py3.10"
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install acestream dependencies
RUN apt-get update \
  && apt-get install --no-install-recommends -y \
      ca-certificates wget sudo \
	  python3-gi \
	  gir1.2-gtk-3.0 \
	  ffmpeg \
  && rm -rf /var/lib/apt/lists/* \
  #
  # Download acestream
  && wget --progress=dot:giga "https://download.acestream.media/linux/acestream_${ACESTREAM_VERSION}.tar.gz" \
  && mkdir acestream \
  && tar zxf "acestream_${ACESTREAM_VERSION}.tar.gz" -C acestream \
  && rm "acestream_${ACESTREAM_VERSION}.tar.gz" \
  && mv acestream /opt/acestream \
  && pushd /opt/acestream || exit \
  && bash ./install_dependencies.sh \
  && popd || exit

# Instalar la librería
RUN apt-get update && apt-get install -y libjemalloc2 && rm -rf /var/lib/apt/lists/*

# Clean up APT in base image
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set default environment variables for base image
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
ENV LD_PRELOAD="/usr/lib/x86_64-linux-gnu/libjemalloc.so.2"
ENV MALLOC_CONF="dirty_decay_ms:1000,muzzy_decay_ms:1000"
ENV EXTRA_FLAGS="--cache-dir /tmp --cache-limit 2 --log-stderr --log-stderr-level error --max-connections 300 --max-peers 50 --core-dlrate-helper 0 --stats-report-interval 10 --live-cache-type memory --live-cache-size 209715200"

# Final image with application code
FROM base

# Update metadata labels for the final image
LABEL description="Acestream channel scraper with ZeroNet support" \
      version="3.6"

# Copy application files
COPY --chmod=0755 entrypoint.sh /app/entrypoint.sh
COPY --chmod=0755 healthcheck.sh /app/healthcheck.sh
COPY --chmod=0755 warp-setup.sh /app/warp-setup.sh
COPY --chmod=0755 wgcf /usr/local/bin/wgcf
COPY requirements.txt requirements-prod.txt ./
COPY migrations/ ./migrations/
COPY migrations_app.py manage.py ./
COPY wsgi.py ./
COPY app/ ./app/

# FORZAMOS PERMISOS DE EJECUCIÓN
RUN chmod +x /app/entrypoint.sh /app/healthcheck.sh /app/warp-setup.sh /usr/local/bin/wgcf

# Install the application dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-prod.txt

# Expose the ports
EXPOSE 8040
EXPOSE 43110
EXPOSE 43111
EXPOSE 26552
EXPOSE 8080
EXPOSE 8621/tcp
EXPOSE 8621/udp
EXPOSE 6878

# Set the volume
VOLUME ["/app/ZeroNet/data"]
VOLUME ["/app/config"]
VOLUME ["/app/config/recordings"]

# Make sure WORKDIR is set correctly
WORKDIR /app

# FORZAMOS PERMISOS DE EJECUCIÓN
RUN chmod -R 755 /app

# Define the healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD /app/healthcheck.sh

# IMPORTANT: The following capabilities must be added when running the container with WARP enabled:
# --cap-add NET_ADMIN
# --cap-add SYS_ADMIN
# Example: docker run --cap-add NET_ADMIN --cap-add SYS_ADMIN -e ENABLE_WARP=true ...
# Note: Container runs with IPv6 disabled to avoid DNS lookup issues

ENTRYPOINT ["/app/entrypoint.sh"]
