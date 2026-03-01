# --- STAGE 1: Base image con todas las dependencias ---
FROM python:3.10-slim AS base

LABEL maintainer="visesa" \
      description="Base image for Acestream channel scraper with pyacexy" \
      version="1.2.14"

WORKDIR /app
RUN mkdir -p /app/config

# Instalar dependencias del sistema necesarias para compilar
RUN apt-get update && apt-get install -y \
    wget curl gnupg gcc python3-dev build-essential \
    tor git lsb-release apt-transport-https ca-certificates \
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
    "rsa"

# --- INSTALACIÓN DE PYACEXY ---
RUN git clone https://github.com/wafy80/pyacexy /opt/pyacexy && \
    cd /opt/pyacexy && \
    pip install --no-cache-dir -r requirements.txt

# Descargar e instalar ZeroNet
RUN mkdir -p ZeroNet && \
    wget https://github.com/zeronet-conservancy/zeronet-conservancy/archive/refs/heads/master.tar.gz -O ZeroNet.tar.gz && \
    tar xvf ZeroNet.tar.gz && \
    mv zeronet-conservancy-master/* ZeroNet/ && \
    rm -rf ZeroNet.tar.gz zeronet-conservancy-master

# Instalar Acestream Engine
ENV ACESTREAM_VERSION="3.2.11_ubuntu_22.04_x86_64_py3.10"
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install acestream dependencies
RUN apt-get update \
  && apt-get install --no-install-recommends -y \
      ca-certificates wget sudo \
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

# Install Cloudflare WARP dependencies
RUN apt-get update && apt-get install -y \
    apt-transport-https \
    gnupg \
    curl \
    lsb-release \
    dirmngr \
    ca-certificates \
    --no-install-recommends

# Add Cloudflare GPG key and repository
RUN curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/cloudflare-client.list

# Install Cloudflare WARP
RUN apt-get update \
	&& apt-get install -y libcap2-bin --no-install-recommends \
	&& cp /bin/true /sbin/setcap \
    && cp /bin/true /usr/sbin/setcap \
	&& apt-get install -y cloudflare-warp \
	&& rm /usr/sbin/setcap \
    && rm -rf /var/lib/apt/lists/*

# Copy the pyacexy
RUN cp /opt/pyacexy/pyacexy/proxy.py /usr/local/bin/pyacexy && \
	cp /opt/pyacexy/pyacexy/aceid.py /usr/local/bin/aceid.py && \
	cp /opt/pyacexy/pyacexy/copier.py /usr/local/bin/copier.py && \
	sed -i '4i import sys' /usr/local/bin/pyacexy && \
    sed -i '9i sys.path.append(os.path.dirname(os.path.realpath(__file__)))' /usr/local/bin/pyacexy && \
    # Opción 1: Reemplazar las importaciones relativas (quitar el punto)
    sed -i 's/from \.aceid/from aceid/g' /usr/local/bin/pyacexy && \
    sed -i 's/from \.copier/from copier/g' /usr/local/bin/pyacexy

# FORZAMOS PERMISOS DE EJECUCIÓN
RUN chmod +x /usr/local/bin/pyacexy
RUN chmod +x /usr/local/bin/aceid.py
RUN chmod +x /usr/local/bin/copier.py

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
ENV ENABLE_WARP=false
ENV WARP_ENABLE_NAT=true
ENV WARP_ENABLE_IPV6=false
ENV ACESTREAM_HTTP_PORT=6878
ENV ACESTREAM_HTTP_HOST=ACEXY_HOST
ENV IPV6_DISABLED=true
ENV FLASK_PORT=8000
ENV ACEXY_LISTEN_ADDR=":8080"
ENV ACEXY_HOST="localhost"
ENV ACEXY_PORT=6878
ENV ALLOW_REMOTE_ACCESS="no"
ENV ACEXY_NO_RESPONSE_TIMEOUT=15
ENV ACEXY_BUFFER_SIZE=5
ENV LD_PRELOAD="/usr/lib/x86_64-linux-gnu/libjemalloc.so.2"
ENV MALLOC_CONF="dirty_decay_ms:1000,muzzy_decay_ms:1000"
ENV EXTRA_FLAGS="--cache-dir /tmp --cache-limit 2 --cache-auto 1 --log-stderr --log-stderr-level error"

# Final image with application code
FROM base

# Update metadata labels for the final image
LABEL description="Acestream channel scraper with ZeroNet support" \
      version="1.2.14"

# Copy application files
COPY --chmod=0755 entrypoint.sh /app/entrypoint.sh
COPY --chmod=0755 healthcheck.sh /app/healthcheck.sh
COPY --chmod=0755 warp-setup.sh /app/warp-setup.sh
COPY requirements.txt requirements-prod.txt ./
COPY migrations/ ./migrations/
COPY migrations_app.py manage.py ./
COPY wsgi.py ./
COPY app/ ./app/

# FORZAMOS PERMISOS DE EJECUCIÓN
RUN chmod +x /app/entrypoint.sh /app/healthcheck.sh /app/warp-setup.sh

# Install the application dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-prod.txt

# Expose the ports
EXPOSE 8000
EXPOSE 43110
EXPOSE 43111
EXPOSE 26552
EXPOSE 8080
EXPOSE 8621/tcp
EXPOSE 8621/udp
EXPOSE 6878

# Set the volume
VOLUME ["/app/ZeroNet/data"]

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
