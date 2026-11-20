# ======================================================================
# CLIENTE REST API Y SINCRONIZACIÓN DE DATOS BIOMÉTRICOS / MARCACIONES
# ======================================================================
import os
import threading
from datetime import datetime
import numpy as np
import requests
import urllib3

from config import DIR_ROSTROS
from storage import (
    ARCHIVOS_LOCK,
    MAPA_NFC_A_ID,
    inicializar_entorno,
    get_server_url,
    normalizar_uid_nfc,
    invertir_bytes_uid,
    extraer_nfc_de_info,
    cargar_empleados_locales,
    guardar_empleados_locales,
    reconstruir_mapa_nfc_local,
    registrar_log_incidente,
    guardar_marcacion_pendiente,
    leer_marcaciones_pendientes,
    actualizar_marcaciones_pendientes,
    cargar_enrolamientos_pendientes,
    guardar_enrolamiento_pendiente,
    eliminar_enrolamiento_pendiente,
    guardar_enrolamientos_pendientes_dict,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ----------------------------------------------------------------------
# SINCRONIZACIÓN DE COLAS OFFLINE Y BASE DE EMPLEADOS
# ----------------------------------------------------------------------
def sincronizar_enrolamientos_pendientes():
    """Sube al servidor todos los colaboradores enrolados mientras no había red."""
    pendientes = cargar_enrolamientos_pendientes()
    if not pendientes:
        return

    server_url = get_server_url()
    restantes = {}

    for emp_id, payload in pendientes.items():
        try:
            res = requests.post(f"{server_url}/empleados/enrolar", json=payload, timeout=5, verify=False)
            if res.status_code in [200, 201]:
                print(f"[OFFLINE ENROL SYNC] ✓ Enrolamiento subido (ID: {emp_id}, NFC: {payload.get('nfc', '')})")
            else:
                restantes[emp_id] = payload
        except requests.exceptions.RequestException:
            restantes[emp_id] = payload

    guardar_enrolamientos_pendientes_dict(restantes)


def sincronizar_marcaciones_pendientes():
    """Envía al servidor todas las marcaciones acumuladas localmente en modo offline."""
    pendientes = leer_marcaciones_pendientes()
    if not pendientes:
        return

    server_url = get_server_url()
    restantes = []

    for idx, m in enumerate(pendientes):
        fecha_real = m.get("Fecha_Hora", "")
        nfc_val = normalizar_uid_nfc(m.get("NFC_UID", ""))
        payload = {
            "empleado_id": m["Empleado_ID"],
            "nfc": nfc_val,
            "rfid": nfc_val,
            "tipo_marcacion": m["Tipo_Marcacion"],
            "fecha_hora": fecha_real,
            "timestamp": fecha_real,
            "nota": f"{m.get('Nota', '')} (Sincronizado Offline)".strip(),
        }
        try:
            res = requests.post(f"{server_url}/marcaciones", json=payload, timeout=5, verify=False)
            if res.status_code in [200, 201]:
                print(f"[OFFLINE SYNC] ✓ Marcación enviada (ID: {m['Empleado_ID']}, Hora: {fecha_real})")
            else:
                restantes.append(m)
        except requests.exceptions.RequestException:
            restantes.extend(pendientes[idx:])
            break

    actualizar_marcaciones_pendientes(restantes)


def sincronizar_empleados_servidor():
    """
    1. Sube primero cualquier enrolamiento local pendiente.
    2. Descarga empleados del servidor y los FUSIONA con empleados.json local
       sin borrar colaboradores locales ni tarjetas NFC ya registradas.
    """
    inicializar_entorno()
    server_url = get_server_url()
    sincronizar_enrolamientos_pendientes()

    try:
        res = requests.get(f"{server_url}/empleados", timeout=6, verify=False)
        if res.status_code == 200:
            data = res.json()

            with ARCHIVOS_LOCK:
                emps_previos = cargar_empleados_locales()

                empleados_server = {}
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict):
                            empleados_server[str(k).strip().upper()] = v
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            e_id = item.get("empleado_id") or item.get("id")
                            if e_id:
                                empleados_server[str(e_id).strip().upper()] = item

                # Conservar registros locales existentes para no perder datos offline
                empleados_dict = {k: dict(v) for k, v in emps_previos.items()}

                for emp_id, info_srv in empleados_server.items():
                    prev = empleados_dict.get(emp_id, {})
                    nfc_val = extraer_nfc_de_info(info_srv) or extraer_nfc_de_info(prev)

                    vec_srv = info_srv.get("vector_facial", [])
                    vec_prev = prev.get("vector_facial", [])
                    vector_final = (
                        vec_srv if (isinstance(vec_srv, list) and len(vec_srv) == 128)
                        else vec_prev
                    )

                    empleados_dict[emp_id] = {
                        "nombre": info_srv.get("nombre") or prev.get("nombre", ""),
                        "apellido": info_srv.get("apellido") or prev.get("apellido", ""),
                        "area": info_srv.get("area") or info_srv.get("departamento") or prev.get("area", "OPERACIONES"),
                        "nfc": nfc_val,
                        "rfid": nfc_val,
                        "vector_facial": vector_final if isinstance(vector_final, list) else [],
                    }

                for emp_id, pend in cargar_enrolamientos_pendientes().items():
                    prev = empleados_dict.get(emp_id, {})
                    nfc_pend = extraer_nfc_de_info(pend) or extraer_nfc_de_info(prev)
                    vec_pend = pend.get("vector_facial", [])
                    vec_prev = prev.get("vector_facial", [])
                    empleados_dict[emp_id] = {
                        "nombre": prev.get("nombre", ""),
                        "apellido": prev.get("apellido", ""),
                        "area": pend.get("area") or prev.get("area", "OPERACIONES"),
                        "nfc": nfc_pend,
                        "rfid": nfc_pend,
                        "vector_facial": vec_pend if (isinstance(vec_pend, list) and len(vec_pend) == 128) else vec_prev,
                    }

                contador_nfc = sum(1 for info in empleados_dict.values() if extraer_nfc_de_info(info))
                guardar_empleados_locales(empleados_dict)
                reconstruir_mapa_nfc_local(empleados_dict)

                contador_vectores = 0
                for emp_id, info in empleados_dict.items():
                    emp_id_str = str(emp_id).strip().upper()
                    vector_list = info.get("vector_facial", [])
                    if isinstance(vector_list, list) and len(vector_list) == 128:
                        vector_np = np.array(vector_list, dtype=np.float64)
                        np.save(os.path.join(DIR_ROSTROS, f"{emp_id_str}.npy"), vector_np)
                        contador_vectores += 1

            msg = (
                f"✓ Sincronización exitosa: {len(empleados_dict)} empleados "
                f"({contador_vectores} rostros .npy, {contador_nfc} tarjetas NFC)."
            )
            print(f"[SYNC] {msg}")
            return True, msg

        registrar_log_incidente("SISTEMA", "SINCRONIZACION", "Error HTTP Servidor", f"Código {res.status_code}")
        return False, f"⚠️ Respuesta del servidor HTTP {res.status_code}"

    except requests.exceptions.RequestException as e:
        reconstruir_mapa_nfc_local(cargar_empleados_locales())
        registrar_log_incidente("SISTEMA", "SINCRONIZACION", "Servidor Inalcanzable", str(e))
        return False, f"❌ Sin conexión con el servidor REST ({server_url}). Modo Offline activo."


# ----------------------------------------------------------------------
# CONSULTAS Y OPERACIONES DE COLABORADORES Y MARCACIONES
# ----------------------------------------------------------------------
def obtener_vector_biometrico(identificador):
    """
    Busca al colaborador por ID de empleado o UID de tarjeta NFC:
    1. Revisa empleados.json local, enrolamientos_pendientes.json y base_rostros/<ID>.npy.
    2. Si no está localmente, consulta al Servidor REST en tiempo real.
    """
    inicializar_entorno()
    identificador_limpio = normalizar_uid_nfc(identificador)
    identificador_invertido = invertir_bytes_uid(identificador_limpio)
    candidatos = [identificador_limpio]
    if identificador_invertido and identificador_invertido != identificador_limpio:
        candidatos.append(identificador_invertido)

    with ARCHIVOS_LOCK:
        emps_locales = cargar_empleados_locales()

        for pend_id, pend_info in cargar_enrolamientos_pendientes().items():
            if pend_id not in emps_locales:
                emps_locales[pend_id] = pend_info

        reconstruir_mapa_nfc_local(emps_locales)

        emp_id_real = ""
        for cand in candidatos:
            if cand in MAPA_NFC_A_ID:
                emp_id_real = MAPA_NFC_A_ID[cand]
                break

        if not emp_id_real:
            for e_id, info in emps_locales.items():
                nfc_emp = extraer_nfc_de_info(info)
                if nfc_emp and nfc_emp in candidatos:
                    emp_id_real = e_id
                    break

        if not emp_id_real:
            emp_id_real = identificador_limpio

        if emp_id_real in emps_locales:
            info_emp = emps_locales[emp_id_real]
            depto = info_emp.get("area") or info_emp.get("departamento") or "OPERACIONES"
            ruta_local = os.path.join(DIR_ROSTROS, f"{emp_id_real}.npy")

            if os.path.exists(ruta_local):
                try:
                    vector = np.load(ruta_local)
                    if len(vector) == 128:
                        return True, emp_id_real, depto, vector, "✓ Carga instantánea desde empleados.json local"
                except Exception:
                    pass

            vector_list = info_emp.get("vector_facial", [])
            if isinstance(vector_list, list) and len(vector_list) == 128:
                vector_np = np.array(vector_list, dtype=np.float64)
                np.save(ruta_local, vector_np)
                return True, emp_id_real, depto, vector_np, "✓ Vector restaurado desde empleados.json local"

    # Consultar al Servidor REST en tiempo real si no está en local
    server_url = get_server_url()
    try:
        res = requests.get(f"{server_url}/empleados/{identificador_limpio}", timeout=4, verify=False)
        if res.status_code == 200:
            data = res.json()
            real_id = str(data.get("empleado_id") or data.get("id") or identificador_limpio).strip().upper()
            depto = data.get("area") or data.get("departamento") or "OPERACIONES"
            nfc_val = extraer_nfc_de_info(data) or (identificador_limpio if real_id != identificador_limpio else "")
            vector_list = data.get("vector_facial", [])

            if isinstance(vector_list, list) and len(vector_list) == 128:
                vector_np = np.array(vector_list, dtype=np.float64)

                with ARCHIVOS_LOCK:
                    emps = cargar_empleados_locales()
                    emps[real_id] = {
                        "nombre": data.get("nombre", ""),
                        "apellido": data.get("apellido", ""),
                        "area": depto,
                        "nfc": nfc_val,
                        "rfid": nfc_val,
                        "vector_facial": vector_list,
                    }
                    guardar_empleados_locales(emps)
                    reconstruir_mapa_nfc_local(emps)
                    np.save(os.path.join(DIR_ROSTROS, f"{real_id}.npy"), vector_np)

                return True, real_id, depto, vector_np, "✓ Biometría y NFC obtenidos desde Servidor"

            registrar_log_incidente(real_id, "BUSQUEDA_BIOMETRICA", "Vector Facial Inválido", "Menos de 128 valores")
            return False, real_id, depto, None, f"⚠️ El ID {real_id} no tiene un vector facial válido."

        if res.status_code == 404:
            registrar_log_incidente(identificador_limpio, "BUSQUEDA_BIOMETRICA", "Colaborador/NFC No Registrado", "404 Not Found")
            return False, identificador_limpio, "", None, f"⚠️ La tarjeta o ID '{identificador_limpio}' no está registrado."

    except requests.exceptions.RequestException as e:
        registrar_log_incidente(identificador_limpio, "BUSQUEDA_BIOMETRICA", "Fallo Conexión Servidor", str(e))

    return False, identificador_limpio, "", None, f"❌ La tarjeta o ID '{identificador_limpio}' no fue encontrado."


def api_guardar_nuevo_empleado(emp_id, departamento, nfc_uid, vector_np):
    """Guarda localmente el vector facial y NFC, y los envía al servidor REST."""
    inicializar_entorno()
    emp_id_clean = str(emp_id).strip().upper()
    nfc_clean = normalizar_uid_nfc(nfc_uid)
    vector_list = vector_np.tolist()

    with ARCHIVOS_LOCK:
        np.save(os.path.join(DIR_ROSTROS, f"{emp_id_clean}.npy"), vector_np)

        emps = cargar_empleados_locales()
        for otro_id, info in emps.items():
            if otro_id != emp_id_clean and extraer_nfc_de_info(info) == nfc_clean:
                info["nfc"] = ""
                info["rfid"] = ""

        datos_previos = emps.get(emp_id_clean, {})
        emps[emp_id_clean] = {
            "nombre": datos_previos.get("nombre", ""),
            "apellido": datos_previos.get("apellido", ""),
            "area": departamento,
            "nfc": nfc_clean,
            "rfid": nfc_clean,
            "vector_facial": vector_list,
        }
        guardar_empleados_locales(emps)
        reconstruir_mapa_nfc_local(emps)

    server_url = get_server_url()
    payload = {
        "empleado_id": emp_id_clean,
        "area": departamento,
        "departamento": departamento,
        "nfc": nfc_clean,
        "rfid": nfc_clean,
        "vector_facial": vector_list,
    }

    try:
        res = requests.post(f"{server_url}/empleados/enrolar", json=payload, timeout=5, verify=False)
        if res.status_code in [200, 201]:
            eliminar_enrolamiento_pendiente(emp_id_clean)
            return True, "✓ Colaborador y tarjeta NFC registrados localmente y en el servidor."

        registrar_log_incidente(emp_id_clean, "ENROLAMIENTO", "Error Respuesta Servidor", f"HTTP {res.status_code}")
        guardar_enrolamiento_pendiente(emp_id_clean, departamento, nfc_clean, vector_list)
        return True, "✓ Guardado localmente (⚠️ Servidor rechazó; se reintentará sincronizar)."

    except requests.exceptions.RequestException as e:
        registrar_log_incidente(emp_id_clean, "ENROLAMIENTO", "Servidor Inalcanzable Backup", str(e))
        guardar_enrolamiento_pendiente(emp_id_clean, departamento, nfc_clean, vector_list)
        return True, "✓ Guardado localmente con NFC (⚠️ Sin red; se subirá automáticamente al reconectar)."


def api_registrar_marcacion(emp_id, tipo_marcacion, nota="", nfc_uid="", permiso_admin=False):
    """Registra la marcación con fecha/hora exacta en el servidor o en cola offline."""
    server_url = get_server_url()
    fecha_hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nfc_clean = normalizar_uid_nfc(nfc_uid)

    if permiso_admin:
        if not nota:
            nota = "Permiso Administrador (Sin tarjeta NFC)"
    else:
        if not nfc_clean:
            emps = cargar_empleados_locales()
            nfc_clean = extraer_nfc_de_info(emps.get(str(emp_id).strip().upper(), {}))
        if nfc_clean and not nota:
            nota = f"Tarjeta NFC: {nfc_clean}"

    payload = {
        "empleado_id": str(emp_id),
        "nfc": nfc_clean,
        "rfid": nfc_clean,
        "tipo_marcacion": tipo_marcacion,
        "fecha_hora": fecha_hora_actual,
        "timestamp": fecha_hora_actual,
        "permiso_admin": bool(permiso_admin),
        "nota": nota,
    }

    try:
        res = requests.post(f"{server_url}/marcaciones", json=payload, timeout=5, verify=False)
        if res.status_code in [200, 201]:
            data = res.json()
            threading.Thread(target=sincronizar_enrolamientos_pendientes, daemon=True).start()
            threading.Thread(target=sincronizar_marcaciones_pendientes, daemon=True).start()
            return True, data.get("mensaje", "Marcación registrada exitosamente")

        err_msg = res.json().get("error", f"Error HTTP {res.status_code}")
        registrar_log_incidente(emp_id, tipo_marcacion, "Rechazo del Servidor", err_msg)
        guardar_marcacion_pendiente(
            emp_id,
            tipo_marcacion,
            fecha_hora_actual,
            f"{nota} (Servidor Rechazó: {err_msg})",
            nfc_uid=nfc_clean,
        )
        return True, f"✓ Marcación ({fecha_hora_actual}) guardada LOCALMENTE (Servidor Rechazó)"

    except requests.exceptions.RequestException as e:
        registrar_log_incidente(emp_id, tipo_marcacion, "Fallo Red Marcación", str(e))
        guardar_marcacion_pendiente(
            emp_id,
            tipo_marcacion,
            fecha_hora_actual,
            f"{nota} (Red Caída)",
            nfc_uid=nfc_clean,
        )
        return True, f"✓ Marcación ({fecha_hora_actual}) guardada LOCALMENTE (Servidor Fuera de Línea)"


def api_obtener_historial(emp_id):
    server_url = get_server_url()
    try:
        res = requests.get(f"{server_url}/historial/{emp_id}", timeout=5, verify=False)
        if res.status_code == 200:
            return res.json().get("historial", [])
        return []
    except Exception:
        return []


def probar_conexion_servidor(base_url):
    """Prueba conectividad HTTP contra los endpoints conocidos del servidor."""
    endpoints = [
        f"{base_url}/api/ping",
        f"{base_url}/api",
        f"{base_url}/api/empleados",
        f"{base_url}/api/marcaciones",
        f"{base_url}/",
    ]
    for target_url in endpoints:
        try:
            res = requests.get(target_url, timeout=3, verify=False)
            if res.status_code in [200, 201, 400, 404, 405]:
                return True, f"✅ ¡Conexión con el Servidor Establecida! (HTTP {res.status_code})"
        except requests.exceptions.ConnectionError:
            continue
        except Exception:
            continue
    return False, ""