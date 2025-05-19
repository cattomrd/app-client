from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from modules.restart_services import restart_service
from fastapi.responses import JSONResponse
import subprocess
import os



router = APIRouter(prefix="/services", 
                tags=["services"],
                responses={404: {"massage": "No encontrado"}}) 


def check_service_status(service_name: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return "running" if result.stdout.strip() == "active" else "stopped"
    except Exception as e:
        return f"error: {str(e)}"


def restart_service(service_name: str) -> str:
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "restart", service_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            return "success"
        else:
            return f"error: {result.stderr.strip()}"
    except Exception as e:
        return f"error: {str(e)}"


# Endpoint para manjar los servicios
@router.get("/{service_name}/{command}")
def get_service_status(service_name,command)  -> str:
    try:
        result = subprocess.run(
            ["sudo", "systemctl", command, service_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            return "success"
        else:
            return f"error: {result.stderr.strip()}"
    except Exception as e:
        return f"error: {str(e)}"
