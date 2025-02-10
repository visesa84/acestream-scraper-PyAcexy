import os
from flask import Flask

app = Flask(__name__)

from app.config_loader import load_urls_from_config
from app.db_setup import setup_database

# Set the config directory
config_dir = '/app/config' if os.getenv('DOCKER_ENV') == 'true' else os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config'))

# Setup the database
Session = setup_database(config_dir)

# Load configuration and URLs
load_urls_from_config(config_dir, Session)

from app import routes
