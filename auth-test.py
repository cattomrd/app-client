#!/usr/bin/env python3
# test_cookie_auth.py - Script para probar la autenticación con cookies

import os
import sys
import json
import requests
from datetime import datetime, timedelta

# Configuración
SERVER_URL = "https://gestionpi2.ikeasi.com"
USERNAME = "ikea"
PASSWORD = "Ikea1234"

def test_login_and_cookies():
    """Prueba la autenticación y verifica la funcionalidad de las cookies"""
    print(f"Probando login en {SERVER_URL} con usuario {USERNAME}")
    
    # Paso 1: Hacer login para obtener cookies
    login_url = f"{SERVER_URL}/login"
    form_data = {
        "username": USERNAME,
        "password": PASSWORD,
        "next": "/"
    }
    
    try:
        # Crear una sesión para mantener las cookies
        session = requests.Session()
        
        # Hacer login
        login_response = session.post(
            login_url,
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30
        )
        
        print(f"Respuesta de login: {login_response.status_code}")
        print(f"Cookies recibidas: {dict(session.cookies)}")
        
        if login_response.status_code != 200:
            print(f"Error en login: {login_response.text}")
            return False
        
        # Guardar cookies para uso posterior
        all_cookies = {}
        for cookie_name, cookie_value in session.cookies.items():
            all_cookies[cookie_name] = cookie_value
            print(f"Cookie guardada: {cookie_name}={cookie_value}")
        
        if not all_cookies:
            print("No se recibieron cookies en la respuesta")
            return False
        
        # Paso 2: Probar acceso a la API de playlists con las cookies
        print("\nProbando acceso a API de playlists...")
        
        # Primero, intentar sin device_id específico
        api_url = f"{SERVER_URL}/api/raspberry/playlists/active"
        response = session.get(api_url, timeout=30)
        
        print(f"Respuesta de API (sin device_id): {response.status_code}")
        
        # Si falla, probar con un device_id de ejemplo
        if response.status_code != 200:
            #device_id = "dca632104df8"  # Usar el device_id del ejemplo
            api_url = "https://gestionpi2.ikeasi.com/api/raspberry/playlists/active/dca632104df8"
            response = session.get(api_url, timeout=30)
            
            print(f"Respuesta de API (con device_id={device_id}): {response.status_code}")
        
        # Verificar la respuesta
        if response.status_code == 200:
            playlists = response.json()
            print(f"Éxito! Playlists recibidas: {len(playlists)}")
            
            # Si hay playlists, intentar descargar un video
            if playlists:
                print("\nProbando descarga de video...")
                first_playlist = playlists[0]
                print(f"Playlist encontrada: {first_playlist['title']} (ID: {first_playlist['id']})")
                
                if first_playlist.get("videos"):
                    video = first_playlist["videos"][0]
                    video_id = video["id"]
                    
                    # Probar ambas posibles URLs
                    urls_to_try = [
                        # f"{SERVER_URL}/api/public/videos/{video_id}/download",
                        f"{SERVER_URL}/api/videos/218/download"
                    ]
                    
                    for url in urls_to_try:
                        print(f"Intentando descargar video {video_id} desde {url}")
                        
                        try:
                            # Usar stream=True para no descargar todo el contenido
                            video_response = session.get(url, stream=True, timeout=30)
                            
                            print(f"Respuesta: {video_response.status_code}")
                            
                            if video_response.status_code == 200:
                                # Obtener tamaño y tipo de contenido
                                content_type = video_response.headers.get("Content-Type", "")
                                content_length = video_response.headers.get("Content-Length", "")
                                
                                print(f"Tipo de contenido: {content_type}")
                                print(f"Tamaño: {content_length} bytes")
                                
                                # Descargar solo los primeros 1024 bytes para verificar
                                chunk = next(video_response.iter_content(chunk_size=1024), None)
                                
                                if chunk:
                                    print(f"Descarga iniciada correctamente!")
                                    print(f"URL funcional: {url}")
                                    return True
                        except Exception as e:
                            print(f"Error al probar URL {url}: {e}")
                    
                    print("Ninguna URL de descarga funcionó")
                else:
                    print("No hay videos en la playlist")
            else:
                print("No se encontraron playlists")
        else:
            print(f"Error accediendo a la API: {response.text}")
        
        return False
    
    except Exception as e:
        print(f"Error en la prueba: {e}")
        return False

if __name__ == "__main__":
    print("=== Prueba de autenticación con cookies ===")
    
    success = test_login_and_cookies()
    
    if success:
        print("\n✓ Prueba exitosa! La autenticación con cookies funciona correctamente.")
    else:
        print("\n✗ Prueba fallida. Revise los errores anteriores.")