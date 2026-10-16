import os
import csv
import uuid
import numpy as np
from flask import Blueprint, request, jsonify, send_from_directory, session
from config import DATA_FILE, CONFIG_FILE, EMPLEADOS_FILE, BIOMETRIA_FOLDER
from storage import load_json, save_json, obtener_historial_empleado
from logger import log_event, console_logs
import time_sync

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/ping', methods=['GET'])
@api_bp.route('', methods=['GET'])
def api_ping():
    return jsonify({"status": "ok", "mensaje": "Servidor Rest API en línea"}), 200

@api_bp.route('/hora', methods=['GET'])
def api_hora():
    """Entrega la hora en vivo sincronizada con el servidor NTP para la interfaz web"""
    ahora = time_sync.get_current_time()
    return jsonify({
        "fecha": ahora.strftime("%d/%m/%Y"),
        "hora": ahora.strftime("%H:%M:%S"),
        "estado_sync": time_sync.estado_sync,
        "ultimo_sync": time_sync.ultimo_sync.strftime("%H:%M:%S") if time_sync.ultimo_sync else "Nunca"
    }), 200

@api_bp.route('/empleados/<emp_id>', methods=['GET'])
def api_obtener_empleado(emp_id):
    ip_origen = request.remote_addr
    empleados = load_json(EMPLEADOS_FILE)
    emp_id = str(emp_id).strip().upper()

    if emp_id not in empleados:
        log_event(ip_origen, f"Consulta fallida: {emp_id} no registrado")
        return jsonify({"error": f"El ID {emp_id} no esta registrado."}), 404

    emp = empleados[emp_id]
    ruta_npy = os.path.join(BIOMETRIA_FOLDER, f"{emp_id}.npy")
    
    vector_list = []
    if os.path.exists(ruta_npy):
        try:
            vector_np = np.load(ruta_npy)
            vector_list = vector_np.tolist()
        except Exception as e:
            log_event(ip_origen, f"Error leyendo matriz facial de {emp_id}: {e}")

    log_event(ip_origen, f"Empleado {emp_id} consultado exitosamente.")
    return jsonify({
        "empleado_id": emp_id,
        "nombre": emp.get("nombre", ""),
        "apellido": emp.get("apellido", ""),
        "departamento": emp.get("area", emp.get("departamento", "OPERACIONES")).upper(),
        "vector_facial": vector_list
    }), 200

@api_bp.route('/empleados/enrolar', methods=['POST'])
def api_enrolar_empleado():
    ip_origen = request.remote_addr
    data = request.get_json(silent=True) or {}

    emp_id = str(data.get("empleado_id", "")).strip().upper()
    nombre = str(data.get("nombre", f"Colaborador {emp_id}")).strip()
    apellido = str(data.get("apellido", "")).strip()
    departamento = str(data.get("departamento", "OPERACIONES")).strip().upper().replace("Í", "I")
    vector_list = data.get("vector_facial", [])

    if not emp_id or not vector_list:
        return jsonify({"error": "Datos incompletos para enrolamiento."}), 400

    empleados = load_json(EMPLEADOS_FILE)
    empleados[emp_id] = {
        "nombre": nombre,
        "apellido": apellido,
        "area": departamento
    }
    save_json(EMPLEADOS_FILE, empleados)

    ruta_npy = os.path.join(BIOMETRIA_FOLDER, f"{emp_id}.npy")
    try:
        vector_np = np.array(vector_list, dtype=np.float64)
        np.save(ruta_npy, vector_np)
        log_event(ip_origen, f"Enrolamiento exitoso: {emp_id} ({nombre} {apellido}) [Área: {departamento}]")
        return jsonify({"mensaje": "Colaborador enrolado correctamente"}), 201
    except Exception as e:
        log_event(ip_origen, f"Error al guardar .npy de {emp_id}: {e}")
        return jsonify({"error": "Error interno guardando la biometría"}), 500

@api_bp.route('/marcaciones', methods=['POST'])
def api_registrar_marcacion_json():
    ip_origen = request.remote_addr
    data = request.get_json(silent=True) or {}

    emp_id = str(data.get("empleado_id", "")).strip().upper()
    tipo = str(data.get("tipo_marcacion", "")).strip().upper()
    nota = str(data.get("nota", "")).strip()

    if not emp_id or not tipo:
        return jsonify({"error": "Parámetros incompletos."}), 400

    empleados = load_json(EMPLEADOS_FILE)
    emp_info = empleados.get(emp_id, {"nombre": f"Colaborador {emp_id}", "apellido": "", "area": "OPERACIONES"})
    nombre_completo = f"{emp_info['nombre']} {emp_info.get('apellido', '')}".strip()
    area_normalizada = emp_info.get('area', 'OPERACIONES').strip().upper().replace("Í", "I")

    fecha_hora = time_sync.get_time_str() # Hora oficial sincronizada por NTP
    id_registro = uuid.uuid4().hex[:8]

    with open(DATA_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([id_registro, emp_id, nombre_completo, area_normalizada, tipo, fecha_hora, ip_origen, "Aprobado", nota])

    log_event(ip_origen, f"MARCACIÓN REGISTRADA: {emp_id} ({nombre_completo}) - {tipo} [Área: {area_normalizada}]")
    return jsonify({"mensaje": f"Marcación de {tipo} registrada correctamente a las {fecha_hora}"}), 200

@api_bp.route('/historial/<emp_id>', methods=['GET'])
def api_historial_empleado(emp_id):
    historial = obtener_historial_empleado(emp_id)
    return jsonify({"historial": historial}), 200

@api_bp.route('/sync/empleados', methods=['GET'])
def sync_empleados():
    empleados = load_json(EMPLEADOS_FILE)
    lista_sync = []
    for emp_id, info in empleados.items():
        lista_sync.append({
            "codigo": emp_id,
            "nombre": info.get("nombre", ""),
            "apellido": info.get("apellido", ""),
            "area": info.get("area", "").upper()
        })
    return jsonify({"status": "ok", "data": lista_sync})

@api_bp.route('/sync/biometria/<emp_id>', methods=['GET'])
def sync_biometria(emp_id):
    filename = f"{emp_id.strip().upper()}.npy"
    ruta_archivo = os.path.join(BIOMETRIA_FOLDER, filename)
    if os.path.exists(ruta_archivo):
        return send_from_directory(BIOMETRIA_FOLDER, filename)
    else:
        return jsonify({"error": "Archivo biometrico no encontrado"}), 404

@api_bp.route('/logs', methods=['GET'])
def get_logs():
    if session.get('usuario') != 'admin' and session.get('area') != 'TODAS':
        return jsonify([])
    return jsonify(list(console_logs))

@api_bp.route('/marcar', methods=['POST'])
def recibir_marcacion_texto():
    config = load_json(CONFIG_FILE)
    empleados = load_json(EMPLEADOS_FILE)
    ip_origen = request.remote_addr

    datos_texto = request.get_data(as_text=True).strip()
    log_event(ip_origen, f"Trama entrante texto: '{datos_texto}'")

    if config.get('ips_permitidas') and ip_origen not in config['ips_permitidas']:
        return "ERROR: IP no autorizada\n", 403

    if not datos_texto: 
        return "ERROR: No hay datos\n", 400

    partes = datos_texto.split(',')
    if len(partes) < 2: 
        return "ERROR: Formato incorrecto\n", 400

    id_personal = partes[0].strip().upper()
    tipo = partes[1].strip().upper()

    emp_info = empleados.get(id_personal, {"nombre": "Desconocido", "apellido": "", "area": "OPERACIONES"})
    nombre_completo = f"{emp_info['nombre']} {emp_info.get('apellido', '')}".strip()
    fecha_hora = time_sync.get_time_str() # Hora oficial sincronizada por NTP
    id_registro = uuid.uuid4().hex[:8]

    with open(DATA_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([id_registro, id_personal, nombre_completo, emp_info.get('area', 'OPERACIONES'), tipo, fecha_hora, ip_origen, "Aprobado", ""])

    return f"EXITO: {nombre_completo} - {tipo} a las {fecha_hora}\n", 200