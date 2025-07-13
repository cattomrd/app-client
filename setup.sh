#!/bin/bash
# Script para instalar dependencias y configurar el cliente de sincronización

# Colores para mensajes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Definir el directorio de trabajo al inicio
WORKING_DIR=$(pwd)

# Función para imprimir mensajes de estado
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verificar si estamos en una Raspberry Pi
# if ! grep -q "Raspberry Pi" /proc/cpuinfo &> /dev/null; then
#     print_warning "Este script está diseñado para Raspberry Pi. Es posible que algunas funciones no trabajen correctamente en otras plataformas."
# fi

# Comprobar que estamos usando Python 3
PYTHON_VERSION=$(python3 --version 2>&1)
if [[ $? -ne 0 ]]; then
    print_error "Python 3 no está instalado. Por favor, instale Python 3 e intente nuevamente."
    exit 1
fi
print_status "Usando $PYTHON_VERSION"

# Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    print_status "Creando entorno virtual..."
    python3 -m venv venv
    if [[ $? -ne 0 ]]; then
        print_error "No se pudo crear el entorno virtual. Instalando venv..."
        sudo apt-get update
        sudo apt-get install -y python3-venv
        python3 -m venv venv
        if [[ $? -ne 0 ]]; then
            print_error "Error al crear el entorno virtual. Continuando sin él."
        fi
    fi
else
    print_status "El entorno virtual ya existe."
fi

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    print_status "Activando entorno virtual..."
    source venv/bin/activate
fi

# Instalar dependencias
print_status "Instalando dependencias..."
pip install -U pip
<<<<<<< HEAD
venv/bin/pip install -r requirements.txt
=======
pip install -r requirements.txt
>>>>>>> 2e7bc0c (update clien)

# Crear archivo .env si no existe
if [ ! -f ".env" ]; then
    print_status "Creando archivo .env a partir de la plantilla..."
    if [ -f ".env.template" ]; then
        cp .env.template .env
        print_status "Por favor, edite el archivo .env con sus configuraciones:"
        print_status "nano .env"
    else
        print_error "No se encontró el archivo .env.template. Creando un .env básico..."
        cat > .env << EOL
# Configuración del cliente de sincronización
SERVER_URL=http://ipservidor:8000
DOWNLOAD_PATH=$WORKING_DIR/downloads
CHECK_INTERVAL=30
SERVICE_NAME=videoloop.service
USERNAME=user  
PASSWORD=password
SYNC_ONLY=0
DEBUG=0
EOL
        print_status "Archivo .env creado con configuración básica. Por favor, edítelo:"
        print_status "nano .env"
    fi
else
    print_status "El archivo .env ya existe."
fi

# Crear servicio raspberry-sync systemd si no existe
SERVICE_SYNC="/etc/systemd/system/raspberry-sync.service"
if [ ! -f "$SERVICE_SYNC" ]; then
    print_status "¿Desea crear un servicio systemd para raspberry-sync? (s/n)"
    read -r create_sync_service
    
    if [[ "$create_sync_service" =~ ^[Ss]$ ]]; then
        print_status "Creando servicio systemd para raspberry-sync..."
        
        sudo tee "$SERVICE_SYNC" > /dev/null << EOL
[Unit]
Description=Raspberry Pi Video Sync Client
After=network.target

[Service]
User=$(whoami)
WorkingDirectory=$WORKING_DIR
StandardOutput=journal
StandardError=journal
Environment=WAYLAND_DISPLAY=wayland-0
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStart=$WORKING_DIR/venv/bin/python $WORKING_DIR/main.py
Restart=always
Type=simple
User=pi
Group=pi
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOL

        sudo systemctl daemon-reload
        print_status "Servicio raspberry-sync creado. Para habilitarlo, ejecute:"
        print_status "sudo systemctl enable raspberry-sync.service"
        print_status "sudo systemctl start raspberry-sync.service"
    else
        print_status "No se creó el servicio systemd para raspberry-sync."
    fi
else
    print_status "El servicio systemd para raspberry-sync ya existe en $SERVICE_SYNC"
fi

# Crear script videoloop
VIDEOLOOP="/usr/bin/videoloop"
if [ ! -f "$VIDEOLOOP" ]; then
    print_status "¿Desea crear el script videoloop para reproducción de videos? (s/n)"
    read -r create_videoloop
    
    if [[ "$create_videoloop" =~ ^[Ss]$ ]]; then
        print_status "Creando script videoloop..."
        
        sudo tee "$VIDEOLOOP" > /dev/null << EOL
#!/bin/bash
# Script avanzado para reproducir videos en bucle
# Verifica múltiples reproductores y usa el primero disponible

# Directorio de descarga de videos
VIDEO_DIR="/home/pi/app-client/downloads"
echo "===== Reproductor de Videos ====="
echo "Directorio: \$VIDEO_DIR"
echo "Fecha: \$(date)"

# Crear playlist
ls \$VIDEO_DIR | grep mp4 > \$VIDEO_DIR/playlist.m3u

# Verificar si existe la playlist m3u
PLAYLIST_FILE="\$VIDEO_DIR/playlist.m3u"
if [ ! -f "\$PLAYLIST_FILE" ]; then
    echo "Error: \$PLAYLIST_FILE no encontrada"
    exit 1
fi

# Contar videos en la playlist
NUM_VIDEOS=\$(grep -c . "\$PLAYLIST_FILE")
echo "Encontrados \$NUM_VIDEOS videos en la playlist"

# Mostrar contenido de la playlist
echo "Contenido de \$PLAYLIST_FILE:"
cat "\$PLAYLIST_FILE"

# Función para verificar si un comando está disponible
command_exists() {
    command -v "\$1" >/dev/null 2>&1
}

# Intentar reproducir con VLC (primera opción)
if command_exists cvlc || command_exists vlc; then
    echo "Usando VLC para reproducción..."

    if command_exists cvlc; then
        echo "Ejecutando: cvlc --loop --no-video-title-show --fullscreen \$PLAYLIST_FILE"
        exec cvlc --loop --no-video-title-show --fullscreen "\$PLAYLIST_FILE"
    else
        echo "Ejecutando: vlc --loop --no-video-title-show --fullscreen --started-from-file \$PLAYLIST_FILE"
        exec vlc --loop --no-video-title-show --fullscreen --started-from-file "\$PLAYLIST_FILE"
    fi

# Intentar con MPV
elif command_exists mpv; then
    echo "Usando MPV para reproducción..."
    echo "Ejecutando: mpv --fullscreen --loop-playlist=inf \$PLAYLIST_FILE"
    exec mpv --fullscreen --loop-playlist=inf "\$PLAYLIST_FILE"

# Intentar con SMPlayer
elif command_exists smplayer; then
    echo "Usando SMPlayer para reproducción..."
    echo "Ejecutando: smplayer -fullscreen -loop \$PLAYLIST_FILE"
    exec smplayer -fullscreen -loop "\$PLAYLIST_FILE"

# Intentar con OMXPlayer (Raspberry Pi)
elif command_exists omxplayer; then
    echo "Usando OMXPlayer para reproducción (Raspberry Pi)..."
    echo "OMXPlayer no soporta archivos m3u directamente, reproduciendo videos individualmente..."

    while true; do
        while read -r video_path; do
            # Ignorar líneas vacías
            if [ -z "\$video_path" ]; then
                continue
            fi

            echo "Reproduciendo: \$video_path"
            if [ -f "\$video_path" ]; then
                omxplayer -o hdmi --no-osd --no-keys "\$video_path"
            else
                echo "Advertencia: El archivo \$video_path no existe"
            fi

            # Pequeña pausa entre videos
            sleep 1
        done < "\$PLAYLIST_FILE"

        echo "Playlist completada, reiniciando..."
        sleep 2
    done

# Intentar con MPlayer
elif command_exists mplayer; then
    echo "Usando MPlayer para reproducción..."
    echo "Ejecutando: mplayer -fs -loop 0 -playlist \$PLAYLIST_FILE"
    exec mplayer -fs -loop 0 -playlist "\$PLAYLIST_FILE"

else
    echo "Error: No se encontró ningún reproductor de video compatible"
    echo "Por favor, instale VLC, MPV, SMPlayer, OMXPlayer o MPlayer"
    exit 1
fi
EOL

        sudo chmod +x "$VIDEOLOOP"
        sudo chown pi:pi "$VIDEOLOOP"
        print_status "Script videoloop creado en $VIDEOLOOP"
    else
        print_status "No se creó el script videoloop."
    fi
else
    print_status "El script videoloop ya existe en $VIDEOLOOP"
fi

# Crear servicio videoloop systemd si no existe
SERVICE_LOOP="/etc/systemd/system/videoloop.service"
if [ ! -f "$SERVICE_LOOP" ]; then
    print_status "¿Desea crear un servicio systemd para el reproductor de videos? (s/n)"
    read -r create_loop_service
    
    if [[ "$create_loop_service" =~ ^[Ss]$ ]]; then
        print_status "Creando servicio systemd para videoloop..."
        
        sudo tee "$SERVICE_LOOP" > /dev/null << EOL
[Unit]
Description=Video Loop Service
After=graphical.target
Wants=graphical.target

[Service]
Type=simple
User=pi
Group=pi
Environment=WAYLAND_DISPLAY=wayland-0
Environment=XDG_RUNTIME_DIR=/run/user/1000
Environment=XDG_SESSION_TYPE=wayland
Environment=QT_QPA_PLATFORM=wayland
WorkingDirectory=/home/pi
ExecStartPre=/bin/sleep 5
ExecStart=/usr/bin/videoloop
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical.target
EOL

        sudo systemctl daemon-reload
        print_status "Servicio videoloop creado. Para habilitarlo, ejecute:"
        print_status "sudo systemctl enable videoloop.service"
        print_status "sudo systemctl start videoloop.service"
    else
        print_status "No se creó el servicio systemd para videoloop."
    fi
else
    print_status "El servicio systemd para videoloop ya existe en $SERVICE_LOOP"
fi

print_status "Instalación completada."
print_status "Para ejecutar el cliente, use: python main.py"
if [ -d "venv" ]; then
    print_status "Recuerde activar el entorno virtual antes de ejecutar: source venv/bin/activate"
fi
