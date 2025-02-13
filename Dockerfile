# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Add metadata labels
LABEL maintainer="pipepito" \
      description="Acestream channel scraper with ZeroNet support" \
      version="1.1.0"

# Set the working directory
WORKDIR /app

# Create the config directory
RUN mkdir -p /app/config

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    gcc \
    python3-dev \
    build-essential 

# Copy application files
COPY --chmod=0755 entrypoint.sh /app/entrypoint.sh
COPY requirements.txt wsgi.py ./
COPY app/ ./app/

# Install the required dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Gunicorn
RUN pip install gunicorn

# Install ZeroNet dependencies with specific versions
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
    

# Download and install ZeroNet
WORKDIR /app
RUN mkdir -p ZeroNet && \
    wget https://github.com/zeronet-conservancy/zeronet-conservancy/archive/refs/heads/master.tar.gz -O ZeroNet.tar.gz && \
    tar xvf ZeroNet.tar.gz && \
    mv zeronet-conservancy-master/* ZeroNet/ && \
    rm -rf ZeroNet.tar.gz zeronet-conservancy-master


# Set environment variable to indicate Docker environment
ENV DOCKER_ENV=true

# Expose the port Gunicorn will run on
EXPOSE 8000

# Expose the ZeroNet port
EXPOSE 43110

# Clean up APT when done
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Make sure WORKDIR is set correctly before ENTRYPOINT
WORKDIR /app

ENTRYPOINT ["/app/entrypoint.sh"]
