from typing import List, Tuple
from ..repositories import URLRepository, ChannelRepository
import logging
import inspect
import re
from ..models.url_types import create_url_object
from ..models.scraped_url import BlacklistedChannel

logger = logging.getLogger(__name__)

def clean_channel_name(name: str) -> str:
    if not name:
        return ""
    
    cleaned = re.sub(r'https?://\S+|www\.\S+', '', name)
    cleaned = re.sub(r'\[.*?\]|\(.*?\)', '', cleaned)
    cleaned = cleaned.replace('|', ' ').replace('_', ' ')
    cleaned = ' '.join(cleaned.split())
    
    return cleaned

class ScraperService:
    def __init__(self):
        self.url_repository = URLRepository()
        self.channel_repository = ChannelRepository()

    async def scrape_url(self, url: str, url_type: str = None) -> Tuple[List[Tuple[str, str, dict]], str]:
        """Scrape a URL and update channels."""
        try:
            if url_type is None:
                url_obj = self.url_repository.get_by_url(url)
                url_type = url_obj.url_type if url_obj else 'regular'

            # ----------------------------------------------------
            # 1. BÚSQUEDA DINÁMICA DE ACESTREAM (url_type == 'search')
            # ----------------------------------------------------
            if url_type == 'search':
                logger.info(f"Executing dynamic re-search for query URL: '{url}'")
                self.url_repository.update_status(url, 'processing')
                
                query = url.replace('search://', '').replace('-', ' ').strip()
                
                from ..services.acestream_search_service import AcestreamSearchService
                search_service = AcestreamSearchService()
                
                # Ejecutar re-búsqueda masiva con search_all_pages
                if inspect.iscoroutinefunction(search_service.search_all_pages):
                    raw_response = await search_service.search_all_pages(query)
                else:
                    raw_response = search_service.search_all_pages(query)
                
                if isinstance(raw_response, dict):
                    results_list = raw_response.get('results', [])
                else:
                    results_list = raw_response or []

                links = []
                for res in results_list:
                    if not isinstance(res, dict):
                        continue
                    content_id = res.get('content_id') or res.get('id') or res.get('acestream_id')
                    name = res.get('name') or query.upper()
                    metadata = res.get('metadata') or {}
                    if content_id:
                        links.append((content_id, name, metadata))

                self._update_channels(url, links)
                self.url_repository.update_status(url, 'ok')
                return links, "OK"

            # ----------------------------------------------------
            # 2. TIPOS NO RASPABLES (solo 'manual')
            # ----------------------------------------------------
            non_scrapable_types = ['manual']
            if url_type in non_scrapable_types:
                logger.info(f"Skipping URL '{url}' with type '{url_type}' (not intended for scraping)")
                self.url_repository.update_status(url, 'ok')
                return [], "OK"
            
            # ----------------------------------------------------
            # 3. SCRAPING HABITUAL (HTTP, IPFS, ZERONET)
            # ----------------------------------------------------
            self.url_repository.update_status(url, 'processing')
            
            from ..scrapers import create_scraper_for_url
            
            scraper = create_scraper_for_url(url, url_type)
            links, status = await scraper.scrape()
            
            if status == "OK":
                self._update_channels(url, links)
                self.url_repository.update_status(url, status)
                
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
        """Update channels for a given URL applying Global Blacklist filtering."""
        try:
            blacklist = [b.pattern.lower().strip() for b in BlacklistedChannel.query.all()]
            
            filtered_links = []
            for channel_id, channel_name, metadata in links:
                name_lower = channel_name.lower().strip()
                id_lower = channel_id.lower().strip()
                
                # Coincidencia parcial por subcadena tanto en nombre como en ID
                is_blacklisted = any(
                    pattern in name_lower or pattern in id_lower 
                    for pattern in blacklist
                )
                
                if is_blacklisted:
                    logger.info(f"[Global Blacklist] Skipping banned channel: '{channel_name}' (ID: {channel_id})")
                    continue
                    
                filtered_links.append((channel_id, channel_name, metadata))

            current_channels = set(channel_id for channel_id, _, _ in filtered_links)
            existing_channels = set(
                ch.id for ch in self.channel_repository.get_by_source(url)
            )
            
            # Remove old channels
            channels_to_remove = existing_channels - current_channels
            for cid in channels_to_remove:
                self.channel_repository.delete(cid)
            
            # Add/update new channels
            for channel_id, channel_name, metadata in filtered_links:
                cleaned_name = clean_channel_name(channel_name)
                
                self.channel_repository.update_or_create(
                    channel_id=channel_id,
                    name=cleaned_name,
                    source_url=url,
                    metadata=metadata or {}
                )
                
            self.channel_repository.commit()
            
        except Exception as e:
            self.channel_repository.rollback()
            raise