# Acestream Scraper

A Python-based web scraping application that retrieves Acestream channel information and generates M3U playlists. Built using Flask, BeautifulSoup, and SQLAlchemy.

## Features

- Scrapes Acestream channel information from multiple URLs
- Extracts channel names and URLs from both JSON data and HTML content
- Generates M3U playlists
- Refreshes channel data on demand
- Displays channel metadata via web interface
- Supports ZeroNet URLs

## Quick Start

### Using Docker (Recommended)

1. **Pull and run the container:**
   ```bash
   docker pull pipepito/acestream-scraper:latest
   docker run -d \
     -p 8000:8000 \
     -p 43110:43110 \
     -p 43111:43111 \
     -v "${PWD}/config:/app/config" \
     pipepito/acestream-scraper:latest

2. **Create a config/config.json file:**

Create a file named `config.json` in your config directory with this content:

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

3. **Create config and run:**
   ```bash
   mkdir -p config
   # Create config/config.json as shown above
   python wsgi.py
   ```
## Usage

### Web Interface
Access the web interface at `http://localhost:8000`
![image](https://github.com/user-attachments/assets/f87abf52-bb32-42f1-97e9-b7ca84e6a24c)

### M3U Playlist
- Get playlist: `http://localhost:8000/list.m3u`
- Force refresh: `http://localhost:8000/list.m3u?refresh=true`

## Configuration

### Port Mapping
- `8000`: Main web interface
- `43110`: ZeroNet web interface
- `43111`: ZeroNet transport port

### Volumes
When using Docker, mount your local config directory to `/app/config`:
- `config.json`: Configuration file
- `acestream.db`: SQLite database (created automatically)

## Contributing

Contributions are welcome! Please fork the repository and create a pull request with your changes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgements

Special thanks to the developers of Flask, BeautifulSoup, SQLAlchemy, and other dependencies used in this project.
