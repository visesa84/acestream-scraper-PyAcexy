from flask import Flask
import logging
import json
import os

app = Flask(__name__)

# Define the config path and default config values
config_path = '/app/config/config.json'
default_config = {
    "urls": [
        "https://ipfs.io/ipns/k51qzi5uqu5dgg9al11vomikugim0o1i3l3fxp3ym3jwaswmy9uz8pq4brg1u9",
        "https://ipfs.io/ipns/k51qzi5uqu5di00365631hrj6m22vsjudpbtw8qpfw6g08gf3lsqdn6e89anq5",
        "https://proxy.zeronet.dev/1JKe3VPvFe35bm1aiHdD4p1xcGCkZKhH3Q"
    ],
    "base_url": "http://127.0.0.1:8008/ace/getstream?id="
}

# Ensure the config directory exists
os.makedirs('/app/config', exist_ok=True)

# Create the config file with default values if it doesn't exist
if not os.path.exists(config_path):
    with open(config_path, 'w') as f:
        json.dump(default_config, f, indent=4)

# Load configuration from config file
with open(config_path, 'r') as f:
    config = json.load(f)
app.config.update(config)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from app import routes, tasks
