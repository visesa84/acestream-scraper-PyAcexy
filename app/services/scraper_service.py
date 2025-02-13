from typing import List, Tuple
from ..repositories import URLRepository, ChannelRepository
from ..scrapers import create_scraper
import logging

logger = logging.getLogger(__name__)

class ScraperService:
    def __init__(self):
        self.url_repository = URLRepository()
        self.channel_repository = ChannelRepository()

    async def scrape_url(self, url: str) -> Tuple[List[Tuple[str, str]], str]:
        """Scrape a URL and update channels."""
        try:
            # Update URL status
            self.url_repository.update_status(url, 'processing')
            
            # Create and execute scraper
            scraper = create_scraper(url)
            links, status = await scraper.scrape(url)
            
            if status == "OK":
                # Update channels
                self._update_channels(url, links)
                self.url_repository.update_status(url, status)
            else:
                self.url_repository.update_status(url, status, "Failed to scrape URL")
                
            return links, status
            
        except Exception as e:
            logger.error(f"Error scraping URL {url}: {e}")
            self.url_repository.update_status(url, 'failed', str(e))
            raise

    def _update_channels(self, url: str, links: List[Tuple[str, str]]):
        """Update channels for a given URL."""
        try:
            # Get current and existing channels
            current_channels = set(channel_id for channel_id, _ in links)
            existing_channels = set(
                ch.id for ch in self.channel_repository.get_by_source(url)
            )
            
            # Remove old channels
            channels_to_remove = existing_channels - current_channels
            if channels_to_remove:
                self.channel_repository.delete_by_source(url)
            
            # Add/update new channels
            for channel_id, channel_name in links:
                self.channel_repository.update_or_create(
                    channel_id, channel_name, url
                )
                
            self.channel_repository.commit()
            
        except Exception as e:
            self.channel_repository.rollback()
            raise