from app.extensions import db
from sqlalchemy import event

class RecordingSchedule(db.Model):
    __tablename__ = 'recording_schedules'
    
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('epg_programs.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    
    # Estas columnas ahora se llenarán automáticamente
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    
    retry_start = db.Column(db.DateTime, nullable=True)

    program = db.relationship('EPGProgram', backref=db.backref('recording_info', uselist=False))

# --- AUTOMATIZACIÓN ---
@event.listens_for(RecordingSchedule, 'before_insert')
def sync_times_from_program(mapper, connection, target):
    """Copia start_time y end_time desde EPGProgram antes de guardar"""
    if target.program_id:
        # Buscamos el programa relacionado para extraer sus tiempos
        from app.models import EPGProgram  # Import local para evitar importación circular
        program = db.session.get(EPGProgram, target.program_id)
        if program:
            target.start_time = program.start_time
            target.end_time = program.end_time
