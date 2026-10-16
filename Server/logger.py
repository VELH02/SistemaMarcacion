from collections import deque
from datetime import datetime

# Cola en memoria para los últimos 200 eventos
console_logs = deque(maxlen=200)

def log_event(ip, evento):
    """Registra eventos con hora e IP para la consola del Administrador"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    mensaje = f"[{timestamp}] [IP: {ip}] {evento}"
    console_logs.append(mensaje)
    print(mensaje)