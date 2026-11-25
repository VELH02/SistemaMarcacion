# ======================================================================
# CATÁLOGO LOCAL ATÓMICO Y CONSULTA DE AUDITORÍA
# ======================================================================
import os
import time
import json
import csv
import threading
import hashlib
import hmac
import secrets
from datetime import datetime

from config import (
    ADMIN_PIN,
    CONFIG_FILE,
    EMPLEADOS_FILE_LOCAL,
    LOG_FILE,
    DIR_ROSTROS,
    DEFAULT_SERVER_URL,
)

# Lock reentrante para evitar lecturas vacías o bloqueos con OneDrive / hilos
ARCHIVOS_LOCK = threading.RLock()

# Mapa global en memoria RAM: UID_NFC_NORMALIZADO -> EMPLEADO_ID
MAPA_NFC_A_ID = {}


# ----------------------------------------------------------------------
# UTILIDADES DE NORMALIZACIÓN NFC Y ENTORNO
# ----------------------------------------------------------------------
def inicializar_entorno():
    """Asegura que exista la carpeta local de vectores faciales."""
    if not os.path.exists(DIR_ROSTROS):
        os.makedirs(DIR_ROSTROS, exist_ok=True)


def guardar_pin_administrativo(pin,config_changes=None):
    if not isinstance(pin,str) or not pin.isascii() or not pin.isdigit() or not 6<=len(pin)<=8:
        raise ValueError('El PIN debe contener de 6 a 8 dígitos')
    salt=secrets.token_bytes(16)
    iterations=600000
    digest=hashlib.pbkdf2_hmac('sha256',pin.encode(),salt,iterations)
    with ARCHIVOS_LOCK:
        data=leer_json_seguro(CONFIG_FILE,{})
        if config_changes: data.update(config_changes)
        data['admin_pin_hash']=dict(algorithm='pbkdf2_sha256',iterations=iterations,salt=salt.hex(),digest=digest.hex())
        guardar_json_atomico(CONFIG_FILE,data)


def tiene_pin_administrativo():
    return bool(ADMIN_PIN or cargar_configuracion().get('admin_pin_hash'))


def verificar_pin_administrativo(pin):
    if not isinstance(pin,str) or not pin.isascii() or not pin.isdigit() or not 6<=len(pin)<=8: return False
    if ADMIN_PIN: return hmac.compare_digest(pin,ADMIN_PIN)
    data=cargar_configuracion().get('admin_pin_hash',{})
    try:
        iterations=data['iterations']
        if data.get('algorithm')!='pbkdf2_sha256' or type(iterations)!=int or not 100000<=iterations<=2000000: return False
        salt=bytes.fromhex(data['salt']);expected=bytes.fromhex(data['digest'])
        if len(salt)!=16 or len(expected)!=32: return False
        actual=hashlib.pbkdf2_hmac('sha256',pin.encode(),salt,iterations)
        return hmac.compare_digest(actual,expected)
    except (KeyError,TypeError,ValueError): return False


def normalizar_uid_nfc(valor):
    """Normaliza un UID NFC/RFID a mayúsculas sin espacios ni separadores."""
    if not valor:
        return ""
    return str(valor).strip().replace(" ", "").replace(":", "").replace("-", "").upper()


def invertir_bytes_uid(uid_hex):
    """Devuelve el UID con orden de bytes invertido (respaldo ante cambio de endianness)."""
    uid = normalizar_uid_nfc(uid_hex)
    if len(uid) >= 8 and len(uid) % 2 == 0 and all(c in "0123456789ABCDEF" for c in uid):
        pares = [uid[i:i + 2] for i in range(0, len(uid), 2)]
        return "".join(reversed(pares))
    return ""


def extraer_nfc_de_info(info):
    """Extrae el identificador NFC/RFID desde un diccionario de empleado."""
    if not isinstance(info, dict):
        return ""
    for clave in ("nfc", "nfc_uid", "nfc_id", "rfid", "tarjeta_nfc"):
        val = info.get(clave)
        if val is not None and str(val).strip():
            return normalizar_uid_nfc(val)
    return ""


# ----------------------------------------------------------------------
# LECTURA Y ESCRITURA ATÓMICA DE ARCHIVOS JSON
# ----------------------------------------------------------------------
def leer_json_seguro(ruta_archivo, default):
    with ARCHIVOS_LOCK:
        if not os.path.exists(ruta_archivo): return default
        for intento in range(3):
            try:
                with open(ruta_archivo,'r',encoding='utf-8-sig') as stream:
                    return json.load(stream)
            except (PermissionError,json.JSONDecodeError):
                time.sleep(.05*(intento+1))
        raise OSError(f'No se pudo leer {os.path.basename(ruta_archivo)}; se conserva sin sobrescribir')


def guardar_json_atomico(ruta_archivo,data):
    import tempfile
    with ARCHIVOS_LOCK:
        os.makedirs(os.path.dirname(os.path.abspath(ruta_archivo)),exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix='.alicapsa-',dir=os.path.dirname(os.path.abspath(ruta_archivo)))
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                json.dump(data,stream,ensure_ascii=False,indent=2,allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp,ruta_archivo)
            return True
        finally:
            if os.path.exists(tmp): os.remove(tmp)


# ----------------------------------------------------------------------
# CONFIGURACIÓN DE RED DEL SERVIDOR
# ----------------------------------------------------------------------
def parse_url_to_ip_port(url):
    clean_url = url.replace("/api", "").rstrip("/")
    if ":" in clean_url.replace("http://", "").replace("https://", ""):
        parts = clean_url.rsplit(":", 1)
        return parts[0], parts[1]
    return clean_url, "5000"


def cargar_configuracion():
    if not os.path.exists(CONFIG_FILE):
        config = {
            "server_ip": "http://127.0.0.1",
            "server_port": "5000",
            "server_url": DEFAULT_SERVER_URL,
        }
        guardar_configuracion("http://127.0.0.1", "5000")
        return config

    data = leer_json_seguro(CONFIG_FILE, None)
    if isinstance(data, dict):
        if "server_ip" not in data or "server_port" not in data:
            ip, port = parse_url_to_ip_port(data.get("server_url", DEFAULT_SERVER_URL))
            data["server_ip"] = ip
            data["server_port"] = port
        return data

    return {
        "server_ip": "http://127.0.0.1",
        "server_port": "5000",
        "server_url": DEFAULT_SERVER_URL,
    }


def guardar_configuracion(server_ip, server_port):
    ip = server_ip.strip().rstrip("/")
    port = server_port.strip()

    if not ip.startswith("http://") and not ip.startswith("https://"):
        ip = f"http://{ip}"

    full_url = f"{ip}:{port}/api" if port else f"{ip}/api"
    config = {
        **(leer_json_seguro(CONFIG_FILE, {}) if os.path.exists(CONFIG_FILE) else {}),
        "server_ip": ip,
        "server_port": port,
        "server_url": full_url,
    }
    guardar_json_atomico(CONFIG_FILE, config)
    return config


def get_server_url():
    return cargar_configuracion().get("server_url", DEFAULT_SERVER_URL)


# ----------------------------------------------------------------------
# BASE DE DATOS LOCAL DE EMPLEADOS Y MAPA NFC EN MEMORIA
# ----------------------------------------------------------------------
def cargar_empleados_locales():
    """Lee empleados.json asegurando formato diccionario normalizado por ID."""
    data = leer_json_seguro(EMPLEADOS_FILE_LOCAL, {})
    if isinstance(data, dict):
        return {str(k).strip().upper(): v for k, v in data.items() if isinstance(v, dict)}
    if isinstance(data, list):
        resultado = {}
        for item in data:
            if isinstance(item, dict):
                e_id = item.get("empleado_id") or item.get("id")
                if e_id:
                    resultado[str(e_id).strip().upper()] = item
        return resultado
    return {}


def guardar_empleados_locales(data_empleados):
    """Guarda o actualiza empleados.json de forma atómica."""
    return guardar_json_atomico(EMPLEADOS_FILE_LOCAL, data_empleados)


def reconstruir_mapa_nfc_local(data_empleados):
    """Reconstruye el índice en memoria RAM de UID_NFC/RFID -> EMPLEADO_ID."""
    global MAPA_NFC_A_ID
    with ARCHIVOS_LOCK:
        nuevo_mapa = {}
        ambiguas = set()
        for emp_id, info in data_empleados.items():
            emp_id_clean = str(emp_id).strip().upper()
            nfc_clean = extraer_nfc_de_info(info)
            if nfc_clean:
                if nfc_clean in nuevo_mapa:
                    ambiguas.add(nfc_clean)
                nuevo_mapa[nfc_clean] = emp_id_clean
        for card in ambiguas:
            nuevo_mapa.pop(card, None)
        MAPA_NFC_A_ID.clear()
        MAPA_NFC_A_ID.update(nuevo_mapa)


def obtener_id_por_nfc(uid_hex):
    """Devuelve el ID del empleado asociado al UID NFC si existe en memoria."""
    uid_clean = normalizar_uid_nfc(uid_hex)
    with ARCHIVOS_LOCK:
        return MAPA_NFC_A_ID.get(uid_clean)


# ----------------------------------------------------------------------
# BITÁCORA DE AUDITORÍA E INCIDENTES (CSV LOCAL)
# ----------------------------------------------------------------------
def registrar_log_incidente(emp_id, operacion, motivo, detalle=""):
    """Guarda un registro de incidencia o autorización especial en log_incidentes.csv."""
    with ARCHIVOS_LOCK:
        try:
            existe = os.path.exists(LOG_FILE)
            ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(LOG_FILE, "a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                if not existe:
                    writer.writerow(["Fecha_Hora", "Empleado_ID", "Operacion", "Motivo_Fallo", "Detalle"])
                writer.writerow([ahora, str(emp_id), str(operacion), str(motivo), str(detalle)])
        except Exception as e:
            print(f"[ERROR LOG] No se pudo escribir en la bitácora: {e}")


def leer_logs_incidentes():
    """Incluye pendientes durables, aunque se limpie el CSV de incidencias."""
    rows = []
    with ARCHIVOS_LOCK:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)
                rows.extend(row for row in reader if len(row) >= 5)
    import outbox
    for state in ('PENDING', 'REVIEW'):
        for event in outbox.events(state=state):
            data = event['payload']
            rows.append([data.get('fecha_hora', event['created']), data.get('empleado_id', ''),
                'MARCACION' if event['kind']=='mark' else 'ENROLAMIENTO', state,
                event['event_id']+' · '+event['last_error']])
    return sorted(rows, key=lambda r:r[0], reverse=True)


def limpiar_logs_incidentes():
    """Elimina el archivo de bitácora local."""
    with ARCHIVOS_LOCK:
        if os.path.exists(LOG_FILE):
            try:
                os.remove(LOG_FILE)
            except Exception:
                pass
