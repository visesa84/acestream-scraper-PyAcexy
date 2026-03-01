import re
from typing import Optional
from urllib.parse import urlparse, parse_qs

class StreamService:
    """Service for handling different stream URL formats."""
    
    def __init__(self):
        self.acestream_pattern = re.compile(r'acestream://([\w\d]+)')
        self.id_pattern = re.compile(r'[\w\d]{40}')
    
    def extract_acestream_id(self, url: str) -> Optional[str]:
        """Extract acestream ID from different URL formats."""
        # Direct acestream:// protocol
        if url.startswith('acestream://'):
            match = self.acestream_pattern.match(url)
            return match.group(1) if match else None
            
        # HTTP URL with acestream ID in query params
        parsed = urlparse(url)
        if parsed.scheme in ['http', 'https']:
            # Check query parameters
            query = parse_qs(parsed.query)
            
            # Common parameter names for acestream IDs
            id_params = ['id', 'pid', 'stream_id', 'acestream_id']
            
            for param in id_params:
                if param in query:
                    value = query[param][0]
                    if self.id_pattern.match(value):
                        return value
            
            # Check if the ID is in the path
            path_parts = parsed.path.split('/')
            for part in path_parts:
                if self.id_pattern.match(part):
                    return part
                    
        return None