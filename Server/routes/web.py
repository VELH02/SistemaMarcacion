import io
import unicodedata
from datetime import date, timedelta
from functools import wraps
from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import numpy as np

from config import EMPLEADOS_FILE, CONFIG_FILE, AREAS_FILE, USUARIOS_FILE
from storage import (
    load_catalog, save_catalog, 
    actualizar_codigo_empleado_sistema, guardar_o_actualizar_marcacion_diaria
)
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
        from .planning import role
        if role() != 'admin':
            flash('Acceso restringido: requiere permisos de Administrador Principal.', 'danger')
            return redirect(url_for('web.index'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# GENERADORES DE EXCEL (.XLSX)
# ==========================================

def preparar_excel(titulo, headers):
    wb = Workbook()
    ws = wb.active
    ws.title = titulo
    ws.append(headers)
    fill_header = PatternFill(start_color="184828", end_color="184828", fill_type="solid")
    font_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    font_body = Font(name="Segoe UI", size=10)
    border_thin = Border(
        left=Side(style='thin', color='D3DFD6'), right=Side(style='thin', color='D3DFD6'),
        top=Side(style='thin', color='D3DFD6'), bottom=Side(style='thin', color='D3DFD6')
    )

    ws.row_dimensions[1].height = 26
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = fill_header
        cell.font = font_header
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border_thin

    return wb, ws, font_body, border_thin


def finalizar_excel(wb, ws):
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

# ==========================================
# AUTENTICACIÓN
# ==========================================

@web_bp.route('/login', methods=['GET', 'POST'])
def login():
    usuarios = load_catalog(USUARIOS_FILE)
    if request.method == 'POST':
        user = request.form.get('usuario', '').lower().strip()
        password = request.form.get('password', '').strip()
        if user in usuarios and usuarios[user]['pass'] == password:
            session['usuario'] = user
            session['area'] = usuarios[user]['area'].upper()
            session['rol'] = usuarios[user].get('rol', 'admin' if user == 'admin' or session['area'] == 'TODAS' else 'coordinador')
            log_event("Local", f"Usuario '{user}' ha iniciado sesión.")
            return redirect(url_for('web.gestion_colaboradores' if session['rol']=='rrhh' else 'web.index'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html', usuarios=usuarios)

@web_bp.route('/logout')
def logout():
    log_event("Local", f"Usuario '{session.get('usuario')}' cerró sesión.")
    session.clear()
    return redirect(url_for('web.login'))

# ==========================================
# ASISTENCIAS Y EXPORTACIONES
# ==========================================

@web_bp.route('/')
@login_required
def index():
    from .planning import coordinator_only
    coordinator_only()
    area_usuario = session.get('area', 'TODAS').upper()
    empleados = load_catalog(EMPLEADOS_FILE)
    emp_id = request.args.get('emp_id', '').strip()
    f_inicio = request.args.get('fecha_inicio', '').strip()
    f_fin = request.args.get('fecha_fin', '').strip()

    usr_area = area_usuario.strip().upper().replace("Í", "I")
    empleados_area = {k: v for k, v in empleados.items() if usr_area == 'TODAS' or v.get('area', '').strip().upper().replace("Í", "I") == usr_area}

    from planning import report, today
    if not f_inicio or not f_fin:
        f_fin = today().date().isoformat()
        f_inicio = (today().date() - timedelta(days=14)).isoformat()
    try:
        marcaciones = report(area_usuario, emp_id, f_inicio, f_fin)
    except ValueError as error:
        return str(error), 400
    # Actual markings first, ordered by the latest event, including overnight exits.
    marcaciones.sort(key=lambda row: (bool(row.get('entrada_fecha') or row.get('salida_fecha')),
        max(row.get('entrada_fecha',''),row.get('salida_fecha','')) or row['fecha'],row['fecha'],row['id']),reverse=True)
    return render_template('index.html', marcaciones=marcaciones, area=area_usuario, empleados=empleados_area, emp_id_filtro=emp_id, fecha_inicio=f_inicio, fecha_fin=f_fin)

@web_bp.route('/marcaciones/guardar_ajuste', methods=['POST'])
@login_required
def guardar_ajuste_marcacion():
    from .planning import coordinator_only
    coordinator_only()
    area_usuario = session.get('area', 'TODAS').upper()
    usr_area = area_usuario.strip().upper().replace("Í", "I")

    emp_id = request.form.get('emp_id', '').strip().upper()
    fecha = request.form.get('fecha', '').strip()
    hora_entrada = request.form.get('hora_entrada', '').strip()
    hora_salida = request.form.get('hora_salida', '').strip()

    empleados = load_catalog(EMPLEADOS_FILE)
    if emp_id not in empleados:
        flash('Colaborador no encontrado.', 'danger')
        return redirect(url_for('web.index'))

    emp_area = empleados[emp_id].get('area', '').strip().upper().replace("Í", "I")
    if usr_area != 'TODAS' and emp_area != usr_area:
        flash('No tienes permiso para modificar marcaciones de otra área.', 'danger')
        return redirect(url_for('web.index'))

    if not fecha or (not hora_entrada and not hora_salida):
        flash('Datos incompletos.', 'warning')
        return redirect(url_for('web.index'))

    usuario_actual = session.get('usuario', 'Admin')
    try:
        guardar_o_actualizar_marcacion_diaria(emp_id, fecha, hora_entrada, hora_salida, usuario_actual)
    except ValueError as error:
        return str(error), 400
    log_event("Local", f"Marcación ajustada para {emp_id} el día {fecha} por {usuario_actual}")
    flash(f'Marcación del colaborador {emp_id} para el día {fecha} guardada correctamente.', 'success')
    return redirect(url_for('web.index'))

@web_bp.route('/colaboradores', methods=['GET', 'POST'])
@login_required
def gestion_colaboradores():
    from .planning import collaborator_access
    collaborator_access()
    empleados = load_catalog(EMPLEADOS_FILE)
    areas = load_catalog(AREAS_FILE)
    area_usuario = session.get('area', 'TODAS').upper()
    usr_area = area_usuario.strip().upper().replace("Í", "I")

    if request.method == 'POST':
        area_form = request.form.get('area', 'OPERACIONES').strip().upper().replace("Í", "I")
        if usr_area != 'TODAS' and area_form != usr_area:
            from flask import abort
            abort(403)
        if area_form not in areas:
            return 'Seleccione un área registrada',400

        emp_id = request.form.get('emp_id', '').strip().upper()
        nombre = request.form.get('nombre', '').strip()
        apellido = request.form.get('apellido', '').strip()
        rfid = request.form.get('rfid', '').strip().upper()

        if not emp_id or not nombre:
            flash('El código y el nombre son obligatorios.', 'danger')
            return redirect(url_for('web.gestion_colaboradores'))

        if emp_id in empleados:
            flash(f'El código {emp_id} ya se encuentra registrado para otro colaborador.', 'danger')
            return redirect(url_for('web.gestion_colaboradores'))

        vector_facial = []
        archivo_npy = request.files.get('archivo_npy')
        if archivo_npy and archivo_npy.filename.endswith('.npy'):
            try:
                archivo_npy.seek(0)
                matriz = np.load(archivo_npy)
                vector_facial = matriz.tolist()
                log_event("Local", f"Vector biométrico integrado en JSON para {emp_id}")
            except Exception as e:
                flash(f'No se pudo leer la matriz del archivo .npy: {e}', 'warning')

        hiring = request.form.get('fecha_ingreso', '').strip()
        try:
            if hiring: date.fromisoformat(hiring)
        except ValueError: return 'Fecha de ingreso inválida', 400
        empleados[emp_id] = {
            'fecha_ingreso': hiring,
            "nombre": nombre, "apellido": apellido, "area": area_form, "rfid": rfid, "vector_facial": vector_facial
        }
        try: save_catalog(EMPLEADOS_FILE, empleados)
        except ValueError as error: return str(error),400
        import database, planning
        with database.transaction() as db:
            planning.audit(db,emp_id,planning.today().date().isoformat(),'ALTA_COLABORADOR',None,
                dict(nombre=nombre,apellido=apellido,area=area_form),session['usuario'])
        log_event("Local", f"Colaborador {emp_id} ({nombre} {apellido}) creado por {session.get('usuario')}.")
        flash(f'Colaborador {emp_id} guardado correctamente.', 'success')
        return redirect(url_for('web.gestion_colaboradores'))

    mis_empleados = {k: v for k, v in empleados.items() if usr_area == 'TODAS' or v.get('area', '').strip().upper().replace("Í", "I") == usr_area}
    areas_filtro = areas if usr_area == 'TODAS' else [usr_area]
    busqueda = request.args.get('q', '').strip()
    filtro_area = request.args.get('area', '').strip().upper().replace('Í', 'I')
    filtro_biometria = request.args.get('biometria', '')
    if len(busqueda)>200 or filtro_biometria not in ('', 'registrada', 'pendiente'):
        return 'Filtro de colaboradores inválido',400
    if filtro_area and filtro_area not in areas_filtro:
        return 'Área fuera del alcance del usuario',403

    def texto(valor):
        return ''.join(c for c in unicodedata.normalize('NFKD',str(valor or '')).casefold() if not unicodedata.combining(c))

    palabras = texto(busqueda).split()
    resultados = []
    for code, emp in mis_empleados.items():
        if filtro_area and emp.get('area','').strip().upper().replace('Í','I') != filtro_area: continue
        registrada = bool(emp.get('vector_facial'))
        if filtro_biometria and registrada != (filtro_biometria=='registrada'): continue
        contenido = texto(' '.join(str(value or '') for value in (code,emp.get('nombre'),emp.get('apellido'),emp.get('rfid'))))
        if all(palabra in contenido for palabra in palabras): resultados.append((code,emp))
    resultados.sort(key=lambda item:(texto(item[1].get('nombre')),texto(item[1].get('apellido')),item[0]))
    total = len(resultados)
    por_pagina = 25
    paginas = max(1,(total+por_pagina-1)//por_pagina)
    pagina = min(paginas,max(1,request.args.get('pagina',1,type=int)))
    inicio = (pagina-1)*por_pagina
    return render_template('colaboradores.html', empleados=dict(resultados[inicio:inicio+por_pagina]), areas=areas,
        areas_filtro=areas_filtro,busqueda=busqueda,filtro_area=filtro_area,filtro_biometria=filtro_biometria,
        total_filtrados=total,total_area=len(mis_empleados),pagina=pagina,paginas=paginas,
        desde=inicio+1 if total else 0,hasta=min(inicio+por_pagina,total))

@web_bp.route('/colaboradores/editar/<emp_id>', methods=['POST'])
@login_required
def editar_colaborador(emp_id):
    from .planning import hr_only
    hr_only()
    empleados = load_catalog(EMPLEADOS_FILE)
    emp_id = str(emp_id).strip().upper()
    
    if emp_id in empleados:
        area_usuario = session.get('area', 'TODAS').upper()
        usr_area = area_usuario.strip().upper().replace("Í", "I")
        colab_area_actual = empleados[emp_id].get('area', '').strip().upper().replace("Í", "I")

        if usr_area != 'TODAS' and colab_area_actual != usr_area:
            flash('No tienes permiso para modificar colaboradores de otra área.', 'danger')
            return redirect(url_for('web.gestion_colaboradores'))

        nuevo_codigo = request.form.get('nuevo_emp_id', emp_id).strip().upper()
        nombre = request.form.get('nombre', '').strip()
        apellido = request.form.get('apellido', '').strip()
        rfid = request.form.get('rfid', '').strip().upper()
        nueva_area = request.form.get('area', colab_area_actual).strip().upper().replace("Í", "I")

        if not nuevo_codigo or not nombre:
            flash('El código y el nombre no pueden quedar vacíos.', 'danger')
            return redirect(url_for('web.gestion_colaboradores'))

        if nuevo_codigo != emp_id and nuevo_codigo in empleados:
            flash(f'El código "{nuevo_codigo}" ya está asignado a otro colaborador.', 'danger')
            return redirect(url_for('web.gestion_colaboradores'))

        if usr_area != 'TODAS' and nueva_area != usr_area:
            flash('No puedes reasignar un colaborador fuera de tu área.', 'danger')
            return redirect(url_for('web.gestion_colaboradores'))

        nuevo_vector = None
        archivo_npy = request.files.get('archivo_npy')
        if archivo_npy and archivo_npy.filename.endswith('.npy'):
            try:
                archivo_npy.seek(0)
                matriz = np.load(archivo_npy)
                nuevo_vector = matriz.tolist()
                log_event("Local", f"Vector biométrico actualizado en JSON para {nuevo_codigo}")
            except Exception as e:
                flash(f'Error al procesar archivo .npy: {e}', 'warning')

        hiring = request.form.get('fecha_ingreso', empleados[emp_id].get('fecha_ingreso','')).strip()
        try:
            if hiring: date.fromisoformat(hiring)
        except ValueError: return 'Fecha de ingreso inválida', 400
        try: actualizar_codigo_empleado_sistema(emp_id, nuevo_codigo, nombre, apellido, nueva_area, rfid, nuevo_vector)
        except ValueError as error: return str(error),400
        updated = load_catalog(EMPLEADOS_FILE)
        updated[nuevo_codigo]['fecha_ingreso'] = hiring
        save_catalog(EMPLEADOS_FILE, updated)
        log_event("Local", f"Colaborador {emp_id} actualizado (Código final: {nuevo_codigo}).")
        flash(f'Colaborador {nuevo_codigo} actualizado correctamente.', 'success')
    else:
        flash('Colaborador no encontrado.', 'danger')
    return redirect(url_for('web.gestion_colaboradores'))

@web_bp.route('/colaboradores/eliminar/<emp_id>', methods=['POST'])
@login_required
def eliminar_colaborador(emp_id):
    from .planning import collaborator_access
    collaborator_access()
    empleados = load_catalog(EMPLEADOS_FILE)
    emp_id = str(emp_id).strip().upper()

    if emp_id not in empleados:
        flash('Colaborador no encontrado.', 'danger')
        return redirect(url_for('web.gestion_colaboradores'))

    area_usuario = session.get('area', 'TODAS').upper()
    usr_area = area_usuario.strip().upper().replace("Í", "I")
    colab_area = empleados[emp_id].get('area', '').strip().upper().replace("Í", "I")

    if usr_area != 'TODAS' and colab_area != usr_area:
        from flask import abort
        abort(403)

    nombre_completo = f"{empleados[emp_id].get('nombre', '')} {empleados[emp_id].get('apellido', '')}".strip()
    previous={key:empleados[emp_id].get(key,'') for key in ('nombre','apellido','area','fecha_ingreso')}
    from terminal import archive
    archive(emp_id,empleados[emp_id],session['usuario'])
    del empleados[emp_id]
    save_catalog(EMPLEADOS_FILE, empleados)
    import database, planning
    with database.transaction() as db:
        planning.audit(db,emp_id,planning.today().date().isoformat(),'BAJA_COLABORADOR',previous,None,session['usuario'])

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
    areas = load_catalog(AREAS_FILE)
    empleados = load_catalog(EMPLEADOS_FILE)
    conteo_empleados = {a: sum(1 for e in empleados.values() if e.get('area', '').strip().upper().replace("Í", "I") == a) for a in areas}
    return render_template('areas.html', areas=areas, conteo=conteo_empleados)

@web_bp.route('/admin/areas/crear', methods=['POST'])
@login_required
@admin_required
def crear_area():
    areas = load_catalog(AREAS_FILE)
    nueva_area = request.form.get('nombre_area', '').strip().upper().replace("Í", "I")
    
    if not nueva_area: flash('El nombre del área es requerido.', 'danger')
    elif nueva_area in areas or nueva_area == 'TODAS': flash('El área ingresada ya existe.', 'warning')
    else:
        areas.append(nueva_area)
        save_catalog(AREAS_FILE, sorted(areas))
        log_event("Local", f"Nueva área creada: {nueva_area}")
        flash(f'Área {nueva_area} creada exitosamente.', 'success')
    return redirect(url_for('web.admin_areas'))

@web_bp.route('/admin/areas/editar/<area_actual>', methods=['POST'])
@login_required
@admin_required
def editar_area(area_actual):
    areas = load_catalog(AREAS_FILE)
    empleados = load_catalog(EMPLEADOS_FILE)
    usuarios = load_catalog(USUARIOS_FILE)

    area_actual = area_actual.strip().upper().replace("Í", "I")
    nuevo_nombre = request.form.get('nombre_area', '').strip().upper().replace("Í", "I")

    if not nuevo_nombre:
        flash('El nombre del área no puede estar vacío.', 'danger')
        return redirect(url_for('web.admin_areas'))
    if nuevo_nombre == 'TODAS':
        return 'TODAS es un alcance reservado, no un área', 400

    if nuevo_nombre in areas and nuevo_nombre != area_actual:
        flash('Ya existe otra área con ese nombre.', 'warning')
        return redirect(url_for('web.admin_areas'))

    if area_actual in areas:
        idx = areas.index(area_actual)
        areas[idx] = nuevo_nombre
        save_catalog(AREAS_FILE, sorted(areas))

        for emp in empleados.values():
            if emp.get('area', '').strip().upper().replace("Í", "I") == area_actual: emp['area'] = nuevo_nombre
        save_catalog(EMPLEADOS_FILE, empleados)

        for u in usuarios.values():
            if u.get('area', '').strip().upper().replace("Í", "I") == area_actual: u['area'] = nuevo_nombre
        save_catalog(USUARIOS_FILE, usuarios)

        log_event("Local", f"Área renombrada de {area_actual} a {nuevo_nombre}")
        flash(f'Área renombrada a {nuevo_nombre}. Se actualizaron colaboradores y administradores asociados.', 'success')
    return redirect(url_for('web.admin_areas'))

@web_bp.route('/admin/areas/eliminar/<area_nombre>', methods=['POST'])
@login_required
@admin_required
def eliminar_area(area_nombre):
    areas = load_catalog(AREAS_FILE)
    empleados = load_catalog(EMPLEADOS_FILE)
    area_nombre = area_nombre.strip().upper().replace("Í", "I")

    if any(u.get('area','').strip().upper().replace('Í','I')==area_nombre for u in load_catalog(USUARIOS_FILE).values()):
        flash('Reasigne primero los usuarios asociados a esta área.', 'danger')
        return redirect(url_for('web.admin_areas'))

    if any(e.get('area', '').strip().upper().replace("Í", "I") == area_nombre for e in empleados.values()):
        flash(f'No se puede eliminar el área {area_nombre} porque tiene colaboradores asignados. Reasígnalos primero.', 'danger')
        return redirect(url_for('web.admin_areas'))

    if area_nombre in areas:
        areas.remove(area_nombre)
        save_catalog(AREAS_FILE, areas)
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
    return render_template('usuarios.html', usuarios=load_catalog(USUARIOS_FILE), areas=load_catalog(AREAS_FILE))

@web_bp.route('/admin/usuarios/crear', methods=['POST'])
@login_required
@admin_required
def crear_usuario():
    usuarios = load_catalog(USUARIOS_FILE)
    usuario = request.form.get('usuario', '').lower().strip()
    nombre = request.form.get('nombre', '').strip()
    password = request.form.get('password', '').strip()
    area = request.form.get('area', '').strip().upper().replace("Í", "I")

    rol = request.form.get('rol', 'coordinador')
    if rol not in ('admin', 'rrhh', 'coordinador'): return 'Rol inválido', 400
    if rol in ('admin', 'rrhh'): area = 'TODAS'
    if rol == 'coordinador' and area == 'TODAS': return 'Seleccione el área del coordinador', 400
    if rol == 'coordinador' and area not in load_catalog(AREAS_FILE): return 'El área debe ser creada primero por el administrador', 400
    if not usuario or not password or not area: flash('Todos los campos son obligatorios.', 'danger')
    elif usuario in usuarios: flash(f'El nombre de usuario "{usuario}" ya existe.', 'warning')
    else:
        usuarios[usuario] = {"nombre": nombre or usuario.capitalize(), "pass": password, "area": area, "rol": rol}
        save_catalog(USUARIOS_FILE, usuarios)
        log_event("Local", f"Nuevo usuario creado: {usuario} asignado a {area}")
        flash(f'Usuario "{usuario}" creado con éxito.', 'success')
    return redirect(url_for('web.admin_usuarios'))

@web_bp.route('/admin/usuarios/editar/<username>', methods=['POST'])
@login_required
@admin_required
def editar_usuario(username):
    usuarios = load_catalog(USUARIOS_FILE)
    username = username.lower().strip()

    if username in usuarios:
        nueva_area = request.form.get('area', '').strip().upper().replace("Í", "I")
        nuevo_nombre = request.form.get('nombre', '').strip()

        if username == 'admin' and nueva_area != 'TODAS':
            flash('El usuario admin principal no puede perder el alcance global (TODAS).', 'danger')
            return redirect(url_for('web.admin_usuarios'))

        rol = request.form.get('rol', usuarios[username].get('rol', 'coordinador'))
        if rol not in ('admin','rrhh','coordinador'): return 'Rol inválido', 400
        if username == 'admin': rol = 'admin'
        if rol in ('admin','rrhh'): nueva_area = 'TODAS'
        if rol == 'coordinador' and nueva_area == 'TODAS': return 'Seleccione el área del coordinador', 400
        if rol == 'coordinador' and nueva_area not in load_catalog(AREAS_FILE): return 'Área no registrada', 400
        usuarios[username]['rol'] = rol
        usuarios[username]['area'] = nueva_area
        if nuevo_nombre: usuarios[username]['nombre'] = nuevo_nombre
        save_catalog(USUARIOS_FILE, usuarios)
        log_event("Local", f"Usuario {username} actualizado (Área: {nueva_area})")
        flash(f'Datos del usuario "{username}" actualizados.', 'success')
    return redirect(url_for('web.admin_usuarios'))

@web_bp.route('/admin/usuarios/reset_password/<username>', methods=['POST'])
@login_required
@admin_required
def reset_password_usuario(username):
    usuarios = load_catalog(USUARIOS_FILE)
    username = username.lower().strip()
    nueva_pass = request.form.get('nueva_password', '').strip()

    if not nueva_pass: flash('La contraseña no puede estar en blanco.', 'danger')
    elif username in usuarios:
        usuarios[username]['pass'] = nueva_pass
        save_catalog(USUARIOS_FILE, usuarios)
        log_event("Local", f"Contraseña restablecida para el usuario {username}")
        flash(f'Contraseña actualizada para el usuario "{username}".', 'success')
    return redirect(url_for('web.admin_usuarios'))

@web_bp.route('/admin/usuarios/eliminar/<username>', methods=['POST'])
@login_required
@admin_required
def eliminar_usuario(username):
    usuarios = load_catalog(USUARIOS_FILE)
    username = username.lower().strip()

    if username == 'admin':
        flash('No se puede eliminar el usuario administrador maestro.', 'danger')
        return redirect(url_for('web.admin_usuarios'))

    if username in usuarios:
        del usuarios[username]
        save_catalog(USUARIOS_FILE, usuarios)
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
    import database
    config = load_catalog(CONFIG_FILE)
    if request.method == 'POST':
        puerto = request.form.get('puerto')
        ips = request.form.get('ips')
        servidor_ntp = request.form.get('servidor_ntp', 'pool.ntp.org').strip()
        
        save_catalog(CONFIG_FILE, {
            **config,
            "puerto_escucha": int(puerto),
            "ips_permitidas": [ip.strip() for ip in ips.split(',') if ip.strip()],
            "servidor_ntp": servidor_ntp
        })
        
        time_sync.sincronizar_ntp(servidor_ntp)
        log_event("Local", f"Configuración guardada. Servidor NTP asignado: {servidor_ntp}")
        flash('Configuración y servidor de tiempo actualizados.', 'success')
        return redirect(url_for('web.configuracion'))
    saved=database.saved_location()
    import secrets
    session.setdefault('db_path_csrf',secrets.token_urlsafe(32))
    selected=saved['database_path'] if saved else str(database.DATABASE_PATH.resolve())
    options={str(path.resolve()) for path in (database.BASE_DIR/'data').glob('*') if path.is_file() and path.suffix.lower() in ('.db','.sqlite','.sqlite3')}
    options.update((str(database.DATABASE_PATH.resolve()),selected))
    return render_template('config.html', config=config, estado_ntp=time_sync.estado_sync,
        db_actual=str(database.DATABASE_PATH.resolve()),db_seleccionada=selected,db_opciones=sorted(options),
        db_reinicio=Path(selected).resolve()!=database.DATABASE_PATH.resolve())


@web_bp.route('/admin/base_datos',methods=['POST'])
@login_required
@admin_required
def seleccionar_base_datos():
    import database,planning
    import secrets
    expected=session.get('db_path_csrf','')
    received=request.form.get('csrf_token','')
    if not expected or not secrets.compare_digest(expected.encode(),received.encode()):
        return 'La solicitud caducó o no es válida. Recarga Configuración e inténtalo de nuevo.',403
    try:
        target=database.validate_location(request.form.get('ruta_db',''))
        saved=database.saved_location()
        if saved and Path(saved['database_path']).resolve()==target:
            flash('La ruta ya está guardada. Se aplicará al próximo inicio del servidor.','success')
            return redirect(url_for('web.configuracion'))
        backup=database.backup()
        # Record intent before the independent, atomic configuration write.
        with database.transaction() as db:
            planning.audit(db,'',planning.today().date().isoformat(),'SELECCIONAR_BASE_DATOS',
                dict(activa=str(database.DATABASE_PATH.resolve()),seleccion_anterior=saved),
                dict(solicitada=str(target),respaldo=str(backup),aplica='PROXIMO_INICIO'),session['usuario'])
        database.save_location(target,session['usuario'])
    except (ValueError,OSError) as error:
        return str(error),400
    flash('Ruta validada y guardada. La base activa se conserva hasta reiniciar el servidor. Se creó un respaldo.','success')
    return redirect(url_for('web.configuracion'))

@web_bp.route('/config/sync_ntp', methods=['POST'])
@login_required
@admin_required
def forzar_sync_ntp():
    import time_sync
    config = load_catalog(CONFIG_FILE)
    ok, mensaje = time_sync.sincronizar_ntp(config.get('servidor_ntp', 'pool.ntp.org'))
    if ok: flash(f'✓ {mensaje}', 'success')
    else: flash(f'⚠️ {mensaje}', 'danger')
    return redirect(url_for('web.configuracion'))

@web_bp.route('/consola')
@login_required
@admin_required
def consola():
    return render_template('consola.html')


@web_bp.route('/admin/backup', methods=['POST'])
@login_required
@admin_required
def descargar_respaldo():
    from database import backup
    # The view transaction has no writes; use a separate connection for backup.
    path = backup()
    log_event('Local', f'Respaldo SQLite creado por {session.get("usuario")}')
    return send_file(path, as_attachment=True, download_name=path.name)
