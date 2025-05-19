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
        logging.FileHandler('/var/log/raspberry_client.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(socket.gethostname()) 

router = APIRouter(
    prefix="/api/screenshot",
    tags=["screenshot"]
)
@router.get("/")
async def capture_screenshot():
    """
    Captura una captura de pantalla del dispositivo.
    Intenta diferentes métodos de captura, empezando por grim.
    """
    logger.info("Solicitada captura de pantalla")
    
    # Crear directorio temp si no existe
    temp_dir = "/home/pi/app-client/temp/"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    # Ruta temporal para guardar la captura de pantalla
    screenshot_path = f"{temp_dir}/screenshot_tmp.png"
    screenshot_path_out = f"{temp_dir}/screenshot.png"
    display_target = os.environ.get('DISPLAY')
    try:
        # Primer intento: usar grim (independientemente del entorno)
        capture_success = False
        
        try:
            logger.info("Intentando capturar con grim")
            subprocess.run([
            "grim",
            screenshot_path  
            ], check=True)
            logger.info("Captura con grim exitosa")
            capture_success = True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"Error al capturar con grim: {e}")
        
        # Si grim falló, intentar con otras herramientas
        if not capture_success:
            try:
                logger.info("Intentando capturar con scrot")
                subprocess.run(["scrot", screenshot_path], check=True)
                logger.info("Captura con scrot exitosa")
                capture_success = True
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.warning(f"Error al capturar con scrot: {e}")
        
        # Si scrot falló, intentar con raspi2png
        if not capture_success:
            try:
                logger.info("Intentando capturar con raspi2png")
                subprocess.run(["raspi2png", "-p", screenshot_path], check=True)
                logger.info("Captura con raspi2png exitosa")
                capture_success = True
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.warning(f"Error al capturar con raspi2png: {e}")
        
        # Si raspi2png falló, intentar con fbgrab
        if not capture_success:
            try:
                logger.info("Intentando capturar con fbgrab")
                subprocess.run(["fbgrab", screenshot_path], check=True)
                logger.info("Captura con fbgrab exitosa")
                capture_success = True
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.warning(f"Error al capturar con fbgrab: {e}")
        
        # Si fbgrab falló, intentar con raspistill (específico de Raspberry Pi)
        if not capture_success:
            try:
                logger.info("Intentando capturar con raspistill")
                # raspistill genera JPG, así que usamos un archivo temporal diferente
                jpg_path = f"{temp_dir}/screenshot_tmp.jpg"
                subprocess.run(["raspistill", "-o", jpg_path, "-t", "1"], check=True)
                # Convertir de JPG a PNG usando PIL
                with Image.open(jpg_path) as img:
                    img.save(screenshot_path)
                # Eliminar archivo JPG temporal
                os.remove(jpg_path)
                logger.info("Captura con raspistill exitosa")
                capture_success = True
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.warning(f"Error al capturar con raspistill: {e}")
        
        # Si ningún método funcionó, devolver error
        if not capture_success:
            logger.error("No se pudo capturar la pantalla con ninguna herramienta disponible")
            return JSONResponse(
                status_code=500,
                content={"error": "No se pudo capturar la pantalla. Ninguna herramienta de captura disponible o funcionando."}
            )
        
        # Redimensionar la imagen para reducir tamaño
        try:
            with Image.open(screenshot_path) as img:
                # Redimensionar la imagen conservando la relación de aspecto
                width, height = img.size
                new_width = 640
                new_height = int(height * (new_width / width))
                
                img_resized = img.resize((new_width, new_height), Image.LANCZOS)
                img_resized.save(screenshot_path_out)
                logger.info(f"Imagen redimensionada a {new_width}x{new_height}")
        except Exception as e:
            logger.error(f"Error al redimensionar la imagen: {e}")
            # Si falla el redimensionado, usar la original
            if os.path.exists(screenshot_path):
                os.rename(screenshot_path, screenshot_path_out)
                
        # Leer la imagen y devolverla
        try:
            with open(screenshot_path_out, "rb") as f:
                img_data = f.read()
                logger.info(f"Devolviendo imagen de {len(img_data)} bytes")
                return Response(content=img_data, media_type="image/png")
        except Exception as e:
            logger.error(f"Error al leer la imagen: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Error al leer la imagen: {str(e)}"}
            )
            
    except Exception as e:
        logger.exception(f"Error inesperado en captura de pantalla: {e}")
        return JSONResponse(
            status_code=500, 
            content={"error": f"Error inesperado: {str(e)}"}
        )
    finally:
        # Limpiar archivos temporales
        try:
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
            # No eliminar screenshot_path_out ya que podría ser utilizado en futuras capturas
        except Exception as e:
            logger.warning(f"Error al eliminar archivos temporales: {e}")
