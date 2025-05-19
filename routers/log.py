from fastapi import APIRouter
import os
import socket
import logging
import re

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
    prefix="/api/logs",
    tags=["logs"]
)
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

@router.get("/")
async def get_logs(lines: int = 100, format: str = "text"):
    """Obtiene los logs del dispositivo."""
    try:
        log_path = "raspberry_client.log"
        if not os.path.exists(log_path):
            if format == "json":
                return {"error": "Archivo de log no encontrado"}
            return "Archivo de log no encontrado"
            
        # Leer las últimas líneas del archivo
        with open(log_path, "r") as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
        if format == "json":
            parsed_logs = []
            for line in last_lines:
                timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                timestamp = timestamp_match.group(1) if timestamp_match else None
                
                device_match = re.search(r'Device\[(\w+)\]', line)
                device_id = device_match.group(1) if device_match else None
                
                parsed_logs.append({
                    "timestamp": timestamp,
                    "device_id": device_id,
                    "message": line.strip()
                })
                
            return {
                "logs": parsed_logs,
                "total": len(parsed_logs),
                "source": log_path
            }
        
        return "".join(last_lines)
    except Exception as e:
        if format == "json":
            return {"error": f"Error al leer logs: {str(e)}"}
        return f"Error al leer logs: {str(e)}"
