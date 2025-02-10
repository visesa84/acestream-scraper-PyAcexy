import os
import json
import requests
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import create_engine, Column, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from app import app

executor = ThreadPoolExecutor(max_workers=5)  # Adjust the number of workers as needed

Base = declarative_base()

class AcestreamChannel(Base):
    __tablename__ = 'acestream_channels'
    id = Column(String, primary_key=True)
    name = Column(String)
    added_at = Column(DateTime, default=datetime.utcnow)
    last_processed = Column(DateTime)

class ScrapedURL(Base):
    __tablename__ = 'scraped_urls'
    url = Column(Text, primary_key=True)
    status = Column(String)
    last_processed = Column(DateTime)

# Determine the config directory based on the environment
if os.getenv('DOCKER_ENV') == 'true':
    config_dir = '/app/config'
else:
    config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../config')

# Use the config directory for the database file
db_path = os.path.join(config_dir, 'acestream_channels.db')
engine = create_engine(f'sqlite:///{db_path}', connect_args={'check_same_thread': False})
Base.metadata.create_all(engine)

# Use scoped_session to ensure thread safety
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

def load_urls_from_config():
    config_path = os.path.join(config_dir, 'config.json')
    with open(config_path, 'r') as f:
        config_data = json.load(f)
        urls = config_data['urls']
        for url in urls:
            if url and not Session.query(ScrapedURL).filter_by(url=url).first():
                url_record = ScrapedURL(url=url, status='Pending', last_processed=None)
                Session.add(url_record)
        Session.commit()

def fetch_acestream_channels(url, timeout=10, retries=3):
    status = "OK"
    if not url:
        status = "Error"
        return []

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Error fetching URL {url}: {e}")
        if retries > 0:
            logging.info(f"Retrying {url} ({retries} retries left)...")
            return fetch_acestream_channels(url, timeout + 5, retries - 1)
        else:
            status = "Error"
            return []

    soup = BeautifulSoup(response.content, 'html.parser')

    channels = []
    identified_ids = set()

    # Find and parse the script tag containing the linksData JSON
    script_tag = soup.find('script', text=re.compile(r'const linksData'))
    if script_tag:
        script_content = script_tag.string
        json_str = re.search(r'const linksData = (\{.*?\});', script_content, re.DOTALL)
        if json_str:
            links_data = json.loads(json_str.group(1))
            for link in links_data['links']:
                if 'acestream://' in link['url']:
                    id = link['url'].split('acestream://')[1]
                    if id:  # Ensure ID is not empty
                        channels.append((id, link['name']))
                        identified_ids.add(id)

    # Find all acestream links in the entire HTML that haven't been identified
    ids = re.findall(r'acestream://([\w\d]+)', str(soup))
    for id in ids:
        if id not in identified_ids:
            # Extract the channel name from the div with class link-name
            link_name_div = soup.find('div', class_='link-name')
            channel_name = link_name_div.text.strip() if link_name_div else f"Channel {id}"
            if id:  # Ensure ID is not empty
                channels.append((id, channel_name))

    # Update the ScrapedURL table with the status and timestamp
    url_record = Session.query(ScrapedURL).filter_by(url=url).first()
    if not url_record:
        url_record = ScrapedURL(url=url, status=status, last_processed=datetime.utcnow())
    else:
        url_record.status = status
        url_record.last_processed = datetime.utcnow()
    Session.add(url_record)
    Session.commit()

    return channels

def refresh_acestream_channels():
    global last_refresh_date, last_item_count
    last_item_count = Session.query(AcestreamChannel).count()
    Session.query(AcestreamChannel).delete()
    Session.commit()
    
    # Synchronize the URLs from the config file with the database
    load_urls_from_config()

    # Use ThreadPoolExecutor to fetch channels in parallel
    urls = Session.query(ScrapedURL).all()  # Load URLs from the database
    future_to_url = {executor.submit(fetch_acestream_channels, url.url): url.url for url in urls if url.url}
    for future in as_completed(future_to_url):
        url = future_to_url[future]
        try:
            channels = future.result()
            for id, name in channels:
                if id and not Session.query(AcestreamChannel).filter_by(id=id).first():  # Ensure ID is not empty
                    channel = AcestreamChannel(id=id, name=name, last_processed=datetime.utcnow())
                    Session.add(channel)
            Session.commit()
        except Exception as e:
            logging.error(f"Error fetching channels from URL {url}: {e}")
            Session.rollback()
    
    last_refresh_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logging.info(f"Refreshed acestream channels: {Session.query(AcestreamChannel).count()} items found.")

def generate_m3u_content(base_url):
    m3u_content = '#EXTM3U @Pipepito\n'
    channels = Session.query(AcestreamChannel).all()

    for channel in channels:
        m3u_content += f'#EXTINF:-1,{channel.name}\n{base_url}{channel.id}\n'

    return m3u_content

# Load URLs from the config file on startup
load_urls_from_config()
