import re
import json
from bs4 import BeautifulSoup
import requests
from datetime import datetime
from app.db_setup import AcestreamChannel, ScrapedURL

def fetch_acestream_channels(url, Session, timeout=10, retries=3):
    status = "OK"
    channels = []
    identified_ids = set()

    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
    except requests.RequestException as e:
        if retries > 0:
            return fetch_acestream_channels(url, Session, timeout + 5, retries - 1)
        else:
            status = "Error"
            return channels, status

    script_tag = soup.find('script', text=re.compile(r'const linksData'))
    if script_tag:
        script_content = script_tag.string
        json_str = re.search(r'const linksData = (\{.*?\});', script_content, re.DOTALL)
        if json_str:
            links_data = json.loads(json_str.group(1))
            for link in links_data['links']:
                if 'acestream://' in link['url']:
                    id = link['url'].split('acestream://')[1]
                    if id:
                        channels.append((id, link['name']))
                        identified_ids.add(id)

    ids = re.findall(r'acestream://([\w\d]+)', str(soup))
    for id in ids:
        if id not in identified_ids:
            link_name_div = soup.find('div', class_='link-name')
            channel_name = link_name_div.text.strip() if link_name_div else f"Channel {id}"
            if id:
                channels.append((id, channel_name))

    url_record = Session.query(ScrapedURL).filter_by(url=url).first()
    if not url_record:
        url_record = ScrapedURL(url=url, status=status, last_processed=datetime.utcnow())
    else:
        url_record.status = status
        url_record.last_processed = datetime.utcnow()
    Session.add(url_record)
    Session.commit()

    return channels, status
