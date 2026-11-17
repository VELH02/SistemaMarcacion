import io
import numpy as np
from flask import Blueprint, request, jsonify, send_file, session
from config import CONFIG_FILE, EMPLEADOS_FILE
from storage import registrar_marcacion, load_catalog, save_catalog, obtener_historial_empleado, buscar_empleado_por_id_o_rfid
from logger import log_event, console_logs
import time_sync

api_bp = Blueprint('api', __name__, url_prefix='/api')

# ==========================================
# DESCARGA COMPLETA DE EMPLEADOS (PARA CLIENTE)
# ==========================================

@api_bp.route('/empleados', methods=['GET'])
@api_bp.route('/sync/empleados.json', methods=['GET'])
@api_bp.route('/empleados/json', methods=['GET'])
def api_obtener_todos_empleados():
    """
    Satisface la llamada GET /api/empleados de Main_2.py.
    Retorna el diccionario de colaboradores con RFID y matrices faciales.
    """
    ip_origen = request.remote_addr
    empleados = load_catalog(EMPLEADOS_FILE)
    log_event(ip_origen, f"Sincronización completa: {len(empleados)} colaboradores enviados a {ip_origen}")
    return jsonify(empleados), 200

# ==========================================
# DIAGNÓSTICO Y HORA
# ==========================================

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

# ==========================================
# OPERACIONES DE EMPLEADOS Y BIOMETRÍA
# ==========================================

@api_bp.route('/empleados/<emp_id>', methods=['GET'])
def api_obtener_empleado(emp_id):
    ip_origen = request.remote_addr
    real_id, emp = buscar_empleado_por_id_o_rfid(emp_id)

    if not emp:
        log_event(ip_origen, f"Consulta fallida: {emp_id} no registrado")
        return jsonify({"error": f"El ID o tarjeta {emp_id} no esta registrado."}), 404

    log_event(ip_origen, f"Empleado {real_id} consultado exitosamente.")
    return jsonify({
        "empleado_id": real_id,
        "nombre": emp.get("nombre", ""),
        "apellido": emp.get("apellido", ""),
        "area": emp.get("area", "OPERACIONES").upper(),
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
    departamento = str(data.get("area") or data.get("departamento") or "OPERACIONES").strip().upper().replace("Í", "I")
    rfid = str(data.get("rfid", "")).strip().upper()
    vector_list = data.get("vector_facial", [])

    if not emp_id or not vector_list:
        return jsonify({"error": "Datos incompletos para enrolamiento."}), 400

    empleados = load_catalog(EMPLEADOS_FILE)
    datos_previos = empleados.get(emp_id, {})
    
    empleados[emp_id] = {
        **datos_previos,
        "nombre": nombre if nombre != f"Colaborador {emp_id}" else datos_previos.get("nombre", nombre),
        "apellido": apellido or datos_previos.get("apellido", ""),
        "area": departamento,
        "rfid": rfid or datos_previos.get("rfid", ""),
        "vector_facial": vector_list
    }
    save_catalog(EMPLEADOS_FILE, empleados)
    log_event(ip_origen, f"Enrolamiento exitoso guardado en SQLite: {emp_id} ({nombre}) [RFID: {rfid}]")
    return jsonify({"mensaje": "Colaborador enrolado y consolidado correctamente"}), 201

# ==========================================
# MARCACIONES (PRIORIZA HORA DEL CLIENTE)
# ==========================================

@api_bp.route('/marcaciones', methods=['POST'])
def api_registrar_marcacion_json():
    ip_origen = request.remote_addr
    data = request.get_json(silent=True) or {}

    raw_id = str(data.get("empleado_id", "")).strip().upper()
    tipo = str(data.get("tipo_marcacion", "")).strip().upper()
    nota = str(data.get("nota", "")).strip()

    if not raw_id or not tipo:
        return jsonify({"error": "Parámetros incompletos."}), 400

    # Prioridad: Fecha y hora exacta registrada en el cliente biométrico
    fecha_hora_cliente = data.get("fecha_hora") or data.get("timestamp")
    if fecha_hora_cliente and str(fecha_hora_cliente).strip():
        fecha_hora = str(fecha_hora_cliente).strip()
    else:
        # Respaldo en caso de que un cliente antiguo no envíe el campo
        fecha_hora = time_sync.get_time_str()

    try:
        nombre, fecha_hora = registrar_marcacion(raw_id, tipo, fecha_hora, ip_origen, nota)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    log_event(ip_origen, f'Marcación registrada: {nombre} - {tipo} a las {fecha_hora}')
    return jsonify({'mensaje': f'Marcación de {tipo} registrada correctamente a las {fecha_hora}'}), 200


@api_bp.route('/historial/<emp_id>', methods=['GET'])
def api_historial_empleado(emp_id):
    real_id, _ = buscar_empleado_por_id_o_rfid(emp_id)
    historial = obtener_historial_empleado(real_id or emp_id)
    return jsonify({"historial": historial}), 200

# ==========================================
# RUTAS DE COMPATIBILIDAD Y SYNC INDIVIDUAL
# ==========================================

@api_bp.route('/sync/empleados', methods=['GET'])
def sync_empleados_resumen():
    empleados = load_catalog(EMPLEADOS_FILE)
    lista_sync = []
    for emp_id, info in empleados.items():
        lista_sync.append({
            "codigo": emp_id,
            "nombre": info.get("nombre", ""),
            "apellido": info.get("apellido", ""),
            "area": info.get("area", "").upper(),
            "rfid": info.get("rfid", ""),
            "tiene_biometria": len(info.get("vector_facial", [])) == 128
        })
    return jsonify({"status": "ok", "data": lista_sync})

@api_bp.route('/sync/biometria/<emp_id>', methods=['GET'])
def sync_biometria(emp_id):
    real_id, emp = buscar_empleado_por_id_o_rfid(emp_id)
    if emp and emp.get("vector_facial") and len(emp["vector_facial"]) == 128:
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
    if not session.get('usuario'): return jsonify([])
    from .planning import role
    if role() != 'admin':
        return jsonify([])
    return jsonify(list(console_logs))

@api_bp.route('/marcar', methods=['POST'])
def recibir_marcacion_texto():
    config = load_catalog(CONFIG_FILE)
    empleados = load_catalog(EMPLEADOS_FILE)
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

    # Si el cliente de texto plano envía un 3er parámetro con la fecha_hora
    if len(partes) >= 3 and partes[2].strip():
        fecha_hora = partes[2].strip()
    else:
        fecha_hora = time_sync.get_time_str()

    try:
        nombre_completo, fecha_hora = registrar_marcacion(raw_id, tipo, fecha_hora, ip_origen)
    except ValueError as error:
        return f'ERROR: {error}\n', 400
    return f'EXITO: {nombre_completo} - {tipo} a las {fecha_hora}\n', 200
