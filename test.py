import os

def create_play_script(playlist_dir="downloads/"):
    """Crea o actualiza el script play_videos.sh en el directorio de la playlist"""
    script_path = os.path.join(playlist_dir, "play_videos.sh")
    
    # Contenido del script
    script_content = """#!/bin/bash
# Script avanzado para reproducir videos en bucle
# Verifica múltiples reproductores y usa el primero disponible

# Obtener directorio del script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "===== Reproductor de Videos ====="
echo "Directorio: $(pwd)"
echo "Fecha: $(date)"

# Verificar si existe la playlist m3u
if [ ! -f "playlist.m3u" ]; then
    echo "Error: playlist.m3u no encontrada"
    exit 1
fi

# Contar videos en la playlist
NUM_VIDEOS=$(grep -c . playlist.m3u)
echo "Encontrados $NUM_VIDEOS videos en la playlist"

# Mostrar contenido de la playlist
echo "Contenido de playlist.m3u:"
cat playlist.m3u

# Función para verificar si un comando está disponible
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Intentar reproducir con VLC (primera opción)
if command_exists cvlc || command_exists vlc; then
    echo "Usando VLC para reproducción..."

    if command_exists cvlc; then
        echo "Ejecutando: cvlc --loop --no-video-title-show --fullscreen playlist.m3u"
        exec cvlc --loop --no-video-title-show --fullscreen playlist.m3u
    else
        echo "Ejecutando: vlc --loop --no-video-title-show --fullscreen --started-from-file playlist.m3u"
        exec vlc --loop --no-video-title-show --fullscreen --started-from-file playlist.m3u
    fi

# Intentar con MPV
elif command_exists mpv; then
    echo "Usando MPV para reproducción..."
    echo "Ejecutando: mpv --fullscreen --loop-playlist=inf playlist.m3u"
    exec mpv --fullscreen --loop-playlist=inf playlist.m3u

# Intentar con SMPlayer
elif command_exists smplayer; then
    echo "Usando SMPlayer para reproducción..."
    echo "Ejecutando: smplayer -fullscreen -loop playlist.m3u"
    exec smplayer -fullscreen -loop playlist.m3u

# Intentar con OMXPlayer (Raspberry Pi)
elif command_exists omxplayer; then
    echo "Usando OMXPlayer para reproducción (Raspberry Pi)..."
    echo "OMXPlayer no soporta archivos m3u directamente, reproduciendo videos individualmente..."

    while true; do
        while read -r video_path; do
            # Ignorar líneas vacías
            if [ -z "$video_path" ]; then
                continue
            fi

            echo "Reproduciendo: $video_path"
            if [ -f "$video_path" ]; then
                omxplayer -o hdmi --no-osd --no-keys "$video_path"
            else
                echo "Advertencia: El archivo $video_path no existe"
            fi

            # Pequeña pausa entre videos
            sleep 1
        done < playlist.m3u

        echo "Playlist completada, reiniciando..."
        sleep 2
    done

# Intentar con MPlayer
elif command_exists mplayer; then
    echo "Usando MPlayer para reproducción..."
    echo "Ejecutando: mplayer -fs -loop 0 -playlist playlist.m3u"
    exec mplayer -fs -loop 0 -playlist playlist.m3u

else
    echo "Error: No se encontró ningún reproductor de video compatible"
    echo "Por favor, instale VLC, MPV, SMPlayer, OMXPlayer o MPlayer"
    exit 1
fi
"""
    
    # Asegurar que el directorio existe
    os.makedirs(playlist_dir, exist_ok=True)
    
    # Escribir el contenido al archivo con permisos de escritura
    with open(script_path, "w") as f:
        f.write(script_content)
    
    # Hacer el script ejecutable
    os.chmod(script_path, 0o755)  # Equivalente a chmod +x
    
    print(f"Script creado en: {script_path}")
    return script_path

create_play_script()
