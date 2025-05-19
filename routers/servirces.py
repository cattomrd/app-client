from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
import os
import subprocess
import socket
import logging
from PIL import Image


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
    prefix="/api/services",
    tags=["services"]
)


@router.post("/services")
def manager_service(service_name, service_option) -> str:
    try:
        result = subprocess.run(
            ["sudo", "systemctl", service_option, service_name], check=True,
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