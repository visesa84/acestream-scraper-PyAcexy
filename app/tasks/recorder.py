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
    - Utiliza start_time y end_time de la tabla RecordingSchedule (schedules_recordings).
    - Si single_program_id tiene valor, fuerza el inicio/parada de ese ID.
    """
    with app.app_context():
        now = datetime.now()
        save_path = "/app/config/recordings"
        
        # ASEGURAR CARPETA Y OBTENER CONFIGURACIÓN
        if not os.path.exists(save_path):
            os.makedirs(save_path, exist_ok=True)

        setting_rec = Setting.query.filter_by(key='base_url').first()
        base_url = setting_rec.value if setting_rec else "http://localhost:8080/ace/getstream?id="

        # 1. DETENER GRABACIONES CANCELADAS O FUERA DE TIEMPO
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                cmdline_str = " ".join(cmdline)
                
                if 'ffmpeg' in (proc.info.get('name') or '') and "prog_id:" in cmdline_str:
                    match = re.search(r"prog_id:(\d+)", cmdline_str)
                    if match:
                        found_id = int(match.group(1))
                        rec_entry = RecordingSchedule.query.filter_by(program_id=found_id).first()
                        
                        # Si no existe, no está en estado activo, o ya pasó su end_time personalizado
                        if not rec_entry or rec_entry.status not in ['recording', 'pending', 'retrying'] or rec_entry.end_time <= now:
                            app.logger.warning(f"[RECORDER] Stopping ffmpeg process for program ID {found_id}")
                            proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # 2. REVISAR ESTADO DE GRABACIONES (ACTUALIZAR ESTADOS)
        active_or_pending = RecordingSchedule.query.filter(
            RecordingSchedule.status.in_(['recording', 'pending', 'retrying'])
        ).all()

        for rec in active_or_pending:
            prog = rec.program
            clean_title = "".join([c for c in prog.title if c.isalnum() or c in (' ', '_')]).strip().replace(' ', '_')
            
            # Buscar archivos existentes para este programa (Partes)
            parts = [f for f in os.listdir(save_path) if f.startswith(f"{clean_title}_{prog.id}")]
            file_exists = len(parts) > 0

            # SI EL TIEMPO PERSONALIZADO TERMINÓ
            if rec.end_time <= now:
                if file_exists:
                    total_size = sum(os.path.getsize(os.path.join(save_path, f)) for f in parts)
                    if total_size > 0:
                        parts_ts = [f for f in os.listdir(save_path) if f.startswith(f"{clean_title}_{prog.id}") and f.endswith('.ts')]
                        rec.status = 'converting'
                        db.session.commit()
                        
                        for ts_file in parts_ts:
                            input_path = os.path.join(save_path, ts_file)
                            output_path = input_path.replace('.ts', '.mp4')
                
                            cmd_conv = f'ffmpeg -y -i "{input_path}" -c copy -movflags +faststart -nostdin "{output_path}"'
                            try:
                                subprocess.run(cmd_conv, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                                if os.path.exists(output_path):
                                    os.remove(input_path)
                            except Exception as e:
                                app.logger.error(f"Error converting recording for {prog.id}: {e}")
                        
                        rec.status = 'completed'
                        app.logger.info(f"[CONVERTER] Successful: {prog.title} ID:{prog.id}")
                    else:
                        rec.status = 'failed'
                else:
                    rec.status = 'failed'
                app.logger.info(f"[RECORDER] Finished: {prog.title} (Status: {rec.status})")
                db.session.commit()
                continue

            # Si estaba grabando pero no hay archivo (pérdida de stream)
            if rec.status == 'recording' and not file_exists:
                app.logger.warning(f"[RECORDER] No file for {prog.title}. Starting retry window.")
                # Matar proceso colgado si existe
                for proc in psutil.process_iter(['cmdline']):
                    try:
                        if f"prog_id:{rec.program_id}" in " ".join(proc.info.get('cmdline') or []):
                            proc.terminate()
                    except: pass
                rec.status = 'retrying'
                rec.retry_start = datetime.now()
                db.session.commit()
                continue

            # Lógica de reintentos
            if rec.status == 'retrying':
                elapsed = (datetime.now() - rec.retry_start).total_seconds()
                if elapsed >= 120:  # 2 minutos de margen
                    rec.status = 'failed'
                    db.session.commit()
                    continue

                # Intentar reanudar si el canal vuelve online
                tv_chan = TVChannel.query.filter_by(epg_id=prog.epg_channel.channel_xml_id).first()
                if tv_chan:
                    ace_chan = AcestreamChannel.query.filter_by(tv_channel_id=tv_chan.id, status='active', is_online=True).first()
                    if ace_chan:
                        rec.status = 'pending'
                        db.session.commit()
                continue

            # Verificar si el proceso de grabación sigue vivo
            if rec.status == 'recording':
                is_alive = any(f"prog_id:{rec.program_id}" in " ".join(p.info.get('cmdline') or []) 
                               for p in psutil.process_iter(['cmdline']))
                if not is_alive:
                    rec.status = 'retrying'
                    rec.retry_start = datetime.now()
                    db.session.commit()

        # 3. INICIAR GRABACIONES PENDIENTES (Basado en start_time de schedules_recordings)
        query = RecordingSchedule.query.filter(
            RecordingSchedule.status == 'pending',
            RecordingSchedule.start_time <= now,
            RecordingSchedule.end_time > now
        )

        if single_program_id:
            to_start = query.filter(RecordingSchedule.program_id == single_program_id).all()
        else:
            to_start = query.all()

        for rec in to_start:
            prog = rec.program
            tv_chan = TVChannel.query.filter_by(epg_id=prog.epg_channel.channel_xml_id).first()
            if not tv_chan: continue

            ace_chan = AcestreamChannel.query.filter_by(tv_channel_id=tv_chan.id, status='active', is_online=True).first()
            if not ace_chan: continue

            clean_title = "".join([c for c in prog.title if c.isalnum() or c in (' ', '_')]).strip().replace(' ', '_')
            existing_parts = [f for f in os.listdir(save_path) if f.startswith(f"{clean_title}_{prog.id}")]
            part_suffix = f"_part{len(existing_parts) + 1}" if existing_parts else ""
            
            filename = f"{save_path}/{clean_title}_{prog.id}{part_suffix}.ts"
            # Duración basada en el end_time de la tabla schedules_recordings
            duration = int((rec.end_time - now).total_seconds())
            
            if duration <= 0: continue

            stream_url = f"{base_url}{ace_chan.id}"
            
            # Comando FFmpeg
            cmd_str = f'ffmpeg -y -hide_banner -loglevel error -fflags +genpts+discardcorrupt -reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_delay_max 5 -rw_timeout 15000000 -i "{stream_url}" -t {int(duration)} -c:v copy -c:a aac -af "aresample=async=1" -vsync 1 -user_agent "prog_id:{prog.id}" "{filename}"'

            try:
                subprocess.Popen(cmd_str, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                rec.status = 'recording'
                db.session.commit()
                app.logger.info(f"[RECORDER] Started: {prog.title} ID:{prog.id}")
            except Exception as e:
                app.logger.error(f"Error starting recording for {prog.id}: {e}")

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