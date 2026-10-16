import os
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.utils import secure_filename
from config import EMPLEADOS_FILE, CONFIG_FILE, AREAS_FILE, USUARIOS_FILE, BIOMETRIA_FOLDER
from storage import load_json, save_json, obtener_registros_agrupados
from logger import log_event

web_bp = Blueprint('web', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('web.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('usuario') != 'admin' and session.get('area') != 'TODAS':
            flash('Acceso restringido: requiere permisos de Administrador Principal.', 'danger')
            return redirect(url_for('web.index'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# AUTENTICACIÓN
# ==========================================

@web_bp.route('/login', methods=['GET', 'POST'])
def login():
    usuarios = load_json(USUARIOS_FILE)
    if request.method == 'POST':
        user = request.form.get('usuario', '').lower().strip()
        password = request.form.get('password', '').strip()
        if user in usuarios and usuarios[user]['pass'] == password:
            session['usuario'] = user
            session['area'] = usuarios[user]['area'].upper()
            log_event("Local", f"Usuario '{user}' ha iniciado sesión.")
            return redirect(url_for('web.index'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html', usuarios=usuarios)

@web_bp.route('/logout')
def logout():
    log_event("Local", f"Usuario '{session.get('usuario')}' cerró sesión.")
    session.clear()
    return redirect(url_for('web.login'))

# ==========================================
# ASISTENCIAS
# ==========================================

@web_bp.route('/')
@login_required
def index():
    area_usuario = session.get('area', 'TODAS').upper()
    empleados = load_json(EMPLEADOS_FILE)

    emp_id = request.args.get('emp_id', '').strip()
    f_inicio = request.args.get('fecha_inicio', '').strip()
    f_fin = request.args.get('fecha_fin', '').strip()

    usr_area = area_usuario.strip().upper().replace("Í", "I")
    empleados_area = {}
    for k, v in empleados.items():
        emp_area = v.get('area', '').strip().upper().replace("Í", "I")
        if usr_area == 'TODAS' or emp_area == usr_area:
            empleados_area[k] = v

    marcaciones = obtener_registros_agrupados(area_usuario, emp_id, f_inicio, f_fin)
    return render_template('index.html', marcaciones=marcaciones, area=area_usuario, empleados=empleados_area, emp_id_filtro=emp_id, fecha_inicio=f_inicio, fecha_fin=f_fin)

@web_bp.route('/exportar')
@login_required
def exportar():
    area_usuario = session.get('area', 'TODAS').upper()
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
# GESTIÓN DE COLABORADORES
# ==========================================

@web_bp.route('/colaboradores', methods=['GET', 'POST'])
@login_required
def gestion_colaboradores():
    empleados = load_json(EMPLEADOS_FILE)
    areas = load_json(AREAS_FILE)
    area_usuario = session.get('area', 'TODAS').upper()
    usr_area = area_usuario.strip().upper().replace("Í", "I")

    if request.method == 'POST':
        area_form = request.form.get('area', 'OPERACIONES').strip().upper().replace("Í", "I")
        if usr_area != 'TODAS' and area_form != usr_area:
            flash('No tienes permiso para crear colaboradores en otra área.', 'danger')
            return redirect(url_for('web.gestion_colaboradores'))

        emp_id = request.form.get('emp_id', '').strip().upper()
        nombre = request.form.get('nombre', '').strip()
        apellido = request.form.get('apellido', '').strip()

        if not emp_id or not nombre:
            flash('El código y el nombre son obligatorios.', 'danger')
            return redirect(url_for('web.gestion_colaboradores'))

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
        log_event("Local", f"Colaborador {emp_id} ({nombre} {apellido}) creado por {session.get('usuario')}.")
        flash(f'Colaborador {emp_id} guardado correctamente.', 'success')
        return redirect(url_for('web.gestion_colaboradores'))

    mis_empleados = {k: v for k, v in empleados.items() if usr_area == 'TODAS' or v.get('area', '').strip().upper().replace("Í", "I") == usr_area}
    return render_template('colaboradores.html', empleados=mis_empleados, areas=areas)

@web_bp.route('/colaboradores/editar/<emp_id>', methods=['POST'])
@login_required
def editar_colaborador(emp_id):
    empleados = load_json(EMPLEADOS_FILE)
    emp_id = str(emp_id).strip().upper()
    
    if emp_id in empleados:
        area_usuario = session.get('area', 'TODAS').upper()
        usr_area = area_usuario.strip().upper().replace("Í", "I")
        colab_area_actual = empleados[emp_id].get('area', '').strip().upper().replace("Í", "I")

        if usr_area != 'TODAS' and colab_area_actual != usr_area:
            flash('No tienes permiso para modificar colaboradores de otra área.', 'danger')
            return redirect(url_for('web.gestion_colaboradores'))

        nueva_area = request.form.get('area', colab_area_actual).strip().upper().replace("Í", "I")
        if usr_area != 'TODAS' and nueva_area != usr_area:
            flash('No puedes reasignar un colaborador fuera de tu área.', 'danger')
            return redirect(url_for('web.gestion_colaboradores'))

        empleados[emp_id]['nombre'] = request.form.get('nombre', '').strip()
        empleados[emp_id]['apellido'] = request.form.get('apellido', '').strip()
        empleados[emp_id]['area'] = nueva_area
        
        archivo_npy = request.files.get('archivo_npy')
        if archivo_npy and archivo_npy.filename.endswith('.npy'):
            filename = secure_filename(f"{emp_id}.npy")
            archivo_npy.save(os.path.join(BIOMETRIA_FOLDER, filename))
            log_event("Local", f"Biometría actualizada para {emp_id}")

        save_json(EMPLEADOS_FILE, empleados)
        log_event("Local", f"Colaborador {emp_id} editado exitosamente.")
        flash(f'Colaborador {emp_id} actualizado correctamente.', 'success')
    else:
        flash('Colaborador no encontrado.', 'danger')

    return redirect(url_for('web.gestion_colaboradores'))

@web_bp.route('/colaboradores/eliminar/<emp_id>', methods=['POST'])
@login_required
def eliminar_colaborador(emp_id):
    empleados = load_json(EMPLEADOS_FILE)
    emp_id = str(emp_id).strip().upper()

    if emp_id not in empleados:
        flash('Colaborador no encontrado.', 'danger')
        return redirect(url_for('web.gestion_colaboradores'))

    area_usuario = session.get('area', 'TODAS').upper()
    usr_area = area_usuario.strip().upper().replace("Í", "I")
    colab_area = empleados[emp_id].get('area', '').strip().upper().replace("Í", "I")

    if usr_area != 'TODAS' and colab_area != usr_area:
        flash('No tienes permiso para eliminar colaboradores de otra área.', 'danger')
        return redirect(url_for('web.gestion_colaboradores'))

    nombre_completo = f"{empleados[emp_id].get('nombre', '')} {empleados[emp_id].get('apellido', '')}".strip()
    del empleados[emp_id]
    save_json(EMPLEADOS_FILE, empleados)

    # Eliminar archivo biométrico (.npy) si existe
    ruta_npy = os.path.join(BIOMETRIA_FOLDER, f"{emp_id}.npy")
    if os.path.exists(ruta_npy):
        try:
            os.remove(ruta_npy)
            log_event("Local", f"Biometría {emp_id}.npy eliminada del disco.")
        except Exception as e:
            log_event("Local", f"Error eliminando biometría de {emp_id}: {e}")

    log_event("Local", f"Colaborador {emp_id} ({nombre_completo}) eliminado por {session.get('usuario')}.")
    flash(f'Colaborador {emp_id} ({nombre_completo}) eliminado permanentemente.', 'success')
    return redirect(url_for('web.gestion_colaboradores'))

# ==========================================
# ADMINISTRACIÓN DE ÁREAS (SÓLO ADMIN)
# ==========================================

@web_bp.route('/admin/areas')
@login_required
@admin_required
def admin_areas():
    areas = load_json(AREAS_FILE)
    empleados = load_json(EMPLEADOS_FILE)
    conteo_empleados = {}
    for a in areas:
        conteo_empleados[a] = sum(1 for e in empleados.values() if e.get('area', '').strip().upper().replace("Í", "I") == a)
    return render_template('areas.html', areas=areas, conteo=conteo_empleados)

@web_bp.route('/admin/areas/crear', methods=['POST'])
@login_required
@admin_required
def crear_area():
    areas = load_json(AREAS_FILE)
    nueva_area = request.form.get('nombre_area', '').strip().upper().replace("Í", "I")
    
    if not nueva_area:
        flash('El nombre del área es requerido.', 'danger')
    elif nueva_area in areas or nueva_area == 'TODAS':
        flash('El área ingresada ya existe.', 'warning')
    else:
        areas.append(nueva_area)
        save_json(AREAS_FILE, sorted(areas))
        log_event("Local", f"Nueva área creada: {nueva_area}")
        flash(f'Área {nueva_area} creada exitosamente.', 'success')
    return redirect(url_for('web.admin_areas'))

@web_bp.route('/admin/areas/editar/<area_actual>', methods=['POST'])
@login_required
@admin_required
def editar_area(area_actual):
    areas = load_json(AREAS_FILE)
    empleados = load_json(EMPLEADOS_FILE)
    usuarios = load_json(USUARIOS_FILE)

    area_actual = area_actual.strip().upper().replace("Í", "I")
    nuevo_nombre = request.form.get('nombre_area', '').strip().upper().replace("Í", "I")

    if not nuevo_nombre:
        flash('El nombre del área no puede estar vacío.', 'danger')
        return redirect(url_for('web.admin_areas'))

    if nuevo_nombre in areas and nuevo_nombre != area_actual:
        flash('Ya existe otra área con ese nombre.', 'warning')
        return redirect(url_for('web.admin_areas'))

    if area_actual in areas:
        idx = areas.index(area_actual)
        areas[idx] = nuevo_nombre
        save_json(AREAS_FILE, sorted(areas))

        # Actualización en cascada para colaboradores
        for emp in empleados.values():
            if emp.get('area', '').strip().upper().replace("Í", "I") == area_actual:
                emp['area'] = nuevo_nombre
        save_json(EMPLEADOS_FILE, empleados)

        # Actualización en cascada para usuarios asignados
        for u in usuarios.values():
            if u.get('area', '').strip().upper().replace("Í", "I") == area_actual:
                u['area'] = nuevo_nombre
        save_json(USUARIOS_FILE, usuarios)

        log_event("Local", f"Área renombrada de {area_actual} a {nuevo_nombre}")
        flash(f'Área renombrada a {nuevo_nombre}. Se actualizaron colaboradores y administradores asociados.', 'success')

    return redirect(url_for('web.admin_areas'))

@web_bp.route('/admin/areas/eliminar/<area_nombre>', methods=['POST'])
@login_required
@admin_required
def eliminar_area(area_nombre):
    areas = load_json(AREAS_FILE)
    empleados = load_json(EMPLEADOS_FILE)
    area_nombre = area_nombre.strip().upper().replace("Í", "I")

    # Validación: no permitir borrar áreas que contengan colaboradores
    tiene_empleados = any(e.get('area', '').strip().upper().replace("Í", "I") == area_nombre for e in empleados.values())
    if tiene_empleados:
        flash(f'No se puede eliminar el área {area_nombre} porque tiene colaboradores asignados. Reasígnalos primero.', 'danger')
        return redirect(url_for('web.admin_areas'))

    if area_nombre in areas:
        areas.remove(area_nombre)
        save_json(AREAS_FILE, areas)
        log_event("Local", f"Área eliminada: {area_nombre}")
        flash(f'Área {area_nombre} eliminada.', 'success')

    return redirect(url_for('web.admin_areas'))

# ==========================================
# GESTIÓN DE USUARIOS (SÓLO ADMIN)
# ==========================================

@web_bp.route('/admin/usuarios')
@login_required
@admin_required
def admin_usuarios():
    usuarios = load_json(USUARIOS_FILE)
    areas = load_json(AREAS_FILE)
    return render_template('usuarios.html', usuarios=usuarios, areas=areas)

@web_bp.route('/admin/usuarios/crear', methods=['POST'])
@login_required
@admin_required
def crear_usuario():
    usuarios = load_json(USUARIOS_FILE)
    usuario = request.form.get('usuario', '').lower().strip()
    nombre = request.form.get('nombre', '').strip()
    password = request.form.get('password', '').strip()
    area = request.form.get('area', '').strip().upper().replace("Í", "I")

    if not usuario or not password or not area:
        flash('Todos los campos son obligatorios.', 'danger')
    elif usuario in usuarios:
        flash(f'El nombre de usuario "{usuario}" ya existe.', 'warning')
    else:
        usuarios[usuario] = {
            "nombre": nombre or usuario.capitalize(),
            "pass": password,
            "area": area
        }
        save_json(USUARIOS_FILE, usuarios)
        log_event("Local", f"Nuevo usuario creado: {usuario} asignado a {area}")
        flash(f'Usuario "{usuario}" creado con éxito.', 'success')

    return redirect(url_for('web.admin_usuarios'))

@web_bp.route('/admin/usuarios/editar/<username>', methods=['POST'])
@login_required
@admin_required
def editar_usuario(username):
    usuarios = load_json(USUARIOS_FILE)
    username = username.lower().strip()

    if username in usuarios:
        nueva_area = request.form.get('area', '').strip().upper().replace("Í", "I")
        nuevo_nombre = request.form.get('nombre', '').strip()

        if username == 'admin' and nueva_area != 'TODAS':
            flash('El usuario admin principal no puede perder el alcance global (TODAS).', 'danger')
            return redirect(url_for('web.admin_usuarios'))

        usuarios[username]['area'] = nueva_area
        if nuevo_nombre:
            usuarios[username]['nombre'] = nuevo_nombre

        save_json(USUARIOS_FILE, usuarios)
        log_event("Local", f"Usuario {username} actualizado (Área: {nueva_area})")
        flash(f'Datos del usuario "{username}" actualizados.', 'success')

    return redirect(url_for('web.admin_usuarios'))

@web_bp.route('/admin/usuarios/reset_password/<username>', methods=['POST'])
@login_required
@admin_required
def reset_password_usuario(username):
    usuarios = load_json(USUARIOS_FILE)
    username = username.lower().strip()
    nueva_pass = request.form.get('nueva_password', '').strip()

    if not nueva_pass:
        flash('La contraseña no puede estar en blanco.', 'danger')
    elif username in usuarios:
        usuarios[username]['pass'] = nueva_pass
        save_json(USUARIOS_FILE, usuarios)
        log_event("Local", f"Contraseña restablecida para el usuario {username}")
        flash(f'Contraseña actualizada para el usuario "{username}".', 'success')

    return redirect(url_for('web.admin_usuarios'))

@web_bp.route('/admin/usuarios/eliminar/<username>', methods=['POST'])
@login_required
@admin_required
def eliminar_usuario(username):
    usuarios = load_json(USUARIOS_FILE)
    username = username.lower().strip()

    if username == 'admin':
        flash('No se puede eliminar el usuario administrador maestro.', 'danger')
        return redirect(url_for('web.admin_usuarios'))

    if username in usuarios:
        del usuarios[username]
        save_json(USUARIOS_FILE, usuarios)
        log_event("Local", f"Usuario eliminado: {username}")
        flash(f'Usuario "{username}" eliminado del sistema.', 'success')

    return redirect(url_for('web.admin_usuarios'))

# ==========================================
# CONFIGURACIÓN Y CONSOLA DE RED
# ==========================================

@web_bp.route('/config', methods=['GET', 'POST'])
@login_required
@admin_required
def configuracion():
    import time_sync
    config = load_json(CONFIG_FILE)
    if request.method == 'POST':
        puerto = request.form.get('puerto')
        ips = request.form.get('ips')
        servidor_ntp = request.form.get('servidor_ntp', 'pool.ntp.org').strip()
        
        save_json(CONFIG_FILE, {
            "puerto_escucha": int(puerto),
            "ips_permitidas": [ip.strip() for ip in ips.split(',') if ip.strip()],
            "servidor_ntp": servidor_ntp
        })
        
        # Intentar sincronizar con el nuevo servidor configurado
        time_sync.sincronizar_ntp(servidor_ntp)
        log_event("Local", f"Configuración guardada. Servidor NTP asignado: {servidor_ntp}")
        flash('Configuración y servidor de tiempo actualizados.', 'success')
        return redirect(url_for('web.configuracion'))

    return render_template('config.html', config=config, estado_ntp=time_sync.estado_sync)

@web_bp.route('/config/sync_ntp', methods=['POST'])
@login_required
@admin_required
def forzar_sync_ntp():
    import time_sync
    config = load_json(CONFIG_FILE)
    servidor_ntp = config.get('servidor_ntp', 'pool.ntp.org')
    ok, mensaje = time_sync.sincronizar_ntp(servidor_ntp)
    if ok:
        flash(f'✓ {mensaje}', 'success')
    else:
        flash(f'⚠️ {mensaje}', 'danger')
    return redirect(url_for('web.configuracion'))

@web_bp.route('/consola')
@login_required
@admin_required
def consola():
    return render_template('consola.html')