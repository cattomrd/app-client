from dotenv import load_dotenv
import os
import requests
import logging
from typing import Optional, Tuple
from requests.exceptions import RequestException

# Configuración inicial
load_dotenv()
logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip('/')
        self.username = os.getenv("API_USERNAME")  # Mejor nombre para evitar conflictos
        self.password = os.getenv("API_PASSWORD")
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

    def authenticate(self) -> bool:
        """
        Autentica en el servidor y obtiene tokens de acceso
        
        Returns:
            bool: True si la autenticación fue exitosa
        """
        try:
            if not all([self.username, self.password]):
                logger.error("Credenciales no configuradas en variables de entorno")
                return False

            auth_url = f"{self.server_url}/api/auth/login"
            payload = {
                "username": self.username,
                "password": self.password
            }

            response = self.session.post(
                auth_url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            tokens = self._process_auth_response(response)
            if not tokens:
                return False

            self.access_token, self.refresh_token = tokens
            self._update_session_headers()
            logger.info("Autenticación exitosa")
            return True

        except RequestException as e:
            logger.error(f"Error de conexión durante autenticación: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error inesperado durante autenticación: {str(e)}", exc_info=True)
            return False

    def refresh_token(self) -> bool:
        """
        Refresca el token de acceso usando el refresh token
        
        Returns:
            bool: True si el refresh fue exitoso
        """
        try:
            if not self.refresh_token:
                logger.warning("No hay refresh token disponible, intentando autenticación completa")
                return self.authenticate()

            refresh_url = f"{self.server_url}/api/auth/refresh"
            payload = {"refresh_token": self.refresh_token}

            response = self.session.post(
                refresh_url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            tokens = self._process_auth_response(response)
            if not tokens:
                return False

            self.access_token, self.refresh_token = tokens
            self._update_session_headers()
            logger.info("Token refrescado exitosamente")
            return True

        except RequestException as e:
            logger.error(f"Error de conexión al refrescar token: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error inesperado al refrescar token: {str(e)}", exc_info=True)
            return False

    def _process_auth_response(self, response: requests.Response) -> Optional[Tuple[str, str]]:
        """
        Procesa la respuesta de autenticación y extrae los tokens
        
        Args:
            response: Respuesta del servidor
            
        Returns:
            Tuple con (access_token, refresh_token) o None si hay error
        """
        try:
            data = response.json()
            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token") or self.refresh_token  # Mantiene el anterior si no hay nuevo
            
            if not access_token:
                logger.error("La respuesta no contiene access_token")
                return None
                
            return (access_token, refresh_token)
            
        except ValueError as e:
            logger.error(f"Error al decodificar respuesta JSON: {str(e)}")
            return None

    def _update_session_headers(self):
        """Actualiza los headers de la sesión con el token de acceso"""
        if self.access_token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.access_token}"
            })

    def ensure_authentication(self) -> bool:
        """
        Verifica y mantiene una autenticación activa
        
        Returns:
            bool: True si hay autenticación válida
        """
        if self.access_token:
            # Podrías añadir aquí una verificación de token válido si conoces su estructura
            return True
            
        return self.authenticate() or self.refresh_token()