from db_setup import setup_database
from config_loader import load_urls_from_config
from acestream_scraper import fetch_acestream_channels
from zeronet_scraper import fetch_zeronet_channels
from task_manager import refresh_acestream_channels, generate_m3u_content

# Determine the config directory based on the environment
config_dir = '/app/config' if os.getenv('DOCKER_ENV') == 'true' else os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config2'))

# Setup the database
Session = setup_database(config_dir)

# Load URLs from the config file on startup
load_urls_from_config(config_dir, Session)

