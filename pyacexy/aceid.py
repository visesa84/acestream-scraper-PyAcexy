"""AceStream ID management module"""
import hashlib
from typing import Dict, Set


class AceIDManager:
    """Manages unique PIDs (Player IDs) for AceStream connections"""
    
    def __init__(self):
        self._pids: Dict[str, Set[str]] = {}
    
    def generate_pid(self, stream_id: str, client_id: str) -> str:
        """
        Generate a unique PID for a client watching a specific stream
        
        Args:
            stream_id: The AceStream content ID
            client_id: Unique identifier for the client
            
        Returns:
            A unique PID string
        """
        # Create a unique hash based on stream and client
        pid_input = f"{stream_id}:{client_id}"
        pid = hashlib.md5(pid_input.encode()).hexdigest()[:16]
        
        # Track PIDs per stream
        if stream_id not in self._pids:
            self._pids[stream_id] = set()
        self._pids[stream_id].add(pid)
        
        return pid
    
    def remove_pid(self, stream_id: str, pid: str):
        """Remove a PID when client disconnects"""
        if stream_id in self._pids:
            self._pids[stream_id].discard(pid)
            if not self._pids[stream_id]:
                del self._pids[stream_id]
    
    def get_stream_pids(self, stream_id: str) -> Set[str]:
        """Get all active PIDs for a stream"""
        return self._pids.get(stream_id, set())
