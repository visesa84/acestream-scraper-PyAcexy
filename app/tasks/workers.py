import asyncio
import logging
from typing import List, Tuple
from datetime import datetime, timedelta
from ..models import AcestreamChannel, ScrapedURL, EPGSource
from ..extensions import db
from ..scrapers import create_scraper_for_url
from ..services.epg_service import EPGService

logger = logging.getLogger(__name__)

class ScrapeWorker:
    """Worker class for executing scraping tasks."""
    
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(self, url: str) -> Tuple[List[Tuple[str, str, dict]], str]:
        """Execute a scraping task for a single URL."""
        async with self.semaphore:
            # Get URL type from database
            url_obj = ScrapedURL.query.filter_by(url=url).first()
            url_type = url_obj.url_type if url_obj else 'auto'
            
            # Create scraper with the correct URL type
            scraper = create_scraper_for_url(url, url_type)
            return await scraper.scrape()

class ChannelCleanupWorker:
    """Worker class for cleaning up old channels."""
    
    def __init__(self, max_age_days: int = 7):
        self.max_age_days = max_age_days

    async def cleanup_old_channels(self):
        """Remove channels that haven't been seen in a while."""
        cutoff_date = datetime.now() - timedelta(days=self.max_age_days)
        
        try:
            old_channels = AcestreamChannel.query.filter(
                AcestreamChannel.last_processed < cutoff_date
            ).all()
            
            for channel in old_channels:
                db.session.delete(channel)
            
            db.session.commit()
            logger.info(f"Removed {len(old_channels)} old channels")
            
        except Exception as e:
            logger.error(f"Error during channel cleanup: {e}")
            db.session.rollback()


class EPGRefreshWorker:
    """Worker class for refreshing EPG data and programs."""
    
    def __init__(self, cleanup_old_programs_days: int = 7):
        self.cleanup_old_programs_days = cleanup_old_programs_days
        self.epg_service = EPGService()
    
    async def refresh_epg_data(self, source_url=None):
        """
        Ahora acepta una URL opcional. Si se pasa, fuerza la descarga de esa fuente.
        """
        try:
            logger.info(f"Starting EPG download: {source_url if source_url else 'Default sources'}")
            
            # Llamamos directamente a fetch, saltándonos el should_refresh_epg del service
            epg_data = self.epg_service.fetch_epg_data(source_url)
            if epg_data is None:
                logger.error("El Service devolvió None. Revisa la conexión o la URL.")
                return 0
            
            await self.cleanup_old_programs()
            return len(epg_data)
        except Exception as e:
            logger.error(f"Worker Error: {e}")
            raise

    async def cleanup_old_programs(self):
        """Remove old program data to prevent database bloat."""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.cleanup_old_programs_days)
            
            deleted_count = self.epg_service.epg_program_repo.delete_old_programs(cutoff_date)
            logger.info(f"Cleaned up {deleted_count} old EPG programs (older than {self.cleanup_old_programs_days} days)")
            
        except Exception as e:
            logger.error(f"Error during EPG program cleanup: {e}")