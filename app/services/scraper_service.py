from typing import List, Tuple
from ..repositories import URLRepository, ChannelRepository
import logging
from ..models.url_types import create_url_object
from ..models.scraped_url import BlacklistedChannel

logger = logging.getLogger(__name__)

class ScraperService:
    def __init__(self):
        self.url_repository = URLRepository()
        self.channel_repository = ChannelRepository()

    async def scrape_url(self, url: str, url_type: str = None) -> Tuple[List[Tuple[str, str, dict]], str]:
        """Scrape a URL and update channels."""
        try:
            # If URL type not provided, get it from database
            if url_type is None:
                url_obj = self.url_repository.get_by_url(url)
                url_type = url_obj.url_type if url_obj else 'regular'  # Default to regular if not found
            
            # Skip processing for special URL types that should not be scraped
            non_scrapable_types = ['search', 'manual']
            if url_type in non_scrapable_types:
                logger.info(f"Skipping URL '{url}' with type '{url_type}' (not intended for scraping)")
                # Update status to OK without actually scraping
                self.url_repository.update_status(url, 'ok')
                # Return empty links list and OK status
                return [], "OK"
            
            # Update URL status
            self.url_repository.update_status(url, 'processing')
            
            # Import here to avoid circular dependency
            from ..scrapers import create_scraper_for_url
            
            # Create and execute scraper with explicit URL type
            scraper = create_scraper_for_url(url, url_type)
            links, status = await scraper.scrape()
            
            if status == "OK":
                # Update channels with metadata
                self._update_channels(url, links)
                self.url_repository.update_status(url, status)
                
                # Update URL type in database if needed
                url_obj = create_url_object(url, url_type)
                self.url_repository.update_url_type(url, url_obj.type_name)
            else:
                self.url_repository.update_status(url, status, "Failed to scrape URL")
                
            return links, status
            
        except Exception as e:
            logger.error(f"Error scraping URL {url}: {e}")
            self.url_repository.update_status(url, 'failed', str(e))
            raise

    def _update_channels(self, url: str, links: List[Tuple[str, str, dict]]):
        """Update channels for a given URL."""
        try:
            # Traemos todos los patrones prohibidos de la base de datos
            blacklist = [b.pattern.lower().strip() for b in BlacklistedChannel.query.all()]
            
            # Creamos una nueva lista solo con los canales permitidos
            filtered_links = []
            for channel_id, channel_name, metadata in links:
                name_lower = channel_name.lower().strip()
                id_lower = channel_id.lower().strip()
                
                # Comprobamos si el nombre o el ID del canal contiene alguna palabra prohibida
                is_blacklisted = any(
                    pattern in name_lower or pattern == id_lower 
                    for pattern in blacklist
                )
                
                if is_blacklisted:
                    logger.info(f"[Global Blacklist] Skipping banned channel: '{channel_name}' (ID: {channel_id})")
                    continue # Saltamos este canal, no lo añadimos a 'filtered_links'
                    
                filtered_links.append((channel_id, channel_name, metadata))

            # A partir de aquí, usamos 'filtered_links' en vez de 'links'
            current_channels = set(channel_id for channel_id, _, _ in filtered_links)
            existing_channels = set(
                ch.id for ch in self.channel_repository.get_by_source(url)
            )
            
            # Remove old channels
            # (¡Ojo! Esto eliminará automáticamente de la base de datos los canales que ya tenías guardados pero acabas de bloquear)
            channels_to_remove = existing_channels - current_channels
            for cid in channels_to_remove:
                self.channel_repository.delete(cid) #[cite: 11]
            
            # Add/update new channels with metadata (solo los que no están bloqueados)
            for channel_id, channel_name, metadata in filtered_links:
                self.channel_repository.update_or_create(
                    channel_id=channel_id,
                    name=channel_name,
                    source_url=url,
                    metadata=metadata or {}
                )
                
            self.channel_repository.commit()
            
        except Exception as e:
            self.channel_repository.rollback()
            raise