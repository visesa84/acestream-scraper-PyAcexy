# Installation Guide

This guide covers different methods for installing and setting up Acestream Scraper.

## Contents
- [Docker Compose Method (Recommended)](#docker-compose-method-recommended)
- [Docker Method](#docker-method)
- [Manual Installation](#manual-installation)

## Docker Compose Method (Recommended)

Docker Compose provides the easiest way to get started with Acestream Scraper.

### Prerequisites
- Docker and Docker Compose installed on your system
- Basic understanding of Docker (see [Docker Guide](Docker.md))

### Steps

1. **Create a docker-compose.yml file:**

   ```yaml
   version: '3.8'

   services:
     acestream-scraper:
       image: visesa84/acestream-scraper-pyacexy
       container_name: acestream-scraper
       environment:
         - TZ=Europe/Madrid
		 - ENABLE_TOR=false
		 - ENABLE_ACEXY=true
		 - ENABLE_ACESTREAM_ENGINE=true
		 - ENABLE_WARP=false
		 - WARP_ENABLE_NAT=true
		 - WARP_ENABLE_IPV6=false
		 - IPV6_DISABLED=true
		 - ACESTREAM_HTTP_PORT=6878
		 - ACESTREAM_HTTP_HOST=ACEXY_HOST
		 - FLASK_PORT=8040
		 - ACEXY_LISTEN_ADDR=:8080
		 - ACEXY_HOST=localhost
		 - ACEXY_PORT=6878
		 - ALLOW_REMOTE_ACCESS=no
		 - ACEXY_NO_RESPONSE_TIMEOUT=15
		 - ACEXY_BUFFER_SIZE=5
		 - LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2
		 - MALLOC_CONF=dirty_decay_ms:1000,muzzy_decay_ms:1000
		 - EXTRA_FLAGS="--cache-dir /tmp --cache-limit 2 --cache-auto 1 --log-stderr --log-stderr-level error --max-connections 300 --max-peers 50 --core-dlrate-helper 0 --stats-report-interval 10 --live-cache-type memory"
       ports:
         - "8040:8040"  # Flask application
         - "8080:8080"  # Acexy proxy
         - "8621:8621"  # Acestream P2P Port
         - "43110:43110"  # ZeroNet UI
         - "43111:43111"  # ZeroNet peer
         - "26552:26552"  # ZeroNet peer
       volumes:
         - ./data/zeronet:/app/ZeroNet/data
         - ./data/config:/app/config
       restart: unless-stopped
       healthcheck:
         test: ["CMD", "/app/healthcheck.sh"]
         interval: 30s
         timeout: 10s
         retries: 3
         start_period: 60s
   ```

2. **Start the service:**

   ```bash
   docker-compose up -d
   ```

3. **Access the application:**
   
   Open your browser and navigate to `http://localhost:8040`
   
   The first-time setup wizard will guide you through configuration

## Docker Method

If you prefer using Docker without Docker Compose, follow these steps:

### Basic Installation

```bash
docker pull visesa84/acestream-scraper-pyacexy:latest
docker run -d \
  -p 8040:8040 \
  -v "${PWD}/config:/app/config" \
  --name acestream-scraper \
  visesa84/acestream-scraper-pyacexy:latest
```

### With Acexy and Internal Acestream Engine

```bash
docker run -d \
  -p 8040:8040 \
  -p 8080:8080 \
  -e ENABLE_ACEXY=true \
  -e ENABLE_ACESTREAM_ENGINE=true \
  -e ALLOW_REMOTE_ACCESS=yes \
  -v "${PWD}/config:/app/config" \
  --name acestream-scraper \
  visesa84/acestream-scraper-pyacexy:latest
```

### With External Acestream Engine

```bash
docker run -d \
  -p 8040:8040 \
  -p 8080:8080 \
  -e ENABLE_ACEXY=true \
  -e ENABLE_ACESTREAM_ENGINE=false \
  -e ACEXY_HOST=192.168.1.100 \
  -e ACEXY_PORT=6878 \
  -v "${PWD}/config:/app/config" \
  --name acestream-scraper \
  visesa84/acestream-scraper-pyacexy:latest
```

### With ZeroNet (TOR disabled)

```bash
docker run -d \
  -p 8040:8040 \
  -p 43110:43110 \
  -p 43111:43111 \
  -v "${PWD}/config:/app/config" \
  -v "${PWD}/zeronet_data:/app/ZeroNet/data" \
  --name acestream-scraper \
  visesa84/acestream-scraper-pyacexy:latest
```

### With ZeroNet (TOR enabled)

```bash
docker run -d \
  -p 8040:8040 \
  -p 43110:43110 \
  -p 43111:43111 \
  -e ENABLE_TOR=true \
  -v "${PWD}/config:/app/config" \
  -v "${PWD}/zeronet_data:/app/ZeroNet/data" \
  --name acestream-scraper \
  visesa84/acestream-scraper-pyacexy:latest
```

## Manual Installation

For advanced users who want to run the application directly on their system:

### Prerequisites
- Python 3.10 or higher
- pip package manager

### Steps

1. **Clone the repository:**

   ```bash
   git clone https://github.com/visesa84/acestream-scraper-PyAcexy.git
   cd acestream-scraper
   ```

2. **Set up virtual environment:**

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Create configuration:**

   ```bash
   mkdir -p config
   ```
   
   Create a `config/config.json` file:

   ```json
   {
       "urls": [
           "https://example.com/url1",
           "https://example.com/url2"
       ],
       "base_url": "http://127.0.0.1:8008/ace/getstream?id=",
       "ace_engine_url": "http://127.0.0.1:6878"
   }
   ```

4. **Run the application:**

   For development:
   ```bash
   python run_dev.py
   ```

   For production:
   ```bash
   python wsgi.py
   ```

5. **Access the application:**
   
   Open your browser and navigate to `http://localhost:8040`
