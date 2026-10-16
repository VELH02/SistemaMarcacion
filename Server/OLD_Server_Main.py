from flask import Flask, request, render_template, redirect, url_for, session, flash, Response, send_from_directory, jsonify
from collections import deque
import csv
import json
import os
import uuid
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'super_secreto_alicapsa_cambiar_en_produccion'

# Archivos y Directorios
DATA_FILE = 'marcaciones.csv'
CONFIG_FILE = 'config.json'
EMPLEADOS_FILE = 'empleados.json'
BIOMETRIA_FOLDER = 'biometria'

# Cola en memoria para la consola en tiempo real (mantiene los últimos 200 mensajes)
console_logs = deque(maxlen=200)

def log_event(ip, evento):
    """Guarda los eventos del servidor para mostrarlos en la consola del Admin"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    mensaje = f"[{timestamp}] [IP: {ip}] {evento}"
    console_logs.append(mensaje)
    print(mensaje) # También imprime en la terminal del sistema operativo

def init_files():
    # Crear carpeta para los .npy
    os.makedirs(BIOMETRIA_FOLDER, exist_ok=True) 

    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"puerto_escucha": 5000, "ips_permitidas": []}, f, indent=4)

    if not os.path.exists(EMPLEADOS_FILE):
        with open(EMPLEADOS_FILE, 'w') as f:
            json.dump({
                "EMP-001": {"nombre": "Pedro", "apellido": "Martinez", "area": "Produccion"},
                "EMP-002": {"nombre": "Maria", "apellido": "Gomez", "area": "Mantenimiento"}
            }, f, indent=4)

    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["ID_Registro", "ID_Personal", "Nombre", "Area", "Tipo", "Fecha_Hora", "IP_Origen", "Estado"])

init_files()

USUARIOS = {
    "produccion": {"pass": "1234", "area": "Produccion"},
    "mantenimiento": {"pass": "1234", "area": "Mantenimiento"},
    "saneamiento": {"pass": "1234", "area": "Saneamiento"},
    "operaciones": {"pass": "1234", "area": "Operaciones"},
    "logistica": {"pass": "1234", "area": "Logistica"},
    "admin": {"pass": "admin", "area": "Todas"}
}

def load_json(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

def save_json(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# RUTAS DE INTERFAZ WEB
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('usuario').lower()
        password = request.form.get('password')
        if user in USUARIOS and USUARIOS[user]['pass'] == password:
            session['usuario'] = user
            session['area'] = USUARIOS[user]['area']
            log_event("Local", f"Usuario '{user}' ha iniciado sesión.")
            return redirect(url_for('index'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    log_event("Local", f"Usuario '{session.get('usuario')}' cerró sesión.")
    session.clear()
    return redirect(url_for('login'))

def obtener_registros_agrupados(area_usuario, emp_id_filtro, fecha_inicio, fecha_fin):
    """Lee el CSV y agrupa Entrada y Salida por Colaborador y Fecha"""
    registros_diarios = {}
    
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if area_usuario != 'Todas' and row['Area'] != area_usuario: continue
                if emp_id_filtro and row['ID_Personal'] != emp_id_filtro: continue

                try:
                    fecha_str, hora_str = row['Fecha_Hora'].split(' ')
                except ValueError:
                    continue # Saltar registros corruptos

                if fecha_inicio and fecha_str < fecha_inicio: continue
                if fecha_fin and fecha_str > fecha_fin: continue

                key = (row['ID_Personal'], fecha_str)
                if key not in registros_diarios:
                    registros_diarios[key] = {
                        'id': row['ID_Personal'], 'nombre': row['Nombre'], 'area': row['Area'],
                        'fecha': fecha_str, 'entrada': None, 'salida': None
                    }

                # Tomar primera entrada y última salida del día
                if row['Tipo'] == 'ENTRADA':
                    if not registros_diarios[key]['entrada'] or hora_str < registros_diarios[key]['entrada']:
                        registros_diarios[key]['entrada'] = hora_str
                elif row['Tipo'] == 'SALIDA':
                    if not registros_diarios[key]['salida'] or hora_str > registros_diarios[key]['salida']:
                        registros_diarios[key]['salida'] = hora_str

    # Calcular totales
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

@app.route('/')
@login_required
def index():
    area_usuario = session.get('area')
    empleados = load_json(EMPLEADOS_FILE)

    emp_id = request.args.get('emp_id', '').strip()
    f_inicio = request.args.get('fecha_inicio', '').strip()
    f_fin = request.args.get('fecha_fin', '').strip()

    empleados_area = {k: v for k, v in empleados.items() if area_usuario == 'Todas' or v['area'] == area_usuario}
    marcaciones = obtener_registros_agrupados(area_usuario, emp_id, f_inicio, f_fin)

    return render_template('index.html', marcaciones=marcaciones, area=area_usuario, empleados=empleados_area, emp_id_filtro=emp_id, fecha_inicio=f_inicio, fecha_fin=f_fin)

@app.route('/exportar')
@login_required
def exportar():
    area_usuario = session.get('area')
    emp_id = request.args.get('emp_id', '').strip()
    f_inicio = request.args.get('fecha_inicio', '').strip()
    f_fin = request.args.get('fecha_fin', '').strip()

    marcaciones = obtener_registros_agrupados(area_usuario, emp_id, f_inicio, f_fin)
    log_event("Local", f"Usuario '{session.get('usuario')}' exportó un reporte a CSV.")

    def generate():
        yield "ID_Personal,Nombre,Area,Fecha,Hora_Entrada,Hora_Salida,Horas_Totales\n"
        for m in marcaciones:
            yield f"{m['id']},{m['nombre']},{m['area']},{m['fecha']},{m['entrada'] or 'N/A'},{m['salida'] or 'N/A'},{m['horas_totales']}\n"

    return Response(generate(), mimetype='text/csv', headers={"Content-Disposition": "attachment; filename=horas_trabajadas.csv"})

# ==========================================
# MÓDULO DE COLABORADORES
# ==========================================
@app.route('/colaboradores', methods=['GET', 'POST'])
@login_required
def gestion_colaboradores():
    empleados = load_json(EMPLEADOS_FILE)
    area_usuario = session.get('area')

    if request.method == 'POST':
        area_form = request.form.get('area')
        if area_usuario != 'Todas' and area_form != area_usuario:
            flash('No tienes permiso para crear empleados en otra área.', 'danger')
            return redirect(url_for('gestion_colaboradores'))

        emp_id = request.form.get('emp_id').strip().upper()
        nombre = request.form.get('nombre').strip()
        apellido = request.form.get('apellido').strip()

        archivo_npy = request.files.get('archivo_npy')
        if archivo_npy and archivo_npy.filename.endswith('.npy'):
            filename = secure_filename(f"{emp_id}.npy")
            archivo_npy.save(os.path.join(BIOMETRIA_FOLDER, filename))
            log_event("Local", f"Archivo biométrico guardado para {emp_id}")

        empleados[emp_id] = {
            "nombre": nombre,
            "apellido": apellido,
            "area": area_form
        }
        save_json(EMPLEADOS_FILE, empleados)
        log_event("Local", f"Colaborador {emp_id} ({nombre} {apellido}) creado/actualizado.")
        flash(f'Colaborador {emp_id} guardado correctamente.', 'success')
        return redirect(url_for('gestion_colaboradores'))

    mis_empleados = {k: v for k, v in empleados.items() if area_usuario == 'Todas' or v['area'] == area_usuario}
    return render_template('colaboradores.html', empleados=mis_empleados)

@app.route('/config', methods=['GET', 'POST'])
@login_required
def configuracion():
    if session.get('area') != 'Todas':
        flash('Solo el administrador puede acceder a configuración.', 'danger')
        return redirect(url_for('index'))

    config = load_json(CONFIG_FILE)
    if request.method == 'POST':
        puerto = request.form.get('puerto')
        ips = request.form.get('ips')
        save_json(CONFIG_FILE, {"puerto_escucha": int(puerto), "ips_permitidas": [ip.strip() for ip in ips.split(',') if ip.strip()]})
        log_event("Local", "El administrador actualizó la configuración de IPs y Puertos.")
        flash('Configuración guardada.', 'success')
        return redirect(url_for('configuracion'))

    return render_template('config.html', config=config)

# ==========================================
# MÓDULO CONSOLA DE RED (ADMIN)
# ==========================================
@app.route('/consola')
@login_required
def consola():
    if session.get('area') != 'Todas':
        flash('Solo el administrador puede acceder a la consola.', 'danger')
        return redirect(url_for('index'))
    return render_template('consola.html')

@app.route('/api/logs')
@login_required
def get_logs():
    """API para obtener los logs en tiempo real mediante JavaScript"""
    if session.get('area') != 'Todas':
        return jsonify([])
    return jsonify(list(console_logs))

# ==========================================
# RUTA API PARA DISPOSITIVOS BIOMÉTRICOS (MARCACIONES)
# ==========================================
@app.route('/api/marcar', methods=['POST'])
def recibir_marcacion():
    config = load_json(CONFIG_FILE)
    empleados = load_json(EMPLEADOS_FILE)
    ip_origen = request.remote_addr

    datos_texto = request.get_data(as_text=True).strip()
    log_event(ip_origen, f"Trama entrante (HTTP POST): '{datos_texto}'")

    if config['ips_permitidas'] and ip_origen not in config['ips_permitidas']:
        log_event(ip_origen, "ACCESO DENEGADO - IP NO AUTORIZADA.")
        return "ERROR: IP no autorizada\n", 403

    if not datos_texto: 
        log_event(ip_origen, "ERROR: La petición no contiene datos de texto.")
        return "ERROR: No hay datos\n", 400

    partes = datos_texto.split(',')
    if len(partes) < 2: 
        log_event(ip_origen, "ERROR: Formato incorrecto. No contiene la coma separadora.")
        return "ERROR: Formato incorrecto. Se esperaba ID,TIPO\n", 400

    id_personal = partes[0].strip()
    tipo = partes[1].strip().upper()

    emp_info = empleados.get(id_personal, {"nombre": "Desconocido", "apellido": "", "area": "Sin Asignar"})
    nombre_completo = f"{emp_info['nombre']} {emp_info.get('apellido', '')}".strip()
    
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    id_registro = uuid.uuid4().hex[:8]

    with open(DATA_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([id_registro, id_personal, nombre_completo, emp_info['area'], tipo, fecha_hora, ip_origen, "Aprobado"])

    log_event(ip_origen, f"PROCESADO OK: {nombre_completo} - {tipo}")
    return f"EXITO: {nombre_completo} - {tipo} a las {fecha_hora}\n", 200

# ==========================================
# API PARA SINCRONIZACIÓN DE CLIENTES
# ==========================================
@app.route('/api/sync/empleados', methods=['GET'])
def sync_empleados():
    ip_origen = request.remote_addr
    log_event(ip_origen, "Cliente solicitó sincronización de lista de empleados (GET /api/sync/empleados)")
    
    empleados = load_json(EMPLEADOS_FILE)
    lista_sync = []
    for emp_id, info in empleados.items():
        lista_sync.append({
            "codigo": emp_id,
            "nombre": info.get("nombre", ""),
            "apellido": info.get("apellido", ""),
            "area": info.get("area", "")
        })
    return jsonify({"status": "ok", "data": lista_sync})

@app.route('/api/sync/biometria/<emp_id>', methods=['GET'])
def sync_biometria(emp_id):
    ip_origen = request.remote_addr
    log_event(ip_origen, f"Cliente solicitó descarga biométrica (.npy) de: {emp_id}")
    
    filename = f"{emp_id}.npy"
    if os.path.exists(os.path.join(BIOMETRIA_FOLDER, filename)):
        return send_from_directory(BIOMETRIA_FOLDER, filename)
    else:
        log_event(ip_origen, f"ERROR: Archivo {filename} no encontrado en el servidor.")
        return jsonify({"error": "Archivo biometrico no encontrado"}), 404

if __name__ == '__main__':
    config = load_json(CONFIG_FILE)
    puerto = config.get("puerto_escucha", 5000)
    log_event("Sistema", f"Iniciando Servidor Alicapsa en el puerto {puerto}")
    app.run(host='0.0.0.0', port=puerto, ssl_context='adhoc', debug=True)