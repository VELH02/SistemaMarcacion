import csv
import json
import os
import uuid
import numpy as np
from datetime import datetime
from config import DATA_FILE, CONFIG_FILE, EMPLEADOS_FILE, AREAS_FILE, USUARIOS_FILE, BIOMETRIA_FOLDER
import time_sync

DEFAULT_CONFIG = {
    "puerto_escucha": 5000,
    "ips_permitidas": [],
    "servidor_ntp": "pool.ntp.org"
}

DEFAULT_EMPLEADOS = {
    "EMP-001": {
        "nombre": "Pedro", 
        "apellido": "Martinez", 
        "area": "OPERACIONES", 
        "rfid": "0012938471", 
        "vector_facial": []
    },
    "EMP-002": {
        "nombre": "Maria", 
        "apellido": "Gomez", 
        "area": "MANTENIMIENTO", 
        "rfid": "0012938472", 
        "vector_facial": []
    }
}

DEFAULT_AREAS = [
    "PRODUCCION",
    "MANTENIMIENTO",
    "SANEAMIENTO",
    "OPERACIONES",
    "LOGISTICA"
]

DEFAULT_USUARIOS = {
    "admin": {"pass": "admin", "area": "TODAS", "nombre": "Administrador General"},
    "produccion": {"pass": "1234", "area": "PRODUCCION", "nombre": "Jefe de Producción"},
    "mantenimiento": {"pass": "1234", "area": "MANTENIMIENTO", "nombre": "Jefe de Mantenimiento"},
    "saneamiento": {"pass": "1234", "area": "SANEAMIENTO", "nombre": "Jefe de Saneamiento"},
    "operaciones": {"pass": "1234", "area": "OPERACIONES", "nombre": "Jefe de Operaciones"},
    "logistica": {"pass": "1234", "area": "LOGISTICA", "nombre": "Jefe de Logística"}
}

def init_files():
    """Inicializa archivos base y migra matrices .npy existentes dentro de empleados.json"""
    os.makedirs(BIOMETRIA_FOLDER, exist_ok=True)

    if not os.path.exists(CONFIG_FILE) or os.path.getsize(CONFIG_FILE) == 0:
        save_json(CONFIG_FILE, DEFAULT_CONFIG)

    if not os.path.exists(EMPLEADOS_FILE) or os.path.getsize(EMPLEADOS_FILE) == 0:
        save_json(EMPLEADOS_FILE, DEFAULT_EMPLEADOS)

    if not os.path.exists(AREAS_FILE) or os.path.getsize(AREAS_FILE) == 0:
        save_json(AREAS_FILE, DEFAULT_AREAS)

    if not os.path.exists(USUARIOS_FILE) or os.path.getsize(USUARIOS_FILE) == 0:
        save_json(USUARIOS_FILE, DEFAULT_USUARIOS)

    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["ID_Registro", "ID_Personal", "Nombre", "Area", "Tipo", "Fecha_Hora", "IP_Origen", "Estado", "Nota"])

    # Migración automática: integrar matrices .npy sueltas hacia empleados.json
    empleados = load_json(EMPLEADOS_FILE)
    cambios = False
    for emp_id, emp_data in empleados.items():
        if "rfid" not in emp_data:
            emp_data["rfid"] = ""
            cambios = True
        if "vector_facial" not in emp_data or len(emp_data["vector_facial"]) == 0:
            ruta_npy = os.path.join(BIOMETRIA_FOLDER, f"{emp_id}.npy")
            if os.path.exists(ruta_npy):
                try:
                    matriz = np.load(ruta_npy)
                    emp_data["vector_facial"] = matriz.tolist()
                    cambios = True
                except Exception:
                    pass
    if cambios:
        save_json(EMPLEADOS_FILE, empleados)

    cfg = load_json(CONFIG_FILE)
    ntp_host = cfg.get("servidor_ntp", "pool.ntp.org")
    time_sync.sincronizar_ntp(ntp_host)

def load_json(file_path):
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        if file_path == CONFIG_FILE:
            save_json(CONFIG_FILE, DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
        elif file_path == EMPLEADOS_FILE:
            save_json(EMPLEADOS_FILE, DEFAULT_EMPLEADOS)
            return DEFAULT_EMPLEADOS.copy()
        elif file_path == AREAS_FILE:
            save_json(AREAS_FILE, DEFAULT_AREAS)
            return DEFAULT_AREAS.copy()
        elif file_path == USUARIOS_FILE:
            save_json(USUARIOS_FILE, DEFAULT_USUARIOS)
            return DEFAULT_USUARIOS.copy()
        return {}

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        if file_path == CONFIG_FILE:
            save_json(CONFIG_FILE, DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
        elif file_path == EMPLEADOS_FILE:
            save_json(EMPLEADOS_FILE, DEFAULT_EMPLEADOS)
            return DEFAULT_EMPLEADOS.copy()
        elif file_path == AREAS_FILE:
            save_json(AREAS_FILE, DEFAULT_AREAS)
            return DEFAULT_AREAS.copy()
        elif file_path == USUARIOS_FILE:
            save_json(USUARIOS_FILE, DEFAULT_USUARIOS)
            return DEFAULT_USUARIOS.copy()
        return {}

def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def buscar_empleado_por_id_o_rfid(identificador):
    """Busca al colaborador por su código de empleado o por su tarjeta RFID"""
    empleados = load_json(EMPLEADOS_FILE)
    identificador_limpio = str(identificador).strip().upper()

    # Búsqueda directa por ID
    if identificador_limpio in empleados:
        return identificador_limpio, empleados[identificador_limpio]

    # Búsqueda por código de tarjeta RFID
    for code, info in empleados.items():
        if info.get('rfid', '').strip().upper() == identificador_limpio:
            return code, info

    return None, None

def actualizar_codigo_empleado_sistema(codigo_viejo, codigo_nuevo, nuevo_nombre, nuevo_apellido, nueva_area, nuevo_rfid, nuevo_vector=None):
    """Actualiza los datos consolidados del colaborador en empleados.json y en marcaciones.csv"""
    empleados = load_json(EMPLEADOS_FILE)
    codigo_viejo = str(codigo_viejo).strip().upper()
    codigo_nuevo = str(codigo_nuevo).strip().upper()

    datos_anteriores = empleados.get(codigo_viejo, {})
    vector_conservado = nuevo_vector if nuevo_vector is not None else datos_anteriores.get("vector_facial", [])

    if codigo_viejo in empleados:
        del empleados[codigo_viejo]
    
    empleados[codigo_nuevo] = {
        "nombre": nuevo_nombre,
        "apellido": nuevo_apellido,
        "area": nueva_area,
        "rfid": nuevo_rfid,
        "vector_facial": vector_conservado
    }
    save_json(EMPLEADOS_FILE, empleados)

    # Actualizar histórico en marcaciones.csv si el ID cambió
    if os.path.exists(DATA_FILE) and os.path.getsize(DATA_FILE) > 0 and codigo_viejo != codigo_nuevo:
        filas_actualizadas = []
        nombre_completo = f"{nuevo_nombre} {nuevo_apellido}".strip()
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or ["ID_Registro", "ID_Personal", "Nombre", "Area", "Tipo", "Fecha_Hora", "IP_Origen", "Estado", "Nota"]
            for row in reader:
                if row.get('ID_Personal', '').strip().upper() == codigo_viejo:
                    row['ID_Personal'] = codigo_nuevo
                    row['Nombre'] = nombre_completo
                    row['Area'] = nueva_area
                filas_actualizadas.append(row)
        
        with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(filas_actualizadas)

def guardar_o_actualizar_marcacion_diaria(emp_id, fecha, hora_entrada, hora_salida, usuario_modifica):
    emp_id = str(emp_id).strip().upper()
    empleados = load_json(EMPLEADOS_FILE)
    emp_info = empleados.get(emp_id, {"nombre": f"Colaborador {emp_id}", "apellido": "", "area": "OPERACIONES"})
    nombre_completo = f"{emp_info.get('nombre', '')} {emp_info.get('apellido', '')}".strip()
    area = emp_info.get('area', 'OPERACIONES').strip().upper()

    filas = []
    entrada_encontrada = False
    salida_encontrada = False

    def formatear_hora(h):
        h = h.strip()
        if not h: return ""
        partes = h.split(':')
        if len(partes) == 2:
            return f"{partes[0].zfill(2)}:{partes[1].zfill(2)}:00"
        elif len(partes) == 3:
            return f"{partes[0].zfill(2)}:{partes[1].zfill(2)}:{partes[2].zfill(2)}"
        return h

    h_in = formatear_hora(hora_entrada)
    h_out = formatear_hora(hora_salida)

    fieldnames = ["ID_Registro", "ID_Personal", "Nombre", "Area", "Tipo", "Fecha_Hora", "IP_Origen", "Estado", "Nota"]

    if os.path.exists(DATA_FILE) and os.path.getsize(DATA_FILE) > 0:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or fieldnames
            for row in reader:
                r_id = row.get('ID_Personal', '').strip().upper()
                r_fh = row.get('Fecha_Hora', '').strip()
                r_fecha = r_fh.split(' ')[0] if ' ' in r_fh else ""
                r_tipo = row.get('Tipo', '').strip().upper()

                if r_id == emp_id and r_fecha == fecha:
                    if r_tipo == 'ENTRADA' and h_in:
                        row['Fecha_Hora'] = f"{fecha} {h_in}"
                        row['Nota'] = f"Modificado por {usuario_modifica}"
                        entrada_encontrada = True
                    elif r_tipo in ['SALIDA', 'TIEMPO EXTRA'] and h_out:
                        row['Fecha_Hora'] = f"{fecha} {h_out}"
                        row['Nota'] = f"Modificado por {usuario_modifica}"
                        salida_encontrada = True
                
                filas.append(row)

    if h_in and not entrada_encontrada:
        filas.append({
            "ID_Registro": uuid.uuid4().hex[:8],
            "ID_Personal": emp_id,
            "Nombre": nombre_completo,
            "Area": area,
            "Tipo": "ENTRADA",
            "Fecha_Hora": f"{fecha} {h_in}",
            "IP_Origen": "Ajuste Manual",
            "Estado": "Aprobado",
            "Nota": f"Añadido por {usuario_modifica}"
        })

    if h_out and not salida_encontrada:
        filas.append({
            "ID_Registro": uuid.uuid4().hex[:8],
            "ID_Personal": emp_id,
            "Nombre": nombre_completo,
            "Area": area,
            "Tipo": "SALIDA",
            "Fecha_Hora": f"{fecha} {h_out}",
            "IP_Origen": "Ajuste Manual",
            "Estado": "Aprobado",
            "Nota": f"Añadido por {usuario_modifica}"
        })

    with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(filas)

def obtener_registros_agrupados(area_usuario, emp_id_filtro, fecha_inicio, fecha_fin):
    registros_diarios = {}
    usr_area = str(area_usuario).strip().upper().replace("Í", "I")
    
    if os.path.exists(DATA_FILE) and os.path.getsize(DATA_FILE) > 0:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                fecha_hora_raw = row.get('Fecha_Hora', '').strip()
                if not fecha_hora_raw or ' ' not in fecha_hora_raw:
                    continue

                parts = fecha_hora_raw.split(' ')
                fecha_str, hora_str = parts[0], parts[1]

                if len(fecha_str) < 8 or '-' not in fecha_str:
                    continue

                row_area = (row.get('Area') or row.get('area') or 'OPERACIONES').strip().upper().replace("Í", "I")
                if usr_area != 'TODAS' and row_area != usr_area:
                    continue

                row_id = row.get('ID_Personal', '').strip().upper()
                if emp_id_filtro and row_id != emp_id_filtro.strip().upper():
                    continue

                if fecha_inicio and fecha_str < fecha_inicio:
                    continue
                if fecha_fin and fecha_str > fecha_fin:
                    continue

                key = (row_id, fecha_str)
                if key not in registros_diarios:
                    registros_diarios[key] = {
                        'id': row_id, 
                        'nombre': row.get('Nombre', ''), 
                        'area': row_area,
                        'fecha': fecha_str, 
                        'entrada': None, 
                        'salida': None
                    }

                tipo_m = row.get('Tipo', '').strip().upper()
                if tipo_m == 'ENTRADA':
                    if not registros_diarios[key]['entrada'] or hora_str < registros_diarios[key]['entrada']:
                        registros_diarios[key]['entrada'] = hora_str
                elif tipo_m in ['SALIDA', 'TIEMPO EXTRA']:
                    if not registros_diarios[key]['salida'] or hora_str > registros_diarios[key]['salida']:
                        registros_diarios[key]['salida'] = hora_str

    resultado = []
    for data in registros_diarios.values():
        if data['entrada'] and data['salida']:
            t_in = datetime.strptime(data['entrada'], "%H:%M:%S")
            t_out = datetime.strptime(data['salida'], "%H:%M:%S")
            delta = t_out - t_in
            data['horas_totales'] = round(delta.total_seconds() / 3600, 2)
        else:
            data['horas_totales'] = "Incompleto"
        
        resultado.append(data)
        
    return sorted(resultado, key=lambda x: x['fecha'], reverse=True)

def obtener_historial_empleado(emp_id):
    emp_id = str(emp_id).strip().upper()
    registros_diarios = {}

    if os.path.exists(DATA_FILE) and os.path.getsize(DATA_FILE) > 0:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('ID_Personal', '').strip().upper() != emp_id:
                    continue

                fecha_hora_raw = row.get('Fecha_Hora', '').strip()
                if not fecha_hora_raw or ' ' not in fecha_hora_raw:
                    continue

                parts = fecha_hora_raw.split(' ')
                fecha_str, hora_str = parts[0], parts[1]

                if fecha_str not in registros_diarios:
                    registros_diarios[fecha_str] = {'entrada': None, 'salida': None}

                tipo_m = row.get('Tipo', '').strip().upper()
                if tipo_m == 'ENTRADA':
                    if not registros_diarios[fecha_str]['entrada'] or hora_str < registros_diarios[fecha_str]['entrada']:
                        registros_diarios[fecha_str]['entrada'] = hora_str
                elif tipo_m in ['SALIDA', 'TIEMPO EXTRA']:
                    if not registros_diarios[fecha_str]['salida'] or hora_str > registros_diarios[fecha_str]['salida']:
                        registros_diarios[fecha_str]['salida'] = hora_str

    historial = []
    for fecha, horas in sorted(registros_diarios.items(), reverse=True):
        entrada = horas['entrada'] or "--:--:--"
        salida = horas['salida'] or "--:--:--"
        horas_trabajadas = "Incompleto"
        tarde_min = "0"

        if horas['entrada'] and horas['salida']:
            t_in = datetime.strptime(horas['entrada'], "%H:%M:%S")
            t_out = datetime.strptime(horas['salida'], "%H:%M:%S")
            delta = t_out - t_in
            horas_trabajadas = f"{round(delta.total_seconds() / 3600, 2)} hrs"

        if horas['entrada']:
            t_in = datetime.strptime(horas['entrada'], "%H:%M:%S")
            t_esperada = datetime.strptime("08:00:00", "%H:%M:%S")
            if t_in > t_esperada:
                tarde_min = str(int((t_in - t_esperada).total_seconds() // 60))

        historial.append({
            "fecha": fecha,
            "entrada": entrada,
            "salida": salida,
            "horas": horas_trabajadas,
            "tarde": tarde_min
        })

    return historial