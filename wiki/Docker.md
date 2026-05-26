# Docker Guide

## What is Docker?

Docker is a platform that uses containerization technology to package applications and their dependencies together in isolated containers. These containers are lightweight, portable units that can run consistently across different environments.

### Key Docker Concepts

- **Container**: A lightweight, standalone executable package that includes everything needed to run an application
- **Image**: A read-only template used to create containers
- **Dockerfile**: A script with instructions for building a Docker image
- **Docker Compose**: A tool for defining and running multi-container applications
- **Volume**: Persistent data storage that exists outside the container lifecycle

### Benefits of Using Docker with Acestream Scraper

1. **Simplified Installation**: No need to worry about dependencies or system compatibility
2. **Consistent Environment**: Works the same way on any system that supports Docker
3. **Built-in Services**: Easily includes Acestream Engine, ZeroNet, and Acexy proxy
4. **Isolation**: Keeps the application and its dependencies contained
5. **Easy Updates**: Simple command to update to the latest version
6. **Resource Management**: Controls how much system resources the application can use

## Docker vs. Docker Compose

### Docker
- Manages individual containers
- Best for simple deployments
- Uses CLI commands to configure containers
- Example: `docker run -p 8040:8040 visesa84/acestream-scraper-pyacexy:latest`

### Docker Compose
- Manages multi-container applications
- Configuration in a YAML file
- Easier to maintain complex setups
- Example: `docker-compose up -d`

For Acestream Scraper, Docker Compose is recommended as it makes managing all configuration parameters easier.

## Basic Docker Commands

### Pull the Image
```bash
docker pull visesa84/acestream-scraper-pyacexy:latest
```

### Run the Container
```bash
docker run -d -p 8040:8040 --name acestream-scraper visesa84/acestream-scraper-pyacexy:latest
```

### View Running Containers
```bash
docker ps
```

### View Container Logs
```bash
docker logs acestream-scraper
```

### Stop the Container
```bash
docker stop acestream-scraper
```

### Remove the Container
```bash
docker rm acestream-scraper
```

### Update to Latest Version
```bash
docker pull visesa84/acestream-scraper-pyacexy:latest
docker stop acestream-scraper
docker rm acestream-scraper
# Run the container again with your preferred configuration
```

## Docker Compose Commands

### Start Services
```bash
docker-compose up -d
```

### View Logs
```bash
docker-compose logs
```

### Stop Services
```bash
docker-compose down
```

### Update to Latest Version
```bash
docker-compose pull
docker-compose up -d
```

## Docker Data Persistence

Acestream Scraper uses Docker volumes to persist data:

- `/app/config`: Configuration files including database
- `/app/recordings`: Records files
- `/app/ZeroNet/data`: ZeroNet data directory (if using ZeroNet)

These volumes should be mounted to local directories to ensure your data persists when containers are updated or replaced.

Example:
```bash
docker run -d -p 8040:8040 -v "${PWD}/config:/app/config" -v "${PWD}/recordings:/app/config/recordings" visesa84/acestream-scraper-pyacexy:latest
```

This mounts your local `./config` directory to the container's `/app/config` directory.

## Environment Variables (Canonical Reference)

The following table is the canonical reference for environment variables used by the Docker image and entrypoint. Override any value in your `docker run` or `docker-compose` configuration.

| Variable | Default | Description |
|---|---:|---|
| `DOCKER_ENV` | (unset) | When present, container treats paths as Docker mounts and uses `/app/config` for config and DB. |
| `ENABLE_ACEXY` | `true` | Enable the PyAcexy proxy. |
| `ACEXY_LISTEN_ADDR` | `:8080` | Listen address for PyAcexy. |
| `ACEXY_HOST` | `localhost` | Hostname/IP where PyAcexy connects to the engine. |
| `ACEXY_PORT` | `6878` | Port of the Acestream Engine. |
| `ENABLE_ACESTREAM_ENGINE` | `true` | Start internal Acestream Engine instances. If `false`, entrypoint forces `CHECKSTATUS_ENABLED=false`. |
| `ACESTREAM_HTTP_PORT` | `6878` | Main Acestream Engine HTTP port; background-checker uses `6879` internally. |
| `CHECKSTATUS_ENABLED` | `true` | Enable automatic stream status checking; may be overridden by entrypoint logic. |

Notes:
- `start_two_engines.sh` and `bind_remap.so` are used to run a background checker engine while remapping P2P ports (default remap `8621`→`8622`) to avoid collisions.
