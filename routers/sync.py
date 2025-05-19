from fastapi import FastAPI, APIRouter
from datetime import datetime
from modules import get_device_id, register_device, update_status
import os
import json
import logging
import requests
import asyncio
import socket
import subprocess
import traceback
import re
import time
import websockets
import uvicorn

app=FastAPI()
from modules.devices import get_device_id, API_URL
# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('raspberry_client.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(socket.gethostname()) 


router = APIRouter(
    prefix="/sync",
    tags=["sync"]
)

# Configuraciones de sincronización - valores por defecto
# DOWNLOAD_PATH = os.path.expanduser("~/downloads")
# CHECK_INTERVAL = 30  # minutos
# SERVICE_NAME = "videoloop.service"

# Clase del cliente de sincronización
class VideoSyncClient:
    def __init__(self, device_id):
        self.device_id = device_id
        self.download_path = DOWNLOAD_PATH
        self.check_interval = CHECK_INTERVAL
        self.service_name = SERVICE_NAME
        self.playlists_path = os.path.join(self.download_path, "playlists")
        self.active_playlists = {}
        self.last_update = None
        self.changes_detected = False
        
        # Crear directorios si no existen
        os.makedirs(self.playlists_path, exist_ok=True)
        
        logger.info(f"Cliente de sincronización inicializado para dispositivo {self.device_id}")
    
    def load_state(self):
        """Carga el estado previo si existe"""
        state_file = os.path.join(self.download_path, "client_state.json")
        
        if os.path.exists(state_file):
            try:
                with open(state_file, "r") as f:
                    state = json.load(f)
                    self.active_playlists = state.get("active_playlists", {})
                    self.last_update = state.get("last_update")
                logger.info(f"Estado cargado: {len(self.active_playlists)} playlists activas")
            except Exception as e:
                logger.error(f"Error al cargar el estado: {e}")
    
    def save_state(self):
        """Guarda el estado actual del cliente"""
        state_file = os.path.join(self.download_path, "client_state.json")
        
        try:
            state = {
                "active_playlists": self.active_playlists,
                "last_update": self.last_update,
                "last_sync": datetime.now().isoformat()
            }
            
            with open(state_file, "w") as f:
                json.dump(state, f, indent=4)
            
            logger.debug("Estado guardado correctamente")
        except Exception as e:
            logger.error(f"Error al guardar el estado: {e}")
    
    async def check_for_updates(self):
        """Verifica si hay actualizaciones en las playlists asignadas a este dispositivo"""
        logger.info("Verificando actualizaciones de playlists...")
        
        # Resetear flag de cambios
        self.changes_detected = False
        
        try:
            # Preparar parámetros para la verificación
            params = {
                "device_id": self.device_id  # Incluir ID del dispositivo para obtener solo playlists asignadas
            }
            
            if self.last_update:
                params["last_update"] = self.last_update
            
            if self.active_playlists:
                playlist_ids = ",".join([str(pid) for pid in self.active_playlists.keys()])
                params["playlist_ids"] = playlist_ids
            
            # Obtener actualizaciones del servidor
            logger.info(f"Solicitando playlists activas para dispositivo {self.device_id} de: {API_URL}/raspberry/playlists/active")
            try:
                response = await asyncio.to_thread(
                    requests.get,
                    f"{API_URL}/raspberry/playlists/active", 
                    params=params,
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.error(f"Error al obtener actualizaciones: {response.status_code}")
                    return
                
                # Procesar playlists activas
                active_playlists = response.json()
                logger.info(f"Recibidas {len(active_playlists)} playlists activas")
                
                # Identificar playlists nuevas o modificadas
                playlists_to_update = []
                for playlist in active_playlists:
                    playlist_id = str(playlist["id"])
                    
                    # Verificar si es una playlist nueva o modificada
                    if playlist_id not in self.active_playlists:
                        logger.info(f"Nueva playlist encontrada: {playlist['title']} (ID: {playlist_id})")
                        playlists_to_update.append(playlist)
                        self.changes_detected = True
                    else:
                        # Comparar para ver si ha sido modificada
                        old_playlist = self.active_playlists[playlist_id]
                        
                        # Verificar si hay cambios en los videos de la playlist
                        old_videos = {str(v["id"]): v for v in old_playlist.get("videos", [])}
                        new_videos = {str(v["id"]): v for v in playlist.get("videos", [])}
                        
                        if len(old_videos) != len(new_videos):
                            logger.info(f"Cambio en el número de videos en playlist: {playlist['title']} (ID: {playlist_id})")
                            playlists_to_update.append(playlist)
                            self.changes_detected = True
                        else:
                            # Verificar si hay nuevos videos o videos modificados
                            for video_id, video in new_videos.items():
                                if video_id not in old_videos:
                                    logger.info(f"Nuevo video en playlist {playlist_id}: Video ID {video_id}")
                                    playlists_to_update.append(playlist)
                                    self.changes_detected = True
                                    break
                
                # Identificar playlists expiradas
                expired_playlists = []
                for playlist_id in list(self.active_playlists.keys()):
                    if not any(str(p["id"]) == playlist_id for p in active_playlists):
                        logger.info(f"Playlist expirada o eliminada: ID {playlist_id}")
                        expired_playlists.append(playlist_id)
                        self.changes_detected = True
                
                # Procesar playlists expiradas
                for playlist_id in expired_playlists:
                    await asyncio.to_thread(self.remove_playlist, playlist_id)
                
                # Descargar playlists nuevas o modificadas
                for playlist in playlists_to_update:
                    await asyncio.to_thread(self.download_playlist, playlist)
                
                # Actualizar lista de playlists activas
                self.active_playlists = {str(p["id"]): p for p in active_playlists}
                self.last_update = datetime.now().isoformat()
                
                # Actualizar estado en el sistema de archivos
                await asyncio.to_thread(self.save_state)
                
                logger.info(f"Sincronización completada. Total playlists activas: {len(self.active_playlists)}")
                logger.info(f"¿Se detectaron cambios? {'Sí' if self.changes_detected else 'No'}")
                
                # Devolver si se detectaron cambios para que el llamador pueda decidir si reiniciar el servicio
                return self.changes_detected
                
            except Exception as e:
                logger.error(f"Error al comunicarse con el servidor: {e}")
                logger.error(traceback.format_exc())
        
        except Exception as e:
            logger.error(f"Error durante la verificación de actualizaciones: {e}")
            logger.error(traceback.format_exc())
    
    def download_playlist(self, playlist):
        """Descarga una playlist y sus videos"""
        playlist_id = str(playlist["id"])
        logger.info(f"Descargando playlist {playlist_id}: {playlist['title']}")
        
        # Crear directorio para la playlist
        playlist_dir = os.path.join(self.playlists_path, playlist_id)
        os.makedirs(playlist_dir, exist_ok=True)
        
        # Guardar información de la playlist
        playlist_file = os.path.join(playlist_dir, "playlist.json")
        with open(playlist_file, "w") as f:
            json.dump(playlist, f, indent=4)
        
        # Descargar videos
        for video in playlist.get("videos", []):
            video_id = str(video["id"])
            video_filename = f"{video_id}.mp4"
            video_path = os.path.join(playlist_dir, video_filename)
            
            # Si el video ya existe y tiene tamaño mayor que cero, omitir descarga
            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                logger.debug(f"Video {video_id} ya existe, omitiendo descarga")
                continue
            
            # Descargar el video
            try:
                video_url = f"{API_URL}/videos/{video_id}/download"
                logger.info(f"Descargando video {video_id}: {video['title']}")
                
                with requests.get(video_url, stream=True, timeout=120) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get('content-length', 0))
                    
                    # Crear archivo temporal para la descarga
                    temp_path = f"{video_path}.tmp"
                    
                    # Descargar en chunks para archivos grandes
                    downloaded = 0
                    with open(temp_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                                # Mostrar progreso cada 5%
                                if total_size > 0 and downloaded % (total_size // 20) < 8192:
                                    progress = (downloaded / total_size) * 100
                                    logger.info(f"Progreso de descarga {video_id}: {progress:.1f}%")
                    
                    # Mover archivo temporal a destino final
                    os.rename(temp_path, video_path)
                    logger.info(f"Video {video_id} descargado correctamente")
                    
                    # Marcar que se detectaron cambios
                    self.changes_detected = True
            
            except Exception as e:
                logger.error(f"Error al descargar video {video_id}: {e}")
                # Eliminar archivo temporal si existe
                if os.path.exists(f"{video_path}.tmp"):
                    os.remove(f"{video_path}.tmp")
        
        # Crear archivo m3u con rutas absolutas
        self.create_m3u_playlist(playlist, playlist_dir)
        
        logger.info(f"Playlist {playlist_id} descargada correctamente")
    
    def create_m3u_playlist(self, playlist, playlist_dir):
        """Crea un archivo m3u con la lista de videos"""
        m3u_path = os.path.join(playlist_dir, "playlist.m3u")
        
        # Guardar contenido anterior para verificar cambios
        old_content = ""
        if os.path.exists(m3u_path):
            with open(m3u_path, "r") as f:
                old_content = f.read()
        
        # Recopilar rutas de videos
        video_paths = []
        for video in playlist.get("videos", []):
            video_id = str(video["id"])
            video_path = os.path.join(playlist_dir, f"{video_id}.mp4")
            
            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                # Usar ruta absoluta para mayor compatibilidad
                video_absolute_path = os.path.abspath(video_path)
                video_paths.append(video_absolute_path)
        
        # Crear archivo m3u
        if video_paths:
            new_content = "\n".join(video_paths)
            
            # Verificar si el contenido ha cambiado
            if new_content != old_content:
                with open(m3u_path, "w") as f:
                    f.write(new_content)
                
                logger.info(f"Archivo m3u actualizado con {len(video_paths)} videos")
                self.changes_detected = True
            else:
                logger.debug("Archivo m3u sin cambios")
        else:
            logger.warning(f"No se encontraron videos válidos para crear el archivo m3u")
        
        # Copiar el script de reproducción mejorado
        self.create_play_script(playlist_dir)
    
    def remove_playlist(self, playlist_id):
        """Elimina una playlist expirada"""
        logger.info(f"Eliminando playlist {playlist_id}")
        
        # Marcar la playlist como inactiva pero mantener los archivos
        if playlist_id in self.active_playlists:
            del self.active_playlists[playlist_id]
    
    async def restart_videoloop_service(self):
        """Reinicia el servicio de reproducción de video"""
        logger.info(f"Reiniciando servicio {self.service_name}...")
        
        try:
            # Verificar si el servicio existe
            check_cmd = ["systemctl", "status", self.service_name]
            check_result = subprocess.run(check_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if check_result.returncode == 4:  # 4 indica que el servicio no existe
                logger.warning(f"El servicio {self.service_name} no existe")
                return
            
            # Reiniciar el servicio
            restart_cmd = ["sudo", "systemctl", "restart", self.service_name]
            restart_result = subprocess.run(restart_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if restart_result.returncode == 0:
                logger.info(f"Servicio {self.service_name} reiniciado correctamente")
            else:
                error = restart_result.stderr.decode('utf-8', errors='ignore')
                logger.error(f"Error al reiniciar el servicio: {error}")
                
                # Intento alternativo con sudo explícito por si hay problemas de permisos
                if "permission denied" in error.lower():
                    logger.info("Intentando reiniciar con sudo explícito...")
                    os.system(f"echo 'Reiniciando servicio desde script' | sudo -S systemctl restart {self.service_name}")
                    logger.info("Comando de reinicio alternativo ejecutado")
        
        except Exception as e:
            logger.error(f"Error al intentar reiniciar el servicio: {e}")


# Endpoints para el router de sincronización
@router.get("/status")
async def sync_status():
    """Obtiene el estado actual de la sincronización"""
    device_id = get_device_id()
    client = VideoSyncClient(device_id)
    client.load_state()
    
    # Contar número de playlists y videos
    total_videos = 0
    for playlist_id, playlist in client.active_playlists.items():
        total_videos += len(playlist.get("videos", []))
    
    return {
        "device_id": device_id,
        "active_playlists": len(client.active_playlists),
        "total_videos": total_videos,
        "last_update": client.last_update,
        "download_path": client.download_path,
        "service_name": client.service_name
    }

@router.post("/force-update")
async def force_sync_update():
    """Fuerza una actualización de la sincronización"""
    device_id = get_device_id()
    client = VideoSyncClient(device_id)
    client.load_state()
    
    changes = await client.check_for_updates()
    
    if changes:
        await client.restart_videoloop_service()
        return {"status": "updated", "message": "Se detectaron cambios y se reinició el servicio"}
    else:
        return {"status": "no_changes", "message": "No se detectaron cambios"}

@router.get("/list-playlists")
async def list_sync_playlists():
    """Lista las playlists sincronizadas actualmente"""
    device_id = get_device_id()
    client = VideoSyncClient(device_id)
    client.load_state()
    
    playlists = []
    for playlist_id, playlist in client.active_playlists.items():
        videos = []
        for video in playlist.get("videos", []):
            video_id = str(video["id"])
            video_path = os.path.join(client.playlists_path, playlist_id, f"{video_id}.mp4")
            video_exists = os.path.exists(video_path)
            
            videos.append({
                "id": video["id"],
                "title": video["title"],
                "downloaded": video_exists,
                "size": os.path.getsize(video_path) if video_exists else 0
            })
            
        playlists.append({
            "id": playlist["id"],
            "title": playlist["title"],
            "videos_count": len(videos),
            "videos": videos
        })
    
    return {
        "device_id": device_id,
        "playlists_count": len(playlists),
        "playlists": playlists
    }


# Función para manejar conexiones WebSocket
async def websocket_handler(websocket, path):
    """Maneja la conexión WebSocket para streaming de logs."""
    logger.info(f"Cliente conectado vía WebSocket desde {websocket.remote_address}")
    tail_task = None

    try:
        # Función para leer el archivo de log en tiempo real
        async def tail_log():
            try:
                with open('/var/log/raspberry_client.log', 'r') as f:
                    f.seek(0, 2)  # Ir al final del archivo
                    while True:
                        line = f.readline()
                        if line:
                            try:
                                # Enviar en formato JSON para mayor compatibilidad
                                log_entry = {
                                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "content": line.strip()
                                }
                                
                                # Extraer ID del dispositivo si está disponible
                                device_match = re.search(r'Device\[(\w+)\]', line)
                                if device_match:
                                    log_entry["device_id"] = device_match.group(1)
                                
                                await websocket.send(json.dumps(log_entry))
                            except Exception as e:
                                logger.error(f"Error al procesar línea de log: {str(e)}")
                        await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error en tail_log: {str(e)}")

        # Ejecutar la función de lectura de logs en segundo plano
        tail_task = asyncio.create_task(tail_log())

        # Mantener la conexión WebSocket abierta
        while True:
            try:
                # Escuchar mensajes del cliente
                message = await websocket.recv()
                try:
                    data = json.loads(message)
                    if isinstance(data, dict) and data.get("action") == "filter":
                        logger.info(f"Recibido filtro: {data}")
                except:
                    pass  # Ignorar mensajes que no sean JSON válido
            except websockets.ConnectionClosed:
                break
            except Exception as e:
                logger.error(f"Error al recibir mensaje: {str(e)}")
                break

    except Exception as e:
        logger.error(f"Error en websocket_handler: {str(e)}")
    finally:
        if tail_task:
            tail_task.cancel()
            try:
                await tail_task
            except asyncio.CancelledError:
                pass
        logger.info("Conexión WebSocket cerrada")

# Función principal asíncrona que combina todas las funcionalidades
async def main():
    """
    Función principal que combina todas las funcionalidades del cliente Raspberry Pi:
    - Servidor WebSocket
    - Servidor API
    - Registro y actualización de estado del dispositivo
    - Sincronización de videos
    """
    try:
        logger.info("Iniciando cliente Raspberry Pi completo")
        
        # Obtener el ID del dispositivo
        device_id = get_device_id()
        logger.info(f"ID del dispositivo: {device_id}")
        
        # Inicializar el cliente de sincronización
        sync_client = VideoSyncClient(device_id)
        sync_client.load_state()
        
        # Iniciar servidor WebSocket
        websocket_server = await websockets.serve(websocket_handler, "0.0.0.0", 8001)
        logger.info("Iniciando servidor WebSocket en ws://0.0.0.0:8001")
        
        # Iniciar servidor API usando uvicorn como tarea asíncrona
        config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
        server = uvicorn.Server(config)
        api_server_task = asyncio.create_task(server.serve())
        logger.info("Iniciando servidor API en http://0.0.0.0:8000")
        
        # Intentar registrar el dispositivo
        is_registered = await asyncio.to_thread(register_device)
        
        if not is_registered:
            logger.error("No se pudo registrar el dispositivo, reintentando en 30 segundos")
            await asyncio.sleep(30)
            is_registered = await asyncio.to_thread(register_device)
            
            if not is_registered:
                logger.error("Fallo al registrar el dispositivo después de reintentos. Continuando de todos modos.")
        
        # Verificación inicial de playlists
        changes_detected = await sync_client.check_for_updates()
        
        # Si se detectaron cambios en la verificación inicial, reiniciar servicio
        if changes_detected:
            await sync_client.restart_videoloop_service()
        
        # Configurar intervalos de actualización
        update_status_interval = 300  # segundos - 5 minutos
        sync_check_interval = sync_client.check_interval * 60  # convertir a segundos
        
        # Bucle principal para actualizar el estado y sincronizar periódicamente
        max_failures = 3
        consecutive_failures = 0
        
        while True:
            # Tareas de actualización de estado
            success = await asyncio.to_thread(update_status)
            
            if success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logger.warning(f"Fallo al actualizar estado ({consecutive_failures}/{max_failures})")
                
                if consecutive_failures >= max_failures:
                    logger.error("Demasiados fallos consecutivos, se reiniciará el proceso de registro")
                    is_registered = await asyncio.to_thread(register_device)
                    consecutive_failures = 0
            
            # Verificar si es momento de sincronizar videos también
            current_time = time.time()
            if not hasattr(main, 'last_sync_time') or current_time - main.last_sync_time >= sync_check_interval:
                logger.info(f"Verificando actualizaciones de playlists...")
                changes_detected = await sync_client.check_for_updates()
                
                if changes_detected:
                    await sync_client.restart_videoloop_service()
                
                # Actualizar tiempo de la última sincronización
                main.last_sync_time = current_time
            
            # Esperar antes de la próxima actualización
            await asyncio.sleep(update_status_interval)
            
    except KeyboardInterrupt:
        logger.info("Cliente detenido por el usuario")
    except Exception as e:
        logger.critical(f"Error crítico: {str(e)}")
        logger.error(traceback.format_exc())
        raise

# Inicializar el tiempo de última sincronización
main.last_sync_time = 0