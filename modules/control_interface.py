import logging
import subprocess
import socket, re
import uuid
import os
import platform

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('raspberry_client.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(socket.gethostname()) 


def get_interface_mac(interface: str = "eth0") -> str:
    """
    Obtiene la dirección MAC de una interfaz de red de forma segura
    
    Args:
        interface: Nombre de la interfaz (eth0, wlan0, etc.)
    
    Returns:
        str: Dirección MAC o string vacío si no se puede obtener
    """
    try:
        # Método 1: Leer desde /sys/class/net
        mac_file = f"/sys/class/net/{interface}/address"
        if os.path.exists(mac_file):
            with open(mac_file, 'r') as f:
                mac = f.read().strip()
                if mac and mac != "00:00:00:00:00:00":
                    return mac.lower()
        
        # Método 2: Usar comando ip
        result = subprocess.run(['ip', 'link', 'show', interface], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'link/ether' in line:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        mac = parts[1]
                        if mac and mac != "00:00:00:00:00:00":
                            return mac.upper()
        
        # Método 3: Usar ifconfig (fallback)
        result = subprocess.run(['ifconfig', interface], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            import re
            mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', result.stdout)
            if mac_match:
                mac = mac_match.group(0)
                if mac and mac != "00:00:00:00:00:00":
                    return mac.upper()
                    
    except Exception as e:
        logger.warning(f"Error al obtener MAC de {interface}: {e}")
    
    # Retornar string vacío por defecto (nunca None)
    return ""



def get_device_id():
    """
    Obtiene un ID de dispositivo consistente basado en la MAC de eth0
    """
    mac = get_interface_mac('eth0')
    if not mac:
        # Si no se puede obtener la MAC de eth0, usar la de wlan0 o generar un ID único
        mac = get_interface_mac('wlan0')
        if not mac:
            logger.warning("No se pudo obtener MAC de ninguna interfaz, generando ID único")
            return f"unknown-{str(uuid.uuid4())[:8]}"
    
    return mac.replace(":", "")


def get_interface_ip(interface_name) -> str:
    """
    Obtiene la dirección IP de una interfaz específica
    """
    try:
        # Ejecuta el comando para obtener la dirección IP
        result = subprocess.run(
            ["ip", "address", "show", interface_name],
            capture_output=True,
            text=True,
            check=True
        )
        # Busca la dirección IP en la salida
        for line in result.stdout.splitlines():
            if "inet " in line:
                # Extrae la dirección IP antes del símbolo "/"
                ip_address = line.split()[1].split("/")[0]
                logger.info(f"Dirección IP de {interface_name}: {ip_address}")
                return ip_address
    except subprocess.CalledProcessError:
        logger.error(f"Error al obtener IP de {interface_name}: Comando fallido")
    except IndexError:
        logger.error(f"Error al obtener IP de {interface_name}: Formato inesperado")
    except Exception as e:
        logger.error(f"Error al obtener IP de {interface_name}: {str(e)}")
    
    return None

def get_tienda(ip):
    """
    Versión compacta que retorna diferentes códigos según los primeros octetos de la IP
    
    Args:
        ip: Dirección IP (puede ser None)
    
    Returns:
        str o None: Código de tienda correspondiente o None si no se puede determinar
    """
    # Verificar que ip no sea None antes de usar startswith()
    if ip is None:
        logger.warning("IP es None, no se puede determinar la tienda")
        return None
    
    if ip.startswith("172.19.14."):
        return "SDQ"
    elif ip.startswith("192.168.36"):
        return "SDQ"
    elif ip.startswith("172.30.42."):
        return "STI"
    elif ip.startswith("172.30.43."):  # Corregido: era duplicado
        return "PUJ"
    elif ip.startswith("172.50.42."):
        return "LRM"
    else:
        logger.info(f"IP {ip} no coincide con ninguna tienda conocida")
        return None


def get_device_model() -> str:
    """
    Obtiene el modelo del dispositivo de forma segura.
    Primero intenta detectar Raspberry Pi, y si no lo logra, intenta detectar Orange Pi.

    Returns:
        str: Modelo del dispositivo o string vacío si no se puede determinar
    """
    # Variable para almacenar el modelo detectado
    model = ""

    # Intentar obtener el modelo desde /proc/device-tree/model (Raspberry Pi)
    if os.path.exists('/proc/device-tree/model'):
        with open('/proc/device-tree/model', 'r') as f:
            model = f.read().strip('\x00').strip()
            if model:
                return model

    # Intentar obtener desde /proc/cpuinfo
    if os.path.exists('/proc/cpuinfo'):
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()

            # Detectar Raspberry Pi
            if 'Raspberry Pi' in cpuinfo:
                for line in cpuinfo.splitlines():
                    if line.startswith('Model'):
                        model = line.split(':', 1)[1].strip()
                        if model:
                            return model
            
            # Detectar Orange Pi
            elif 'H3' in cpuinfo or 'H2+' in cpuinfo or 'Orange Pi' in cpuinfo:
                for line in cpuinfo.splitlines():
                    if line.startswith('Hardware'):
                        model = line.split(':', 1)[1].strip()
                        if model:
                            return f"Orange Pi ({model})"
                    elif line.startswith('Model'):
                        model = line.split(':', 1)[1].strip()
                        if model:
                            return f"Orange Pi ({model})"

    # Fallback a platform.machine()
    machine = platform.machine()
    if machine:
        return f"Platform: {machine}"

    return ""
            
    except Exception as e:
        logger.warning(f"Error al obtener modelo del dispositivo: {e}")
    
    # Retornar string vacío por defecto (nunca None)
    return ""

def get_cpu_temperature():
    """Obtiene la temperatura de la CPU"""
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp = int(f.read()) / 1000
            return round(temp, 1)
    except:
        return 0.0

def get_memory_usage():
    """Obtiene el porcentaje de uso de memoria"""
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
            
        mem_total = mem_free = mem_available = 0
        for line in lines:
            if line.startswith('MemTotal:'):
                mem_total = int(line.split()[1])
            elif line.startswith('MemFree:'):
                mem_free = int(line.split()[1])
            elif line.startswith('MemAvailable:'):
                mem_available = int(line.split()[1])
        
        if mem_total > 0:
            used = mem_total - (mem_available if mem_available > 0 else mem_free)
            return round((used / mem_total) * 100, 1)
    except:
        pass
    return 0.0

def get_disk_usage():
    """Obtiene el porcentaje de uso del disco"""
    try:
        import shutil
        total, used, free = shutil.disk_usage('/')
        return round((used / total) * 100, 1)
    except:
        return 0.0
