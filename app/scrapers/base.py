import re
import logging
import json
from abc import ABC, abstractmethod
from typing import List, Tuple, Set
from datetime import datetime
from bs4 import BeautifulSoup

from ..extensions import db
from ..models import ScrapedURL
from ..services.m3u_service import M3UService

logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    """Base scraper class with common acestream link extraction logic."""

    def __init__(self, timeout: int = 10, retries: int = 3):
        self.timeout = timeout
        self.retries = retries
        self.acestream_pattern = re.compile(r'acestream://([\w\d]+)')
        self.m3u_pattern = re.compile(r'https?://[^\s<>"]+?\.m3u[8]?(?=[\s<>"]|$)')
        self.identified_ids: Set[str] = set()
        self.m3u_service = M3UService()

    @abstractmethod
    async def fetch_content(self, url: str) -> str:
        """Fetch content from the source URL."""
        pass

    def extract_from_script(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """Extract acestream links from script tags."""
        channels = []
        script_tag = soup.find('script', text=re.compile(r'const linksData'))
        
        if script_tag:
            script_content = script_tag.string
            json_str = re.search(r'const linksData = (\{.*?\});', script_content, re.DOTALL)
            if json_str:
                try:
                    links_data = json.loads(json_str.group(1))
                    for link in links_data.get('links', []):
                        if 'acestream://' in link.get('url', ''):
                            id = link['url'].split('acestream://')[1]
                            if id and id not in self.identified_ids:
                                channels.append((id, link.get('name', f'Channel {id}')))
                                self.identified_ids.add(id)
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing JSON from script tag: {e}")

        return channels

    def extract_from_content(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """Extract acestream links from general content."""
        channels = []
        ids = self.acestream_pattern.findall(str(soup))
        
        for id in ids:
            if id not in self.identified_ids:
                link_name_div = soup.find('div', class_='link-name')
                channel_name = link_name_div.text.strip() if link_name_div else f"Channel {id}"
                channels.append((id, channel_name))
                self.identified_ids.add(id)

        return channels

    async def extract_from_m3u_links(self, content: str) -> List[Tuple[str, str, dict]]:
        """Extract channels from M3U files linked in the content."""
        channels = []
        
        # Find M3U links in content
        m3u_urls = await self.m3u_service.find_m3u_links(content, self.current_url)
        
        # Add any direct M3U URLs found via regex
        direct_m3u_urls = set(self.m3u_pattern.findall(content))
        m3u_urls.extend(direct_m3u_urls)
        
        # Process each unique M3U URL
        for m3u_url in set(m3u_urls):
            try:
                m3u_channels = await self.m3u_service.extract_channels_from_m3u(m3u_url)
                for channel_id, name, metadata in m3u_channels:
                    if channel_id not in self.identified_ids:
                        channels.append((channel_id, name, metadata))
                        self.identified_ids.add(channel_id)
            except Exception as e:
                logger.warning(f"Failed to process M3U file {m3u_url}: {e}")
                
        return channels

    async def scrape(self, url: str) -> Tuple[List[Tuple[str, str, dict]], str]:
        """Main scraping method."""
        self.current_url = url  # Store current URL for relative path resolution
        channels = []
        status = "OK"
        retries_left = self.retries

        while retries_left >= 0:
            try:
                content = await self.fetch_content(url)
                soup = BeautifulSoup(content, 'html.parser')
                
                # Extract from all sources
                script_channels = [(id, name, {}) for id, name in self.extract_from_script(soup)]
                content_channels = [(id, name, {}) for id, name in self.extract_from_content(soup)]
                m3u_channels = await self.extract_from_m3u_links(content)
                
                channels.extend(script_channels)
                channels.extend(content_channels)
                channels.extend(m3u_channels)
                
                break
            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")
                retries_left -= 1
                if retries_left < 0:
                    status = "Error"
                    break
                self.timeout += 5

        # Update URL status in database
        self.update_url_status(url, status)
        
        return channels, status

    def update_url_status(self, url: str, status: str, error: str = None):
        """Update URL status in database."""
        url_record = ScrapedURL.query.filter_by(url=url).first()
        
        if not url_record:
            url_record = ScrapedURL(url=url)
        
        url_record.update_status(status, error)
        db.session.add(url_record)
        db.session.commit()