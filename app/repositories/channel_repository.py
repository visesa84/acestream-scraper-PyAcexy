from datetime import datetime
from typing import List, Set
from ..models import AcestreamChannel
from .base import BaseRepository

class ChannelRepository(BaseRepository[AcestreamChannel]):
    def __init__(self):
        super().__init__(AcestreamChannel)

    def get_active(self) -> List[AcestreamChannel]:
        return self.model.query.filter_by(status='active').all()
        
    def get_by_source(self, source_url: str) -> List[AcestreamChannel]:
        return self.model.query.filter_by(source_url=source_url).all()
        
    def delete_by_source(self, source_url: str):
        self.model.query.filter_by(source_url=source_url).delete()
        
    def update_or_create(self, channel_id: str, name: str, source_url: str) -> AcestreamChannel:
        channel = (self.model.query.get(channel_id) or 
                  self.model(id=channel_id))
        channel.name = name
        channel.last_processed = datetime.utcnow()
        channel.status = 'active'
        channel.source_url = source_url
        self._db.session.merge(channel)
        return channel