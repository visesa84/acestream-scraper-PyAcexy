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
    
    # 1. Eliminar URLs o dominios publicitarios (ej. www.canal.com, http://...)
    cleaned = re.sub(r'https?://\S+|www\.\S+', '', name)
    
    # 2. Eliminar corchetes o paréntesis con calidades/idiomas si lo deseas (ej. [DE], [1080p], (HD))
    #    Nota: Si quieres conservar la calidad, elimina esta línea.
    cleaned = re.sub(r'\[.*?\]|\(.*?\)', '', cleaned)
    
    # 3. Reemplazar símbolos molestos (como tuberías '|' o guiones bajos) por espacios
    cleaned = cleaned.replace('|', ' ').replace('_', ' ')
    
    # 4. Normalizar múltiples espacios a uno solo y recortar bordes
    cleaned = ' '.join(cleaned.split())
    
    return cleaned

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
                url_type = url_obj.url_type if url_obj else 'regular'

            # ----------------------------------------------------
            # 1. BÚSQUEDA DINÁMICA DE ACESTREAM (url_type == 'search')
            # ----------------------------------------------------
            if url_type == 'search':
                logger.info(f"Executing dynamic re-search for query URL: '{url}'")
                self.url_repository.update_status(url, 'processing')
                
                # Extraemos la búsqueda original: search://dazn-1 -> "dazn 1"
                query = url.replace('search://', '').replace('-', ' ').strip()
                
                from ..services.acestream_search_service import AcestreamSearchService
                search_service = AcestreamSearchService()
                
                # Ejecutamos la búsqueda (soportando sincrónico y asincrónico)
                if inspect.iscoroutinefunction(search_service.search):
                    raw_response = await search_service.search(query)
                else:
                    raw_response = search_service.search(query)
                
                # Extraer la lista de la clave 'results' si viene envuelta en un dict
                if isinstance(raw_response, dict):
                    results_list = raw_response.get('results', [])
                else:
                    results_list = raw_response or []

                # Formateamos resultados en la tupla estándar (channel_id, channel_name, metadata)
                links = []
                for res in results_list:
                    if not isinstance(res, dict):
                        continue
                    content_id = res.get('content_id') or res.get('id') or res.get('acestream_id')
                    name = res.get('name') or query.upper()
                    metadata = res.get('metadata') or {}
                    if content_id:
                        links.append((content_id, name, metadata))

                # Actualizamos canales y aplicamos filtro de Blacklist
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
            
            # Add/update new channels with metadata
            for channel_id, channel_name, metadata in filtered_links:
                # <-- Limpieza aplicada aquí antes de guardar
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