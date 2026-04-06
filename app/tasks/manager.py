import asyncio
import logging
import time
import aiohttp
import re
from datetime import datetime, timedelta
from typing import Optional, List, Union, Dict, Any
from ..models import ScrapedURL, AcestreamChannel
from ..extensions import db
from ..scrapers import create_scraper
from flask import current_app
from sqlalchemy.exc import OperationalError
from contextlib import contextmanager
from ..services import ScraperService
from ..repositories import URLRepository
from ..utils.config import Config
from .workers import EPGRefreshWorker
from app.models.epg_source import EPGSource
from app.services.epg_service import EPGService
from app.services.tv_channel_service import TVChannelService
from app.services.channel_status_service import start_background_check

class TaskManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.is_checking_status = False
        self.MAX_RETRIES = 3
        #self.config = Config()
        self.config = None
        self.RETRY_DELAY = 60  # seconds between retries
        self.app = None
        self._processing_urls = set()
        self.scraper_service = ScraperService()
        self.url_repository = URLRepository()
        self.epg_refresh_worker = EPGRefreshWorker()
        self.tv_channel_service = TVChannelService()
        # Setting last_epg_refresh to None will force an initial refresh
        # This will be updated after the first refresh
        self.last_epg_refresh = None
        # Track if channels were updated during current cycle
        self.channels_updated_in_cycle = False
    
    def init_app(self, app):
        """Initialize with Flask app context"""
        self.app = app
        # INICIALIZA AQUÍ LA CONFIGURACIÓN:
        from app.utils.config import Config
        self.config = Config()
        self.running = True

    @contextmanager
    def database_retry(self, max_retries=3):
        """Context manager for handling SQLite disk I/O errors with retries."""
        retry_count = 0
        while True:
            try:
                yield
                break
            except OperationalError as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise
                self.logger.warning(f"SQLite error, retrying ({retry_count}/{max_retries}): {e}")
                db.session.rollback()
                time.sleep(1)

    def add_task(self, task_type: str, *args, **kwargs):
        """
        Este es el puente entre Flask y el TaskManager.
        Lanza la tarea en el background de asyncio (Uvicorn).
        """
        if task_type == 'scrape_url':
            url = args[0] if args else kwargs.get('url')
            if not url:
                return
            
            self.logger.info(f"Manual trigger for URL: {url}")
            
            # Intentamos obtener el loop de Uvicorn/Asyncio
            try:
                loop = asyncio.get_running_loop()
                # Lanzamos la tarea sin bloquear la respuesta de la API
                loop.create_task(self.process_url(url))
            except RuntimeError:
                # Si por algún motivo no hay loop (desarrollo local), creamos uno
                self.logger.warning("No running loop found, starting task in new thread")
                asyncio.run(self.process_url(url))
    
    async def process_url(self, url: str):
        if url in self._processing_urls:
            self.logger.info(f"URL {url} is already being processed")
            return
            
        self._processing_urls.add(url)        
        try:
            if self.app and not current_app._get_current_object():
                with self.app.app_context():
                    links, status = await self.scraper_service.scrape_url(url)
                    # Track if channels were actually updated (not just checked)
                    if status == "OK" and links:
                        self.channels_updated_in_cycle = True
            else:
                links, status = await self.scraper_service.scrape_url(url)
                # Track if channels were actually updated (not just checked)
                if status == "OK" and links:
                    self.channels_updated_in_cycle = True
        finally:
            self._processing_urls.remove(url)
    
    def should_refresh_epg(self):
        """Check if EPG data needs to be refreshed."""
        sources = EPGSource.query.filter_by(enabled=True).all()
        config = Config()
        refresh_interval = timedelta(hours=config.epg_refresh_interval)
        now = datetime.now()

        for source in sources:
            if not source.last_updated:
                self.logger.info(f"Source '{source.url}' requires initial refresh.")
                return True
                
            if (now - source.last_updated) >= refresh_interval:
                self.logger.info(f"Source '{source.url}' expired (Last: {source.last_updated}).")
                return True
                
        return False

    async def refresh_epg_if_needed(self):
        """Refresh EPG data if the refresh interval has passed."""
        sources = EPGSource.query.filter_by(enabled=True).all()
        config = Config()
        refresh_interval = timedelta(hours=config.epg_refresh_interval)
        now = datetime.now()

        for source in sources:
            # Verificamos cada fuente individualmente
            needs_update = (not source.last_updated) or \
                           (now - source.last_updated >= refresh_interval)

            if needs_update:
                try:
                    self.logger.info(f"Updating EPG from: {source.url}")
                    
                    await self.epg_refresh_worker.refresh_epg_data(source.url)
                    
                    # Actualizamos la DB específicamente para esta fuente
                    source.last_updated = now
                    source.error_count = 0
                    db.session.commit()
                    self.logger.info(f"EPG '{source.url}' successfully updated.")
                    
                except Exception as e:
                    db.session.rollback()
                    source.error_count += 1
                    source.last_error = str(e)
                    db.session.commit()
                    self.logger.error(f"Error updating {source.url}: {e}")
        
    async def start(self):
        """Main task loop."""
        if not self.app:
            raise RuntimeError("TaskManager not initialized with Flask app. Call init_app() first.")
            
        self.running = True
        self.logger.info("Task Manager started")
        while self.running:
            await asyncio.sleep(5)
            try:
                with self.app.app_context():
                    # Check and refresh EPG data if needed
                    await self.refresh_epg_if_needed()

                    config = Config()                    
                    cutoff_time_epg = datetime.now() - timedelta(hours=config.rescrape_interval)
                    urls = ScrapedURL.query.filter(
                        (ScrapedURL.status != 'disabled') &  # Skip disabled URLs
                        ((ScrapedURL.status == 'pending') |
                         ((ScrapedURL.status == 'failed') & 
                          (ScrapedURL.error_count < self.MAX_RETRIES)) |
                         (ScrapedURL.last_processed < cutoff_time_epg))
                    ).all()
                    
                    if urls:
                        self.logger.info(f"Found {len(urls)} URLs to process")
                        # Reset the update tracking flag at the start of a new cycle
                        self.channels_updated_in_cycle = False
                        
                        # Process all URLs
                        for url_obj in urls:
                            if url_obj.url not in self._processing_urls:
                                if url_obj.status == 'OK':
                                    url_obj.status = 'pending'
                                    db.session.commit()
                                await self.process_url(url_obj.url)
                                # IMPORTANTE: Da un respiro al servidor después de cada URL
                                await asyncio.sleep(5)
                        
                        # After all URLs are processed, associate channels if any were updated
                        if self.channels_updated_in_cycle:
                            self.logger.info("URLs processed, re-associating channels by EPG ID...")
                            await self.associate_channels_by_epg()
                            await asyncio.sleep(5)
                            
                    # 2. Lógica de Status Channels
                    # Verificamos primero si la tarea está habilitada en la configuración
                    if not config.checkstatus_enabled:
                        self.logger.debug("Automatic status checking is disabled by the user.")
                    
                    elif not self.is_checking_status:
                        cutoff = datetime.now() - timedelta(hours=config.checkstatus_interval)
                        
                        channels = AcestreamChannel.query.filter(
                            (AcestreamChannel.status == 'active'),
                            (AcestreamChannel.last_processed.is_(None)) |
                            (AcestreamChannel.last_processed < cutoff)
                        ).all()

                        if channels:
                            self.logger.info(f"Found {len(channels)} channels to check.")
                            # Pasamos 'self' para que el servicio pueda resetear is_checking_status
                            start_background_check(channels, manager=self)
                            await asyncio.sleep(5)
                    else:
                        self.logger.debug("The status check is already underway...")

                                
            except Exception as e:
                self.logger.error(f"Task Manager error: {str(e)}")
            await asyncio.sleep(self.RETRY_DELAY)

    def stop(self):
        """Stop the task manager loop."""
        self.running = False
        self.logger.info("Task Manager stopped")

    async def associate_channels_by_epg(self):
        """Associate acestream channels with TV channels based on EPG ID."""
        try:
            self.logger.info("Starting automatic EPG association after scraping")
            
            # Asumimos que associate_by_epg_id() es síncrona o necesita ser awaited
            # Si es asíncrona, usa: stats = await self.tv_channel_service.associate_by_epg_id()
            stats = self.tv_channel_service.associate_by_epg_id()
            
            # Extraer resultados para el log
            matched = stats.get('matched', 0)
            created = stats.get('created', 0)
            unmatched = stats.get('unmatched', 0)
            
            if matched > 0 or created > 0:
                self.logger.info(f"EPG Association complete: Created {created} TV channels, matched {matched} acestreams, {unmatched} remain unmatched")
            else:
                self.logger.debug("EPG Association complete: No new associations made")
                
        except Exception as e:
            self.logger.error(f"Error during automatic EPG association: {str(e)}")
