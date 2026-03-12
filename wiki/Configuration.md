# Configuration Reference

This guide provides detailed information about configuring Acestream Scraper.

## Contents
- [Application Settings](#application-settings)
- [Environment Variables](#environment-variables)
- [Channel Status Checking](#channel-status-checking)
- [Port Mapping](#port-mapping)
- [Volumes](#volumes)
- [ZeroNet Configuration](#zeronet-configuration)
- [Running Behind a Reverse Proxy](#running-behind-a-reverse-proxy)
- [Security Considerations](#security-considerations)
- [Healthchecks](#healthchecks)

## Application Settings

Acestream Scraper can be configured through the setup wizard or directly by editing configuration files.

### Setup Wizard

When first accessing the application at `http://localhost:8040`, you'll be guided through the setup process if no configuration exists:

1. Configure Base URL format
2. Set Acestream Engine URL
3. Add source URLs to scrape
4. Set rescrape interval

### Manual Configuration

Create or edit `config/config.json`:

```json
{
    "urls": [
        "https://example.com/url1",
        "https://example.com/url2"
    ],
    "base_url": "http://localhost:6878/ace/getstream?id=",
    "ace_engine_url": "http://localhost:6878",
    "rescrape_interval": 24
}
```

### Key Settings

- **urls**: Array of URLs to scrape for Acestream channels
- **base_url**: Base URL format for playlist generation
  - `acestream://` - For players with Acestream protocol support
  - `http://localhost:6878/ace/getstream?id=` - For local HTTP streaming
  - `http://server-ip:acexy_port/ace/getstream?id=` - For using built-in PyAcexy proxy
- **ace_engine_url**: URL of your Acestream Engine instance
- **rescrape_interval**: Hours between automatic rescans of URLs
- **checkstatus_interval**: Hours between automatic rescans of streams
- **checkstatus_enabled**: Enable or disable Task

## Environment Variables

### Core Application

| Variable | Description | Default | Notes |
|----------|-------------|---------|-------|
| `FLASK_PORT` | Port the Flask application runs on | `8040` | Can be changed if port 8040 is in use |
| `FLASK_ENV` | Flask environment mode | `production` | Use `development` for debugging |

### Acestream Configuration

| Variable | Description | Default | Notes |
|----------|-------------|---------|-------|
| `ENABLE_ACESTREAM_ENGINE` | Enable built-in Acestream Engine | Matches `ENABLE_ACEXY` | Set to `true` to run Acestream in the container |
| `ACESTREAM_HTTP_PORT` | Port for Acestream engine | `6878` | Internal Acestream Engine HTTP port |
| `ACESTREAM_HTTP_HOST` | Host for Acestream engine | Uses `ACEXY_HOST` | Address to access Acestream Engine |

### PyAcexy Configuration

| Variable | Description | Default | Notes |
|----------|-------------|---------|-------|
| `ENABLE_ACEXY` | Enable Acexy proxy | `false` | Set to `true` to enable enhanced Acestream proxy |
| `ACEXY_LISTEN_ADDR` | Address for Acexy to listen on | `:8080` | Format is `[host]:port` or just `:port` |
| `ACEXY_HOST` | Hostname of Acestream Engine | `localhost` | Hostname or IP where Acestream Engine runs |
| `ACEXY_PORT` | Port of Acestream Engine | `6878` | Port where Acestream Engine is accessible |
| `ACEXY_NO_RESPONSE_TIMEOUT` | Timeout for Acestream responses | `15s` | Format: `15s`, `1m`, etc. |
| `ACEXY_BUFFER_SIZE` | Buffer size for data transfers in MiB | `5` | Format: `5`, `10`, etc. |

### Why Both PyAcexy and Acestream Engine?

Acestream Scraper includes both PyAcexy and Acestream Engine for improved multi-client handling:

1. **Connection Management**: When multiple clients access the same stream, each needs a unique process ID (PID)
2. **Automatic PID Handling**: PyAcexy automatically adds the required `pid=id` parameter to stream requests
3. **Error Isolation**: With proper PID management, one client disconnecting won't affect others
4. **Simplified URLs**: End users don't need to worry about adding PID parameters manually
5. **Performance**: PyAcexy includes buffering mechanisms to improve streaming performance

Without PyAcexy, you'd need to manually append `&pid={unique_id}` to each stream URL to properly handle multiple connections. When a stream ends for one client, without this parameter, it might terminate the stream for all users. Acexy transparently manages these connections, making the system more robust for multi-user environments.

### ZeroNet and Other Settings

| Variable | Description | Default | Notes |
|----------|-------------|---------|-------|
| `ENABLE_TOR` | Enable TOR for ZeroNet connections | `false` | Set to `true` to use TOR with ZeroNet |
| `TZ` | Timezone for the container | `Europe/Madrid` | Use any valid TZ identifier |
| `DOCKER_ENVIRONMENT` | Mark as running in Docker | `true` | Used for internal path configuration |

### WARP Configuration

Cloudflare WARP provides enhanced privacy and secure connection options:

| Variable | Description | Default | Notes |
|----------|-------------|---------|-------|
| `ENABLE_WARP` | Enable Cloudflare WARP | `false` | Requires `NET_ADMIN` and `SYS_ADMIN` capabilities |
| `WARP_LICENSE_KEY` | WARP license key | - | Optional: For WARP+ or Team accounts |

### Docker Example with WARP Enabled

```bash
docker run -d \
  -p 8040:8040 \
  --cap-add NET_ADMIN \
  --cap-add SYS_ADMIN \
  --device /dev/net/tun:/dev/net/tun \
  --sysctl net.ipv4.conf.all.src_valid_mark=1 \
  --sysctl net.ipv4.ip_forward=1 \
  -e ENABLE_WARP=true \
  -v "${PWD}/config:/app/config" \
  --name acestream-scraper \
  visesa84/acestream-scraper-pyacexy:latest
```

### Docker Compose Example with WARP Enabled

```yaml
version: '3.8'

services:
  acestream-scraper:
    image: visesa84/acestream-scraper-pyacexy:latest
    container_name: acestream-scraper
    devices:
      - /dev/net/tun:/dev/net/tun
    sysctls:
      - net.ipv4.conf.all.src_valid_mark=1
      - net.ipv4.ip_forward=1
    environment:
      - TZ=Europe/Madrid
      - ENABLE_WARP=true
    ports:
      - "8040:8040"
    volumes:
      - ./data/config:/app/config
    restart: unless-stopped
```

## Channel Status Checking

The application verifies if channels are available:

1. Ensure you have Acestream Engine running (built-in if ENABLE_ACESTREAM_ENGINE=true)
2. Configure `ace_engine_url` to point to your Acestream Engine instance
3. Use the "Check Status" buttons in the UI to verify channel availability

### Status Tracking

- The application maintains history of status checks
- Status is color-coded in the interface (green = online, red = offline)
- Error messages are displayed when a channel cannot be accessed

## Port Mapping

When using Docker, map these ports as needed:

| Port | Service | Notes |
|------|---------|-------|
| 8040 | Main web interface | Configurable via `FLASK_PORT` |
| 8080 | Acexy web interface | Only if Acexy is enabled |
| 6878 | Acestream HTTP API | Configurable via `ACESTREAM_HTTP_PORT` |
| 43110 | ZeroNet web interface | Only if ZeroNet is enabled |
| 43111 | ZeroNet transport port | Only if ZeroNet is enabled |
| 26552 | Additional ZeroNet peer port | Only if ZeroNet is enabled |
| 8621 | Acestream P2P port | For Acestream peer connections |

## Volumes

When using Docker, mount these volumes:

| Container Path | Purpose | Notes |
|----------------|---------|-------|
| `/app/config` | Configuration files | Contains config.json and database |
| `/app/ZeroNet/data` | ZeroNet data directory | Only required if using ZeroNet |

Example mount:
```bash
docker run -v "${PWD}/config:/app/config" -v "${PWD}/zeronet_data:/app/ZeroNet/data" ...
```

## ZeroNet Configuration

The application looks for a `zeronet.conf` file in the `/app/config` directory.

### Default Configuration

If no configuration file exists, this default is created:
```ini
[global]
ui_ip = *
ui_host =
 0.0.0.0
 localhost
ui_port = 43110
```

### Custom Configuration

Create your own `config/zeronet.conf`:
```ini
[global]
ui_ip = *
ui_host =
 127.0.0.1
 your.domain.com
 localhost
ui_port = 43110
```

## Running Behind a Reverse Proxy

The application includes proper headers handling for running behind a reverse proxy:

- Automatic handling of SSL/TLS termination
- Correct handling of X-Forwarded-Proto and X-Forwarded-Host headers
- Works with nginx, Apache, Traefik or other reverse proxies

### Nginx Example

```nginx
server {
    listen 80;
    server_name acestream.example.com;

    # Permanent redirect to HTTPS
    return 301 https://$host$request_uri;
}

upstream flask_app {
    server IP:8040;
}

upstream acestream_engine {
    server IP:8080;
}

server {
    listen 443 ssl http2;
    server_name acestream.example.com;

    # Certificates SSL
    ssl_certificate /etc/letsencrypt/live/acestream.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/acestream.example.com/privkey.pem;

    # ----------------------------------------------------
	# 1. Basic Authentication
    # ----------------------------------------------------
    auth_basic "Restricted Content";
    auth_basic_user_file /etc/nginx/.htpasswd;

    # ----------------------------------------------------
    #2. Forward Authorization to the backend
    # ----------------------------------------------------
    proxy_set_header Authorization $http_authorization;

    # ----------------------------------------------------
    # 3. PyAcexy App (8080)
    # ----------------------------------------------------
    location ^~ /ace {
        proxy_pass http://IP:8080;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }

    # ----------------------------------------------------
    # 4. Flask App (8040)
    # ----------------------------------------------------
    location / {
        proxy_pass http://IP:8040;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header Authorization $http_authorization;
    }
}
```

### Traefik Example

```traefik
labels:
  - "traefik.enable=true"

  # ----------------------------------------------------
  # 1. HTTP → HTTPS REDIRECT
  # ----------------------------------------------------
  - "traefik.http.routers.scraper-redirect.entrypoints=web"
  - "traefik.http.routers.scraper-redirect.rule=Host(`acestream.example.com`)"
  - "traefik.http.routers.scraper-redirect.middlewares=scraper-https"
  - "traefik.http.middlewares.scraper-https.redirectscheme.scheme=https"

  # ----------------------------------------------------
  #2. MAIN ROUTER (Flask - port 8040)
  # ----------------------------------------------------
  - "traefik.http.routers.scraper-app.rule=Host(`acestream.example.com`)"
  - "traefik.http.routers.scraper-app.entrypoints=websecure"
  - "traefik.http.routers.scraper-app.tls=true"
  - "traefik.http.routers.scraper-app.service=scraper-app-service"
  - "traefik.http.services.scraper-app-service.loadbalancer.server.port=8040"

  # ----------------------------------------------------
  # 3. PYACEXY ROUTER (port 8080)
  # HIGH PRIORITY to intercept /ace
  # ----------------------------------------------------
  - "traefik.http.routers.scraper-ace.rule=Host(`acestream.example.com`) && PathPrefix(`/ace`)"
  - "traefik.http.routers.scraper-ace.entrypoints=websecure"
  - "traefik.http.routers.scraper-ace.tls=true"
  - "traefik.http.routers.scraper-ace.priority=100"
  - "traefik.http.routers.scraper-ace.service=scraper-ace-service"
  - "traefik.http.services.scraper-ace-service.loadbalancer.server.port=8080"

  # ----------------------------------------------------
  # 4. BASIC AUTH
  # ----------------------------------------------------
  - "traefik.http.middlewares.scraper-auth.basicauth.users=usuario:$$apr1$$H64pzS7X$$h89SzhS..."

  # Apply BasicAuth to both routers
  - "traefik.http.routers.scraper-app.middlewares=scraper-auth"
  - "traefik.http.routers.scraper-ace.middlewares=scraper-auth"

  # ----------------------------------------------------
  # 5. CORRECT HEADERS FOR FLASK
  # ----------------------------------------------------
  - "traefik.http.middlewares.scraper-headers.headers.customrequestheaders.X-Forwarded-Host=acestream.example.com"
  - "traefik.http.routers.scraper-app.middlewares=scraper-auth,scraper-headers"
  - "traefik.http.routers.scraper-ace.middlewares=scraper-auth,scraper-headers"
```

### Apache VirtualHost Example

```apache
  # ----------------------------------------------------
  #Activate these modules
  # ----------------------------------------------------
	a2enmod ssl
	a2enmod proxy
	a2enmod proxy_http
	a2enmod headers
	a2enmod rewrite
	a2enmod auth_basic

<VirtualHost *:80>
    ServerName acestream.example.com
    RewriteEngine On
    RewriteRule ^(.*)$ https://%{HTTP_HOST}$1 [R=301,L]
</VirtualHost>

<VirtualHost *:443>
    ServerName acestream.example.com

    # SSL
    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/acestream.example.com/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/acestream.example.com/privkey.pem

    # ----------------------------------------------------
    # 1. BASIC AUTH
    # ----------------------------------------------------
    <Location />
        AuthType Basic
        AuthName "Restricted Content"
        AuthUserFile /etc/apache2/.htpasswd
        Require valid-user
    </Location>

    # ----------------------------------------------------
    # 2. Resend Authorization to backend
    # ----------------------------------------------------
    RequestHeader set Authorization "%{Authorization}e" env=REDIRECT_AUTHORIZATION

    # ----------------------------------------------------
    # 3. PyAcexy App (8080)
    # ----------------------------------------------------
    ProxyPass        /ace http://IP:8080/ace
    ProxyPassReverse /ace http://IP:8080/ace

    # ----------------------------------------------------
    # 4. Flask App (8040)
    # ----------------------------------------------------
    ProxyPass        / http://IP:8040/
    ProxyPassReverse / http://IP:8040/

    # ----------------------------------------------------
    # 5. Cabeceras Forwarded
    # ----------------------------------------------------
    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"
    RequestHeader set X-Forwarded-Host "%{HTTP_HOST}s"

</VirtualHost>
```

## Security Considerations

- Add your domain(s) to `ui_host` in ZeroNet config for public access
- Always include `localhost` in `ui_host` for local access
- Consider using a reverse proxy with SSL/TLS for secure access
- Configure a Custom Location in the Proxy to route the /ace path to port 8080. The URL generator utilizes Access List from Reverse Proxy to inject credentials and the domain into the streaming links
- Be aware of copyright and legal considerations when sharing playlists

## Healthchecks

The container includes comprehensive health checks:

- Main application health check at `/health` endpoint
- Acexy health check (if enabled)
- Acestream Engine health check (if enabled)
- Automatic monitoring of internal services
- Graceful handling of service dependencies

### Docker Health Check

The Docker container is configured with a health check that verifies all services are running correctly:

```yaml
healthcheck:
  test: ["CMD", "/app/healthcheck.sh"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

You can check the health status with: `docker inspect --format='{{.State.Health.Status}}' acestream-scraper
