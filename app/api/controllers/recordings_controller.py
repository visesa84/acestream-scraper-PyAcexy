import os, re, psutil
from datetime import datetime
from flask import request, current_app, send_from_directory
from flask_restx import Namespace, Resource, fields
from app import db
from app.repositories.epg_program_repository import EPGProgramRepository
from app.models import RecordingSchedule, EPGProgram
from app.tasks.recorder import start_recording_now, stop_recording_now

api = Namespace('recordings', description='Program recording operations')

repo = EPGProgramRepository()

recording_model = api.model('RecordingToggle', {
    'program_id': fields.Integer(required=True, description='ID of the program to be recorded')
})

# Definimos la ruta base de las grabaciones
RECORDINGS_DIR = "/app/config/recordings"

@api.route('/toggle')
class RecordingToggle(Resource):
    @api.expect(recording_model)
    def post(self):
        """Activa o desactiva la programación y el proceso de grabado al instante"""
        data = request.json
        program_id = data.get('program_id')

        if not program_id:
            api.abort(400, "program_id is required")

        try:
            # Actualizamos el estado en la base de datos
            result = repo.toggle_recording(program_id)
            
            # ACCIÓN REACTIVA: Control directo del proceso ffmpeg
            # Obtenemos el objeto app real para pasarlo al hilo de grabación
            flask_app = current_app._get_current_object()

            message = ""
            if result['status'] == 'scheduled':
                prog = EPGProgram.query.filter_by(id=program_id).first()
                now = datetime.now()

                if prog.start_time <= now:
                    start_recording_now(flask_app, program_id)
                    message = "Recording scheduled and started"
                else:
                    message = "Recording scheduled (will start at program time)"
            else:
                stop_recording_now(program_id)
                message = "Recording cancelled and stopped"
            
            status_code = 201 if result['status'] == 'scheduled' else 200
            
            return {
                'status': result['status'],
                'message': message,
                'program_id': program_id
            }, status_code

        except Exception as e:
            api.abort(500, f"Error processing the recording: {str(e)}")

@api.route('/update_times/<int:program_id>')
class UpdateRecordingTimes(Resource):
    def post(self, program_id):
        """Actualiza los horarios de una grabación buscando por program_id."""
        data = request.json
        
        rec = RecordingSchedule.query.filter_by(program_id=program_id).first()
        
        if not rec:
            return {"message": f"The recording with program_id {program_id} was not found"}, 404
        
        try:
            # Solo permitimos cambiar el inicio si aún es 'pending'
            if rec.status == 'pending' and 'start_time' in data:
                # Convertimos el string ISO (YYYY-MM-DDTHH:mm) a objeto datetime
                rec.start_time = datetime.fromisoformat(data['start_time'])
            
            # El fin se puede cambiar en 'pending' o 'recording'
            if rec.status in ['pending', 'recording'] and 'end_time' in data:
                rec.end_time = datetime.fromisoformat(data['end_time'])
                
            db.session.commit()
            return {"message": "Schedules updated correctly", "program_id": program_id}, 200

        except Exception as e:
            db.session.rollback()
            return {"error": str(e)}, 500

@api.route('/list')
class RecordingList(Resource):
    def get(self):
        items = []
        valid_states = {'completed', 'recording', 'failed', 'pending', 'converting'}
        schedules = RecordingSchedule.query.all()
        schedules_map = {s.program_id: s for s in schedules}
        files_in_disk = os.listdir(RECORDINGS_DIR)

        # 1) Procesar archivos físicos
        for filename in files_in_disk:
            if not (filename.lower().endswith('.mp4') or filename.lower().endswith('.ts')):
                continue
            
            match = re.search(r"_(\d+)(?:_part(\d+))?\.(?:mp4|ts)$", filename)
            program_id = int(match.group(1)) if match else None
            part_num = int(match.group(2)) if match and match.group(2) else 0
            
            rec = schedules_map.get(program_id)
            
            # PRIORIDAD DE FECHAS: Schedule modificado > EPG Original
            d_start = rec.start_time.isoformat() if (rec and rec.start_time) else (rec.program.start_time.isoformat() if rec else None)
            d_end = rec.end_time.isoformat() if (rec and rec.end_time) else (rec.program.end_time.isoformat() if rec else None)

            # Lógica de estado de parte activa
            actual_status = 'completed'
            if rec:
                if rec.status == 'converting':
                    actual_status = 'converting'
                elif rec.status == 'recording':
                    # Buscamos si existe una parte posterior sin importar la extensión
                    has_newer = any(
                        f"_{program_id}_part{part_num + 1}.mp4" in f or 
                        f"_{program_id}_part{part_num + 1}.ts" in f 
                        for f in files_in_disk
                    )
                
                    if not has_newer:
                        actual_status = 'recording'

            items.append({
                'filename': filename,
                'program_id': program_id,
                'part': part_num,
                'title': rec.program.title if rec else filename,
                'size_display': f"{os.stat(os.path.join(RECORDINGS_DIR, filename)).st_size / (1024*1024):.2f} MB",
                'date_start': d_start,
                'date_end': d_end,
                'status': actual_status
            })

        # 2) Añadir schedules sin archivo
        for rec in schedules:
            if rec.program_id not in [i['program_id'] for i in items]:
                d_start = rec.start_time.isoformat() if rec.start_time else rec.program.start_time.isoformat()
                d_end = rec.end_time.isoformat() if rec.end_time else rec.program.end_time.isoformat()
                
                items.append({
                    'filename': '',
                    'program_id': rec.program_id,
                    'part': 0,
                    'title': rec.program.title,
                    'size_display': '0 MB',
                    'date_start': d_start,
                    'date_end': d_end,
                    'status': rec.status if rec.status in valid_states else 'pending'
                })
        return items, 200

@api.route('/stop/<int:program_id>')
class RecordingStop(Resource):
    def post(self, program_id):
        """Detiene una grabación en curso buscando el proceso por el tag de prog_id."""
        rec = RecordingSchedule.query.filter_by(program_id=program_id).first()
        
        if rec and rec.status == 'recording':
            rec.end_time = datetime.now()
            for proc in psutil.process_iter(['cmdline']):
                try:
                    cmdline = " ".join(proc.info.get('cmdline') or [])
                    if f"prog_id:{program_id}" in cmdline:
                        proc.terminate()
                except:
                    pass

            # Actualizar base de datos
            db.session.commit()
            
            return {
                'message': 'Stopped successfully', 
                'program_id': program_id
            }, 200
            
        return {'message': 'Recording not found or not in progress'}, 404

@api.route('/delete/<string:filename>')
class RecordingDelete(Resource):
    def delete(self, filename):
        file_path = os.path.join(RECORDINGS_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"message": "File deleted"}, 200
        api.abort(404, "File not found")
        
@api.route('/schedule/<int:program_id>')
class DeleteSchedule(Resource):
    def delete(self, program_id):
        """Borra un schedule sin archivo asociado."""
        try:
            rec = RecordingSchedule.query.filter_by(program_id=program_id).first()

            if not rec:
                return {"message": "Schedule not found"}, 404

            # Si por algún motivo está grabando, matar ffmpeg
            for proc in psutil.process_iter(['cmdline']):
                try:
                    cmdline = " ".join(proc.info.get('cmdline') or [])
                    if f"prog_id:{program_id}" in cmdline:
                        proc.terminate()
                except:
                    pass

            db.session.delete(rec)
            db.session.commit()

            return {"message": "Schedule deleted"}, 200

        except Exception as e:
            return {"error": str(e)}, 500

@api.route('/download/<string:filename>')
class RecordingDownload(Resource):
    def get(self, filename):
        """Descarga el archivo (Fuerza cuadro de diálogo de guardado)"""
        return send_from_directory(RECORDINGS_DIR, filename, as_attachment=True)
        
@api.route('/stream/<string:filename>')
class RecordingStream(Resource):
    def get(self, filename):
        """Sirve el archivo para el reproductor del navegador"""
        # IMPORTANTE: mimetype video/mp4 para archivos .mp4
        # as_attachment=False para que el navegador lo reproduzca
        return send_from_directory(RECORDINGS_DIR, filename, mimetype='video/mp4', as_attachment=False)
