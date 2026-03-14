import os
import subprocess
import psutil
import re
from datetime import datetime
from app.extensions import db
from app.models import RecordingSchedule, EPGProgram, TVChannel, AcestreamChannel, Setting

def process_recordings(app, single_program_id=None):
    """
    Motor de grabación:
    - Si single_program_id tiene valor, fuerza el inicio/parada de ese ID.
    - Si es None (ejecución automática), escanea toda la tabla cada 60s.
    """
    with app.app_context():
        now = datetime.now()
        save_path = "/app/config/recordings"
        
        # ASEGURAR CARPETA Y OBTENER CONFIGURACIÓN
        if not os.path.exists(save_path):
            os.makedirs(save_path, exist_ok=True)

        setting_rec = Setting.query.filter_by(key='base_url').first()
        base_url = setting_rec.value if setting_rec else "http://localhost:8080/ace/getstream?id="

        # DETENER GRABACIONES CANCELADAS (Reactividad al pulsar "Parar")
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                cmdline_str = " ".join(cmdline)
                
                if 'ffmpeg' in (proc.info.get('name') or '') and "prog_id:" in cmdline_str:
                    match = re.search(r"prog_id:(\d+)", cmdline_str)
                    if match:
                        found_id = int(match.group(1))
                        
                        exists = RecordingSchedule.query.filter_by(program_id=found_id).first()
                        
                        if not exists or exists.status not in ['recording', 'pending']:
                            app.logger.warning(f"[RECORDER] Stopping ffmpeg process for program ID {found_id}")
                            proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # REVISAR ESTADO DE GRABACIONES (Terminadas, Interrumpidas o Archivo Borrado)
        active_or_pending = RecordingSchedule.query.filter(
            RecordingSchedule.status.in_(['recording', 'pending'])
        ).all()

        for rec in active_or_pending:
            prog = rec.program
            clean_title = "".join([c for c in prog.title if c.isalnum() or c in (' ', '_')]).strip().replace(' ', '_')
            
            # Buscar archivos existentes para este programa (Partes)
            parts = [f for f in os.listdir(save_path) if f.startswith(f"{clean_title}_{prog.id}")]
            file_exists = len(parts) > 0

            # Si está grabando pero el archivo ha sido borrado manualmente
            if rec.status == 'recording' and not file_exists:
                app.logger.warning(f"[RECORDER] File deleted manually for {prog.title}. Removing schedule and killing process.")

                # Matar proceso ffmpeg asociado
                for proc in psutil.process_iter(['cmdline']):
                    try:
                        cmdline = " ".join(proc.info.get('cmdline') or [])
                        if f"prog_id:{rec.program_id}" in cmdline:
                            proc.terminate()
                    except:
                        pass

                # Borrar schedule
                db.session.delete(rec)
                db.session.commit()
                continue

            # El programa ya terminó en la EPG
            if prog.end_time <= now:
                if file_exists:
                    total_size = sum(os.path.getsize(os.path.join(save_path, f)) for f in parts)
                    if total_size > 0:
                        app.logger.info(f"[RECORDER] Completed OK: {prog.title}")
                        rec.status = 'completed'
                    else:
                        rec.status = 'failed'
                else:
                    rec.status = 'failed'
                db.session.commit()
                continue

            # Caso B: Está marcado como 'recording', verificar si el proceso sigue vivo
            if rec.status == 'recording':
                is_alive = False
                for proc in psutil.process_iter(['name', 'cmdline']):
                    try:
                        cmdline = proc.info.get('cmdline') or []
                        if f"prog_id:{rec.program_id}" in " ".join(cmdline):
                            is_alive = True
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                if not is_alive:
                    app.logger.warning(f"[RECORDER] Stream lost for {prog.title}. Set to pending for retry.")
                    rec.status = 'pending'
                    db.session.commit()

        # INICIAR GRABACIONES (Nuevas o Partes por reintento)
        to_start = []
        if single_program_id:
            to_start = RecordingSchedule.query.join(EPGProgram).filter(
                RecordingSchedule.program_id == single_program_id,
                RecordingSchedule.status == 'pending',
                EPGProgram.start_time <= now,
                EPGProgram.end_time > now
            ).all()
        else:
            to_start = RecordingSchedule.query.join(EPGProgram).filter(
                RecordingSchedule.status == 'pending',
                EPGProgram.start_time <= now,
                EPGProgram.end_time > now
            ).all()

        for rec in to_start:
            prog = rec.program
            tv_chan = TVChannel.query.filter_by(epg_id=prog.epg_channel.channel_xml_id).first()
            if not tv_chan:
                continue

            ace_chan = AcestreamChannel.query.filter_by(tv_channel_id=tv_chan.id, status='active', is_online=True).first()
            if not ace_chan:
                continue

            clean_title = "".join([c for c in prog.title if c.isalnum() or c in (' ', '_')]).strip().replace(' ', '_')
            existing_parts = [f for f in os.listdir(save_path) if f.startswith(f"{clean_title}_{prog.id}")]
            part_suffix = f"_part{len(existing_parts) + 1}" if existing_parts else ""
            
            filename = f"{save_path}/{clean_title}_{prog.id}{part_suffix}.mp4"
            duration = int((prog.end_time - now).total_seconds())
            stream_url = f"{base_url}{ace_chan.id}"

            # Comando FFMPEG con Timeouts de red y tag de identificación
            cmd_str = f'ffmpeg -y -hide_banner -loglevel error -i "{stream_url}" -reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_delay_max 5 -rw_timeout 15000000 -t {int(duration)} -c:v copy -c:a aac -movflags +faststart -user_agent "prog_id:{prog.id}" "{filename}"'

            try:
                subprocess.Popen(cmd_str, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                rec.status = 'recording'
                db.session.commit()
                app.logger.info(f"[RECORDER] Started: {prog.title} {part_suffix} (ID:{prog.id})")
            except Exception as e:
                app.logger.error(f"Error starting ffmpeg: {e}")

def start_recording_now(app, program_id):
    """Disparo instantáneo en un hilo nuevo"""
    import threading
    thread = threading.Thread(target=process_recordings, args=(app, program_id))
    thread.daemon = True
    thread.start()

def stop_recording_now(program_id):
    from flask import current_app
    import threading
    threading.Thread(target=process_recordings, args=(current_app._get_current_object(),), daemon=True).start()