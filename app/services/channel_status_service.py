import asyncio
import logging
import aiohttp
import threading
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional, List, Union, Dict, Any
from ..models import AcestreamChannel
from ..extensions import db
from ..utils.config import Config
from ..repositories.channel_repository import ChannelRepository

logger = logging.getLogger(__name__)

class ChannelStatusService:
    def __init__(self):
        config = Config()
        # Lee la URL configurada por el usuario en la BD
        raw_url = config.base_url or "http://127.0.0.1:8080"

        # Extrae estrictamente 'esquema://host:puerto' descartando rutas como /ace/getstream?id=
        parsed = urlparse(raw_url)
        netloc = parsed.netloc or parsed.path.split('/')[0]
        self.proxy_url = f"{parsed.scheme or 'http'}://{netloc}"
        
        self.timeout = aiohttp.ClientTimeout(total=10, connect=4)
        self._session = None

    async def get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def check_channel(self, channel_id: str) -> bool:
        from flask import current_app
        
        session = await self.get_session()
        if not session:
            return False

        is_online = False
        error_msg = "Unknown error"
        check_time = datetime.now()
        
        stream_url = f"{self.proxy_url}/ace/getstream"
        headers = {'Range': 'bytes=0-4095'}
        
        try:
            # allow_redirects=False evita que aiohttp falle al intentar seguir esquemas acestream://
            async with session.get(
                stream_url, 
                params={'id': channel_id}, 
                headers=headers, 
                timeout=aiohttp.ClientTimeout(total=8),
                allow_redirects=False
            ) as response:
                # Transmisión de bytes directa
                if response.status in (200, 206):
                    content = await response.content.read(4096)
                    if len(content) >= 1024:
                        is_online = True
                    else:
                        error_msg = "Stream delivered insufficient or empty data"
                # Redirección de Acexy (indica que el stream fue resuelto correctamente)
                elif response.status in (301, 302, 303, 307, 308):
                    is_online = True
                else:
                    error_msg = f"HTTP Error {response.status} from Acexy"

        except asyncio.TimeoutError:
            error_msg = "Timeout waiting for Acexy buffer"
        except Exception as e:
            logger.error(f"Error checking {channel_id} via Acexy: {e}")
            error_msg = str(e)

        # Actualización en Base de Datos
        try:
            with current_app.app_context():
                db_channel = db.session.get(AcestreamChannel, channel_id)
                if db_channel:
                    db_channel.is_online = is_online
                    db_channel.last_processed = check_time
                    db_channel.last_checked = check_time
                    db_channel.check_error = None if is_online else error_msg
                        
                    logger.info(f"[{'ONLINE' if is_online else 'OFFLINE'}] {channel_id}")
                    db.session.commit()
        except Exception as db_e:
            logger.error(f"DB Error: {db_e}")
            
        return is_online

    async def check_channels(self, channels: List[AcestreamChannel]):
        """Procesa canales en lotes de 2 conservando el tiempo original"""
        channel_ids = [c.id for c in channels]
        semaphore = asyncio.Semaphore(2)
        
        async def sem_task(cid, delay):
            await asyncio.sleep(delay)
            async with semaphore:
                return await self.check_channel(cid)

        total = len(channel_ids)
        for i in range(0, total, 2):
            from ..utils.config import Config
            if not Config().checkstatus_enabled:
                logger.info("Stopping checking status: The user has deactivated it.")
                break

            batch = channel_ids[i:i+2]
            tasks = []
            
            for idx, cid in enumerate(batch):
                delay = idx * 4  # Escalonamiento de 4 segundos por canal
                tasks.append(asyncio.create_task(sem_task(cid, delay)))
            
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(3) # Pausa de 3 segundos tras cada lote
        
        await self.close()

async def check_channel_status(channel_id_or_obj: Union[str, AcestreamChannel, Dict[str, Any]]) -> dict:
    from flask import current_app
    
    channel_id = None
    channel_name = None
    
    if isinstance(channel_id_or_obj, str):
        channel_id = channel_id_or_obj
    elif isinstance(channel_id_or_obj, dict):
        channel_id = channel_id_or_obj.get('id')
        channel_name = channel_id_or_obj.get('name', 'Unknown')
    elif hasattr(channel_id_or_obj, 'id'):
        channel_id = channel_id_or_obj.id
        channel_name = getattr(channel_id_or_obj, 'name', 'Unknown')
    
    if not channel_id:
        raise ValueError("Missing channel ID")
        
    with current_app.app_context():
        service = ChannelStatusService()
        try:
            repo = ChannelRepository()
            channel = repo.get_by_id(channel_id)
            if not channel:
                raise ValueError(f"Channel {channel_id} not found")
                
            is_online = await service.check_channel(channel_id)
            updated_channel = repo.get_by_id(channel_id)
            
            return {
                'id': channel_id,
                'name': channel_name or updated_channel.name,
                'is_online': is_online, 
                'status': 'online' if is_online else 'offline',
                'last_checked': updated_channel.last_checked,
                'error': updated_channel.check_error
            }
        finally:
            await service.close()

_status_lock = threading.Lock()
_is_running = False

def start_background_check(channels, manager=None):
    global _is_running
    from flask import current_app
    
    with _status_lock:
        if _is_running:
            logger.warning("Attempted duplicate execution aborted.")
            return
        _is_running = True

    if manager:
        manager.is_checking_status = True

    app = current_app._get_current_object()
    channel_ids = [c.id for c in channels]

    async def run_checks():
        global _is_running
        try:
            # CLAVE: Instanciar dentro de app_context para que lea la BD correctamente
            with app.app_context():
                service = ChannelStatusService()
                
                db_channels = db.session.query(AcestreamChannel).filter(AcestreamChannel.id.in_(channel_ids)).all()
                if db_channels:
                    await service.check_channels(db_channels)
        except Exception as e:
            logger.error(f"Error in background execution: {e}")
        finally:
            with app.app_context():
                db.session.remove()
            with _status_lock:
                _is_running = False
            if manager:
                manager.is_checking_status = False
            logger.info("Background process completed.")

    def run_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try: 
            loop.run_until_complete(run_checks())
        finally: 
            loop.close()
            import gc
            gc.collect()

    try:
        threading.Thread(target=run_thread, daemon=True, name="StatusCheckThread").start()
    except Exception as e:
        with _status_lock:
            _is_running = False
        if manager:
            manager.is_checking_status = False
        logger.error(f"Failed to start thread: {e}")