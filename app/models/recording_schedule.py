from datetime import datetime
from app.extensions import db

class RecordingSchedule(db.Model):
    __tablename__ = 'recording_schedules'
    
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('epg_programs.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    retry_start = db.Column(db.DateTime, nullable=True)

    # La relación se define aquí y crea automáticamente el campo en EPGProgram
    program = db.relationship('EPGProgram', backref=db.backref('recording_info', uselist=False))
