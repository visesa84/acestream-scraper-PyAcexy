from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import and_, or_
from app.extensions import db
from app.models.epg_program import EPGProgram
from app.models.recording_schedule import RecordingSchedule
from sqlalchemy.dialects.sqlite import insert
import logging

logger = logging.getLogger(__name__)

class EPGProgramRepository:
    """Repository for managing EPG program data."""
    
    def create(self, program_data: Dict[str, Any]) -> EPGProgram:
        """Create a new EPG program."""
        program = EPGProgram(**program_data)
        db.session.add(program)
        db.session.commit()
        return program
    
    def bulk_insert(self, programs_data: List[Dict[str, Any]]) -> int:
        """Bulk insert EPG programs for better performance."""
        try:
            if not programs_data:
                return 0
            
            # SQLite-specific upsert (INSERT OR REPLACE)
            # This will replace any existing records that would violate the unique constraint
            stmt = insert(EPGProgram).prefix_with('OR REPLACE')
            db.session.execute(stmt, programs_data)
            db.session.commit()
            
            logger.info(f"Bulk inserted {len(programs_data)} EPG programs")
            return len(programs_data)
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error in bulk_insert: {str(e)}")
            raise
    
    def get_by_id(self, program_id: int) -> Optional[EPGProgram]:
        """Get program by ID."""
        return EPGProgram.query.get(program_id)
    
    def get_programs_for_channel(self, epg_channel_id: int, start_time: datetime = None, end_time: datetime = None):
        # Consulta limpia de programas para el canal específico
        programs = EPGProgram.query.filter_by(epg_channel_id=epg_channel_id).order_by(EPGProgram.start_time).all()
        
        # Obtenemos IDs de grabaciones para este canal de una sola vez
        scheduled_ids = [r[0] for r in db.session.query(RecordingSchedule.program_id).all()]

        programs_with_status = []
        for p in programs:
            # EXTRAEMOS EL ID REAL DE LA FILA DE LA BASE DE DATOS
            real_db_id = int(p.id) 
            
            # Construimos el diccionario
            prog_data = {
                'id': real_db_id, # <--- ESTE ID NO PUEDE FALLAR
                'start_time': p.start_time.isoformat(),
                'end_time': p.end_time.isoformat(),
                'title': str(p.title),
                'description': str(p.description) if p.description else "",
                'is_recording': real_db_id in scheduled_ids
            }
            programs_with_status.append(prog_data)
                
        return programs_with_status
    
    def get_current_program(self, epg_channel_id: int, current_time: datetime = None) -> Optional[EPGProgram]:
        """Get the current program for a channel."""
        if current_time is None:
            current_time = datetime.now()
        
        return EPGProgram.query.filter(
            EPGProgram.epg_channel_id == epg_channel_id,
            EPGProgram.start_time <= current_time,
            EPGProgram.end_time > current_time
        ).first()
    
    def delete_by_channel_id(self, epg_channel_id: int) -> int:
        """Delete all programs for a specific EPG channel."""
        count = EPGProgram.query.filter(EPGProgram.epg_channel_id == epg_channel_id).count()
        EPGProgram.query.filter(EPGProgram.epg_channel_id == epg_channel_id).delete()
        db.session.commit()
        return count
    
    def delete_by_source_id(self, epg_source_id: int) -> int:
        """Delete all programs for channels from a specific EPG source."""
        from app.models.epg_channel import EPGChannel
        from sqlalchemy import select
        
        # First get the list of channel IDs from the source
        channel_ids = db.session.query(EPGChannel.id).filter(
            EPGChannel.epg_source_id == epg_source_id
        ).all()
        channel_ids = [c[0] for c in channel_ids]
        
        if not channel_ids:
            return 0
        
        # Count programs
        count = EPGProgram.query.filter(
            EPGProgram.epg_channel_id.in_(channel_ids)
        ).count()
        
        # Delete programs for these channels
        EPGProgram.query.filter(
            EPGProgram.epg_channel_id.in_(channel_ids)
        ).delete(synchronize_session=False)
        
        db.session.commit()
        return count
    
    def delete_old_programs(self, cutoff_date: datetime) -> int:
        """Delete programs older than the cutoff date."""
        count = EPGProgram.query.filter(EPGProgram.end_time < cutoff_date).count()
        EPGProgram.query.filter(EPGProgram.end_time < cutoff_date).delete()
        db.session.commit()
        return count
    
    def get_programs_count_by_channel(self, epg_channel_id: int) -> int:
        """Get the count of programs for a specific channel."""
        return EPGProgram.query.filter(EPGProgram.epg_channel_id == epg_channel_id).count()
    
    def update(self, program: EPGProgram) -> EPGProgram:
        """Update an existing program."""
        program.updated_at = datetime.now()
        db.session.commit()
        return program
    
    def delete(self, program: EPGProgram) -> bool:
        """Delete a specific program."""
        try:
            db.session.delete(program)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting program {program.id}: {str(e)}")
            return False
            
    def toggle_recording(self, program_id: int) -> Dict[str, Any]:
        """
        Activa o desactiva una grabación.
        Retorna un diccionario con el nuevo estado.
        """
        try:
            # Verificar si ya existe la grabación
            existing = RecordingSchedule.query.filter_by(program_id=program_id).first()

            if existing:
                # Si existe, la eliminamos
                db.session.delete(existing)
                db.session.commit()
                return {'status': 'removed', 'program_id': program_id}
            else:
                # Si no existe, la creamos
                new_recording = RecordingSchedule(
                    program_id=program_id,
                    status='pending'
                )
                db.session.add(new_recording)
                db.session.commit()
                return {'status': 'scheduled', 'program_id': program_id}

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error in toggle_recording for program {program_id}: {str(e)}")
            raise