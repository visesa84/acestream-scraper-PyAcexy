from typing import List, Optional
from datetime import datetime
from app.models.epg_source import EPGSource
from app.models.epg_channel import EPGChannel
from app.models.epg_program import EPGProgram
from app.extensions import db

class EPGSourceRepository:
    def get_all(self) -> List[EPGSource]:
        """Get all EPG sources."""
        return EPGSource.query.all()
    
    def get_enabled(self) -> List[EPGSource]:
        """Get all enabled EPG sources."""
        return EPGSource.query.filter_by(enabled=True).all()
    
    def get_by_id(self, id: int) -> Optional[EPGSource]:
        """Get EPG source by ID."""
        return EPGSource.query.get(id)
    
    def get_by_url(self, url: str) -> Optional[EPGSource]:
        """Busca una fuente por su URL exacta."""
        return EPGSource.query.filter_by(url=url).first()
    
    def create(self, source: EPGSource) -> EPGSource:
        """Create a new EPG source."""
        db.session.add(source)
        db.session.commit()
        return source
    
    def update(self, source: EPGSource) -> EPGSource:
        """Update an existing EPG source."""
        db.session.commit()
        return source
    
    def delete(self, source: EPGSource) -> None:
        """Elimina una fuente de EPG, sus canales y todos sus programas."""
        try:
            # 1. Obtener los IDs de todos los canales de esta fuente
            channels = EPGChannel.query.filter_by(epg_source_id=source.id).all()
            channel_ids = [channel.id for channel in channels]

            if channel_ids:
                # 2. Borrar todos los programas asociados a esos canales
                EPGProgram.query.filter(EPGProgram.epg_channel_id.in_(channel_ids)).delete(synchronize_session=False)
                
                # 3. Borrar los canales de la fuente
                EPGChannel.query.filter_by(epg_source_id=source.id).delete(synchronize_session=False)

            # 4. Finalmente, borrar la fuente
            db.session.delete(source)
            
            # Un solo commit para asegurar la atomicidad de la operación
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e
    
    def toggle_enabled(self, source: EPGSource) -> EPGSource:
        """Toggle enabled status of an EPG source."""
        source.enabled = not source.enabled
        db.session.commit()
        return source
    
    def update_last_updated(self, source: EPGSource) -> EPGSource:
        """Update last_updated timestamp."""
        source.last_updated = datetime.now()
        db.session.commit()
        return source