import socket
from .control_interface import get_interface_ip, get_device_id, get_interface_mac
from .services import check_service
import uuid
import logging
import psutil
import subprocess
import os
import requests
import re
from dotenv import load_dotenv

load_dotenv()


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

def get_device_info():
    """
    Obtiene información del dispositivo para el registro
    """
    hostname = socket.gethostname()
    device_id = get_device_id()
    
    # Obtener modelo de Raspberry Pi
    try:
        with open('/proc/device-tree/model', 'r') as f:
            model = f.read().strip()
    except:
        model = "Raspberry Pi (Unknown Model)"
    
    # Obtener MACs
    eth0_mac = get_interface_mac('eth0')
    wlan0_mac = get_interface_mac('wlan0')
    
    # Obtener IPs
    ip_address_lan = get_interface_ip('eth0')
    ip_address_wifi = get_interface_ip('wlan0')
    
    # Si no hay eth0_mac, usar cualquier otra MAC disponible
    if not eth0_mac:
        eth0_mac = wlan0_mac if wlan0_mac else str(uuid.getnode())
    
    logger.info(f"Información del dispositivo: ID={device_id}, Hostname={hostname}")
    
    return {
        "device_id": device_id,
        "name": hostname,
        "model": model,
        "ip_address_lan": ip_address_lan,
        "ip_address_wifi": ip_address_wifi,
        "mac_address": eth0_mac,
        "wlan0_mac": wlan0_mac,
        "location": "Lab Room"  # Esto podría ser configurado manualmente
    }

def get_rpi_cpu_temperature():
    try:
        temp = subprocess.check_output(['vcgencmd', 'measure_temp']).decode()
        return float(re.search(r'\d+\.\d+', temp).group())
    except Exception as e:
        logger.error(f"Error al obtener temperatura CPU: {str(e)}")
        return 0.0
def get_op_cpu_temperature():
    try:
        # Usando 'cat' para leer el archivo (opcional)
        temp_millicelsius = subprocess.check_output(['cat', '/sys/class/thermal/thermal_zone0/temp']).decode().strip()
        return float(temp_millicelsius) / 1000.00
    except Exception as e:
        logger.error(f"Error al obtener temperatura CPU: {str(e)}")
        return 0.0

def read_service_logs(lines=50):
    """
    Lee los últimos logs del servicio.
    
    Args:
        lines: Número de líneas a leer de cada archivo
    """
    log_paths = [
        "/var/log/raspberry_client.log"
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





def register_device():
    """
    Registra el dispositivo en el servidor
    """
    device_info = get_device_info()
    
    try:
        logger.info(f"Intentando registrar dispositivo: {device_info['device_id']}")
        response = requests.post(API_URL, json=device_info)
        
        if response.status_code == 201:
            logger.info("Dispositivo registrado exitosamente!")
            return True
        elif response.status_code == 400 and "already registered" in response.text:
            logger.info("Dispositivo ya registrado, continuando...")
            return True
        else:
            logger.error(f"Error al registrar dispositivo: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Excepción al registrar dispositivo: {str(e)}")
        return False

def update_status():
    """
    Actualiza el estado del dispositivo en el servidor
    """
    device_id = get_device_id()
    
    try:
        cpu_temp = get_rpi_cpu_temperature()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Obtener IPs actualizadas
        ip_address_lan = get_interface_ip('eth0')
        ip_address_wifi = get_interface_ip('wlan0')
        
        # Obtener MAC de WiFi (puede cambiar si se cambia el adaptador)
        wlan0_mac = get_interface_mac('wlan0')
        
        # Verificar estado de servicios
        videoloop_status = check_service("videoloop")
        kiosk_status = check_service("kiosk")
        
        # Leer los últimos logs
        log_content = read_service_logs()
        
        status_data = {
            "device_id": device_id,
            "cpu_temp": cpu_temp,
            "memory_usage": memory.percent,
            "disk_usage": disk.percent,
            "ip_address_lan": ip_address_lan,
            "ip_address_wifi": ip_address_wifi,
            "wlan0_mac": wlan0_mac,
            "videoloop_status": videoloop_status["status"],
            "kiosk_status": kiosk_status["status"],
            "service_logs": log_content  # Ya limitado a 2000 caracteres en read_service_logs
        }
        
        logger.info(f"Actualizando estado del dispositivo {device_id}")
        response = requests.post(API_URL + "/status", json=status_data)
        
        if response.status_code == 200:
            logger.info("Estado actualizado exitosamente")
            return True
        else:
            logger.error(f"Error al actualizar estado: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Excepción al actualizar estado: {str(e)}")
        return False
