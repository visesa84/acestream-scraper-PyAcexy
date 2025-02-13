# Acestream Scraper

A Python-based web scraping application that retrieves Acestream channel information and generates M3U playlists. Built using Flask, BeautifulSoup, and SQLAlchemy.

## Features

- Scrapes Acestream channel information from multiple URLs
- Extracts channel names and URLs from both JSON data and HTML content
- Generates M3U playlists with optional refresh
- Refreshes channel data on demand
- Displays channel metadata via web interface
- Supports ZeroNet URLs
- Database migrations support
- Service-oriented architecture
- Repository pattern for data access

## Quick Start

### Using Docker (Recommended)

[Image in Docker Hub](https://hub.docker.com/r/pipepito/acestream-scraper)

1. **Pull and run the container:**
   ```bash
   docker pull pipepito/acestream-scraper:latest
   docker run -d \
     -p 8000:8000 \
     -p 43110:43110 \
     -p 43111:43111 \
     -v "${PWD}/config:/app/config" \
     pipepito/acestream-scraper:latest
   ```

2. **Create a config/config.json file:**
   ```json
   {
       "urls": [
           "https://example.com/url1",
           "https://example.com/url2"
       ],
       "base_url": "http://127.0.0.1:8008/ace/getstream?id="
   }
   ```

### Manual Installation

1. **Prerequisites:**
   - Python 3.9 or higher
   - pip

2. **Setup:**
   ```bash
   git clone https://github.com/Pipepito/acestream-scraper.git
   cd acestream-scraper
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Create config and run:**
   ```bash
   mkdir -p config
   # Create config/config.json as shown above
   python run_dev.py  # For development
   # or
   python wsgi.py     # For production
   ```

## Usage

### Web Interface
Access the web interface at `http://localhost:8000`

### M3U Playlist
- Get current playlist: `http://localhost:8000/playlist.m3u`
- Force refresh and get playlist: `http://localhost:8000/playlist.m3u?refresh=true`

### Database Management
The application now includes database migration support:

```bash
# Initialize database (first time only)
python manage.py init

# Create a new migration
python manage.py migrate "description"

# Apply migrations
python manage.py upgrade

# Rollback migrations
python manage.py downgrade
```

## Configuration

### Port Mapping
- `8000`: Main web interface
- `43110`: ZeroNet web interface
- `43111`: ZeroNet transport port

### Volumes
When using Docker, mount your local config directory to `/app/config`:
- `config.json`: Configuration file
- `acestream.db`: SQLite database (created automatically)

### Development
For development, use `run_dev.py` which provides:
- Debug mode
- Auto-reloading (disabled for task manager thread)
- Windows compatibility

## Architecture

The application follows a service-oriented architecture with:
- Repository pattern for data access
- Service layer for business logic
- Migrations support for database changes
- Async task management
- Clear separation of concerns

## Contributing

Contributions are welcome! Please fork the repository and create a pull request with your changes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgements

Special thanks to the developers of Flask, BeautifulSoup, SQLAlchemy, and other dependencies used in this project.
