"""RH owns shift definitions; coordinators own their area's weekly assignments."""
import calendar
import json
from datetime import date, timedelta
from functools import wraps
from flask import Blueprint, request, session, render_template, redirect, url_for, flash, abort, send_file
import database
import planning
from storage import atomic
from panama_payroll import CODIGOS_JUSTIFICACION

planning_bp = Blueprint('planning', __name__)


def user_info():
    user = database.read_catalog('usuarios').get(session.get('usuario'))
    if not user: abort(401)
    return user


def role():
    user = user_info()
    return user.get('rol', 'admin' if session.get('usuario')=='admin' or user.get('area')=='TODAS' else 'coordinador')


def area():
    return str(user_info().get('area','')).strip().upper().replace('Í','I')


def allowed_employees():
    scope = area()
    return {k:v for k,v in database.read_catalog('empleados').items() if scope=='TODAS' or str(v.get('area','')).strip().upper().replace('Í','I')==scope}


def check_employee(employee):
    if employee not in allowed_employees(): abort(403)


def authenticated(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if 'usuario' not in session: return redirect(url_for('web.login'))
        user_info()
        return fn(*args, **kwargs)
    return wrapped


def hr_only():
    if role() not in ('admin','rrhh'): abort(403)


def coordinator_only():
    if role() not in ('admin','coordinador'): abort(403)


def range_args():
    now = planning.today().date()
    start = request.args.get('fecha_inicio') or (now-timedelta(days=14)).isoformat()
    end = request.args.get('fecha_fin') or now.isoformat()
    planning.dates(start,end)
    employee = request.args.get('emp_id','').strip().upper()
    if employee: check_employee(employee)
    return start,end,employee


@planning_bp.route('/turnos', methods=['GET','POST'])
@authenticated
def turnos():
    shifts = database.read_catalog('turnos')
    if request.method=='POST':
        hr_only()
        try:
            identifier = request.form.get('turno_id','').strip().upper()
            if not identifier or identifier=='DESCANSO': raise ValueError('ID de turno inválido')
            pauses = []
            for line in request.form.get('descansos','').splitlines():
                if line.strip(): pauses.append(line.strip().split('-'))
            data = dict(nombre=request.form.get('nombre',''),entrada=request.form.get('entrada',''),salida=request.form.get('salida',''),
                        descansos=pauses,descanso_remunerado=request.form.get('descanso_remunerado')=='on')
            shift = planning.validate_shift(data)
            with database.transaction() as db:
                planning.audit(db,'',planning.today().date().isoformat(),'DEFINIR_TURNO',shifts.get(identifier),shift,session['usuario'])
                shifts[identifier] = shift
                database.write_catalog('turnos',shifts)
            flash('Turno guardado. Las asignaciones anteriores conservan su horario histórico.', 'success')
            return redirect(url_for('planning.turnos'))
        except (ValueError,KeyError,TypeError) as error:
            return str(error),400
    editing = request.args.get('editar','')
    return render_template('turnos.html',turnos=shifts,puede_editar=role() in ('admin','rrhh'),edit_id=editing,edit=shifts.get(editing,{}))


@planning_bp.route('/planificacion', methods=['GET','POST'])
@authenticated
def weekly():
    coordinator_only()
    now = planning.today().date()
    monday = request.values.get('semana') or (now-timedelta(days=now.weekday())).isoformat()
    try:
        first = date.fromisoformat(monday)
        if first.weekday()!=0: raise ValueError('La semana debe comenzar un lunes')
        days = [(first+timedelta(days=i)).isoformat() for i in range(7)]
        if request.method=='POST':
            employee = request.form.get('emp_id','')
            check_employee(employee)
            values = [request.form.get('dia_'+str(i),'') for i in range(7)]
            if request.form.get('aplicar_fijo')=='on':
                fixed = request.form.get('turno_fijo','').strip().upper()
                if not fixed or fixed not in database.read_catalog('turnos'):
                    raise ValueError('Seleccione un turno fijo registrado por RH')
                values = [fixed]*6+['DESCANSO']
            planning.assign_week(employee,monday,values,session['usuario'],request.form.get('renovar')=='on')
            flash('Semana asignada. Las novedades de los días modificados requieren revisión.', 'success')
            return redirect(url_for('planning.weekly',semana=monday))
    except (ValueError,KeyError) as error:
        return str(error),400
    return render_template('planificacion.html',semana=monday,dias=days,empleados=allowed_employees(),
        turnos=database.read_catalog('turnos'),asignaciones=planning.assignments(days[0],days[-1]))


@planning_bp.route('/aprobaciones')
@authenticated
def approvals():
    coordinator_only()
    try:
        start,end,employee = range_args()
        import incidents
        with database.transaction():
            rows = planning.report(area(),employee,start,end)
            incidents.sync(rows)
    except ValueError as error:
        return str(error),400
    return render_template('aprobaciones.html',lista=rows,empleados=allowed_employees(),fecha_inicio=start,fecha_fin=end,
        emp_id_filtro=employee,codigos={k:v for k,v in CODIGOS_JUSTIFICACION.items() if k!='732'},
        incidencias=[dict(item=r,tipo=k,segundos=q) for r in rows for k,q in incidents.quantities(r).items() if q>0])


@planning_bp.route('/aprobaciones/guardar_fila', methods=['POST'])
@planning_bp.route('/aprobaciones/guardar_incidencia', methods=['POST'])
@authenticated
def save_row():
    coordinator_only()
    employee=request.form.get('emp_id','')
    check_employee(employee)
    try:
        import incidents
        kind=request.form.get('tipo','')
        identity={'emp_id','fecha','tipo','q_emp_id','q_fecha_inicio','q_fecha_fin'}
        data={key:value for key,value in request.form.items() if key not in identity}
        incidents.validate(area(),employee,request.form.get('fecha',''),kind,data,session['usuario'])
        flash('Incidencia guardada por separado en la auditoría.', 'success')
        return redirect(url_for('planning.approvals',emp_id=request.form.get('q_emp_id',''),fecha_inicio=request.form.get('q_fecha_inicio',''),fecha_fin=request.form.get('q_fecha_fin','')))
    except (ValueError,KeyError) as error: return str(error),400


@planning_bp.route('/bono')
@authenticated
def bonus():
    coordinator_only()
    month = request.args.get('mes') or planning.today().strftime('%Y-%m')
    try: rows = planning.monthly(area(),month)
    except ValueError as error: return str(error),400
    return render_template('bono.html',mes=month,lista=rows)


@planning_bp.route('/bono/validar',methods=['POST'])
@authenticated
def save_bonus():
    coordinator_only()
    employee=request.form.get('emp_id','')
    check_employee(employee)
    try:
        month=request.form.get('mes','')
        planning.validate_bonus(area(),employee,month,request.form.get('decision',''),request.form.get('motivo',''),session['usuario'])
        flash('Revisión del bono guardada. Si cambian los datos deberá revisarse nuevamente.', 'success')
        return redirect(url_for('planning.bonus',mes=month))
    except ValueError as error: return str(error),400


def export_workbook(rows, start, end, employee, payroll=False):
    from .web import preparar_excel, finalizar_excel
    headers = ['CÓDIGO','COLABORADOR','FECHA JORNADA','TURNO','JORNADA','ENTRADA REAL','SALIDA REAL',
        'HORAS ORDINARIAS PROGRAMADAS','HORAS TRABAJADAS','HORAS ORDINARIAS TRABAJADAS','MINUTOS TARDE','MINUTOS ANTICIPACIÓN',
        'HORAS AUSENCIA','CONCEPTO AUSENCIA','PERMISO REMUNERADO HORAS','DESCUENTO HORAS EFECTIVAS','BASE PAGABLE HORAS EFECTIVAS',
        'BASE PAGABLE EQUIVALENTE DIURNA','HE DETECTADAS','HE APROBADAS','ESTADO','ALERTAS','TARDANZA COMPUTABLE MIN','VALIDACIÓN TARDANZA','MOTIVO TARDANZA','HORAS FIN DE SEMANA RECONOCIBLES','HORAS FIN DE SEMANA APROBADAS','COMPLEMENTO CONVENIO DOMINGO','VALIDACIÓN DOMINGO']
    wb,ws,font,border = preparar_excel('Asistencia',headers)
    for item in rows:
        ws.append([item['id'],item['nombre'],item['fecha'],item['turno_id'],item['jornada'],item['entrada_fecha'],item['salida_fecha'],
            item['horas_programadas'],item['horas_totales'],item['horas_ordinarias'],item['tardanza_min'],item['anticipacion_min'],
            item['ausencia_horas'],item['cod_ausencia'],item['permiso_horas'],item['descuento_horas'],item['horas_pagables'],
            item['horas_equivalentes'],item['extra_horas'],item['extra_aprobadas'],item['estado'],', '.join(item['alertas']),item.get('tardanza_computable_min',0),item.get('tardanza_estado',''),item.get('motivo_tardanza',''),item.get('horas_fin_semana',0),item.get('horas_fin_semana_aprobadas',0),item.get('complemento_dominical',0),item.get('domingo_estado','')])
    details = wb.create_sheet('Novedades detalle')
    details.append(['CODIGO_COLABORADOR','FECHA','CON_CODIGO','CANTIDAD_HORAS','CON_NOMBRE','TRATAMIENTO','FACTOR'])
    summary = wb.create_sheet('Novedades RRHH')
    summary.append(['CODIGO_COLABORADOR','CON_CODIGO','CANTIDAD_HORAS','CON_NOMBRE','TRATAMIENTO','FACTOR','FECHA','INCIDENCIA','INCIDENCIA_ID'])
    with database.reading() as db:
        identifiers={(r['empleado_id'],r['fecha'],r['tipo']):r['id'] for r in db.execute('SELECT id,empleado_id,fecha,tipo FROM incidencias WHERE fecha>=? AND fecha<=?',(start,end))}
    for item in rows:
        for c in item['conceptos']:
            kind='DOMINGO' if c['tratamiento']=='FIN_SEMANA' else ('HE' if c['tratamiento']=='HE' else ('TARDANZA' if c['con_codigo']=='732' or c['tratamiento'].startswith('TARDANZA_') else ('RECARGO' if c['tratamiento']=='RECARGO' else 'FALTANTE')))
            record=[item['id'],item['fecha'],c['con_codigo'],c['cantidad_horas'],c['con_nombre'],c['tratamiento'],c['factor']]
            details.append(record)
            summary.append([item['id'],c['con_codigo'],c['cantidad_horas'],c['con_nombre'],c['tratamiento'],c['factor'],item['fecha'],kind,identifiers.get((item['id'],item['fecha'],kind),'')])
    months = sorted({d[:7] for d in planning.dates(start,end)})
    bonus_sheet = wb.create_sheet('Bono mensual')
    bonus_sheet.append(['MES','CÓDIGO','COLABORADOR','MINUTOS TARDE MES COMPLETO','DÍAS CON AUSENCIA','DÍAS SIN PLAN','ESTADO CALCULADO','VALIDACIÓN COORDINADOR','VALIDADO POR','MOTIVO','MINUTOS REALES'])
    for month in months:
        for result in planning.monthly(area(),month,employee):
            bonus_sheet.append([month,result['id'],result['nombre'],result['minutos_tarde'],result['ausencias'],result['dias_sin_plan'],result['estado'],result['validacion'],result['validado_por'],result['motivo_bono'],result['minutos_tarde_reales']])
    rules = wb.create_sheet('Criterios')
    for line in ['Jornada asignada al día de inicio, incluso al cruzar medianoche.',
        'Ordinarias máximas: diurna 8, mixta 7.5, nocturna 7. Arts. 30-32.',
        'Equivalencia diurna: base pagable efectiva x 8 / límite de la jornada; no se suma nuevamente al salario base.',
        'Los recargos de domingo/feriado y HE son conceptos separados de la base; no sumar factores íntegros dos veces.',
        'HE requieren aprobación. Pendientes se muestran y bloquean la exportación de nómina.',
        'Recargos por fecha real y período; exceso de 3 HE/día o 9 HE/semana añade 75% al factor. Arts. 33,36,48-50.',
        'El catálogo original conserva sus códigos. Los factores legales calculados figuran explícitamente por concepto.',
        'Bono: mes completo, hasta 30 minutos de tardanza y cero ausencias de cualquier concepto. Estado provisional antes de cierre.',
        'SIN_TURNO, marcaciones incompletas, permisos sin remuneración definida y turnos sin validar requieren revisión.',
        'Domingo trabajado: mínimo 8 horas reconocidas por convenio; HE y horas reales se muestran separadas. No hay ausencia por completar menos horas.',
        'No contiene montos monetarios. RH debe conciliar códigos y factores con el sistema de planilla receptor.']:
        rules.append([line])
    if payroll:
        wb.active = wb.sheetnames.index('Novedades RRHH')
    for sheet in wb:
        sheet.freeze_panes='A2'
        sheet.auto_filter.ref=sheet.dimensions
        for row in sheet:
            for cell in row:
                # Employee-supplied strings must never become spreadsheet formulas.
                if cell.data_type=='f': cell.data_type='s'
                cell.font=font
                cell.border=border
                if isinstance(cell.value,float): cell.number_format='0.000000'
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width=min(65,max(15,max(len(str(c.value or '')) for c in col)+2))
    return finalizar_excel(wb,wb.active)


@planning_bp.route('/exportar')
@planning_bp.route('/exportar/rrhh')
@authenticated
@atomic
def export():
    coordinator_only()
    try:
        start,end,employee=range_args()
        rows=planning.report(area(),employee,start,end)
        import incidents
        incidents.sync(rows)
        payroll=request.path.endswith('/rrhh')
        blockers={'TURNO_SIN_VALIDAR_RH','MARCACION_INCOMPLETA','MARCACIONES_AMBIGUAS','ASIGNACION_AMBIGUA',
                  'MARCACION_SIN_TURNO','DEFINIR_REMUNERACION_PERMISO','HE_PENDIENTE',
                  'PLANIFICACION_PENDIENTE','REVISAR_LIMITE_ORDINARIO_SEMANAL','TARDANZA_PENDIENTE','AUSENCIA_PENDIENTE_CODIGO','DOMINGO_PENDIENTE'}
        if payroll and any(blockers.intersection(r['alertas']) or r['estado'] in ('EN_CURSO','PROGRAMADO') for r in rows):
            return 'Hay novedades pendientes. Revise Aprobaciones y descargue Asistencias para ver el detalle.',409
        stream=export_workbook(rows,start,end,employee,payroll)
        return send_file(stream,as_attachment=True,download_name=f"{'nomina' if payroll else 'asistencias'}_{start}_{end}.xlsx",mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except ValueError as error: return str(error),400


@planning_bp.route('/rrhh/calendario',methods=['GET','POST'])
@authenticated
def calendar_settings():
    if role()!='admin': abort(403)
    config=database.read_catalog('config')
    if request.method=='POST':
        try:
            day=request.form.get('fecha','')
            date.fromisoformat(day)
            kind=request.form.get('tipo','')
            if kind not in ('','normal','feriado','descanso_compensatorio'): raise ValueError('Tipo de día inválido')
            settings=config.setdefault('calendario',{})
            before=settings.get(day)
            if kind: settings[day]=kind
            else: settings.pop(day,None)
            with database.transaction() as db:
                database.write_catalog('config',config)
                planning.audit(db,'',day,'CALENDARIO',before,kind,session['usuario'])
            return redirect(url_for('planning.calendar_settings'))
        except ValueError as error: return str(error),400
    return render_template('calendario.html',calendario=config.get('calendario',{}))


@planning_bp.route('/admin/conceptos',methods=['GET','POST'])
@authenticated
def absence_codes():
    if role()!='admin': abort(403)
    config=database.read_catalog('config')
    if request.method=='POST':
        code=request.form.get('codigo','')
        value=request.form.get('remunerada','')
        if code not in CODIGOS_JUSTIFICACION or code=='732' or code in planning.PAID_DEFAULTS or value not in ('si','no',''):
            return 'Código o tratamiento inválido',400
        with database.transaction() as db:
            policies=config.setdefault('politicas_ausencia',{})
            previous=policies.get(code)
            policies[code]={'si':True,'no':False,'':None}[value]
            database.write_catalog('config',config)
            planning.audit(db,'',planning.today().date().isoformat(),'TRATAMIENTO_CODIGO',
                           dict(codigo=code,remunerada=previous),dict(codigo=code,remunerada=policies[code]),session['usuario'])
        return redirect(url_for('planning.absence_codes'))
    return render_template('conceptos.html',codigos={k:v for k,v in CODIGOS_JUSTIFICACION.items() if k!='732'},
        fijos=planning.PAID_DEFAULTS,politicas=config.get('politicas_ausencia',{}))
