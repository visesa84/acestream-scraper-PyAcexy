import logging
import os
import requests
import time
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class AcestreamStatusService:
    """Service for checking Acestream Engine status."""
    
    # Variable de clase para compartir la caché entre todas las instancias
    _cache = None
    _last_check = 0
    _cache_duration = 30  # Segundos que guardamos el estado
    
    def __init__(self, engine_url: str = None):
        """
        Initialize the service with optional custom engine URL.
        
        Args:
            engine_url: Optional URL from Config for external Acestream engine
        """
        self.config_engine_url = engine_url
        self.is_internal_engine = self.is_enabled()
        
        # Determine the URL to use based on whether internal engine is enabled
        if self.is_internal_engine:
            # Use environment variables for internal engine
            host = os.environ.get('ACESTREAM_HTTP_HOST', 'localhost')
            if host == "ACEXY_HOST":
                host = os.environ.get('ACEXY_HOST', 'localhost')
            port = os.environ.get('ACESTREAM_HTTP_PORT', '6878')
            self.engine_url = f"http://{host}:{port}"
        else:
            # Use the config URL for external engine
            self.engine_url = self.config_engine_url
            
            # If still no URL provided, use a default
            if not self.engine_url:
                self.engine_url = "http://localhost:6878"
        
        # If URL doesn't start with a protocol, assume http://
        if not self.engine_url.startswith('http'):
            self.engine_url = f"http://{self.engine_url}"
        
        # Ensure the URL doesn't end with a slash
        self.engine_url = self.engine_url.rstrip('/')
        
        logger.debug(f"Acestream Engine URL set to: {self.engine_url} (internal engine: {self.is_internal_engine})")
    
    def is_enabled(self) -> bool:
        """Check if internal Acestream Engine is enabled based on environment variable."""
        return os.environ.get('ENABLE_ACESTREAM_ENGINE', 'false').lower() == 'true'
    
    def check_status(self) -> Dict[str, Any]:
        """
        Check Acestream Engine status and return details.
        
        Returns:
            Dict with status details including:
            - enabled: Whether the internal engine is enabled (for UI logic)
            - is_internal: Whether the engine is internal or external
            - engine_url: The URL being used for the engine
            - available: Whether any engine (internal or external) is responding
            - message: Status message
            - version: Engine version if available
            - platform: Engine platform if available
            - connected: Whether engine is connected to network
            - playlist_loaded: Whether engine has loaded its playlist
        """
        # 1. Retornar caché si es reciente
        now = time.time()
        if AcestreamStatusService._cache and (now - AcestreamStatusService._last_check < self._cache_duration):
            return AcestreamStatusService._cache
        
        # Always attempt to check status, regardless of whether internal engine is enabled
        try:
            # 2. Solo hacemos UNA petición para no saturar
            status_url = f"{self.engine_url}/server/api?api_version=3&method=get_status"
            # Bajamos el timeout a 1.5 para ser más ágiles
            status_response = requests.get(status_url, timeout=1.5)
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                res = status_data.get('result', {})
                
                version = res.get('version', {}).get('version', 'Unknown')
                
                result = {
                    "enabled": self.is_internal_engine,
                    "is_internal": self.is_internal_engine,
                    "engine_url": self.engine_url,
                    "available": True,
                    "message": f"Acestream Engine v{version} is online",
                    "version": version,
                    "platform": res.get('version', {}).get('platform', 'Unknown'),
                    "playlist_loaded": res.get('playlist_loaded', False),
                    "connected": True # Si respondió el status, asumimos conexión básica
                }
                # Guardamos en caché
                AcestreamStatusService._cache = result
                AcestreamStatusService._last_check = now
                return result

        except Exception as e:
            # Logueamos como warning para no ensuciar el log de errores críticos
            logger.warning(f"Acestream Engine timeout/error: {str(e)}")
            
        # Si falla, devolvemos estado offline (y no cacheamos el error para reintentar antes)
        return {
            "enabled": self.is_internal_engine,
            "available": False,
            "message": "Acestream Engine is offline or slow",
            "is_internal": self.is_internal_engine,
            "engine_url": self.engine_url
        }