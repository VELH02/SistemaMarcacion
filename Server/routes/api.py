import io
import csv
import uuid
import numpy as np
from flask import Blueprint, request, jsonify, send_file, session
from config import DATA_FILE, CONFIG_FILE, EMPLEADOS_FILE
from storage import load_json, save_json, obtener_historial_empleado, buscar_empleado_por_id_o_rfid
from logger import log_event, console_logs
import time_sync

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/ping', methods=['GET'])
@api_bp.route('', methods=['GET'])
def api_ping():
    return jsonify({"status": "ok", "mensaje": "Servidor Rest API en línea"}), 200

@api_bp.route('/hora', methods=['GET'])
def api_hora():
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
    # Permite buscar tanto por ID como por RFID
    real_id, emp = buscar_empleado_por_id_o_rfid(emp_id)

    if not emp:
        log_event(ip_origen, f"Consulta fallida: {emp_id} no registrado")
        return jsonify({"error": f"El ID o tarjeta {emp_id} no esta registrado."}), 404

    log_event(ip_origen, f"Empleado {real_id} consultado exitosamente.")
    return jsonify({
        "empleado_id": real_id,
        "nombre": emp.get("nombre", ""),
        "apellido": emp.get("apellido", ""),
        "departamento": emp.get("area", "OPERACIONES").upper(),
        "rfid": emp.get("rfid", ""),
        "vector_facial": emp.get("vector_facial", [])
    }), 200

@api_bp.route('/empleados/enrolar', methods=['POST'])
def api_enrolar_empleado():
    ip_origen = request.remote_addr
    data = request.get_json(silent=True) or {}

    emp_id = str(data.get("empleado_id", "")).strip().upper()
    nombre = str(data.get("nombre", f"Colaborador {emp_id}")).strip()
    apellido = str(data.get("apellido", "")).strip()
    departamento = str(data.get("departamento", "OPERACIONES")).strip().upper().replace("Í", "I")
    rfid = str(data.get("rfid", "")).strip()
    vector_list = data.get("vector_facial", [])

    if not emp_id or not vector_list:
        return jsonify({"error": "Datos incompletos para enrolamiento."}), 400

    empleados = load_json(EMPLEADOS_FILE)
    empleados[emp_id] = {
        "nombre": nombre,
        "apellido": apellido,
        "area": departamento,
        "rfid": rfid,
        "vector_facial": vector_list
    }
    save_json(EMPLEADOS_FILE, empleados)
    log_event(ip_origen, f"Enrolamiento exitoso guardado en JSON: {emp_id} ({nombre} {apellido})")
    return jsonify({"mensaje": "Colaborador enrolado y consolidado correctamente"}), 201

@api_bp.route('/marcaciones', methods=['POST'])
def api_registrar_marcacion_json():
    ip_origen = request.remote_addr
    data = request.get_json(silent=True) or {}

    raw_id = str(data.get("empleado_id", "")).strip().upper()
    tipo = str(data.get("tipo_marcacion", "")).strip().upper()
    nota = str(data.get("nota", "")).strip()

    if not raw_id or not tipo:
        return jsonify({"error": "Parámetros incompletos."}), 400

    empleados = load_json(EMPLEADOS_FILE)
    real_id, emp_info = buscar_empleado_por_id_o_rfid(raw_id)

    # AUTO-REGISTRO: Si el colaborador no existe en el sistema, crearlo automáticamente
    if not emp_info:
        real_id = raw_id
        emp_info = {
            "nombre": f"Colaborador {real_id}",
            "apellido": "",
            "area": "OPERACIONES",
            "rfid": "",
            "vector_facial": []
        }
        empleados[real_id] = emp_info
        save_json(EMPLEADOS_FILE, empleados)
        log_event(ip_origen, f"✨ AUTO-REGISTRO: Colaborador nuevo {real_id} creado automáticamente al marcar.")

    nombre_completo = f"{emp_info.get('nombre', '')} {emp_info.get('apellido', '')}".strip()
    area_normalizada = emp_info.get('area', 'OPERACIONES').strip().upper().replace("Í", "I")
    fecha_hora = time_sync.get_time_str()
    id_registro = uuid.uuid4().hex[:8]

    with open(DATA_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([id_registro, real_id, nombre_completo, area_normalizada, tipo, fecha_hora, ip_origen, "Aprobado", nota])

    log_event(ip_origen, f"MARCACIÓN REGISTRADA: {real_id} ({nombre_completo}) - {tipo} [Área: {area_normalizada}]")
    return jsonify({"mensaje": f"Marcación de {tipo} registrada correctamente a las {fecha_hora}"}), 200

@api_bp.route('/historial/<emp_id>', methods=['GET'])
def api_historial_empleado(emp_id):
    real_id, _ = buscar_empleado_por_id_o_rfid(emp_id)
    historial = obtener_historial_empleado(real_id or emp_id)
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
            "area": info.get("area", "").upper(),
            "rfid": info.get("rfid", ""),
            "tiene_biometria": len(info.get("vector_facial", [])) > 0
        })
    return jsonify({"status": "ok", "data": lista_sync})

@api_bp.route('/sync/biometria/<emp_id>', methods=['GET'])
def sync_biometria(emp_id):
    """Genera en memoria el archivo .npy a partir de la matriz guardada en empleados.json"""
    real_id, emp = buscar_empleado_por_id_o_rfid(emp_id)
    if emp and emp.get("vector_facial"):
        try:
            vec_np = np.array(emp["vector_facial"], dtype=np.float64)
            buf = io.BytesIO()
            np.save(buf, vec_np)
            buf.seek(0)
            return send_file(
                buf, 
                mimetype="application/octet-stream", 
                as_attachment=True, 
                download_name=f"{real_id}.npy"
            )
        except Exception as e:
            return jsonify({"error": f"Error serializando vector: {e}"}), 500

    return jsonify({"error": "Archivo biométrico no registrado para este colaborador"}), 404

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

    raw_id = partes[0].strip().upper()
    tipo = partes[1].strip().upper()

    real_id, emp_info = buscar_empleado_por_id_o_rfid(raw_id)

    # AUTO-REGISTRO en modo texto plano
    if not emp_info:
        real_id = raw_id
        emp_info = {
            "nombre": f"Colaborador {real_id}",
            "apellido": "",
            "area": "OPERACIONES",
            "rfid": "",
            "vector_facial": []
        }
        empleados[real_id] = emp_info
        save_json(EMPLEADOS_FILE, empleados)
        log_event(ip_origen, f"✨ AUTO-REGISTRO: Colaborador {real_id} creado automáticamente.")

    nombre_completo = f"{emp_info.get('nombre', '')} {emp_info.get('apellido', '')}".strip()
    fecha_hora = time_sync.get_time_str()
    id_registro = uuid.uuid4().hex[:8]

    with open(DATA_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([id_registro, real_id, nombre_completo, emp_info.get('area', 'OPERACIONES'), tipo, fecha_hora, ip_origen, "Aprobado", ""])

    return f"EXITO: {nombre_completo} - {tipo} a las {fecha_hora}\n", 200