#!/usr/bin/env python3
"""
Script para probar la descarga directa de videos
"""

import requests
import os
import sys
import json
from datetime import datetime

# Configuración
SERVER_URL = "https://gestionpi2.ikeasi.com"
USERNAME = "ikea"
PASSWORD = "Ikea1234"
VIDEO_ID = "218"  # El ID del video que funcionó en tus pruebas
OUTPUT_DIR = "./downloads"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def test_direct_download():
    """Prueba de descarga directa sin autenticación compleja"""
    print("=== Test de descarga directa ===")
    print(f"Intentando descargar video {VIDEO_ID} desde {SERVER_URL}")
    
    # Crear una sesión para mantener cookies
    session = requests.Session()
    
    # Paso 1: Hacer login para obtener cookies
    print("\n1. Iniciando sesión...")
    login_url = f"{SERVER_URL}/login"
    form_data = {
        "username": USERNAME,
        "password": PASSWORD,
        "next": "/"
    }
    
    try:
        login_response = session.post(
            login_url,
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30
        )
        
        print(f"Respuesta de login: {login_response.status_code}")
        print(f"Cookies en la sesión: {dict(session.cookies)}")
        
        if login_response.status_code != 200:
            print(f"Error en login: {login_response.text}")
            return False
    except Exception as e:
        print(f"Error en login: {e}")
        return False
    
    # Paso 2: Intentar descargar el video
    print("\n2. Descargando video...")
    video_url = f"{SERVER_URL}/api/videos/{VIDEO_ID}/download"
    
    try:
        # Intentar la descarga usando la sesión (mantiene las cookies)
        with session.get(video_url, stream=True, timeout=60) as response:
            print(f"Respuesta de descarga: {response.status_code}")
            
            if response.status_code == 200:
                # Extraer información de la respuesta
                content_type = response.headers.get("Content-Type", "")
                content_length = int(response.headers.get("Content-Length", 0))
                
                print(f"Tipo de contenido: {content_type}")
                print(f"Tamaño: {content_length} bytes")
                
                # Guardar el archivo
                output_path = os.path.join(OUTPUT_DIR, f"{VIDEO_ID}.mp4")
                print(f"Guardando en: {output_path}")
                
                with open(output_path, 'wb') as f:
                    total_downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total_downloaded += len(chunk)
                            
                            # Mostrar progreso
                            if content_length > 0:
                                percent = (total_downloaded / content_length) * 100
                                sys.stdout.write(f"\rProgreso: {percent:.1f}%")
                                sys.stdout.flush()
                
                print("\nDescarga completada!")
                print(f"Tamaño del archivo: {os.path.getsize(output_path)} bytes")
                return True
            else:
                print(f"Error en descarga: {response.text}")
                return False
    except Exception as e:
        print(f"Error durante la descarga: {e}")
        return False

if __name__ == "__main__":
    success = test_direct_download()
    
    if success:
        print("\n✓ Prueba exitosa! El video se descargó correctamente.")
    else:
        print("\n✗ Prueba fallida. Revise los errores anteriores.")