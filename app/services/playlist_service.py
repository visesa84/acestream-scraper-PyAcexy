from ..repositories import ChannelRepository

class PlaylistService:
    def __init__(self):
        self.channel_repository = ChannelRepository()

    def generate_playlist(self) -> str:
        """Generate M3U playlist from active channels."""
        channels = self.channel_repository.get_active()
        
        playlist = ['#EXTM3U']
        for channel in channels:
            playlist.append(f'#EXTINF:-1,{channel.name}')
            playlist.append(f'acestream://{channel.id}')
            
        return '\n'.join(playlist)