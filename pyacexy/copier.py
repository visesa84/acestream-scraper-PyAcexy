"""Stream copier module for handling data transfer"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class StreamCopier:
    """Handles copying data from AceStream to multiple clients"""
    
    def __init__(self, buffer_size: int = 4 * 1024 * 1024):
        self.buffer_size = buffer_size
        self._buffer = bytearray()
        self._clients = set()
        self._lock = asyncio.Lock()
    
    async def copy_stream(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        Copy stream data from AceStream to a client
        
        Args:
            reader: Stream reader from AceStream
            writer: Stream writer to client
        """
        try:
            while True:
                chunk = await reader.read(8192)
                if not chunk:
                    break
                
                async with self._lock:
                    self._buffer.extend(chunk)
                    
                    # Write to all connected clients
                    for client_writer in list(self._clients):
                        try:
                            client_writer.write(chunk)
                            await client_writer.drain()
                        except Exception as e:
                            logger.error(f"Error writing to client: {e}")
                            self._clients.discard(client_writer)
                
                # Limit buffer size
                if len(self._buffer) > self.buffer_size:
                    self._buffer = self._buffer[-self.buffer_size:]
                    
        except Exception as e:
            logger.error(f"Error copying stream: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
    
    def add_client(self, writer: asyncio.StreamWriter):
        """Add a client to receive stream data"""
        self._clients.add(writer)
    
    def remove_client(self, writer: asyncio.StreamWriter):
        """Remove a client from receiving stream data"""
        self._clients.discard(writer)
    
    def get_buffer(self) -> bytes:
        """Get current buffer content"""
        return bytes(self._buffer)
