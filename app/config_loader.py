import os
import json
from app.db_setup import ScrapedURL
from app import app

def load_urls_from_config(config_dir, Session):
    # Ensure the config directory exists
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    config_path = os.path.join(config_dir, 'config.json')
    print(f"Config path: {config_path}")  # Debugging line to print the config path
    with open(config_path, 'r') as f:
        config_data = json.load(f)
        
        # Set base_url in Flask app config
        app.config['base_url'] = config_data.get('base_url', 'acestream://')
        
        urls = config_data.get('urls', [])
        for url in urls:
            if url and not Session.query(ScrapedURL).filter_by(url=url).first():
                url_record = ScrapedURL(url=url, status='Pending', last_processed=None)
                Session.add(url_record)
        Session.commit()
