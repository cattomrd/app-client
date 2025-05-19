import logging
import subprocess
import socket, re



logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('raspberry_client.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(socket.gethostname()) 
def get_interface_mac(interface_name):
    """
    Obtiene la dirección MAC de una interfaz específica
    """
    try:
        # Método 1: Usar ip
        result = subprocess.check_output(['ip', 'link', 'show', interface_name]).decode()
        mac_match = re.search(r'link/ether\s+([0-9a-f:]{17})', result)
        if mac_match:
            return mac_match.group(1)
        
        # Método 2: Leer desde /sys
        try:
            with open(f'/sys/class/net/{interface_name}/address', 'r') as f:
                return f.read().strip()
        except:
            pass
        
        # Método 3: Usar ifconfig
        result = subprocess.check_output(['ifconfig', interface_name]).decode()
        mac_match = re.search(r'ether\s+([0-9a-f:]{17})', result)
        if mac_match:
            return mac_match.group(1)
            
        return None
    except Exception as e:
        logger.error(f"Error al obtener MAC de {interface_name}: {str(e)}")
        return None
    



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


def get_interface_ip(interface_name):
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

