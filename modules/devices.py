import socket
from modules.control_interface import get_device_id, get_interface_ip, get_tienda, get_interface_mac, get_device_model, get_memory_usage, get_cpu_temperature, get_disk_usage
from modules.services import check_service
import uuid
import logging
import psutil
import subprocess
import os
import requests
import re
import ssl
import certifi
import os
import socket
from dotenv import load_dotenv
import datetime

load_dotenv()

# Configuración para SSL
VERIFY_SSL = os.getenv("VERIFY_SSL", "True").lower() != "false"
SSL_CERT_PATH = os.getenv("SSL_CERT_PATH", None)  # Ruta a un certificado personalizado, si existe

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('raspberry_client.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(socket.gethostname()) 
API_URL = os.getenv("SERVER_URL") + "/api/devices"


def read_service_logs(lines=50):
    """
    Lee los últimos logs del servicio.
    
    Args:
        lines: Número de líneas a leer de cada archivo
    """
    log_paths = [
        "raspberry_client.log"
    ]
    
    combined_logs = ""
    
    for log_path in log_paths:
        try:
            if os.path.exists(log_path):
                # Leer las últimas líneas de cada archivo de log
                with os.popen(f"tail -n {lines} {log_path}") as f:
                    log_content = f.read()
                    combined_logs += f"\n--- {log_path} ---\n{log_content}\n"
        except Exception as e:
            logger.error(f"Error al leer log {log_path}: {str(e)}")
    
    # Limitar el tamaño total de los logs
    max_log_size = 2000
    if len(combined_logs) > max_log_size:
        combined_logs = "...(truncado)...\n" + combined_logs[-max_log_size:]
    
    return combined_logs or "No se encontraron logs disponibles"

def get_device_info():
    """
    Obtiene información del dispositivo para el registro
    """

        # Obtener datos del dispositivo
    hostname = socket.gethostname()
    device_id = get_device_id()
    model = get_device_model()
    
    # Obtener MACs
    eth0_mac = get_interface_mac('eth0')
    wlan0_mac = get_interface_mac('wlan0')
    
    # Obtener IPs
    ip_address_lan = get_interface_ip('eth0')
    ip_address_wifi = get_interface_ip('wlan0')
    
    # Si no hay eth0_mac, usar cualquier otra MAC disponible
    if not eth0_mac:
        eth0_mac = wlan0_mac if wlan0_mac else str(uuid.getnode())
    tienda_id = get_tienda(ip_address_lan)

    logger.info(f"Información del dispositivo: ID={device_id}, Hostname={hostname}")
    
    return {
        "device_id": device_id,
        "name": hostname,
        "model": model,
        "ip_address_lan": ip_address_lan,
        "ip_address_wifi": ip_address_wifi,
        "mac_address": eth0_mac,
        "wlan0_mac": wlan0_mac,
        "location": tienda_id,
        "tienda": tienda_id
    }


### REGISTRAR TERMINAL ###
def register_device(verify_ssl=True):
    """
    Registra el dispositivo en el servidor manejando valores None correctamente
    
    Args:
        verify_ssl: Si verificar certificados SSL
    
    Returns:
        bool: True si el registro fue exitoso
    """
    try:
        # Obtener datos del dispositivo
        device_id = get_device_id()
        if not device_id:
            logger.error("No se pudo obtener device_id")
            return False
        hostname = socket.gethostname()

        # Obtener modelo y MAC de forma segura (nunca None)
        model = get_device_model()  # Siempre retorna string
        mac_address = get_interface_mac("eth0")  # Siempre retorna string
        wlan0_mac = get_interface_mac("wlan0")  # Siempre retorna string
        
        # Obtener información de red
        ip_lan = get_interface_ip("eth0")
        ip_wifi = get_interface_ip("wlan0")
        
        # Obtener tienda/ubicación
        tienda = get_tienda(ip_lan) or get_tienda(ip_wifi)
        
        # Preparar datos del dispositivo asegurando que nunca haya valores None
        device_data = {
            "device_id": device_id.lower(),
            "name": hostname,
            'model': model if model else "player",  # Convertir None a string vacío
            "mac_address": mac_address,
            "wlan0_mac": wlan0_mac,
            "ip_address_lan": ip_lan if ip_lan else None,
            "ip_address_wifi": ip_wifi if ip_wifi else None,            
            "location": tienda,
            "tienda": tienda,
            "is_active": True,
            "videoloop_enabled": True,
            "kiosk_enabled": False,
            "service_logs": "string"
        }
        
        # Limpiar campos None para campos que no pueden ser None en el esquema
        cleaned_data = {}
        for key, value in device_data.items():
            if key in ["model"] and value is None:
                cleaned_data[key] = ""  # Convertir None a string vacío para campos requeridos
            else:
                cleaned_data[key] = value
        
        # Log de información para debug
        logger.info(f"Registrando dispositivo {device_id}")
        logger.info(f"Modelo: '{model}' (length: {len(model)})")
        logger.info(f"MAC eth0: '{mac_address}' (length: {len(mac_address)})")
        logger.info(f"MAC wlan0: '{wlan0_mac}' (length: {len(wlan0_mac)})")
        
        # Realizar petición al servidor
        SERVER_URL = os.getenv("SERVER_URL")
        logger.info(f"Registrando dispositivo en {SERVER_URL}/api/devices/register")
        response = requests.post(
            f"{SERVER_URL}/api/devices/register",
            json=cleaned_data,
            timeout=30,
            verify=verify_ssl
        )
        
        if response.status_code == 200:
            logger.info(f"Dispositivo {device_id} registrado exitosamente")
            return True
        elif response.status_code == 400:
            error_detail = response.json().get("detail", "Error desconocido")
            if "already registered" in error_detail:
                logger.info(f"Dispositivo {device_id} ya estaba registrado")
                return True
            else:
                logger.error(f"Error de validación al registrar dispositivo: {error_detail}")
                return False
        else:
            logger.error(f"Error al registrar dispositivo: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error durante el registro del dispositivo: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def update_status(verify_ssl=True):
    """
    Actualiza el estado del dispositivo con el formato correcto que espera el servidor
    
    Args:
        verify_ssl: Si verificar certificados SSL
    
    Returns:
        bool: True si la actualización fue exitosa
    """
    try:
        device_id = get_device_id()
        if not device_id:
            logger.error("No se pudo obtener device_id para actualización de estado")
            return False
        
        # Obtener métricas del sistema
        cpu_temp = get_cpu_temperature()
        memory_usage = get_memory_usage()
        disk_usage = get_disk_usage()
        
        # Obtener estados de servicios (solo el valor de estado, no el objeto completo)
        videoloop_status = check_service("videoloop.service").get("status", "unknown")
        kiosk_status = check_service("kiosk.service").get("status", "unknown")
        
        # Convertir estados para compatibilidad con el API
        status_mapping = {
            "up": "running",
            "down": "stopped",
            "active": "running",
            "inactive": "stopped"
        }
        
        videoloop_status = status_mapping.get(videoloop_status.lower(), videoloop_status)
        kiosk_status = status_mapping.get(kiosk_status.lower(), kiosk_status)
        
        # Obtener IPs actuales
        ip_lan = get_interface_ip("eth0")
        ip_wifi = get_interface_ip("wlan0")
        
        # Preparar datos de estado en el formato correcto
        status_data = {
            "device_id": device_id,
            "ip_address_lan": ip_lan if ip_lan else None,
            "ip_address_wifi": ip_wifi if ip_wifi else None, 
            "cpu_temp": round(cpu_temp, 2) if cpu_temp is not None else None,
            "memory_usage": round(memory_usage, 2) if memory_usage is not None else None,
            "disk_usage": round(disk_usage, 2) if disk_usage is not None else None,
            "videoloop_status": videoloop_status,  # Solo el string (ej: "running")
            "kiosk_status": kiosk_status,          # Solo el string (ej: "stopped")
            "last_heartbeat": datetime.datetime.utcnow().isoformat() + "Z"
        }
        
        # Limpieza de valores None para campos requeridos
        cleaned_data = {k: v for k, v in status_data.items() if v is not None}
        
        logger.debug(f"Datos de estado preparados: {cleaned_data}")
        
        # Realizar petición al servidor
        SERVER_URL = os.getenv("SERVER_URL")
        if not SERVER_URL:
            logger.error("SERVER_URL no está configurado")
            return False
            
        response = requests.post(
            f"{SERVER_URL.rstrip('/')}/api/devices/status",
            json=cleaned_data,
            timeout=30,
            verify=verify_ssl
        )
        
        if response.status_code == 200:
            logger.info(f"Estado del dispositivo {device_id} actualizado exitosamente")
            return True
        elif response.status_code == 422:
            logger.error(f"Error de validación al actualizar estado: {response.json()}")
            return False
        else:
            logger.error(f"Error al actualizar estado: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión durante actualización de estado: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado durante actualización de estado: {str(e)}", exc_info=True)
        return False