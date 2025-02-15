from ..repositories import ChannelRepository
from ..utils.config import Config

class PlaylistService:
    def __init__(self):
        self.channel_repository = ChannelRepository()
        self.config = Config()

    def _format_stream_url(self, channel_id: str) -> str:
        """Format stream URL based on base_url configuration."""
        base_url = self.config.base_url
        return f'{base_url}{channel_id}'

    def generate_playlist(self) -> str:
        """Generate M3U playlist from active channels."""
        channels = self.channel_repository.get_active()
        
        playlist = ['#EXTM3U']
        for channel in channels:
            # Add metadata if available
            metadata = []
            if channel.tvg_name:
                metadata.append(f'tvg-name="{channel.tvg_name}"')
            if channel.tvg_id:
                metadata.append(f'tvg-id="{channel.tvg_id}"')
            if channel.logo:
                metadata.append(f'tvg-logo="{channel.logo}"')
            if channel.group:
                metadata.append(f'group-title="{channel.group}"')
            
            # Create EXTINF line with metadata
            extinf = '#EXTINF:-1'
            if metadata:
                extinf += f' {" ".join(metadata)}'
            extinf += f',{channel.name}'
            
            playlist.append(extinf)
            playlist.append(self._format_stream_url(channel.id))
            
        return '\n'.join(playlist)