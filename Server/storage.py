import csv
import json
import os
from datetime import datetime
from config import DATA_FILE, CONFIG_FILE, EMPLEADOS_FILE, AREAS_FILE, USUARIOS_FILE, BIOMETRIA_FOLDER
import time_sync

DEFAULT_CONFIG = {
    "puerto_escucha": 5000,
    "ips_permitidas": [],
    "servidor_ntp": "pool.ntp.org"
}

DEFAULT_EMPLEADOS = {
    "EMP-001": {"nombre": "Pedro", "apellido": "Martinez", "area": "OPERACIONES"},
    "EMP-002": {"nombre": "Maria", "apellido": "Gomez", "area": "MANTENIMIENTO"}
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

    # Intentar sincronizar hora inicial por NTP
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
                    if not registros_diarios[key]['entrada'] or hora_str < registros_diarios[key]['entrada']:
                        registros_diarios[key]['entrada'] = hora_str
                elif tipo_m in ['SALIDA', 'TIEMPO EXTRA']:
                    if not registros_diarios[key]['salida'] or hora_str > registros_diarios[key]['salida']:
                        registros_diarios[key]['salida'] = hora_str

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