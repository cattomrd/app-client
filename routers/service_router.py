from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
import subprocess
import logging
import asyncio
import os

# Configuración del logger
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/services",
    tags=["services"],
    responses={404: {"message": "No encontrado"}}
)

# Lista de servicios permitidos
ALLOWED_SERVICES = ['videoloop', 'kiosk']

# Función mejorada para verificar el estado de un servicio
def check_service_status(service_name: str) -> str:
    """
    Verifica si un servicio está activo o detenido
    
    Args:
        service_name (str): Nombre del servicio a verificar
        
    Returns:
        str: Estado del servicio ('running', 'stopped', o mensaje de error)
    """
    if service_name not in ALLOWED_SERVICES:
        logger.warning(f"Intento de verificar servicio no permitido: {service_name}")
        return f"error: servicio {service_name} no permitido"
        
    try:
        logger.info(f"Verificando estado del servicio {service_name}")
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        status = "running" if result.stdout.strip() == "active" else "stopped"
        logger.info(f"Estado del servicio {service_name}: {status}")
        return status
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout al verificar estado del servicio {service_name}")
        return f"error: timeout al verificar estado"
    except Exception as e:
        logger.error(f"Error al verificar estado del servicio {service_name}: {str(e)}")
        return f"error: {str(e)}"

# Función para verificar si un servicio está habilitado
def check_service_enabled(service_name: str) -> str:
    """
    Verifica si un servicio está habilitado para iniciar automáticamente
    
    Args:
        service_name (str): Nombre del servicio a verificar
        
    Returns:
        str: 'enabled', 'disabled', o mensaje de error
    """
    if service_name not in ALLOWED_SERVICES:
        logger.warning(f"Intento de verificar servicio no permitido: {service_name}")
        return f"error: servicio {service_name} no permitido"
        
    try:
        logger.info(f"Verificando si el servicio {service_name} está habilitado")
        result = subprocess.run(
            ["systemctl", "is-enabled", service_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        enabled_status = result.stdout.strip()
        logger.info(f"Estado de habilitación del servicio {service_name}: {enabled_status}")
        return enabled_status  # Devuelve 'enabled' o 'disabled' directamente
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout al verificar si el servicio {service_name} está habilitado")
        return f"error: timeout al verificar estado de habilitación"
    except Exception as e:
        logger.error(f"Error al verificar si el servicio {service_name} está habilitado: {str(e)}")
        return f"error: {str(e)}"

# Función para gestionar un servicio (start, stop, restart, enable, disable)
def manage_service(service_name: str, action: str) -> str:
    """
    Ejecuta una acción en un servicio
    
    Args:
        service_name (str): Nombre del servicio a gestionar
        action (str): Acción a realizar ('start', 'stop', 'restart', 'enable', 'disable')
        
    Returns:
        str: 'success' si la acción se completó correctamente, o mensaje de error
    """
    if service_name not in ALLOWED_SERVICES:
        logger.warning(f"Intento de gestionar servicio no permitido: {service_name}")
        return f"error: servicio {service_name} no permitido"
    
    valid_actions = ['start', 'stop', 'restart', 'enable', 'disable']
    if action not in valid_actions:
        logger.warning(f"Acción no válida: {action}")
        return f"error: acción {action} no válida"
    
    try:
        logger.info(f"Ejecutando {action} en el servicio {service_name}")
        
        # Usar sudo si es necesario
        cmd = ["sudo", "systemctl", action, service_name]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15  # Mayor timeout para operaciones de servicio
        )
        
        if result.returncode == 0:
            logger.info(f"Acción {action} completada correctamente en el servicio {service_name}")
            return "success"
        else:
            error_msg = result.stderr.strip()
            logger.error(f"Error al ejecutar {action} en {service_name}: {error_msg}")
            return f"error: {error_msg}"
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout al ejecutar {action} en el servicio {service_name}")
        return f"error: timeout al ejecutar {action}"
    except Exception as e:
        logger.error(f"Error al ejecutar {action} en el servicio {service_name}: {str(e)}")
        return f"error: {str(e)}"

# Endpoint para verificar el estado de un servicio
@router.get("/{service_name}/status", response_class=PlainTextResponse)
def get_service_status(service_name: str):
    """
    Verifica y devuelve el estado de un servicio
    
    Args:
        service_name (str): Nombre del servicio a verificar
        
    Returns:
        PlainTextResponse: Estado del servicio ('running', 'stopped', o error)
    """
    if service_name not in ALLOWED_SERVICES:
        return PlainTextResponse(f"error: servicio {service_name} no permitido", status_code=400)
    
    status = check_service_status(service_name)
    return PlainTextResponse(status)

# Endpoint para verificar si un servicio está habilitado
@router.get("/{service_name}/is-enabled", response_class=PlainTextResponse)
def get_service_enabled(service_name: str):
    """
    Verifica y devuelve si un servicio está habilitado para inicio automático
    
    Args:
        service_name (str): Nombre del servicio a verificar
        
    Returns:
        PlainTextResponse: Estado de habilitación ('enabled', 'disabled', o error)
    """
    if service_name not in ALLOWED_SERVICES:
        return PlainTextResponse(f"error: servicio {service_name} no permitido", status_code=400)
    
    enabled = check_service_enabled(service_name)
    return PlainTextResponse(enabled)

# Endpoint para iniciar un servicio
@router.get("/{service_name}/start", response_class=PlainTextResponse)
def start_service(service_name: str):
    """
    Inicia un servicio
    
    Args:
        service_name (str): Nombre del servicio a iniciar
        
    Returns:
        PlainTextResponse: 'success' o mensaje de error
    """
    if service_name not in ALLOWED_SERVICES:
        return PlainTextResponse(f"error: servicio {service_name} no permitido", status_code=400)
    
    result = manage_service(service_name, "start")
    status_code = 200 if result == "success" else 500
    return PlainTextResponse(result, status_code=status_code)

# Endpoint para detener un servicio
@router.get("/{service_name}/stop", response_class=PlainTextResponse)
def stop_service(service_name: str):
    """
    Detiene un servicio
    
    Args:
        service_name (str): Nombre del servicio a detener
        
    Returns:
        PlainTextResponse: 'success' o mensaje de error
    """
    if service_name not in ALLOWED_SERVICES:
        return PlainTextResponse(f"error: servicio {service_name} no permitido", status_code=400)
    
    result = manage_service(service_name, "stop")
    status_code = 200 if result == "success" else 500
    return PlainTextResponse(result, status_code=status_code)

# Endpoint para reiniciar un servicio
@router.get("/{service_name}/restart", response_class=PlainTextResponse)
def restart_service(service_name: str):
    """
    Reinicia un servicio
    
    Args:
        service_name (str): Nombre del servicio a reiniciar
        
    Returns:
        PlainTextResponse: 'success' o mensaje de error
    """
    if service_name not in ALLOWED_SERVICES:
        return PlainTextResponse(f"error: servicio {service_name} no permitido", status_code=400)
    
    result = manage_service(service_name, "restart")
    status_code = 200 if result == "success" else 500
    return PlainTextResponse(result, status_code=status_code)

# Endpoint para habilitar un servicio
@router.get("/{service_name}/enable", response_class=PlainTextResponse)
def enable_service(service_name: str):
    """
    Habilita un servicio para inicio automático
    
    Args:
        service_name (str): Nombre del servicio a habilitar
        
    Returns:
        PlainTextResponse: 'success' o mensaje de error
    """
    if service_name not in ALLOWED_SERVICES:
        return PlainTextResponse(f"error: servicio {service_name} no permitido", status_code=400)
    
    result = manage_service(service_name, "enable")
    status_code = 200 if result == "success" else 500
    return PlainTextResponse(result, status_code=status_code)

# Endpoint para deshabilitar un servicio
@router.get("/{service_name}/disable", response_class=PlainTextResponse)
def disable_service(service_name: str):
    """
    Deshabilita un servicio para inicio automático
    
    Args:
        service_name (str): Nombre del servicio a deshabilitar
        
    Returns:
        PlainTextResponse: 'success' o mensaje de error
    """
    if service_name not in ALLOWED_SERVICES:
        return PlainTextResponse(f"error: servicio {service_name} no permitido", status_code=400)
    
    result = manage_service(service_name, "disable")
    status_code = 200 if result == "success" else 500
    return PlainTextResponse(result, status_code=status_code)

# Endpoint general para realizar cualquier acción en un servicio
@router.get("/{service_name}/{action}", response_class=PlainTextResponse)
def service_action(service_name: str, action: str):
    """
    Ejecuta una acción en un servicio
    
    Args:
        service_name (str): Nombre del servicio a gestionar
        action (str): Acción a realizar (start, stop, restart, enable, disable, status, is-enabled)
        
    Returns:
        PlainTextResponse: Resultado de la acción
    """
    if service_name not in ALLOWED_SERVICES:
        return PlainTextResponse(f"error: servicio {service_name} no permitido", status_code=400)
    
    # Manejar acciones especiales primero
    if action == "status":
        return get_service_status(service_name)
    elif action == "is-enabled":
        return get_service_enabled(service_name)
    
    # Para las demás acciones, usar la función general
    valid_actions = ['start', 'stop', 'restart', 'enable', 'disable']
    if action not in valid_actions:
        return PlainTextResponse(f"error: acción {action} no válida", status_code=400)
    
    result = manage_service(service_name, action)
    status_code = 200 if result == "success" else 500
    return PlainTextResponse(result, status_code=status_code)

# Endpoint para obtener detalles completos de un servicio
@router.get("/{service_name}")
def get_service_details(service_name: str):
    """
    Obtiene información detallada sobre un servicio
    
    Args:
        service_name (str): Nombre del servicio
        
    Returns:
        JSONResponse: Información detallada del servicio
    """
    if service_name not in ALLOWED_SERVICES:
        return JSONResponse(
            {"error": f"Servicio {service_name} no permitido"},
            status_code=400
        )
    
    # Obtener estado actual
    status = check_service_status(service_name)
    is_running = status == "running"
    
    # Obtener si está habilitado
    enabled = check_service_enabled(service_name)
    is_enabled = enabled == "enabled"
    
    # Obtener información detallada si está disponible
    details = {}
    try:
        result = subprocess.run(
            ["systemctl", "show", service_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # Procesar la salida como un diccionario
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    details[key] = value
    except Exception as e:
        logger.error(f"Error al obtener detalles del servicio {service_name}: {str(e)}")
    
    # Construir respuesta
    response = {
        "name": service_name,
        "status": status,
        "is_running": is_running,
        "enabled": enabled,
        "is_enabled": is_enabled,
        "details": details
    }
    
    return JSONResponse(response)

router.get("/services/status", response_class=JSONResponse)
def get_all_services_status():
    """
    Obtiene el estado de todos los servicios monitoreados
    
    Returns:
        JSONResponse: Estado de todos los servicios disponibles
    """
    result = {}
    
    for service_name in ALLOWED_SERVICES:
        try:
            # Obtener estado
            status = check_service_status(service_name)
            
            # Obtener información de habilitación
            enabled = check_service_enabled(service_name)
            
            # Añadir al resultado
            result[service_name] = {
                "status": status,
                "enabled": enabled,
                "is_running": status == "running",
                "is_enabled": enabled == "enabled"
            }
            
            # Intentar obtener información adicional si está disponible
            try:
                info_cmd = ["systemctl", "show", service_name, "--property=ActiveState,UnitFileState,Description"]
                info_result = subprocess.run(
                    info_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=2
                )
                
                if info_result.returncode == 0:
                    info = {}
                    for line in info_result.stdout.strip().split('\n'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            info[key] = value
                    
                    result[service_name]["info"] = info
            except Exception as e:
                logger.warning(f"No se pudo obtener información adicional de {service_name}: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error al obtener estado de {service_name}: {str(e)}")
            result[service_name] = {
                "status": "error",
                "enabled": "unknown",
                "error": str(e)
            }
    
    return JSONResponse(result)