from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import logging
from app.db_setup import AcestreamChannel, ScrapedURL
from app.config_loader import load_urls_from_config
from app.acestream_scraper import fetch_acestream_channels
from app.zeronet_scraper import fetch_zeronet_channels

executor = ThreadPoolExecutor(max_workers=5)

def refresh_acestream_channels(config_dir, Session):
    global last_refresh_date, last_item_count
    last_item_count = Session.query(AcestreamChannel).count()
    Session.query(AcestreamChannel).delete()
    Session.commit()
    
    load_urls_from_config(config_dir, Session)

    urls = Session.query(ScrapedURL).all()  # Load URLs from the database
    future_to_url = {
        executor.submit(fetch_acestream_channels, url.url, Session) if "43110" not in url.url else executor.submit(fetch_zeronet_channels, url.url, Session): url.url for url in urls if url.url
    }
    for future in as_completed(future_to_url):
        url = future_to_url[future]
        try:
            channels, status = future.result()
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
    return last_refresh_date

def generate_m3u_content(base_url, Session):
    m3u_content = '#EXTM3U @Pipepito\n'
    channels = Session.query(AcestreamChannel).all()

    for channel in channels:
        m3u_content += f'#EXTINF:-1,{channel.name}\n{base_url}{channel.id}\n'

    return m3u_content
