import os
import logging
import cv2
import asyncio
import aiohttp

logger = logging.getLogger(__name__)

class ChannelVisionManager:
    def __init__(self, base_path="config"):
        # Configuración de rutas fijas
        self.picons_folder = os.path.join(base_path, "picons")
        self.snapshots_folder = os.path.join(base_path, "snapshots")
        
        # Asegurar que las carpetas existan al iniciar el contenedor
        os.makedirs(self.picons_folder, exist_ok=True)
        os.makedirs(self.snapshots_folder, exist_ok=True)

    async def procesar_verificacion_completa(self, channel_data, stream_url):
        """
        1. Descarga el logo desde channel.logo si no existe localmente.
        2. Captura un frame del stream.
        3. Compara contra todos los logos para identificar el canal.
        """
        channel_id = channel_data['id']
        logo = channel_data['logo']
        ruta_picon_referencia = None
        
        if logo:
            nombre_archivo_url = logo.split('/')[-1]
            ruta_picon_referencia = os.path.join(self.picons_folder, nombre_archivo_url)
            
            if not os.path.exists(ruta_picon_referencia):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(logo, timeout=10) as resp:
                            if resp.status == 200:
                                with open(ruta_picon_referencia, 'wb') as f:
                                    f.write(await resp.read())
                except Exception:
                    # Si falla la descarga, intentaremos validar con lo que ya haya en la carpeta
                    pass

        ruta_snapshot = os.path.join(self.snapshots_folder, f"temp_{channel_id}.jpg")
        
        try:
            if os.path.exists(ruta_snapshot):
                os.remove(ruta_snapshot)

            cmd_str = (
                f'ffmpeg -y -fflags +genpts+discardcorrupt '
                f'-analyzeduration 3000000 -probesize 3000000 '
                f'-i "{stream_url}" -ss 00:00:05 -frames:v 1 '
                f'-an -sn -f image2 -update 1 -q:v 2 "{ruta_snapshot}"'
            )

            process = await asyncio.create_subprocess_shell(
                cmd_str,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )

            try:
                await asyncio.wait_for(process.wait(), timeout=50)
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except:
                    pass
                logger.warning(f"[IA] Timeout FFmpeg for {channel_id}")
                return None

            await asyncio.sleep(0.5)
            
            if not os.path.exists(ruta_snapshot) or os.path.getsize(ruta_snapshot) < 1000:
                return None

        except Exception as e:
            logger.error(f"[IA] FFmpeg error: {e}")
            return None
        
        # Carga del frame en
        img_frame_full = cv2.imread(ruta_snapshot, cv2.IMREAD_COLOR)
        if img_frame_full is None: 
            if os.path.exists(ruta_snapshot): os.remove(ruta_snapshot)
            return None

        # Redimensionamos el frame
        img_frame = cv2.resize(img_frame_full, (640, 360))
        del img_frame_full
        alto, ancho, _ = img_frame.shape

        # Definimos las zonas de interés (ROI)
        esquinas = [
            img_frame[0:alto//3, 0:ancho//3],          # Arriba Izquierda
            img_frame[0:alto//3, (2*ancho)//3:ancho],  # Arriba Derecha
            img_frame[(2*alto)//3:alto, 0:ancho//3],   # Abajo Izquierda
            img_frame[(2*alto)//3:alto, (2*ancho)//3:ancho], # Abajo Derecha
            img_frame[alto//3:(2*alto)//3, ancho//3:(2*ancho)//3] # Centro
        ]

        mejor_puntuacion = 0.0
        nombre_canal_detectado = None

        # Bucle de picons
        for archivo_picon in os.listdir(self.picons_folder):
            if not archivo_picon.lower().endswith(('.png', '.jpg', '.jpeg')):
                continue
            
            ruta_picon_loop = os.path.join(self.picons_folder, archivo_picon)
            img_picon = cv2.imread(ruta_picon_loop, cv2.IMREAD_COLOR)
            
            if img_picon is not None:
                mu, sigma = cv2.meanStdDev(img_picon)
                if sigma.mean() < 10:
                    del img_picon
                    continue
                
                # Redimensionamos picon a un tamaño coherente con el frame de 1280x720
                picon_ready = cv2.resize(img_picon, (60, 60))
                
                # Probamos el picon en cada zona
                for zona in esquinas:
                    resultado = cv2.matchTemplate(zona, picon_ready, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(resultado)

                    if max_val > mejor_puntuacion:
                        mejor_puntuacion = max_val
                        nombre_canal_detectado = archivo_picon
                
                # Si el match es casi perfecto, dejamos de buscar otros picons
                if mejor_puntuacion > 0.96:
                    break

        # 5. Limpieza y retorno
        if os.path.exists(ruta_snapshot):
            os.remove(ruta_snapshot)
            
        del img_frame
        
        # Umbral estricto para evitar falsos positivos
        if mejor_puntuacion > 0.92 and nombre_canal_detectado:
            # Retornamos el nombre limpio (quitando extensión y cambiando guiones)
            return os.path.splitext(nombre_canal_detectado)[0].replace('_', ' ').replace('-', ' ').upper()
        
        return None