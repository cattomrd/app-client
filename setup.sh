#!/bin/bash
# Script para instalar dependencias y configurar el cliente de sincronización

# Colores para mensajes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

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
if ! grep -q "Raspberry Pi" /proc/cpuinfo &> /dev/null; then
    print_warning "Este script está diseñado para Raspberry Pi. Es posible que algunas funciones no trabajen correctamente en otras plataformas."
fi

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
pip install python-dotenv websockets fastapi uvicorn

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
SERVER_URL=http://localhost:8000
DOWNLOAD_PATH=~/downloads
CHECK_INTERVAL=30
SERVICE_NAME=videoloop.service
USERNAME=admin
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

# Crear servicio systemd si no existe
SERVICE_FILE="/etc/systemd/system/raspberry-sync.service"
if [ ! -f "$SERVICE_FILE" ]; then
    print_status "¿Desea crear un servicio systemd para iniciar automáticamente el cliente? (s/n)"
    read -r create_service
    
    if [[ "$create_service" =~ ^[Ss]$ ]]; then
        print_status "Creando servicio systemd..."
        WORKING_DIR=$(pwd)
        
        sudo tee "$SERVICE_FILE" > /dev/null << EOL
[Unit]
Description=Raspberry Pi Video Sync Client
After=network.target

[Service]
User=$(whoami)
WorkingDirectory=$WORKING_DIR
ExecStart=$WORKING_DIR/venv/bin/python $WORKING_DIR/main.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOL
        
        sudo systemctl daemon-reload
        print_status "Servicio creado. Para habilitarlo, ejecute:"
        print_status "sudo systemctl enable raspberry-sync.service"
        print_status "sudo systemctl start raspberry-sync.service"
    else
        print_status "No se creó el servicio systemd."
    fi
else
    print_status "El servicio systemd ya existe en $SERVICE_FILE"
fi

print_status "Instalación completada."
print_status "Para ejecutar el cliente, use: python main.py"
if [ -d "venv" ]; then
    print_status "Recuerde activar el entorno virtual antes de ejecutar: source venv/bin/activate"
fi