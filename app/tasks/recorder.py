import os
import subprocess
import psutil
import re
import threading
from datetime import datetime
from app.extensions import db
from app.models import RecordingSchedule, EPGProgram, TVChannel, AcestreamChannel, Setting

def background_conversion(app, input_path, output_path, rec_id):
    """Función que corre en segundo plano para no bloquear el bucle principal"""
    with app.app_context():
        
        try:
            # Llamamos a tu función de limpieza
            eliminar_fragmentos_congelados(input_path, output_path)
            
            # Borramos el original si el resultado existe
            if os.path.exists(output_path):
                if os.path.exists(input_path):
                    os.remove(input_path)
                
                # Actualizamos la base de datos desde aquí
                rec = RecordingSchedule.query.get(rec_id)
                if rec:
                    rec.status = 'completed'
                    db.session.commit()
                app.logger.info(f"[CONVERTER] Completed successfully: {output_path}")
            
        except Exception as e:
            print(f"Error in conversion thread: {e}")
            # Si falla, marcamos como failed
            rec = RecordingSchedule.query.get(rec_id)
            if rec:
                rec.status = 'failed'
                db.session.commit()
                
def eliminar_fragmentos_congelados(video_input, video_output, ruido="-60db", duracion_minima="2"):
    print("Analyzing the video for frozen fragments...")
    
    # 1. Ejecutar freezedetect y capturar la salida de texto (stderr)
    cmd_detect = [
        'ffmpeg', '-i', video_input,
        '-vf', f'freezedetect=n={ruido}:d={duracion_minima}',
        '-f', 'null', '-'
    ]
    proceso = subprocess.run(cmd_detect, stderr=subprocess.PIPE, text=True, encoding="utf-8", check=False)
    log_output = proceso.stderr or ''

    # 2. Buscar la duración total del video para el fragmento final
    match_duracion = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", log_output)
    if not match_duracion:
        print("The duration of the video could not be determined.")
        return
    
    horas, minutos, segundos = map(float, match_duracion.groups())
    duracion_total = horas * 3600 + minutos * 60 + segundos

    # 3. Extraer todos los tiempos de freeze_start y freeze_end
    starts = [float(x) for x in re.findall(r"freeze_start:\s*([0-9.]+)", log_output)]
    ends = [float(x) for x in re.findall(r"freeze_end:\s*([0-9.]+)", log_output)]

    if not starts:
        print("No frozen fragments detected. Remuxing to MP4 for web playback...")
        cmd_remux = [
            'ffmpeg', '-y', '-i', video_input,
            '-c', 'copy',
            '-movflags', '+faststart',
            video_output
        ]
        subprocess.run(cmd_remux, check=True)
        return

    print(f"{len(starts)} frozen fragments were detected. Calculating cuts...")

    # 4. Construir las reglas de selección (partes limpias a conservar)
    filtros_retencion = []
    inicio_bueno = 0.0
    
    # Asegurarse de que tenemos la misma cantidad de inicios y finales
    # Si falta un 'end', asumimos que el video termina en el último frame
    if len(starts) > len(ends):
        ends.append(duracion_total)
    
    for start, end in zip(starts, ends):
        # Guardar el fragmento limpio que va desde el fin del último congelado hasta el inicio de este
        filtros_retencion.append(f"between(t,{inicio_bueno},{start})")
        inicio_bueno = end

    # Añadir el último fragmento limpio desde el último congelado hasta el final del video
    if inicio_bueno < duracion_total:
        filtros_retencion.append(f"between(t,{inicio_bueno},{duracion_total})")

    # Unir todos los fragmentos con el signo '+' exigido por FFmpeg
    filtro_final = "+".join(filtros_retencion)

    # 5. Configurar y lanzar el comando de corte final
    print("Processing and exporting the clean video (re-encoding)...")
    vf_value = f'select={filtro_final},setpts=N/FRAME_RATE/TB'
    af_value = f'aselect={filtro_final},asetpts=N/SR/TB'
    cmd_cut = [
        'ffmpeg', '-y', '-i', video_input,
        '-vf', vf_value,
        '-af', af_value,
        '-c:v', 'libx264', '-preset', 'superfast',
        '-c:a', 'aac', '-movflags', '+faststart', video_output
    ]

    subprocess.run(cmd_cut, check=True)
    print(f"Process completed successfully! File saved as: {video_output}")

def disparar_conversion(app, rec):
    """Lógica que ya tenías dentro de process_recordings, ahora reutilizable."""
    save_path = "/app/config/recordings"
    prog = rec.program
    clean_title = "".join([c for c in prog.title if c.isalnum() or c in (' ', '_')]).strip().replace(' ', '_')
    
    parts_ts = [f for f in os.listdir(save_path) if f.startswith(f"{clean_title}_{prog.id}") and f.endswith('.ts')]
    
    if not parts_ts:
        return False
    
    rec.status = 'converting'
    db.session.commit()
    
    for ts_file in parts_ts:
        input_path = os.path.join(save_path, ts_file)
        output_path = input_path.replace('.ts', '.mp4')
        
        conv_thread = threading.Thread(
            target=background_conversion, 
            args=(app, input_path, output_path, rec.id)
        )
        conv_thread.start()
    return True

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
                    disparar_conversion(app, rec)
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
                # Build argument list to avoid shell injection and handle spaces in paths
                cmd = [
                    'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                    '-fflags', '+genpts+discardcorrupt',
                    '-reconnect', '1', '-reconnect_at_eof', '1', '-reconnect_streamed', '1',
                    '-reconnect_delay_max', '5', '-rw_timeout', '15000000',
                    '-i', stream_url,
                    '-t', str(int(duration)),
                    '-c:v', 'copy', '-c:a', 'aac',
                    '-af', 'aresample=async=1', '-vsync', '1',
                    '-user_agent', f'prog_id:{prog.id}', filename
                ]

                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
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