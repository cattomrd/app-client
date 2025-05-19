import subprocess
import platform
import psutil
import logging
import socket
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('raspberry_client.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('socket.gethostname())')


def check_service(service_name: str) -> dict:
    """Comprueba el estado de un servicio."""
    status = "unknown"
    port = None
    additional_info = {}

    # Verificar si el servicio está en ejecución
    try:
        if platform.system() == "Linux":
            result = subprocess.run(["systemctl", "is-active", service_name], capture_output=True, text=True)
            status = "up" if result.stdout.strip() == "active" else "down"
        elif platform.system() == "Windows":
            result = subprocess.run(["sc", "query", service_name], capture_output=True, text=True)
            status = "up" if "RUNNING" in result.stdout else "down"
        
        # Convertir estado para servicios específicos para que sea compatible con el modelo
        if service_name in ["videoloop", "kiosk"]:
            status = "running" if status == "up" else "stopped"
        
        # Obtener puerto para servicios comunes
        if service_name == "nginx" and status == "up":
            for conn in psutil.net_connections(kind='inet'):
                if conn.status == 'LISTEN' and conn.laddr.port in [80, 443]:
                    port = conn.laddr.port
                    break
        elif service_name == "mysql" and status == "up":
            for conn in psutil.net_connections(kind='inet'):
                if conn.status == 'LISTEN' and conn.laddr.port == 3306:
                    port = conn.laddr.port
                    break
    except Exception as e:
        logger.error(f"Error al verificar servicio {service_name}: {str(e)}")
        status = "unknown"

    return {
        "name": service_name,
        "status": status,
        "port": port,
        "additional_info": additional_info
    }
    

    