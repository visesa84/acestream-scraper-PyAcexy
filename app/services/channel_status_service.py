import asyncio
import logging
import aiohttp
from datetime import datetime, timezone
from typing import Optional
from ..models import AcestreamChannel
from ..extensions import db
from ..utils.config import Config
from ..repositories.channel_repository import ChannelRepository  # Add this import

logger = logging.getLogger(__name__)

class ChannelStatusService:
    """Service for checking Acestream channel status."""
    
    def __init__(self):
        config = Config()
        self.ace_engine_url = config.ace_engine_url
        self.timeout = 10
        self.repo = ChannelRepository()  # Create single repository instance
        
    async def check_channel(self, channel: AcestreamChannel) -> bool:
        """
        Check if a channel is alive by querying the Acestream engine.
        Returns True if channel is online, False otherwise.
        """
        try:
            check_time = datetime.now(timezone.utc)
            
            # Build status check URL
            status_url = f"{self.ace_engine_url}/ace/getstream"
            params = {
                'id': channel.id,
                'format': 'json',
                'method': 'get_status'
            }
            
            logger.info(f"Checking channel {channel.id} ({channel.name}) status at {status_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(status_url, 
                                     params=params,
                                     timeout=self.timeout) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            
                            if isinstance(data, dict):
                                response_data = data.get('response', {})
                                error = data.get('error')
                                
                                # Check for "got newer download" message
                                if error and "got newer download" in str(error).lower():
                                    self.repo.update_channel_status(channel.id, True, check_time)
                                    logger.info(f"Channel {channel.id} ({channel.name}) is online (newer version available)")
                                    return True
                                
                                # Check regular online status
                                if (error is None and 
                                    response_data and 
                                    response_data.get('is_live') == 1):
                                    self.repo.update_channel_status(channel.id, True, check_time)
                                    logger.info(f"Channel {channel.id} ({channel.name}) is online")
                                    return True
                                
                                # Channel exists but not available
                                error_msg = error if error else "Channel is not live"
                                self.repo.update_channel_status(channel.id, False, check_time, error_msg)
                                logger.info(f"Channel {channel.id} ({channel.name}) is offline: {error_msg}")
                                return False
                                
                            self.repo.update_channel_status(channel.id, False, check_time, "Invalid response format")
                            return False
                                
                        except ValueError as e:
                            self.repo.update_channel_status(channel.id, False, check_time, f"Invalid response format: {str(e)}")
                            return False
                    
                    self.repo.update_channel_status(channel.id, False, check_time, f"HTTP {response.status}")
                    return False
            
        except Exception as e:
            logger.error(f"Error checking channel {channel.id}: {e}")
            self.repo.update_channel_status(channel.id, False, check_time, str(e))
            return False
            
    async def check_channels(self, channels: list[AcestreamChannel], concurrency: int = 5):
        """Check multiple channels concurrently."""
        semaphore = asyncio.Semaphore(concurrency)
        
        async def check_with_semaphore(channel):
            async with semaphore:
                return await self.check_channel(channel)
        
        tasks = [check_with_semaphore(channel) for channel in channels]
        return await asyncio.gather(*tasks)

async def check_channel_status(channel: AcestreamChannel) -> dict:
    """Check status of a single channel."""
    service = ChannelStatusService()
    is_online = await service.check_channel(channel)
    
    return {
        'is_online': is_online,
        'last_checked': channel.last_checked,
        'error': channel.check_error
    }

def check_all_channels_status() -> dict:
    """Check status for all channels in the database."""
    try:
        from ..repositories.channel_repository import ChannelRepository
        
        # Get all channels
        channel_repo = ChannelRepository()
        channels = channel_repo.get_all()
        
        # Create service instance
        service = ChannelStatusService()
        
        # Always create a new event loop in thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Run status checks using new loop
            results = loop.run_until_complete(service.check_channels(channels))
            
            # Count results
            online_count = sum(1 for result in results if result)
            offline_count = len(results) - online_count
            
            return {
                'online': online_count,
                'offline': offline_count,
                'total': len(results)
            }
        finally:
            # Clean up the loop
            loop.close()
            
    except Exception as e:
        logger.error(f"Error checking all channels status: {e}", exc_info=True)
        raise