# ======================================================================
# PERSISTENCIA LOCAL SEGURA, COLAS OFFLINE Y AUDITORÍA (JSON / CSV)
# ======================================================================
import os
import time
import json
import csv
import threading
from datetime import datetime

from config import (
    CONFIG_FILE,
    EMPLEADOS_FILE_LOCAL,
    ENROLAMIENTOS_PENDIENTES_FILE,
    MARCACIONES_PENDIENTES_FILE,
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
    """Lee un archivo JSON de forma segura con reintentos breves ante bloqueos."""
    with ARCHIVOS_LOCK:
        if not os.path.exists(ruta_archivo) or os.path.getsize(ruta_archivo) == 0:
            return default
        for intento in range(3):
            try:
                with open(ruta_archivo, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (PermissionError, json.JSONDecodeError):
                time.sleep(0.05 * (intento + 1))
            except Exception:
                return default
        return default


def guardar_json_atomico(ruta_archivo, data):
    """Escribe un JSON de forma atómica (.tmp -> os.replace) para evitar archivos vacíos."""
    with ARCHIVOS_LOCK:
        tmp_path = f"{ruta_archivo}.tmp"
        for intento in range(3):
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, ruta_archivo)
                return True
            except PermissionError:
                time.sleep(0.05 * (intento + 1))
            except Exception as e:
                print(f"[ERROR JSON] No se pudo guardar {ruta_archivo}: {e}")
                break
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False


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
    guardar_json_atomico(EMPLEADOS_FILE_LOCAL, data_empleados)


def reconstruir_mapa_nfc_local(data_empleados):
    """Reconstruye el índice en memoria RAM de UID_NFC/RFID -> EMPLEADO_ID."""
    global MAPA_NFC_A_ID
    with ARCHIVOS_LOCK:
        nuevo_mapa = {}
        for emp_id, info in data_empleados.items():
            emp_id_clean = str(emp_id).strip().upper()
            nfc_clean = extraer_nfc_de_info(info)
            if nfc_clean:
                nuevo_mapa[nfc_clean] = emp_id_clean
        MAPA_NFC_A_ID = nuevo_mapa


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
    """Devuelve la lista de registros de la bitácora."""
    with ARCHIVOS_LOCK:
        if not os.path.exists(LOG_FILE):
            return []
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)
                return [row for row in reader if len(row) >= 5]
        except Exception as e:
            print(f"[LOG DISPLAY ERROR] {e}")
            return []


def limpiar_logs_incidentes():
    """Elimina el archivo de bitácora local."""
    with ARCHIVOS_LOCK:
        if os.path.exists(LOG_FILE):
            try:
                os.remove(LOG_FILE)
            except Exception:
                pass


# ----------------------------------------------------------------------
# COLA OFFLINE DE MARCACIONES PENDIENTES
# ----------------------------------------------------------------------
def guardar_marcacion_pendiente(emp_id, tipo_marcacion, fecha_hora_str, nota="", nfc_uid=""):
    """Almacena localmente una marcación no enviada por falta de red."""
    with ARCHIVOS_LOCK:
        try:
            existe = (
                os.path.exists(MARCACIONES_PENDIENTES_FILE)
                and os.path.getsize(MARCACIONES_PENDIENTES_FILE) > 0
            )
            with open(MARCACIONES_PENDIENTES_FILE, "a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                if not existe:
                    writer.writerow(["Fecha_Hora", "Empleado_ID", "Tipo_Marcacion", "Nota", "NFC_UID"])
                writer.writerow([
                    fecha_hora_str,
                    str(emp_id),
                    str(tipo_marcacion),
                    str(nota),
                    normalizar_uid_nfc(nfc_uid),
                ])
            print(f"[OFFLINE QUEUE] Marcación de {emp_id} (NFC: {nfc_uid}) guardada en cola local: {fecha_hora_str}")
        except Exception as e:
            print(f"[OFFLINE QUEUE ERROR] No se pudo guardar marcación local: {e}")


def leer_marcaciones_pendientes():
    with ARCHIVOS_LOCK:
        if not os.path.exists(MARCACIONES_PENDIENTES_FILE) or os.path.getsize(MARCACIONES_PENDIENTES_FILE) == 0:
            return []
        pendientes = []
        try:
            with open(MARCACIONES_PENDIENTES_FILE, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Empleado_ID"):
                        pendientes.append(row)
        except Exception as e:
            print(f"[OFFLINE SYNC ERROR] Error leyendo cola de marcaciones: {e}")
        return pendientes


def actualizar_marcaciones_pendientes(restantes):
    with ARCHIVOS_LOCK:
        try:
            if restantes:
                with open(MARCACIONES_PENDIENTES_FILE, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(
                        f, fieldnames=["Fecha_Hora", "Empleado_ID", "Tipo_Marcacion", "Nota", "NFC_UID"]
                    )
                    writer.writeheader()
                    for row in restantes:
                        writer.writerow({
                            "Fecha_Hora": row.get("Fecha_Hora", ""),
                            "Empleado_ID": row.get("Empleado_ID", ""),
                            "Tipo_Marcacion": row.get("Tipo_Marcacion", ""),
                            "Nota": row.get("Nota", ""),
                            "NFC_UID": row.get("NFC_UID", ""),
                        })
            else:
                if os.path.exists(MARCACIONES_PENDIENTES_FILE):
                    os.remove(MARCACIONES_PENDIENTES_FILE)
                print("[OFFLINE SYNC] ✓ Todas las marcaciones pendientes fueron subidas al servidor.")
        except Exception as e:
            print(f"[OFFLINE SYNC ERROR] Error actualizando cola local: {e}")


# ----------------------------------------------------------------------
# COLA OFFLINE DE ENROLAMIENTOS PENDIENTES
# ----------------------------------------------------------------------
def cargar_enrolamientos_pendientes():
    data = leer_json_seguro(ENROLAMIENTOS_PENDIENTES_FILE, {})
    return data if isinstance(data, dict) else {}


def guardar_enrolamiento_pendiente(emp_id, departamento, nfc_uid, vector_list):
    with ARCHIVOS_LOCK:
        pendientes = cargar_enrolamientos_pendientes()
        emp_id_clean = str(emp_id).strip().upper()
        nfc_clean = normalizar_uid_nfc(nfc_uid)
        pendientes[emp_id_clean] = {
            "empleado_id": emp_id_clean,
            "area": departamento,
            "departamento": departamento,
            "nfc": nfc_clean,
            "rfid": nfc_clean,
            "vector_facial": vector_list,
            "fecha_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        guardar_json_atomico(ENROLAMIENTOS_PENDIENTES_FILE, pendientes)
        print(f"[OFFLINE ENROL] Colaborador {emp_id_clean} (NFC: {nfc_clean}) guardado en cola de respaldo.")


def eliminar_enrolamiento_pendiente(emp_id):
    with ARCHIVOS_LOCK:
        pendientes = cargar_enrolamientos_pendientes()
        emp_id_clean = str(emp_id).strip().upper()
        if emp_id_clean in pendientes:
            del pendientes[emp_id_clean]
            if pendientes:
                guardar_json_atomico(ENROLAMIENTOS_PENDIENTES_FILE, pendientes)
            elif os.path.exists(ENROLAMIENTOS_PENDIENTES_FILE):
                try:
                    os.remove(ENROLAMIENTOS_PENDIENTES_FILE)
                except Exception:
                    pass


def guardar_enrolamientos_pendientes_dict(restantes):
    with ARCHIVOS_LOCK:
        try:
            if restantes:
                guardar_json_atomico(ENROLAMIENTOS_PENDIENTES_FILE, restantes)
            elif os.path.exists(ENROLAMIENTOS_PENDIENTES_FILE):
                os.remove(ENROLAMIENTOS_PENDIENTES_FILE)
        except Exception as e:
            print(f"[OFFLINE ENROL SYNC ERROR] {e}")