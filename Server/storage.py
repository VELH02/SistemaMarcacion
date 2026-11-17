"""Servicios de almacenamiento compartidos por la web y los terminales."""
import os
import uuid
from datetime import datetime, timedelta
from functools import wraps
from config import CONFIG_FILE, EMPLEADOS_FILE, USUARIOS_FILE
from defaults import (DEFAULT_CONFIG, DEFAULT_EMPLEADOS, DEFAULT_AREAS,
                      DEFAULT_USUARIOS, DEFAULT_TURNOS, DEFAULT_APROBACIONES)
import database
import time_sync


def atomic(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with database.transaction():
            return function(*args, **kwargs)
    return wrapped


def init_storage():
    database.initialize(dict(config=DEFAULT_CONFIG, empleados=DEFAULT_EMPLEADOS,
        areas=DEFAULT_AREAS, usuarios=DEFAULT_USUARIOS, turnos=DEFAULT_TURNOS,
        aprobaciones=DEFAULT_APROBACIONES))


def load_catalog(file_path):
    return database.read_catalog(os.path.splitext(os.path.basename(file_path))[0])


def save_catalog(file_path, data):
    database.write_catalog(os.path.splitext(os.path.basename(file_path))[0], data)


def normalizar_area(area):
    return str(area).strip().upper().replace('Í', 'I')


def buscar_empleado_por_id_o_rfid(identificador):
    identifier = str(identificador).strip().upper()
    if not identifier:
        return None, None
    return database.find_employee(identifier)


@atomic
def registrar_marcacion(identifier, tipo, fecha_hora=None, ip='', nota=''):
    identifier = str(identifier).strip().upper()
    tipo = str(tipo).strip().upper()
    if not identifier or tipo not in {'ENTRADA', 'SALIDA', 'TIEMPO EXTRA'}:
        raise ValueError('Identificador o tipo de marcación inválido')
    timestamp = datetime.strptime(str(fecha_hora or time_sync.get_time_str()).strip(), '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
    emp_id, employee = buscar_empleado_por_id_o_rfid(identifier)
    if employee is None:
        emp_id = identifier
        employee = dict(nombre=f'Colaborador {emp_id}', apellido='', area='OPERACIONES', rfid='', vector_facial=[])
        employees = load_catalog(EMPLEADOS_FILE)
        employees[emp_id] = employee
        save_catalog(EMPLEADOS_FILE, employees)
    name = f"{employee.get('nombre', '')} {employee.get('apellido', '')}".strip()
    database.insert_mark(dict(ID_Registro=uuid.uuid4().hex, ID_Personal=emp_id,
        Nombre=name, Area=normalizar_area(employee.get('area', 'OPERACIONES')),
        Tipo=tipo, Fecha_Hora=timestamp, IP_Origen=ip or '', Estado='Aprobado', Nota=nota))
    return name, timestamp


@atomic
def actualizar_codigo_empleado_sistema(codigo_viejo, codigo_nuevo, nuevo_nombre, nuevo_apellido, nueva_area, nuevo_rfid, nuevo_vector=None):
    employees = load_catalog(EMPLEADOS_FILE)
    old, new = str(codigo_viejo).strip().upper(), str(codigo_nuevo).strip().upper()
    if new != old and new in employees:
        raise ValueError('Código de empleado ya registrado')
    previous = employees.pop(old)
    employees[new] = dict(previous, nombre=nuevo_nombre, apellido=nuevo_apellido, area=nueva_area,
        rfid=nuevo_rfid, vector_facial=nuevo_vector if nuevo_vector is not None else previous.get('vector_facial', []))
    save_catalog(EMPLEADOS_FILE, employees)
    if old != new:
        with database.transaction() as db:
            db.execute('UPDATE marcaciones SET ID_Personal=?, Nombre=?, Area=? WHERE ID_Personal=?',
                       (new, f'{nuevo_nombre} {nuevo_apellido}'.strip(), nueva_area, old))
            for table in ('asignaciones', 'decisiones', 'incidencias', 'validaciones_bono'):
                db.execute(f'UPDATE {table} SET empleado_id=? WHERE empleado_id=?', (new, old))
        approvals = database.read_catalog('aprobaciones')
        if old in approvals:
            approvals.setdefault(new, {}).update(approvals.pop(old))
            database.write_catalog('aprobaciones', approvals)


@atomic
def guardar_o_actualizar_marcacion_diaria(emp_id, fecha, hora_entrada, hora_salida, usuario_modifica):
    import planning
    day = datetime.strptime(fecha, '%Y-%m-%d').date()
    schedule = planning.assignments((day-timedelta(days=1)).isoformat(),(day+timedelta(days=1)).isoformat())
    assignment = schedule.get((emp_id,fecha))
    if assignment and assignment['turno_id'] != 'DESCANSO':
        import json
        start,end = planning.bounds(fecha,json.loads(assignment['turno_json']))
        records = database.marks(employee=emp_id,start=(day-timedelta(days=1)).isoformat(),end=(day+timedelta(days=2)).isoformat())
        groups,_ = planning.allocate({emp_id:records},schedule)
        attendance = groups[(emp_id,fecha)]
    else:
        start = datetime.combine(day,datetime.min.time())
        end = start
        records = database.marks(employee=emp_id,start=fecha,end=(day+timedelta(days=1)).isoformat() if day.weekday()==6 else fecha)
        attendance = [item for item in planning.sessions(records) if
            (item['start'] and item['start'].date()==day) or
            (not item['start'] and item['end'] and item['end'].date()==day)]
    before = [dict(start=str(item['start'] or ''),end=str(item['end'] or '')) for item in attendance]
    changes = {}
    for tipo, hour in [('ENTRADA',hora_entrada),('SALIDA',hora_salida)]:
        if not hour: continue
        hour = planning.clock(hour.strip())
        reference = start if tipo=='ENTRADA' else end
        candidate = datetime.fromisoformat(fecha+' '+hour)
        if assignment and assignment['turno_id']!='DESCANSO':
            candidate = min([candidate+timedelta(days=i) for i in (-1,0,1)],key=lambda value:abs((value-reference).total_seconds()))
        elif tipo=='SALIDA':
            entry=planning.clock(hora_entrada.strip()) if hora_entrada else next((item['start'].strftime('%H:%M:%S') for item in attendance if item['start']),None)
            if entry and hour<entry:
                candidate+=timedelta(days=1)
        stamp = candidate.strftime('%Y-%m-%d %H:%M:%S')
        old = [item['start'] if tipo=='ENTRADA' else item['end'] for item in attendance]
        kinds = ('ENTRADA',) if tipo=='ENTRADA' else ('SALIDA','TIEMPO EXTRA')
        affected = 0
        with database.transaction() as db:
            for value in set(old)-{None}:
                result = db.execute('UPDATE marcaciones SET Fecha_Hora=?,Nota=? WHERE ID_Personal=? AND Fecha_Hora=? AND Tipo IN ('+','.join('?' for _ in kinds)+')',
                    (stamp,f'Modificado por {usuario_modifica}',emp_id,value.strftime('%Y-%m-%d %H:%M:%S'),*kinds))
                affected += result.rowcount
            if not affected:
                registrar_marcacion(emp_id,tipo,stamp,'Ajuste Manual',f'Añadido por {usuario_modifica}')
        changes[tipo] = stamp
    with database.transaction() as db:
        planning.audit(db,emp_id,fecha,'AJUSTAR_MARCACION',before,changes,usuario_modifica)
        decision = db.execute('SELECT datos FROM decisiones WHERE empleado_id=? AND fecha=?',(emp_id,fecha)).fetchone()
        if decision:
            import json
            data = json.loads(decision['datos'])
            data['he_aprobadas'] = False
            data['he_estado'] = 'pendiente'
            data['motivo_he'] = ''
            data['domingo_estado'] = 'pendiente'
            data['motivo_domingo'] = ''
            data['tardanza_estado'] = 'pendiente'
            data['motivo_tardanza'] = ''
            planning.save_decision(emp_id,fecha,data,usuario_modifica)


def horas_efectivas(entrada, salida):
    elapsed = (datetime.strptime(salida, '%H:%M:%S') - datetime.strptime(entrada, '%H:%M:%S')).total_seconds() / 3600
    return round(max(0, elapsed - (0.5 if elapsed >= 4.5 else 0)), 2)


def obtener_registros_agrupados(area_usuario, emp_id_filtro='', fecha_inicio='', fecha_fin=''):
    days = {}
    for row in database.marks(normalizar_area(area_usuario), str(emp_id_filtro).strip().upper(), fecha_inicio, fecha_fin):
        try:
            stamp = datetime.strptime(row['Fecha_Hora'], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
        date, hour = stamp.strftime('%Y-%m-%d'), stamp.strftime('%H:%M:%S')
        day = days.setdefault((row['ID_Personal'], date), dict(id=row['ID_Personal'], nombre=row['Nombre'],
            area=row['Area'], fecha=date, entrada=None, salida=None))
        kind = row['Tipo'].strip().upper()
        if kind == 'ENTRADA':
            day['entrada'] = min(day['entrada'] or hour, hour)
        elif kind in ('SALIDA', 'TIEMPO EXTRA'):
            day['salida'] = max(day['salida'] or hour, hour)
    for day in days.values():
        day['horas_totales'] = horas_efectivas(day['entrada'], day['salida']) if day['entrada'] and day['salida'] else 'Incompleto'
    return sorted(days.values(), key=lambda day: day['fecha'], reverse=True)


def obtener_historial_empleado(emp_id):
    result = []
    for day in obtener_registros_agrupados('TODAS', emp_id):
        late = 0
        if day['entrada']:
            late = max(0, int((datetime.strptime(day['entrada'], '%H:%M:%S') - datetime.strptime('08:00:00', '%H:%M:%S')).total_seconds() // 60))
        result.append(dict(fecha=day['fecha'], entrada=day['entrada'] or '--:--:--', salida=day['salida'] or '--:--:--',
            horas=f"{day['horas_totales']} hrs" if day['horas_totales'] != 'Incompleto' else 'Incompleto', tarde=str(late)))
    return result
