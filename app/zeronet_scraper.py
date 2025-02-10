from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re
from app.db_setup import AcestreamChannel, ScrapedURL
from datetime import datetime

def fetch_zeronet_channels(url, Session, timeout=10, retries=3):
    status = "OK"
    channels = []
    identified_ids = set()

    options = Options()
    options.headless = True
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
    except Exception as e:
        if retries > 0:
            return fetch_zeronet_channels(url, Session, timeout + 5, retries - 1)
        else:
            status = "Error"
            return channels, status
    finally:
        driver.quit()

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
