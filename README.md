# Acestream Scrapper

Acestream Scrapper is a Python-based web scraping application that retrieves Acestream channel information and generates M3U playlists. The application is built using Flask, BeautifulSoup, SQLAlchemy, and can be run locally or inside a Docker container.

## Features

- Scrapes Acestream channel information from multiple URLs.
- Extracts channel names and URLs from both JSON data within script tags and HTML content.
- Generates M3U playlists.
- Refreshes channel data on demand.
- Displays channel metadata on a web interface.
- Supports ZeroNet URLs.

## Prerequisites

- Python 3.9 or higher
- pip
- Docker (optional)

## Installation

1. **Clone the repository:**

    ```bash
    git clone https://github.com/yourusername/acestream-scrapper.git
    cd acestream-scrapper
    ```

2. **Create and activate a virtual environment:**

    On macOS and Linux:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

    On Windows:
    ```bash
    python -m venv venv
    venv\Scripts\activate
    ```

3. **Install the dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

4. **Set up the configuration:**

    Create a directory named `config` and add a `config.json` file inside it with the following content:

    ```json
    {
        "urls": [
            "https://example.com/url1",
            "https://example.com/url2"
        ],
        "base_url": "http://127.0.0.1:8008/ace/getstream?id="
    }
    ```

5. **Run the application:**

    ```bash
    python wsgi.py
    ```

## Usage

### Access the Web Interface

Open your web browser and navigate to `http://localhost:8000` to access the Acestream Scrapper web interface. You can view the channel metadata and add new URLs for scraping.

### Retrieve M3U Playlist

- Retrieve the M3U playlist without refreshing:

    ```bash
    curl http://localhost:8000/list.m3u
    ```

- Retrieve the M3U playlist with a refresh:

    ```bash
    curl http://localhost:8000/list.m3u?refresh=true
    ```

## Running with Docker

1. **Build the Docker image:**

    ```bash
    docker build -t acestream-scrapper .
    ```

2. **Run the Docker container, mounting the user-provided directory to `/app/config`:**

    ```bash
    docker run -p 8000:8000 -e HOST_PORT=8000 -v /path/to/your/config:/app/config acestream-scrapper
    ```

# Docker Setup for Acestream Scrapper

This document provides an overview of the required and optional variables and paths for setting up the Acestream Scrapper application using Docker. Follow these instructions to ensure a smooth setup experience.

## Required Variables and Paths

### HOST_PORT

- **Description:** The port on which the Flask application will run inside the Docker container.
- **Default Value:** `8000`
- **Usage:** This environment variable specifies the port on which the Flask application will listen for incoming requests. You can change it by setting the `HOST_PORT` environment variable when running the Docker container.

    ```bash
    docker run -p <your_host_port>:<HOST_PORT> -e HOST_PORT=<HOST_PORT> -v /path/to/your/config:/app/config acestream-scrapper
    ```

### /app/config

- **Description:** The directory inside the Docker container where the configuration file (`config.json`) and the database file (`acestream_channels.db`) are stored.
- **Usage:** You need to map a local directory containing the configuration and database files to `/app/config` inside the Docker container.

    ```bash
    docker run -p 8000:8000 -e HOST_PORT=8000 -v /path/to/your/config:/app/config acestream-scrapper
    ```

- **Directory Structure:**
    ```
    /path/to/your/config
    ├── config.json
    └── acestream_channels.db
    ```

## Optional Variables and Paths

### Custom Base URL

- **Description:** The base URL used to generate the M3U playlist.
- **Default Value:** `"http://127.0.0.1:8008/ace/getstream?id="`
- **Usage:** You can change the base URL by updating the `base_url` value in the `config.json` file.

    ```json
    {
        "urls": [
            "https://example.com/url1",
            "https://example.com/url2"
        ],
        "base_url": "http://custom-base-url/ace/getstream?id="
    }
    ```

## Running the Docker Container

- **-p 8000:8000:** Maps port 8000 on the host to port 8000 in the container.
- **-e HOST_PORT=8000:** Sets the HOST_PORT environment variable inside the container.
- **-v /path/to/your/config:/app/config:** Maps the local directory containing the configuration and database files to `/app/config` inside the container.

### Accessing the Application

After running the Docker container, you can access the Acestream Scrapper application in your web browser at [http://localhost:8000](http://localhost:8000).

### Notes

- Make sure the local directory containing the configuration and database files exists before running the Docker container.
- If the configuration file (`config.json`) does not exist, the application will create it with default values.

## Contributing

Contributions are welcome! Please fork the repository and create a pull request with your changes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

## Acknowledgements

Special thanks to the developers of Flask, BeautifulSoup, SQLAlchemy, and other dependencies used in this project.
