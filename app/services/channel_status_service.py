import asyncio
import logging
import aiohttp
import threading
from datetime import datetime
from typing import Optional, List, Union, Dict, Any
from ..tasks.channel_vision_manager import ChannelVisionManager
from ..models import AcestreamChannel
from ..extensions import db
from ..utils.config import Config
from ..repositories.channel_repository import ChannelRepository

logger = logging.getLogger(__name__)

class ChannelStatusService:
    def __init__(self):
        config = Config()
        self.ace_engine_url = config.ace_engine_url 
        # Puerto 8080: Para saber si tú estás viendo el canal
        self.proxy_url = "/".join(config.base_url.split("/")[:3])
        self.vision = ChannelVisionManager()
        self.timeout = aiohttp.ClientTimeout(total=5, connect=2)
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
            logger.error("No session available")
            return False

        is_online = False
        is_already_watching = False
        command_url = None
        stream_url = None
        download_speed = 0
        error_msg = "Unknown error"
        check_time = datetime.now()
        nombre_ia = None
        channel_data = None
        
        try:
            # 1. PROXY
            try:
                status_url = f"{self.proxy_url}/ace/status"
                async with session.get(status_url, params={'id': channel_id}, timeout=3) as st_resp:
                    if st_resp.status == 200:
                        status_data = await st_resp.json() or {}
                        if status_data.get('clients', 0) > 0:
                            is_already_watching = True
                            is_online = True
            except Exception:
                pass

            # 2. MOTOR
            if not is_already_watching:
                get_url = f"{self.ace_engine_url}/ace/getstream"
                async with session.get(get_url, params={'id': channel_id, 'format': 'json'}) as response:
                    data = {}
                    if response.status == 200:
                        data = await response.json() or {}
                    
                    resp_data = data.get('response') or {} 
                    stat_url = resp_data.get('stat_url')
                    command_url = resp_data.get('command_url')
                    
                    if stat_url:
                        for attempt in range(5):
                            await asyncio.sleep(3)
                            async with session.get(stat_url) as s_resp:
                                if s_resp.status == 200:
                                    s_data = await s_resp.json() or {}
                                    res_obj = s_data.get('response') or {}
                                    download_speed = int(res_obj.get('speed_down', 0))
                                    if download_speed > 0:
                                        is_online = True
                                        break
                        if not is_online:
                            error_msg = f"Speed 0 after {attempt+1} attempts"
                    else:
                        error_msg = data.get('error', "No stat_url")

            if is_online:
                # Usamos el contexto para obtener el objeto canal antes de la IA
                with current_app.app_context():
                    db_channel = db.session.get(AcestreamChannel, channel_id)
                    if db_channel:
                        channel_data = {
                            'id': db_channel.id,
                            'logo': db_channel.logo
                        }
                # Ejecutamos la verificación visual completa
                stream_url = f"{self.ace_engine_url}/ace/getstream?id={channel_id}"
                nombre_ia = await self.vision.procesar_verificacion_completa(channel_data, stream_url)
                        
        except Exception as e:
            logger.error(f"Error checking {channel_id}: {e}")
            error_msg = str(e)
        
        finally:
            if command_url and not is_already_watching:
                try:
                    async with session.get(f"{command_url}?method=stop", timeout=2) as r:
                        await r.release()
                except:
                    pass

        # 3. DB
        try:
            with current_app.app_context():
                db_channel = db.session.get(AcestreamChannel, channel_id)
                if db_channel:
                    # Guardamos el nombre antiguo para comparar
                    nombre_antiguo = db_channel.name

                    db_channel.is_online = is_online
                    db_channel.last_processed = check_time
                    db_channel.last_checked = check_time
                    if is_online:
                        db_channel.check_error = None
                        # Si la IA reconoció el logo, actualizamos nombre
                        if nombre_ia and str(nombre_ia).strip() != "None":
                            if nombre_antiguo != nombre_ia:
                                db_channel.name = nombre_ia
                                logger.info(f"[IA] ID: {channel_id} | '{nombre_antiguo}' -> '{nombre_ia}'")
                    else:
                        db_channel.check_error = error_msg
                        
                    logger.info(f"[{'ONLINE' if is_online else 'OFFLINE'}] {channel_id} | {download_speed} KB/s")
                    db.session.commit()
                    
        except Exception as db_e:
            logger.error(f"DB Error: {db_e}")
            
        return is_online

    async def check_channels(self, channels: List[AcestreamChannel]):
        """Procesa canales de 2 en 2 con escalonamiento dinámico"""
        channel_ids = [c.id for c in channels]
        semaphore = asyncio.Semaphore(2)
        
        async def sem_task(cid, delay):
            # El escalonamiento ayuda a que el motor no colapse al inicio
            await asyncio.sleep(delay)
            async with semaphore:
                return await self.check_channel(cid)

        # Procesamos por parejas
        for i in range(0, len(channel_ids), 2):
            batch = channel_ids[i:i+2]
            tasks = []
            
            for idx, cid in enumerate(batch):
                # El 1º sale al seg 0, el 2º sale al seg 4 para dejar espacio al motor
                delay = idx * 4 
                tasks.append(asyncio.create_task(sem_task(cid, delay)))
            
            # Esperamos a que la pareja termine sus chequeos
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Pausa de recuperación tras cerrar ambos streams
            await asyncio.sleep(3)
        
        await self.close()

async def check_channel_status(channel_id_or_obj: Union[str, AcestreamChannel, Dict[str, Any]]) -> dict:
    """
    Check status of a single channel.
    """
    from flask import current_app
    
    # 1. Extraer el ID del canal
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
        
    # 2. Inicializar el servicio
    service = ChannelStatusService()
    is_online = False
    
    try:
        with current_app.app_context():
            repo = ChannelRepository()
            channel = repo.get_by_id(channel_id)
            if not channel:
                raise ValueError(f"Channel {channel_id} not found")
                
            # 3. Realizar el chequeo asíncrono
            is_online = await service.check_channel(channel_id)
            
            # Recargar para obtener datos frescos tras el commit del servicio
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
        # 4. LIMPIEZA OBLIGATORIA: Cerramos la sesión de aiohttp del servicio
        await service.close()

# Bloqueo global para este módulo
_status_lock = threading.Lock()
_is_running = False

def start_background_check(channels, manager=None):
    global _is_running
    from flask import current_app
    
    # Bloqueo atómico para evitar doble hilo
    with _status_lock:
        if _is_running:
            logger.warning("Attempted duplicate execution aborted.")
            return
        _is_running = True

    if manager:
        manager.is_checking_status = True

    app = current_app._get_current_object()
    channel_ids = [c.id for c in channels]
    total = len(channel_ids)

    async def run_checks():
        global _is_running
        try:
            from .channel_status_service import ChannelStatusService
            service = ChannelStatusService()
            batch_size = 2
            
            # Procesamos de 2 en 2
            for i in range(0, len(channel_ids), batch_size):
                from ..utils.config import Config
                if not Config().checkstatus_enabled:
                    logger.info("Stopping checking status: The user has deactivated it.")
                    break
                batch_ids = channel_ids[i:i + batch_size]
                with app.app_context():
                    # RE-CONSULTA: Vital para evitar el error de SQLite de hilos
                    batch = db.session.query(AcestreamChannel).filter(AcestreamChannel.id.in_(batch_ids)).all()
                    if batch:
                        logger.info(f"Processing pair: {i+1}-{min(i+batch_size, total)} of {total}")
                        await service.check_channels(batch)
                        
                        db.session.commit()
                        db.session.expunge_all() # Saca los objetos de la RAM
                        db.session.remove()      # Cierra la sesión de este hilo/contexto
                await asyncio.sleep(1)
        finally:
            with _status_lock:
                _is_running = False
            if manager:
                manager.is_checking_status = False
            logger.info("Background process completed.")

    def run_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try: loop.run_until_complete(run_checks())
        finally: loop.close()
        import gc
        gc.collect() # Limpia la RAM al morir el bucle asyncio

    threading.Thread(target=run_thread, daemon=True, name="StatusCheckThread").start()
