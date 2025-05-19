#!/usr/bin/env python3
# Cliente unificado para sincronización de videos en Raspberry Pi

from fastapi import FastAPI, APIRouter
import os
import sys
import json
import time
import requests
import traceback
import argparse
import logging
import subprocess
from datetime import datetime, timedelta
import asyncio
import websockets
import uvicorn
import socket
import re
from pathlib import Path
import shutil
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
import os

load_dotenv()



# Importaciones de módulos existentes
from routers import log, screenshot, service_router
from modules.devices import register_device, update_status
from modules.control_interface import get_device_id, get_interface_ip, get_interface_mac
from modules.services import check_service


# CHECK_INTERVAL = os.getenv("CHECK_INTERVAL")
# SYNC_ONLY = os.getenv("SYNC_ONLY")

# Configuración predeterminada para la sincronización
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH") # Ruta predeterminada para descargas
CHECK_INTERVAL = 1  # Intervalo predeterminado en minutos 
SERVICE_NAME = "videoloop.service"  # Nombre del servicio predeterminado
SERVER_URL = os.getenv("SERVER_URL")  # URL del servidor predeterminada
API_URL = f"{SERVER_URL}/api"  # URL de la API

# Clase personalizada para rotar basado en número de líneas
class LineCountRotatingFileHandler(RotatingFileHandler):
    def __init__(self, filename, max_lines=2000, backup_count=5, encoding=None):
        self.max_lines = max_lines
        super(LineCountRotatingFileHandler, self).__init__(
            filename, 
            maxBytes=0,  # No rotamos por tamaño
            backupCount=backup_count,
            encoding=encoding
        )
        
    def emit(self, record):
        """Emite un registro y verifica el conteo de líneas después."""
        super(LineCountRotatingFileHandler, self).emit(record)
        self.check_line_count()
        
    def check_line_count(self):
        """Verifica si el archivo ha excedido el máximo de líneas."""
        if os.path.exists(self.baseFilename):
            with open(self.baseFilename, 'r', encoding=self.encoding) as f:
                line_count = sum(1 for _ in f)
                
            if line_count >= self.max_lines:
                self.doRollover()

# Configuración de logging con el handler personalizado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        LineCountRotatingFileHandler('raspberry_client.log', max_lines=2000, backup_count=3),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(socket.gethostname())

# Clase para manejar la autenticación JWT
class JWTAuthManager:
    """Clase para manejar la autenticación JWT del cliente"""
    
    def __init__(self, server_url, username, password, token_file="token.json"):
        """
        Inicializa el gestor de autenticación JWT
        
        Args:
            server_url: URL del servidor
            username: Nombre de usuario
            password: Contraseña
            token_file: Archivo para guardar el token
        """
        self.server_url = server_url
        self.username = username
        self.password = password
        self.token_file = token_file
        self.token_data = None
        self.headers = {"Content-Type": "application/json"}
    
    def get_token(self):
        """Obtiene el token almacenado o solicita uno nuevo si es necesario"""
        # Intentar cargar el token existente
        if self.load_token():
            # Verificar si el token ha expirado
            if not self.is_token_expired():
                return self.token_data["access_token"]
        
        # Si no hay token o ha expirado, solicitar uno nuevo
        return self.request_new_token()
    
    def load_token(self):
        """Carga el token desde el archivo"""
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, "r") as f:
                    self.token_data = json.load(f)
                return True
        except Exception as e:
            logging.error(f"Error al cargar el token: {e}")
        return False
    
    def save_token(self):
        """Guarda el token en un archivo"""
        try:
            with open(self.token_file, "w") as f:
                json.dump(self.token_data, f)
        except Exception as e:
            logging.error(f"Error al guardar el token: {e}")
    
    def is_token_expired(self):
        """Verifica si el token ha expirado"""
        if not self.token_data or "expires_at" not in self.token_data:
            return True
        
        # Verificar si el token expira en menos de 5 minutos
        expires_at = datetime.fromisoformat(self.token_data["expires_at"])
        now = datetime.now()
        
        # Si falta menos de 5 minutos para que expire, considerarlo expirado
        return expires_at - now < timedelta(minutes=5)
    
    def request_new_token(self):
        """Solicita un nuevo token al servidor"""
        try:
            auth_url = f"{self.server_url}/api/auth/token"
            payload = {
                "username": self.username,
                "password": self.password
            }
            
            response = requests.post(
                auth_url,
                json=payload,
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code != 200:
                logging.error(f"Error al obtener token: {response.status_code} - {response.text}")
                return None
            
            # Almacenar datos del token
            self.token_data = response.json()
            
            # Añadir timestamp de expiración
            expires_in_seconds = self.token_data.get("expires_in", 28800)  # 8 horas por defecto
            expiry_time = datetime.now() + timedelta(seconds=expires_in_seconds)
            self.token_data["expires_at"] = expiry_time.isoformat()
            
            # Guardar el token para uso futuro
            self.save_token()
            
            return self.token_data["access_token"]
            
        except Exception as e:
            logging.error(f"Error al solicitar token: {e}")
            return None
    
    def get_auth_headers(self):
        """Obtiene los headers para autenticación"""
        token = self.get_token()
        if not token:
            return self.headers
        
        # Añadir el token a los headers
        auth_headers = self.headers.copy()
        auth_headers["Authorization"] = f"Bearer {token}"
        return auth_headers

# Cliente para sincronización de videos
class VideoDownloaderClient:
    def __init__(self, server_url, download_path, username, password, check_interval=30, service_name="videoloop.service"):
        """Inicializa el cliente de descarga"""
        self.server_url = server_url
        self.download_path = download_path
        self.check_interval = check_interval
        self.service_name = service_name
        
        # Agregar device_id como atributo de la clase
        self.device_id = get_device_id()
        
        # Crear directorio si no existe
        os.makedirs(self.download_path, exist_ok=True)
        
        # Estado del cliente
        self.active_playlists = {}
        self.last_update = None
        self.changes_detected = False
        
        # Inicializar gestor de autenticación JWT
        self.auth_manager = JWTAuthManager(
            server_url=server_url,
            username=username,
            password=password,
            token_file=os.path.join(download_path, "token.json")
        )
        
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
    
    def download_playlist(self, playlist):
        """Descarga una playlist y sus videos directamente en el directorio principal"""
        playlist_id = str(playlist["id"])
        logger.info(f"Descargando playlist {playlist_id}: {playlist['title']}")
        
        # Guardar información de la playlist en el directorio principal
        playlist_file = os.path.join(self.download_path, f"playlist_{playlist_id}.json")
        with open(playlist_file, "w") as f:
            json.dump(playlist, f, indent=4)
        
        # Descargar videos directamente en el directorio principal
        for video in playlist.get("videos", []):
            video_id = str(video["id"])
            video_filename = f"{video_id}.mp4"
            video_path = os.path.join(self.download_path, video_filename)
            
            # Si el video ya existe y tiene tamaño mayor que cero, omitir descarga
            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                logger.debug(f"Video {video_id} ya existe, omitiendo descarga")
                continue
            
            # Descargar el video
            try:
                video_url = f"{self.server_url}/api/videos/{video_id}/download"
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
        
        # Crear archivo m3u para la playlist directamente en el directorio principal
        self.create_m3u_playlist(playlist)
        
        logger.info(f"Playlist {playlist_id} descargada correctamente")
    
    def create_m3u_playlist(self, playlist):
        """Crea un archivo m3u con la lista de videos en el directorio principal"""
        playlist_id = str(playlist["id"])
        m3u_path = os.path.join(self.download_path, "playlist.m3u")
        
        # Guardar contenido anterior para verificar cambios
        old_content = ""
        if os.path.exists(m3u_path):
            with open(m3u_path, "r") as f:
                old_content = f.read()
        
        # Recopilar rutas de videos
        video_paths = []
        for video in playlist.get("videos", []):
            video_id = str(video["id"])
            video_path = os.path.join(self.download_path, f"{video_id}.mp4")
            
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
        
        # Crear un archivo m3u principal que tenga todos los videos de todas las playlists activas
        self.create_main_m3u_playlist()
    
    def create_main_m3u_playlist(self):
        """Crea un archivo m3u principal con los videos de todas las playlists activas"""
        m3u_path = os.path.join(self.download_path, "playlist.m3u")
        
        # Recopilar rutas de videos de todas las playlists activas
        video_paths = []
        
        # Primero recopilar todos los IDs de videos de playlists activas
        video_ids = set()
        for playlist_id, playlist_data in self.active_playlists.items():
            for video in playlist_data.get("videos", []):
                video_ids.add(str(video["id"]))
        
        # Luego verificar la existencia de cada video y añadirlo a la lista
        for video_id in video_ids:
            video_path = os.path.join(self.download_path, f"{video_id}.mp4")
            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                video_absolute_path = os.path.abspath(video_path)
                video_paths.append(video_absolute_path)
        
        # Crear archivo m3u principal
        if video_paths:
            new_content = "\n".join(video_paths)
            with open(m3u_path, "w") as f:
                f.write(new_content)
            
            logger.info(f"Archivo m3u principal creado/actualizado con {len(video_paths)} videos")
            self.changes_detected = True
        else:
            logger.warning(f"No se encontraron videos válidos para crear el archivo m3u principal")
    
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
    
    def remove_playlist(self, playlist_id):
        """Elimina una playlist expirada del estado (pero mantiene los archivos de video)"""
        logger.info(f"Eliminando playlist {playlist_id} del estado")
        
        # Marcar la playlist como inactiva pero mantener los archivos
        if playlist_id in self.active_playlists:
            del self.active_playlists[playlist_id]
            
            # También eliminar el archivo JSON y M3U específico de esta playlist
            playlist_json = os.path.join(self.download_path, f"playlist_{playlist_id}.json")
            playlist_m3u = os.path.join(self.download_path, f"playlist_{playlist_id}.m3u")
            
            try:
                if os.path.exists(playlist_json):
                    os.remove(playlist_json)
                if os.path.exists(playlist_m3u):
                    os.remove(playlist_m3u)
                logger.info(f"Archivos de configuración de playlist {playlist_id} eliminados")
            except Exception as e:
                logger.error(f"Error al eliminar archivos de playlist {playlist_id}: {e}")
        
        # Actualizar el archivo m3u principal para reflejar las playlists activas
        self.create_main_m3u_playlist()

    async def check_for_updates(self):
        """Verifica si hay actualizaciones en las playlists asignadas a este dispositivo"""
        logger.info("Verificando actualizaciones de playlists...")
        
        # Resetear flag de cambios
        self.changes_detected = False
    
        try:
            # Preparar parámetros para la verificación
            params = {}
            
            if self.last_update:
                params["last_update"] = self.last_update
            
            if self.active_playlists:
                playlist_ids = ",".join([str(pid) for pid in self.active_playlists.keys()])
                params["playlist_ids"] = playlist_ids
            
            # Obtener actualizaciones del servidor usando el endpoint específico para este dispositivo
            endpoint_url = f"{API_URL}/raspberry/playlists/active/{self.device_id}"
            logger.info(f"Solicitando playlists activas para dispositivo {self.device_id} de: {endpoint_url}")
            
            try:
                # Usar asyncio.to_thread para hacer la petición HTTP de forma asíncrona
                response = await asyncio.to_thread(
                    requests.get,
                    endpoint_url,
                    params=params,
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.error(f"Error al obtener actualizaciones: {response.status_code}")
                    return False
                
                # Procesar playlists activas
                active_playlists = response.json()
                logger.info(f"Recibidas {len(active_playlists)} playlists activas")
                
                # Verificar si hay cambios comparando con el estado actual
                changes_detected = False
                
                # Identificar playlists nuevas, modificadas o eliminadas
                old_playlist_ids = set(self.active_playlists.keys())
                new_playlist_ids = set(str(p["id"]) for p in active_playlists)
                
                # Si hay cualquier diferencia entre los conjuntos de IDs, hay cambios
                if old_playlist_ids != new_playlist_ids:
                    changes_detected = True
                    logger.info("Detectado cambio en las playlists asignadas")
                else:
                    # Si los IDs son los mismos, verificar si hay cambios en los videos
                    for playlist in active_playlists:
                        playlist_id = str(playlist["id"])
                        old_playlist = self.active_playlists[playlist_id]
                        
                        # Comparar los videos
                        old_videos = {str(v["id"]): v for v in old_playlist.get("videos", [])}
                        new_videos = {str(v["id"]): v for v in playlist.get("videos", [])}
                        
                        # Verificar si hay cambios en los IDs de videos
                        if set(old_videos.keys()) != set(new_videos.keys()):
                            changes_detected = True
                            logger.info(f"Detectado cambio en los videos de la playlist {playlist_id}")
                            break
                        
                        # Verificar si hay cambios en las fechas de expiración o metadatos
                        for video_id, video in new_videos.items():
                            old_video = old_videos[video_id]
                            if video.get("expiration_date") != old_video.get("expiration_date"):
                                changes_detected = True
                                logger.info(f"Detectado cambio en la fecha de expiración del video {video_id}")
                                break
                
                self.changes_detected = changes_detected
                
                # Si se detectaron cambios, borrar todo y volver a descargar
                if changes_detected:
                    logger.info("Se detectaron cambios. Borrando todos los archivos y descargando de nuevo...")
                    
                    # Borrar todos los archivos en el directorio de descargas excepto token.json
                    await self.clear_download_directory()
                    
                    # Descargar todas las playlists activas
                    for playlist in active_playlists:
                        await asyncio.to_thread(self.download_playlist, playlist)
                    
                    # Actualizar lista de playlists activas
                    self.active_playlists = {str(p["id"]): p for p in active_playlists}
                    self.last_update = datetime.now().isoformat()
                    
                    # Actualizar estado en el sistema de archivos
                    await asyncio.to_thread(self.save_state)
                else:
                    logger.info("No se detectaron cambios en las playlists o videos")
                
                logger.info(f"Sincronización completada. Total playlists activas: {len(self.active_playlists)}")
                logger.info(f"¿Se detectaron cambios? {'Sí' if self.changes_detected else 'No'}")
                
                # Devolver si se detectaron cambios para que el llamador pueda decidir si reiniciar el servicio
                return self.changes_detected
                
            except Exception as e:
                logger.error(f"Error al comunicarse con el servidor: {e}")
                logger.error(traceback.format_exc())
                return False
        
        except Exception as e:
            logger.error(f"Error durante la verificación de actualizaciones: {e}")
            logger.error(traceback.format_exc())
            return False
            
    async def clear_download_directory(self):
        """Borra todos los archivos del directorio de descargas excepto token.json"""
        try:
            # Lista todos los archivos en el directorio de descargas
            files = os.listdir(self.download_path)
            
            for filename in files:
                # Preservar el archivo de token
                if filename == "token.json":
                    continue
                    
                file_path = os.path.join(self.download_path, filename)
                
                # Si es un archivo, borrarlo
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    logger.info(f"Archivo eliminado: {filename}")
                # Si es un directorio, borrarlo recursivamente
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    logger.info(f"Directorio eliminado: {filename}")
            
            logger.info(f"Directorio de descargas limpiado: {self.download_path}")
            
        except Exception as e:
            logger.error(f"Error al limpiar el directorio de descargas: {e}")
            logger.error(traceback.format_exc()) 
            """actualizaciones en las playlists asignadas a este dispositivo"""
        logger.info("Verificando actualizaciones de playlists...")
        
        # Resetear flag de cambios
        self.changes_detected = False
    
        try:
            # Preparar parámetros para la verificación
            params = {}
            
            if self.last_update:
                params["last_update"] = self.last_update
            
            if self.active_playlists:
                playlist_ids = ",".join([str(pid) for pid in self.active_playlists.keys()])
                params["playlist_ids"] = playlist_ids
            
            # Obtener actualizaciones del servidor usando el endpoint específico para este dispositivo
            endpoint_url = f"{API_URL}/raspberry/playlists/active/{self.device_id}"
            logger.info(f"Solicitando playlists activas para dispositivo {self.device_id} de: {endpoint_url}")
            
            try:
                # Usar asyncio.to_thread para hacer la petición HTTP de forma asíncrona
                response = await asyncio.to_thread(
                    requests.get,
                    endpoint_url,
                    params=params,
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.error(f"Error al obtener actualizaciones: {response.status_code}")
                    return False
                
                # Procesar playlists activas
                active_playlists = response.json()
                logger.info(f"Recibidas {len(active_playlists)} playlists activas")
                
                # Verificar si hay cambios comparando con el estado actual
                changes_detected = False
                
                # Identificar playlists nuevas, modificadas o eliminadas
                old_playlist_ids = set(self.active_playlists.keys())
                new_playlist_ids = set(str(p["id"]) for p in active_playlists)
                
                # Si hay cualquier diferencia entre los conjuntos de IDs, hay cambios
                if old_playlist_ids != new_playlist_ids:
                    changes_detected = True
                    logger.info("Detectado cambio en las playlists asignadas")
                else:
                    # Si los IDs son los mismos, verificar si hay cambios en los videos
                    for playlist in active_playlists:
                        playlist_id = str(playlist["id"])
                        old_playlist = self.active_playlists[playlist_id]
                        
                        # Comparar los videos
                        old_videos = {str(v["id"]): v for v in old_playlist.get("videos", [])}
                        new_videos = {str(v["id"]): v for v in playlist.get("videos", [])}
                        
                        # Verificar si hay cambios en los IDs de videos
                        if set(old_videos.keys()) != set(new_videos.keys()):
                            changes_detected = True
                            logger.info(f"Detectado cambio en los videos de la playlist {playlist_id}")
                            break
                        
                        # Verificar si hay cambios en las fechas de expiración o metadatos
                        for video_id, video in new_videos.items():
                            old_video = old_videos[video_id]
                            if video.get("expiration_date") != old_video.get("expiration_date"):
                                changes_detected = True
                                logger.info(f"Detectado cambio en la fecha de expiración del video {video_id}")
                                break
                
                self.changes_detected = changes_detected
                
                # Si se detectaron cambios, borrar todo y volver a descargar
                if changes_detected:
                    logger.info("Se detectaron cambios. Borrando todos los archivos y descargando de nuevo...")
                    
                    # Borrar todos los archivos en el directorio de descargas excepto token.json
                    await self.clear_download_directory()
                    
                    # Descargar todas las playlists activas
                    for playlist in active_playlists:
                        await asyncio.to_thread(self.download_playlist, playlist)
                    
                    # Actualizar lista de playlists activas
                    self.active_playlists = {str(p["id"]): p for p in active_playlists}
                    self.last_update = datetime.now().isoformat()
                    
                    # Actualizar estado en el sistema de archivos
                    await asyncio.to_thread(self.save_state)
                else:
                    logger.info("No se detectaron cambios en las playlists o videos")
                
                logger.info(f"Sincronización completada. Total playlists activas: {len(self.active_playlists)}")
                logger.info(f"¿Se detectaron cambios? {'Sí' if self.changes_detected else 'No'}")
                
                # Devolver si se detectaron cambios para que el llamador pueda decidir si reiniciar el servicio
                return self.changes_detected
                
            except Exception as e:
                logger.error(f"Error al comunicarse con el servidor: {e}")
                logger.error(traceback.format_exc())
                return False
        
        except Exception as e:
            logger.error(f"Error durante la verificación de actualizaciones: {e}")
            logger.error(traceback.format_exc())
            return False

    async def clear_download_directory(self):
        """Borra todos los archivos del directorio de descargas excepto token.json"""
        try:
            # Lista todos los archivos en el directorio de descargas
            files = os.listdir(self.download_path)
            
            for filename in files:
                # Preservar el archivo de token
                if filename == "token.json":
                    continue
                    
                file_path = os.path.join(self.download_path, filename)
                
                # Si es un archivo, borrarlo
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    logger.info(f"Archivo eliminado: {filename}")
                # Si es un directorio, borrarlo recursivamente
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    logger.info(f"Directorio eliminado: {filename}")
            
            logger.info(f"Directorio de descargas limpiado: {self.download_path}")
            
        except Exception as e:
            logger.error(f"Error al limpiar el directorio de descargas: {e}")
            #logger.error(traceback.format_exc())d_path, filename)
                
                # Si es un archivo, borrarlo
            if os.path.isfile(file_path):
                os.remove(file_path)
                logger.info(f"Archivo eliminado: {filename}")
            # Si es un directorio, borrarlo recursivamente
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
                logger.info(f"Directorio eliminado: {filename}")
            
            logger.info(f"Directorio de descargas limpiado: {self.download_path}")
            
        except Exception as e:
            logger.error(f"Error al limpiar el directorio de descargas: {e}")
            logger.error(traceback.format_exc())

# Crear la aplicación FastAPI
app = FastAPI()

# Incluir routers existentes
app.include_router(log.router)
app.include_router(screenshot.router)
app.include_router(service_router.router)

# Crear un router para la funcionalidad del cliente de sincronización
sync_router = APIRouter(
    prefix="/sync",
    tags=["sync"]
)

# Endpoints para el router de sincronización
@sync_router.get("/status")
async def sync_status():
    """Obtiene el estado actual de la sincronización"""
    device_id = get_device_id()
    
    # Crear el cliente con los parámetros globales
    client = VideoDownloaderClient(
        server_url=SERVER_URL,
        download_path=DOWNLOAD_PATH,
        username="admin",  # Valor por defecto - debe ser reemplazado con valores reales
        password="password",  # Valor por defecto - debe ser reemplazado con valores reales
        check_interval=CHECK_INTERVAL,
        service_name=SERVICE_NAME
    )
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

@sync_router.post("/force-update")
async def force_sync_update():
    """Fuerza una actualización de la sincronización"""
    device_id = get_device_id()
    
    # Crear el cliente con los parámetros globales
    client = VideoDownloaderClient(
        server_url=SERVER_URL,
        download_path=DOWNLOAD_PATH,
        username="admin",  # Valor por defecto - debe ser reemplazado con valores reales
        password="password",  # Valor por defecto - debe ser reemplazado con valores reales
        check_interval=CHECK_INTERVAL,
        service_name=SERVICE_NAME
    )
    client.load_state()
    
    changes = await client.check_for_updates()
    
    if changes:
        await client.restart_videoloop_service()
        return {"status": "updated", "message": "Se detectaron cambios y se reinició el servicio"}
    else:
        return {"status": "no_changes", "message": "No se detectaron cambios"}

@sync_router.get("/list-playlists")
async def list_sync_playlists():
    """Lista las playlists sincronizadas actualmente"""
    device_id = get_device_id()
    
    # Crear el cliente con los parámetros globales
    client = VideoDownloaderClient(
        server_url=SERVER_URL,
        download_path=DOWNLOAD_PATH,
        username="admin",  # Valor por defecto - debe ser reemplazado con valores reales
        password="password",  # Valor por defecto - debe ser reemplazado con valores reales
        check_interval=CHECK_INTERVAL,
        service_name=SERVICE_NAME
    )
    client.load_state()
    
    playlists = []
    for playlist_id, playlist in client.active_playlists.items():
        videos = []
        for video in playlist.get("videos", []):
            video_id = str(video["id"])
            video_path = os.path.join(client.download_path, f"{video_id}.mp4")
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
        "playlists": playlists,
        "download_path": client.download_path
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
                with open('raspberry_client.log', 'r') as f:
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
async def websocket_handler(websocket, path):
    """Maneja la conexión WebSocket para streaming de logs."""
    logger.info(f"Cliente conectado vía WebSocket desde {websocket.remote_address}")
    tail_task = None

    try:
        # Función para leer el archivo de log en tiempo real
        async def tail_log():
            try:
                with open('raspberry_client.log', 'r') as f:
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

# Crear un router para la funcionalidad del cliente de sincronización
def create_sync_router():
    """Crea y configura el router de sincronización"""
    sync_router = APIRouter(
        prefix="/sync",
        tags=["sync"]
    )
    
    @sync_router.get("/status")
    async def sync_status():
        """Obtiene el estado actual de la sincronización"""
        device_id = get_device_id()
        
        # Crear el cliente con los parámetros globales
        client = VideoDownloaderClient(
            server_url=SERVER_URL,
            download_path=DOWNLOAD_PATH,
            username="admin",  # Valor por defecto - debe ser reemplazado con valores reales
            password="password",  # Valor por defecto - debe ser reemplazado con valores reales
            check_interval=CHECK_INTERVAL,
            service_name=SERVICE_NAME
        )
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

    @sync_router.post("/force-update")
    async def force_sync_update():
        """Fuerza una actualización de la sincronización"""
        device_id = get_device_id()
        
        # Crear el cliente con los parámetros globales
        client = VideoDownloaderClient(
            server_url=SERVER_URL,
            download_path=DOWNLOAD_PATH,
            username="admin",  # Valor por defecto - debe ser reemplazado con valores reales
            password="password",  # Valor por defecto - debe ser reemplazado con valores reales
            check_interval=CHECK_INTERVAL,
            service_name=SERVICE_NAME
        )
        client.load_state()
        
        changes = await client.check_for_updates()
        
        if changes:
            await client.restart_videoloop_service()
            return {"status": "updated", "message": "Se detectaron cambios y se reinició el servicio"}
        else:
            return {"status": "no_changes", "message": "No se detectaron cambios"}

    @sync_router.get("/list-playlists")
    async def list_sync_playlists():
        """Lista las playlists sincronizadas actualmente"""
        device_id = get_device_id()
        
        # Crear el cliente con los parámetros globales
        client = VideoDownloaderClient(
            server_url=SERVER_URL,
            download_path=DOWNLOAD_PATH,
            username="admin",  # Valor por defecto - debe ser reemplazado con valores reales
            password="password",  # Valor por defecto - debe ser reemplazado con valores reales
            check_interval=CHECK_INTERVAL,
            service_name=SERVICE_NAME
        )
        client.load_state()
        
        playlists = []
        for playlist_id, playlist in client.active_playlists.items():
            videos = []
            for video in playlist.get("videos", []):
                video_id = str(video["id"])
                video_path = os.path.join(client.download_path, f"{video_id}.mp4")
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
            "playlists": playlists,
            "download_path": client.download_path
        }
    
    return sync_router

# Función para crear la aplicación FastAPI
def create_app():
    """Crea y configura la aplicación FastAPI"""
    app = FastAPI(title="Raspberry Pi Client")
    
    # Intenta importar los routers externos si existen
    try:
        # Importar routers externos
        from routers import log, screenshot, service_router
        
        # Incluir routers existentes
        app.include_router(log.router)
        app.include_router(screenshot.router)
        app.include_router(service_router.router)
        logger.info("Routers externos cargados correctamente")
    except ImportError as e:
        logger.warning(f"No se pudieron cargar algunos routers externos: {e}")
        
    # Agregar el router de sincronización
    sync_router = create_sync_router()
    app.include_router(sync_router)
    
    return app
def create_app():
    """Crea y configura la aplicación FastAPI"""
    app = FastAPI(title="Raspberry Pi Client")
    
    # Intenta importar los routers externos si existen
    try:
        # Importar routers externos
        from routers import log, screenshot, service_router
        
        # Incluir routers existentes
        app.include_router(log.router)
        app.include_router(screenshot.router)
        app.include_router(service_router.router)
        logger.info("Routers externos cargados correctamente")
    except ImportError as e:
        logger.warning(f"No se pudieron cargar algunos routers externos: {e}")
        
    # Agregar el router de sincronización
    sync_router = create_sync_router()
    app.include_router(sync_router)
    
    return app

# Función principal asíncrona
async def main(username, password):
    """
    Función principal que combina todas las funcionalidades del cliente Raspberry Pi:
    - Servidor WebSocket
    - Servidor API
    - Registro y actualización de estado del dispositivo
    - Sincronización de videos
    """
    try:
        logger.info("Iniciando cliente Raspberry Pi completo")
        logger.info(f"Intervalo de verificación configurado: {CHECK_INTERVAL} minutos")
        
        # Obtener el ID del dispositivo
        device_id = get_device_id()
        logger.info(f"ID del dispositivo: {device_id}")
        
        # Crear la aplicación FastAPI
        app = create_app()
        
        # Inicializar el cliente de sincronización con todos los parámetros requeridos
        sync_client = VideoDownloaderClient(
            server_url=SERVER_URL,
            download_path=DOWNLOAD_PATH,
            username=username,
            password=password,
            check_interval=CHECK_INTERVAL,
            service_name=SERVICE_NAME
        )
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
        logger.info("Realizando verificación inicial de playlists...")
        changes_detected = await sync_client.check_for_updates()
        
        # Si se detectaron cambios en la verificación inicial, reiniciar servicio
        if changes_detected:
            await sync_client.restart_videoloop_service()
        
        # Configurar intervalos de actualización
        update_status_interval = 300  # segundos - 5 minutos
        
        # Convertir minutos a segundos para el intervalo de sincronización
        sync_check_interval = CHECK_INTERVAL * 60  # CHECK_INTERVAL es la variable global
        logger.info(f"Intervalos configurados: actualización de estado cada {update_status_interval} segundos, "
                   f"sincronización de videos cada {sync_check_interval} segundos ({CHECK_INTERVAL} minutos)")
        
        # Establecer tiempo de última sincronización
        last_sync_time = 0
        
        # Bucle principal para actualizar el estado y sincronizar periódicamente
        max_failures = 3
        consecutive_failures = 0
        
        while True:
            current_time = time.time()
            
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
            
            # Verificar si es momento de sincronizar videos
            elapsed_time = current_time - last_sync_time
            if elapsed_time >= sync_check_interval:
                logger.info(f"Han pasado {elapsed_time:.1f} segundos desde la última sincronización. Verificando actualizaciones...")
                changes_detected = await sync_client.check_for_updates()
                
                if changes_detected:
                    await sync_client.restart_videoloop_service()
                
                # Actualizar tiempo de la última sincronización
                last_sync_time = current_time
                logger.info(f"Próxima sincronización en {sync_check_interval} segundos")
            else:
                logger.debug(f"Siguiente sincronización en {sync_check_interval - elapsed_time:.1f} segundos")
            
            # Esperar antes de la próxima actualización de estado
            await asyncio.sleep(min(60, sync_check_interval))  # Dormir máximo 1 minuto o el intervalo de sincronización
            
    except KeyboardInterrupt:
        logger.info("Cliente detenido por el usuario")
    except Exception as e:
        logger.critical(f"Error crítico: {str(e)}")
        logger.error(traceback.format_exc())
        raise
async def main(username, password):
    """
    Función principal que combina todas las funcionalidades del cliente Raspberry Pi:
    - Servidor WebSocket
    - Servidor API
    - Registro y actualización de estado del dispositivo
    - Sincronización de videos
    """
    try:
        logger.info("Iniciando cliente Raspberry Pi completo")
        logger.info(f"Intervalo de verificación configurado: {CHECK_INTERVAL} minutos")
        
        # Obtener el ID del dispositivo
        device_id = get_device_id()
        logger.info(f"ID del dispositivo: {device_id}")
        
        # Crear la aplicación FastAPI
        app = create_app()
        
        # Inicializar el cliente de sincronización con todos los parámetros requeridos
        sync_client = VideoDownloaderClient(
            server_url=SERVER_URL,
            download_path=DOWNLOAD_PATH,
            username=username,
            password=password,
            check_interval=CHECK_INTERVAL,
            service_name=SERVICE_NAME
        )
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
        logger.info("Realizando verificación inicial de playlists...")
        changes_detected = await sync_client.check_for_updates()
        
        # Si se detectaron cambios en la verificación inicial, reiniciar servicio
        if changes_detected:
            await sync_client.restart_videoloop_service()
        
        # Configurar intervalos de actualización
        update_status_interval = 300  # segundos - 5 minutos
        
        # Convertir minutos a segundos para el intervalo de sincronización
        sync_check_interval = CHECK_INTERVAL * 60  # CHECK_INTERVAL es la variable global
        logger.info(f"Intervalos configurados: actualización de estado cada {update_status_interval} segundos, "
                   f"sincronización de videos cada {sync_check_interval} segundos ({CHECK_INTERVAL} minutos)")
        
        # Establecer tiempo de última sincronización
        last_sync_time = 0
        
        # Bucle principal para actualizar el estado y sincronizar periódicamente
        max_failures = 3
        consecutive_failures = 0
        
        while True:
            current_time = time.time()
            
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
            
            # Verificar si es momento de sincronizar videos
            elapsed_time = current_time - last_sync_time
            if elapsed_time >= sync_check_interval:
                logger.info(f"Han pasado {elapsed_time:.1f} segundos desde la última sincronización. Verificando actualizaciones...")
                changes_detected = await sync_client.check_for_updates()
                
                if changes_detected:
                    await sync_client.restart_videoloop_service()
                
                # Actualizar tiempo de la última sincronización
                last_sync_time = current_time
                logger.info(f"Próxima sincronización en {sync_check_interval} segundos")
            else:
                logger.debug(f"Siguiente sincronización en {sync_check_interval - elapsed_time:.1f} segundos")
            
            # Esperar antes de la próxima actualización de estado
            await asyncio.sleep(min(60, sync_check_interval))  # Dormir máximo 1 minuto o el intervalo de sincronización
            
    except KeyboardInterrupt:
        logger.info("Cliente detenido por el usuario")
    except Exception as e:
        logger.critical(f"Error crítico: {str(e)}")
        logger.error(traceback.format_exc())
# Función para ejecutar en modo sincronización simple
def run_sync_only_mode(username, password):
    """Ejecuta el cliente en modo de sincronización simplificado (sin API ni WebSocket)"""
    print("Ejecutando solo el cliente de sincronización de videos (sin API ni WebSocket)")
    
    # Obtener el ID del dispositivo
    device_id = get_device_id()
    print(f"ID del dispositivo: {device_id}")
    
    # Crear el cliente de sincronización
    client = VideoDownloaderClient(
        server_url=SERVER_URL,
        download_path=DOWNLOAD_PATH,
        username=username,
        password=password,
        check_interval=CHECK_INTERVAL,
        service_name=SERVICE_NAME
    )
    client.load_state()
    
    # Bucle de sincronización simplificado
    try:
        last_sync_time = 0
        sync_check_interval = CHECK_INTERVAL * 60  # convertir a segundos
        
        print(f"Intervalo de verificación configurado: {CHECK_INTERVAL} minutos ({sync_check_interval} segundos)")
        
        while True:
            current_time = time.time()
            
            # Intentar registrar el dispositivo si es necesario
            register_device()
            
            # Actualizar estado
            update_status()
            
            # Sincronizar videos si ha pasado el tiempo suficiente
            elapsed_time = current_time - last_sync_time
            if elapsed_time >= sync_check_interval or last_sync_time == 0:
                print(f"Han pasado {elapsed_time:.1f} segundos desde la última sincronización. Verificando actualizaciones...")
                changes_detected = asyncio.run(client.check_for_updates())
                
                if changes_detected:
                    asyncio.run(client.restart_videoloop_service())
                
                # Actualizar tiempo de la última sincronización
                last_sync_time = current_time
                print(f"Próxima sincronización en {sync_check_interval} segundos")
            
            # Calcular tiempo de espera para la próxima iteración
            sleep_time = min(60, max(1, sync_check_interval - (time.time() - current_time)))
            print(f"Esperando {sleep_time:.1f} segundos hasta la próxima verificación...")
            time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("Cliente detenido por el usuario")
    except Exception as e:
        print(f"Error crítico: {str(e)}")
        print(traceback.format_exc())
        return 1
    
    return 0
def run_sync_only_mode(username, password):
    """Ejecuta el cliente en modo de sincronización simplificado (sin API ni WebSocket)"""
    print("Ejecutando solo el cliente de sincronización de videos (sin API ni WebSocket)")
    
    # Obtener el ID del dispositivo
    device_id = get_device_id()
    print(f"ID del dispositivo: {device_id}")
    
    # Crear el cliente de sincronización
    client = VideoDownloaderClient(
        server_url=SERVER_URL,
        download_path=DOWNLOAD_PATH,
        username=username,
        password=password,
        check_interval=CHECK_INTERVAL,
        service_name=SERVICE_NAME
    )
    client.load_state()
    
    # Bucle de sincronización simplificado
    try:
        last_sync_time = 0
        sync_check_interval = CHECK_INTERVAL * 60  # convertir a segundos
        
        print(f"Intervalo de verificación configurado: {CHECK_INTERVAL} minutos ({sync_check_interval} segundos)")
        
        while True:
            current_time = time.time()
            
            # Intentar registrar el dispositivo si es necesario
            register_device()
            
            # Actualizar estado
            update_status()
            
            # Sincronizar videos si ha pasado el tiempo suficiente
            elapsed_time = current_time - last_sync_time
            if elapsed_time >= sync_check_interval or last_sync_time == 0:
                print(f"Han pasado {elapsed_time:.1f} segundos desde la última sincronización. Verificando actualizaciones...")
                changes_detected = asyncio.run(client.check_for_updates())
                
                if changes_detected:
                    asyncio.run(client.restart_videoloop_service())
                
                # Actualizar tiempo de la última sincronización
                last_sync_time = current_time
                print(f"Próxima sincronización en {sync_check_interval} segundos")
            
            # Calcular tiempo de espera para la próxima iteración
            sleep_time = min(60, max(1, sync_check_interval - (time.time() - current_time)))
            print(f"Esperando {sleep_time:.1f} segundos hasta la próxima verificación...")
            time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("Cliente detenido por el usuario")
    except Exception as e:
        print(f"Error crítico: {str(e)}")
        print(traceback.format_exc())
        return 1
    
    return 0

# Punto de entrada principal
if __name__ == "__main__":
    # Mostrar configuración actual
    print(f"Configuración:")
    print(f"  Servidor: {SERVER_URL}")
    print(f"  API URL: {API_URL}")
    print(f"  Ruta de descarga: {DOWNLOAD_PATH}")
    print(f"  Intervalo de verificación: {CHECK_INTERVAL} minutos")
    print(f"  Servicio: {SERVICE_NAME}")
    print(f"  Modo: Completo (API + WebSocket)")
    
    try:
        # Ejecutar modo completo con API y WebSocket
        asyncio.run(main(USERNAME, PASSWORD))
    except Exception as e:
        logger.critical(f"Error al iniciar la aplicación: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1)
if __name__ == "__main__":
    # Mostrar configuración actual
    print(f"Configuración:")
    print(f"  Servidor: {SERVER_URL}")
    print(f"  API URL: {API_URL}")
    print(f"  Ruta de descarga: {DOWNLOAD_PATH}")
    print(f"  Intervalo de verificación: {CHECK_INTERVAL} minutos")
    print(f"  Servicio: {SERVICE_NAME}")
    print(f"  Modo: {'Sincronización simple' if SYNC_ONLY else 'Completo (API + WebSocket)'}")
    
    try:
        if SYNC_ONLY:
            # Ejecutar modo sincronización simple
            sys.exit(run_sync_only_mode(USERNAME, PASSWORD))
        else:
            # Ejecutar modo completo con API y WebSocket
            asyncio.run(main(USERNAME, PASSWORD))
    except Exception as e:
        logger.critical(f"Error al iniciar la aplicación: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1)
async def websocket_handler(websocket, path):
    """Maneja la conexión WebSocket para streaming de logs."""
    logger.info(f"Cliente conectado vía WebSocket desde {websocket.remote_address}")
    tail_task = None

    try:
        # Función para leer el archivo de log en tiempo real
        async def tail_log():
            try:
                with open('raspberry_client.log', 'r') as f:
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