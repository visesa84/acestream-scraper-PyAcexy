import os
import signal
import subprocess
import logging
import requests
import time
from enum import Enum
from typing import Dict, Optional, Tuple, List, Any

class WarpMode(Enum):
    WARP = "warp"
    OFF = "off"

class WarpService:
    def __init__(self, accept_tos: bool = True):
        self.logger = logging.getLogger(__name__)
        self.accept_tos = accept_tos

    def _kill_warp_processes(self) -> bool:
        """Limpieza de WARP"""
        self.logger.info("Shutting down WARP/WireGuard...")
        try:
            # 1. Intentar desmontar la interfaz correctamente (limpia rutas y DNS)
            os.system("wg-quick down /app/config/wg0.conf > /dev/null 2>&1")
            
            # 2. Limpieza radical por si BoringTun se quedó colgado
            pids = [pid for pid in os.listdir('/proc') if pid.isdigit()]
            for pid in pids:
                try:
                    with open(os.path.join('/proc', pid, 'cmdline'), 'rb') as f:
                        content = f.read().decode().replace('\x00', ' ')
                        # Buscamos tanto el binario real como el script puente
                        if 'boringtun' in content or 'wg-quick' in content:
                            self.logger.debug(f"Killing PID {pid}: {content[:20]}...")
                            os.kill(int(pid), signal.SIGKILL)
                except:
                    continue
            return True
        except Exception as e:
            self.logger.error(f"Error closing WARP: {e}")
            return False

    def is_running(self) -> bool:
        """Check de túnel vivo buscando el motor BoringTun"""
        try:
            # Iteramos por los PIDs en /proc
            for pid in [p for p in os.listdir('/proc') if p.isdigit()]:
                try:
                    with open(os.path.join('/proc', pid, 'cmdline'), 'rb') as f:
                        content = f.read().decode().replace('\x00', ' ')
                        # Buscamos 'boringtun', que es el proceso real del túnel
                        if 'boringtun' in content:
                            return True
                except (IOError, UnicodeDecodeError):
                    continue
        except Exception:
            pass
        return False

    def _run_command(self, args: List[Any]) -> Tuple[int, str, str]:
        """Arrancar WARP mediante wg-quick y BoringTun"""
        str_args = [a.value if hasattr(a, 'value') else str(a).lower() for a in args]
        
        # MAPEADOR DE COMANDOS
        if "connect" in str_args:
            # Lanza wg-quick up para activar BoringTun y las rutas PostUp
            cmd = ["wg-quick", "up", "/app/config/wg0.conf"]
        elif "disconnect" in str_args:
            # Lanza wg-quick down para limpiar rutas e interfaz
            cmd = ["wg-quick", "down", "/app/config/wg0.conf"]
        elif "status" in str_args:
            # Comando para ver el estado del túnel
            cmd = ["wgcf", "trace"]
        elif "license" in str_args:
            # Para el registro de clave WARP+ (args[2] sería la KEY)
            cmd = ["wgcf", "update", "--license", str_args[2]] if len(str_args) > 2 else ["wgcf", "update"]
        else:
            # Si el comando no está en la lista, abortamos
            self.logger.warning(f"Command denied or not implemented: {str_args}")
            return 1, "", "Command not supported in BoringTun mode"

        # ENTORNO FORZADO PARA BORINGTUN (Userspace)
        env = os.environ.copy()
        env["WG_QUICK_USERSPACE_IMPLEMENTATION"] = "boringtun"
        env["WG_THREADS"] = "4"

        try:
            # Ejecutamos el comando
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                env=env
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                self.logger.error(f"Error in command {cmd}: {stderr.strip()}")
                
            return process.returncode, stdout.strip(), stderr.strip()
            
        except Exception as e:
            self.logger.error(f"Exception executing {cmd}: {e}")
            return 1, "", str(e)

    def set_mode(self, mode: Any) -> bool:
        """
        Controla el túnel BoringTun desde la web (Modo Túnel Único).
        """
        # Extraer el valor (soporta Enum o String)
        mode_val = mode.value if hasattr(mode, 'value') else str(mode).lower()
        
        # APAGADO
        if mode_val == "off":
            return self._kill_warp_processes()

        # ENCENDIDO
        if not self.is_running():
            self.logger.info("Starting WARP tunnel (BoringTun)...")
            # Limpieza preventiva de procesos huérfanos
            self._kill_warp_processes() 
            
            # Esto levanta el túnel y aplica las rutas PostUp ip route replace
            code, stdout, stderr = self._run_command(["connect"])
            
            if code == 0:
                self.logger.info("Warp tunnel successfully established.")
                return True
            else:
                self.logger.error(f"Tunnel error: {stderr}")
                return False

        # RECONEXIÓN (Si ya está ON pero se pulsa 'conectar' de nuevo)
        self.logger.info("Restarting connection to secure the tunnel...")
        self._run_command(["disconnect"])
        time.sleep(1)
        
        code, stdout, stderr = self._run_command(["connect"])
        return code == 0

    def get_mode(self) -> Optional[WarpMode]:
        """Detecta el modo real consultando la API de Cloudflare a través del túnel"""
        # Si el proceso BoringTun no está en /proc, el modo es OFF
        if not self.is_running():
            return WarpMode.OFF
            
        # Consultamos el trace
        trace = self.get_cf_trace()
        warp_status = trace.get("warp", "off")

        # Mapeo lógico según la respuesta de Cloudflare:
        if warp_status in ["on", "plus"]:
            return WarpMode.WARP
        
        # Si el proceso existe pero warp=off, algo falla en el túnel
        if warp_status == "off" and self.is_running():
            return WarpMode.OFF 

        return None

    def get_cf_trace(self) -> Dict[str, str]:
        """Obtiene el trace real de Cloudflare usando wgcf"""
        try:
            # Llamamos a status (wgcf trace)
            code, stdout, _ = self._run_command(["status"])
            if code != 0: return {}
            # Convertimos las líneas 'key=value' en un diccionario de Python
            return dict(line.split('=') for line in stdout.splitlines() if '=' in line)
        except: 
            return {}

    def get_status(self) -> Dict[str, Any]:
        """Status unificado para tu API Web"""
        res = {"running": self.is_running(), "connected": False, "mode": "off", "ip": None, "account_type": "free"}
        
        if not res["running"]: return res
        
        # 1. Obtener el trace real
        trace = self.get_cf_trace()
        warp_status = trace.get("warp", "off") # Puede ser 'on', 'plus' u 'off'
        
        # 2. Mapear estados
        res["connected"] = warp_status in ["on", "plus"]
        res["ip"] = trace.get("ip")
        res["mode"] = "warp" if res["connected"] else "off"
        
        # 3. Detectar si es WARP+ (plus)
        if warp_status == "plus":
            res["account_type "] = "WARP+"
            
        return res

    def connect(self) -> bool: return self._run_command(["connect"])[0] == 0
    def disconnect(self) -> bool: return self._run_command(["disconnect"])[0] == 0
    def register_license(self, key: str) -> bool:
        """Actualiza la licencia en wgcf y regenera el fichero de configuración"""
        self.logger.info(f"Actualizando licencia WARP+: {key[:8]}****")
        try:
            # 1. Parar el túnel para evitar conflictos de archivos
            self._run_command(["disconnect"])

            # 2. Actualizar el JSON de cuenta con la nueva clave
            # Usamos el mapeador que ya tenemos para 'wgcf update --license KEY'
            code, _, stderr = self._run_command(["license", key])
            if code != 0:
                self.logger.error(f"Error en wgcf update: {stderr}")
                return False

            # 3. Regenerar el perfil (.conf) con los nuevos datos de la cuenta Plus
            # wgcf generate crea 'wgcf-profile.conf' por defecto
            gen_process = subprocess.run(["wgcf", "generate"], 
                                         cwd="/app/config", capture_output=True, text=True)
            
            if gen_process.returncode == 0:
                # 4. Mover y renombrar al archivo que usa wg-quick
                os.rename("/app/config/wgcf-profile.conf", "/app/config/wg0.conf")
                
                # 5. IMPORTANTE: Volver a aplicar las limpiezas (IPv6, MTU, PostUp con replace)
                # Aquí podrías llamar a una función privada que ejecute los 'sed' que definimos
                self._apply_config_patches("/app/config/wg0.conf")
                
                # 6. Arrancar de nuevo con la nueva identidad
                return self._run_command(["connect"])[0] == 0
            
            return False
        except Exception as e:
            self.logger.error(f"Error registering license: {e}")
            return False

    def _apply_config_patches(self, config_path: str) -> bool:
        """
        Aplica exactamente tus comandos sed probados para limpiar IPv6 y rutas.
        """
        try:

            # 1. Obtener el Gateway dinámico (idéntico a tu bash)
            gateway_ip = subprocess.getoutput("ip route | grep default | awk '{print $3}'")
            if not gateway_ip:
                gateway_ip = "172.17.0.1" # Fallback de seguridad

            # 2. Lista de tus comandos sed (escapando caracteres especiales de Python)
            commands = [
                # Limpiar Address: Deja solo la primera IP (IPv4)
                f"sed -i 's/Address = \\([^,]*\\),.*/Address = \\1/' {config_path}",

                # Limpiar DNS: Deja solo las dos primeras (IPv4)
                f"sed -i 's/DNS = \\([^,]*\\), \\([^,]*\\),.*/DNS = \\1, \\2/' {config_path}",

                # Limpiar AllowedIPs: Quita el rango ::/0
                f"sed -i 's/, ::\\/0//' {config_path}",

                # Asegurar MTU bajo
                f"sed -i 's/MTU = .*/MTU = 1280/' {config_path}",

                # Limpiar PostUp/PostDown previos
                f"sed -i '/PostUp = .*/d' {config_path}",
                f"sed -i '/PostDown = .*/d' {config_path}",
                f"sed -i '/FwMark/d' {config_path}",

                # Inyectar tus rutas PostUp/PostDown (usando | como separador para evitar líos con /)
                f"sed -i \"/\\[Interface\\]/a PostUp = ip route replace 162.159.192.1 via {gateway_ip} dev eth0 && ip route replace 0.0.0.0/0 dev wg0\" {config_path}",
                f"sed -i \"/\\[Interface\\]/a PostDown = ip route replace 0.0.0.0/0 via {gateway_ip} dev eth0\" {config_path}"
            ]

            for cmd in commands:
                os.system(cmd)
                
            self.logger.info("WireGuard configuration successfully patched.")
            return True
        except Exception as e:
            self.logger.error(f"Error: {e}")
            return False
