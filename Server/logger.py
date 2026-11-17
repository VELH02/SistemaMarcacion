import os
import logging
from logging.handlers import TimedRotatingFileHandler
from collections import deque
from datetime import datetime
from config import LOGS_FOLDER

# Crear carpeta de logs si no existe
os.makedirs(LOGS_FOLDER, exist_ok=True)

# 1. Cola en memoria (200 eventos para visualización en vivo en la web)
console_logs = deque(maxlen=200)

# 2. Configuración del Logger en disco con retención de 31 días (1 mes)
log_file_path = os.path.join(LOGS_FOLDER, "servidor.log")

disk_logger = logging.getLogger("AlicapsaLogger")
disk_logger.setLevel(logging.INFO)

# Evitar duplicar handlers al reiniciar o recargar módulos
if not disk_logger.handlers:
    # Rota a la medianoche (when="midnight"), intervalo de 1 día, conserva 31 copias
    file_handler = TimedRotatingFileHandler(
        filename=log_file_path,
        when="midnight",
        interval=1,
        backupCount=31,
        encoding="utf-8"
    )
    # Formato de sufijo para los archivos archivados (ej: servidor.log.2026-10-16.log)
    file_handler.suffix = "%Y-%m-%d.log"

    # Formato estricto con código de tiempo completo: [AÑO-MES-DIA HORA:MIN:SEG]
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    disk_logger.addHandler(file_handler)

def log_event(ip, evento):
    """
    Registra el evento simultáneamente en:
    1. Memoria (para la consola web en tiempo real).
    2. Terminal/CMD del sistema.
    3. Archivo físico en disco con timestamp completo y rotación mensual.
    """
    ahora = datetime.now()
    
    # Mensaje corto para la pantalla web
    hora_corta = ahora.strftime("%H:%M:%S")
    mensaje_web = f"[{hora_corta}] [IP: {ip}] {evento}"
    console_logs.append(mensaje_web)
    
    # Imprimir en consola de ejecución
    print(mensaje_web)
    
    # Escribir en archivo físico permanente
    disk_logger.info(f"[IP: {ip}] {evento}")