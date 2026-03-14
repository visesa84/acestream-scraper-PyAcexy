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

@api.route('/list')
class RecordingList(Resource):
    def get(self):
        """Lista grabaciones combinando archivos y schedules."""
        items = []
        valid_states = {'completed', 'recording', 'failed', 'pending'}

        # 1) Cargar todos los schedules
        schedules = RecordingSchedule.query.all()
        schedules_map = {s.program_id: s for s in schedules}

        # 2) Cargar archivos físicos
        files_in_disk = os.listdir(RECORDINGS_DIR)

        # 3) Procesar archivos físicos
        for filename in files_in_disk:
            if not filename.lower().endswith('.mp4'):
                continue

            file_path = os.path.join(RECORDINGS_DIR, filename)
            stat = os.stat(file_path)
            size_display = f"{stat.st_size / (1024*1024):.2f} MB"
            file_date = datetime.fromtimestamp(stat.st_mtime).isoformat()

            # Extraer program_id desde el nombre del archivo
            match = re.search(r"_(\d+)(?:_part\d+)?\.mp4$", filename)
            program_id = int(match.group(1)) if match else None

            rec = schedules_map.get(program_id)

            # Estado normalizado
            status = rec.status if rec and rec.status in valid_states else ''

            # Título del programa (si existe schedule)
            title = rec.program.title if rec else filename

            items.append({
                'filename': filename,
                'program_id': program_id,
                'title': title,
                'size_display': size_display,
                'date': file_date,
                'status': status
            })

        # 4) Añadir schedules sin archivo (pendientes o futuros)
        for rec in schedules:
            if rec.program_id not in [i['program_id'] for i in items]:
                items.append({
                    'filename': '',
                    'program_id': rec.program_id,
                    'title': rec.program.title,
                    'size_display': '0 MB',
                    'date': rec.program.start_time.isoformat(),
                    'status': rec.status if rec.status in valid_states else ''
                })

        return items, 200

@api.route('/delete/<string:filename>')
class RecordingDelete(Resource):
    def delete(self, filename):
        """Borra un archivo físico y elimina su schedule si corresponde."""
        
        # Validar archivo
        file_path = os.path.join(RECORDINGS_DIR, filename)
        if not os.path.exists(file_path):
            api.abort(404, "File not found")

        # Extraer program_id desde el nombre del archivo
        match = re.search(r"_(\d+)(?:_part\d+)?\.mp4$", filename)
        program_id = int(match.group(1)) if match else None

        # Borrar archivo físico
        os.remove(file_path)

        # Si no hay program_id, solo borramos archivo
        if not program_id:
            return {'message': 'File deleted (no schedule associated)'}, 200

        # Buscar schedule asociado
        rec = RecordingSchedule.query.filter_by(program_id=program_id).first()
        if not rec:
            return {'message': 'File deleted (schedule not found)'}, 200

        # Si estaba grabando, matar proceso ffmpeg
        if rec.status == "recording":
            for proc in psutil.process_iter(['cmdline']):
                try:
                    cmdline = " ".join(proc.info.get('cmdline') or [])
                    if f"prog_id:{program_id}" in cmdline:
                        proc.terminate()
                except:
                    pass

        # Borrar schedule de la base de datos
        db.session.delete(rec)
        db.session.commit()

        return {
            'message': 'File and schedule deleted',
            'program_id': program_id
        }, 200
        
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
