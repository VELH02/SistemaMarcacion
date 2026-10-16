import socket
import struct
import time
from datetime import datetime, timedelta

# Variables globales de desfase de tiempo
ntp_offset = 0.0
ultimo_sync = None
estado_sync = "Sin sincronizar"

def sincronizar_ntp(host="pool.ntp.org"):
    """Consulta un servidor NTP en el puerto UDP 123 y calcula el desfase con la máquina local"""
    global ntp_offset, ultimo_sync, estado_sync
    host = host.strip() if host else "pool.ntp.org"
    
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(3.0)
        # Paquete NTP estándar de 48 bytes (Modo cliente)
        data = b'\x1b' + 47 * b'\0'
        client.sendto(data, (host, 123))
        data, _ = client.recvfrom(1024)
        
        if data:
            # Desempaquetar marca de tiempo de transmisión (bytes 40-44)
            t_ntp = struct.unpack("!12I", data)[10]
            # Convertir de época 1900 a época Unix 1970
            t_unix = t_ntp - 2208988800
            
            t_local = time.time()
            ntp_offset = t_unix - t_local
            ultimo_sync = datetime.now()
            estado_sync = f"Sincronizado con {host} (Offset: {ntp_offset:+.2f}s)"
            return True, estado_sync
    except Exception as e:
        estado_sync = f"Error al conectar con {host}: {e}"
        return False, estado_sync

def get_current_time():
    """Retorna un datetime ajustado con la hora oficial del servidor NTP"""
    return datetime.now() + timedelta(seconds=ntp_offset)

def get_time_str(fmt="%Y-%m-%d %H:%M:%S"):
    """Retorna la fecha y hora oficial en formato texto para marcaciones"""
    return get_current_time().strftime(fmt)