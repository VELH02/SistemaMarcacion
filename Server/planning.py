"""Planificación semanal y cálculo por jornada de inicio, en hora de Panamá."""
import calendar
import json
import hashlib
from collections import defaultdict
from datetime import datetime, date, time, timedelta, timezone
import database
from panama_payroll import CODIGOS_JUSTIFICACION, CONCEPTOS_PANAMA

LIMITS = {'DIURNA': 8, 'MIXTA': 7.5, 'NOCTURNA': 7}
MAX_SESSION_DURATION = timedelta(hours=24)
PAID_DEFAULTS = {'310': True, '730': False, '750': False, '760': False, '720': False}


def today():
    from demo_data import evaluation_time
    simulated=evaluation_time()
    if simulated is not None: return simulated
    return datetime.now(timezone(timedelta(hours=-5))).replace(tzinfo=None)


def dates(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first or (last-first).days > 366:
        raise ValueError('El rango debe ser de 1 a 367 días')
    return [(first + timedelta(days=i)).isoformat() for i in range((last-first).days+1)]


def clock(value):
    return time.fromisoformat(value).strftime('%H:%M:%S')


def bounds(day, shift):
    start = datetime.fromisoformat(day + ' ' + shift['entrada'])
    end = datetime.fromisoformat(day + ' ' + shift['salida'])
    if end <= start:
        end += timedelta(days=1)
    return start, end


def overlap(a, b, c, d):
    return max(0.0, (min(b,d)-max(a,c)).total_seconds())


def breaks(day, shift):
    start, end = bounds(day, shift)
    result = []
    for entry in shift.get('descansos', []):
        a = datetime.fromisoformat(day + ' ' + entry[0])
        if a < start:
            a += timedelta(days=1)
        b = datetime.fromisoformat(a.date().isoformat() + ' ' + entry[1])
        if b <= a:
            b += timedelta(days=1)
        if a < start or b > end:
            raise ValueError('El descanso debe estar dentro del turno')
        result.append((a,b))
    result.sort()
    if any(result[i][1] > result[i+1][0] for i in range(len(result)-1)):
        raise ValueError('Los descansos no pueden solaparse')
    return result


def subtract(intervals, removed):
    result = intervals
    for c,d in removed:
        pending = []
        for a,b in result:
            if b <= c or a >= d:
                pending.append((a,b))
            else:
                if a < c: pending.append((a,c))
                if b > d: pending.append((d,b))
        result = pending
    return result


def seconds(intervals):
    return sum((b-a).total_seconds() for a,b in intervals)


def split(intervals):
    """Split at midnight and at day/night boundaries, retaining exact seconds."""
    for a,b in intervals:
        while a < b:
            candidates = [datetime.combine(a.date()+timedelta(days=1), time())]
            candidates += [datetime.combine(a.date(), time(h)) for h in (6,18) if datetime.combine(a.date(), time(h)) > a]
            end = min(b, min(candidates))
            yield a, end
            a = end


def shift_details(shift):
    start, end = bounds('2026-01-05', shift)
    all_breaks = breaks('2026-01-05', shift)
    removed = [] if shift.get('descanso_remunerado') else all_breaks
    intervals = subtract([(start,end)], removed)
    total = seconds(intervals)
    night = sum((b-a).total_seconds() for a,b in split(intervals) if not 6 <= a.hour < 18)
    kind = 'NOCTURNA' if night > 3*3600 or night == total else ('MIXTA' if night else 'DIURNA')
    return dict(jornada=kind, horas_programadas=total/3600,
                horas_ordinarias=min(total/3600, LIMITS[kind]), limite=LIMITS[kind])


def validate_shift(data):
    if not data.get('nombre', '').strip():
        raise ValueError('El nombre del turno es obligatorio')
    shift = dict(nombre=data['nombre'].strip(), entrada=clock(data['entrada']), salida=clock(data['salida']),
                 descansos=[[clock(a), clock(b)] for a,b in data.get('descansos', [])],
                 descanso_remunerado=bool(data.get('descanso_remunerado')), configurado=True)
    details = shift_details(shift)
    if details['horas_programadas'] <= 0 or bounds('2026-01-05',shift)[1]-bounds('2026-01-05',shift)[0] > timedelta(hours=16):
        raise ValueError('Duración del turno inválida (máximo 16 horas)')
    return {**shift, **details}


def audit(db, employee, day, action, before, after, user):
    db.execute('INSERT INTO auditoria_planificacion(empleado_id,fecha,accion,antes,despues,usuario,actualizado) VALUES (?,?,?,?,?,?,?)',
        (employee, day, action, json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), user, today().isoformat()))


def assignments(start, end):
    with database.reading() as db:
        return {(r['empleado_id'],r['fecha']): dict(r) for r in db.execute('SELECT * FROM asignaciones WHERE fecha>=? AND fecha<=?', (start,end))}


def decisions(start, end):
    with database.reading() as db:
        return {(r['empleado_id'],r['fecha']): json.loads(r['datos']) for r in db.execute('SELECT * FROM decisiones WHERE fecha>=? AND fecha<=?', (start,end))}


def assign_week(employee, monday, values, user, renew=False):
    first = date.fromisoformat(monday)
    if first.weekday() != 0 or len(values) != 7:
        raise ValueError('Seleccione un lunes y siete días')
    values = list(values)
    values[6] = values[6] or 'DESCANSO'
    shifts = database.read_catalog('turnos')
    with database.transaction() as db:
        for i, shift_id in enumerate(values):
            day = (first+timedelta(days=i)).isoformat()
            prior = db.execute('SELECT * FROM asignaciones WHERE empleado_id=? AND fecha=?', (employee,day)).fetchone()
            if shift_id == (prior['turno_id'] if prior else '') and not renew:
                continue  # Keep the historical snapshot unless the assignment changes.
            if shift_id and shift_id != 'DESCANSO' and shift_id not in shifts:
                raise ValueError('Turno desconocido')
            snapshot = {} if shift_id == 'DESCANSO' else shifts.get(shift_id, {})
            if shift_id and shift_id != 'DESCANSO' and not snapshot.get('configurado'):
                raise ValueError(f'RH debe validar primero los descansos del turno {shift_id}')
            if shift_id:
                db.execute('INSERT INTO asignaciones VALUES (?,?,?,?,?,?) ON CONFLICT(empleado_id,fecha) DO UPDATE SET turno_id=excluded.turno_id,turno_json=excluded.turno_json,usuario=excluded.usuario,actualizado=excluded.actualizado',
                           (employee,day,shift_id,json.dumps(snapshot,ensure_ascii=False),user,today().isoformat()))
            else:
                db.execute('DELETE FROM asignaciones WHERE empleado_id=? AND fecha=?', (employee,day))
            # A new shift must be reviewed again; an approval never follows a new schedule silently.
            db.execute('DELETE FROM decisiones WHERE empleado_id=? AND fecha=?', (employee,day))
            audit(db,employee,day,'ASIGNAR_TURNO',dict(prior) if prior else None,dict(turno_id=shift_id,turno=snapshot),user)
        # Check neighboring weeks as well.
        all_rows = db.execute("SELECT fecha,turno_json FROM asignaciones WHERE empleado_id=? AND turno_id!='DESCANSO' ORDER BY fecha",(employee,)).fetchall()
        intervals = [bounds(r['fecha'],json.loads(r['turno_json'])) for r in all_rows]
        if any(intervals[i][1] > intervals[i+1][0] for i in range(len(intervals)-1)):
            raise ValueError('La asignación solapa el turno del día siguiente')


def save_decision(employee, day, data, user, audit_combined=True):
    date.fromisoformat(day)
    code = data.get('cod_ausencia', '')
    if code and (code not in CODIGOS_JUSTIFICACION or code == '732'):
        raise ValueError('Concepto de ausencia inválido; las tardanzas se calculan automáticamente')
    paid = data.get('remunerada')
    if paid not in (None, True, False):
        raise ValueError('Estado de remuneración inválido')
    if code in PAID_DEFAULTS:
        paid = PAID_DEFAULTS[code]
    kind = data.get('tipo_dia','normal')
    if kind not in ('normal','descanso_obligatorio','libre','compensatorio_feriado'):
        raise ValueError('Tipo de día inválido')
    late_state = data.get('tardanza_estado','pendiente')
    late_reason = str(data.get('motivo_tardanza','')).strip()[:1000]
    if late_state not in ('pendiente','validada','invalidada'):
        raise ValueError('Validación de tardanza inválida')
    if late_state=='invalidada' and not late_reason:
        raise ValueError('Indique el motivo para invalidar la tardanza')
    extra_state=data.get('he_estado','aprobada' if data.get('he_aprobadas') else 'pendiente')
    extra_reason=str(data.get('motivo_he','')).strip()[:1000]
    if extra_state not in ('pendiente','aprobada','rechazada'):
        raise ValueError('Validación de HE inválida')
    if extra_state=='rechazada' and not extra_reason:
        raise ValueError('Indique el motivo para rechazar las HE')
    sunday_state=data.get('domingo_estado','pendiente')
    sunday_reason=str(data.get('motivo_domingo','')).strip()[:1000]
    if sunday_state not in ('pendiente','aprobada','rechazada'):
        raise ValueError('Validación de domingo inválida')
    if sunday_state=='rechazada' and not sunday_reason:
        raise ValueError('Indique el motivo para rechazar el domingo trabajado')
    values = dict(cod_ausencia=code, remunerada=paid, he_aprobadas=extra_state=='aprobada',he_estado=extra_state,motivo_he=extra_reason,
                  incluir_anticipadas=bool(data.get('incluir_anticipadas')), tipo_dia=kind,
                  tardanza_estado=late_state,motivo_tardanza=late_reason,
                  domingo_estado=sunday_state,motivo_domingo=sunday_reason,nota=str(data.get('nota','')).strip()[:1000])
    with database.transaction() as db:
        row = db.execute('SELECT datos FROM decisiones WHERE empleado_id=? AND fecha=?',(employee,day)).fetchone()
        db.execute('INSERT INTO decisiones VALUES (?,?,?,?,?) ON CONFLICT(empleado_id,fecha) DO UPDATE SET datos=excluded.datos,usuario=excluded.usuario,actualizado=excluded.actualizado',
                   (employee,day,json.dumps(values,ensure_ascii=False),user,today().isoformat()))
        if audit_combined:
            audit(db,employee,day,'DECIDIR_NOVEDAD',json.loads(row['datos']) if row else None,values,user)


def holiday(day, config=None):
    """National statutory dates; configured exceptions override these defaults."""
    config = database.read_catalog('config') if config is None else config
    override = config.get('calendario', {}).get(day.isoformat())
    if override is not None:
        return override  # feriado, descanso_compensatorio, normal
    # Nov 4 is not a statutory national holiday. Dec 20 was added by Law 291/2022.
    fixed = {'01-01','01-09','05-01','11-03','11-05','11-10','11-28','12-08','12-20','12-25'}
    y = day.year
    a,b,c = y%19,y//100,y%100
    d,e = b//4,b%4
    f = (b+8)//25
    g = (b-f+1)//3
    h = (19*a+b-d-g+15)%30
    i,k = c//4,c%4
    l = (32+2*e+2*i-h-k)%7
    m = (a+11*h+22*l)//451
    n = h+l-7*m+114
    easter = date(y,n//31,n%31+1)
    def is_holiday(value):
        return value.strftime('%m-%d') in fixed or value in (easter-timedelta(days=47), easter-timedelta(days=2)) or (value.month == 7 and value.day == 1 and (value.year-2024)%5 == 0)
    if is_holiday(day): return 'feriado'
    if day.weekday() == 0 and is_holiday(day-timedelta(days=1)): return 'descanso_compensatorio'
    return 'normal'


def sessions(rows):
    """Pair consecutive punches without letting an old entry consume a later shift."""
    result, current = [], None
    for row in rows:
        try: instant = datetime.strptime(row['Fecha_Hora'], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            result.append(dict(start=None,end=None,raw=row,error='FECHA_INVALIDA'))
            continue
        kind = row['Tipo'].strip().upper()
        if current and instant-current['start'] >= MAX_SESSION_DURATION:
            current['error'] = 'MARCACION_INCOMPLETA'
            result.append(current)
            current = None
        if kind == 'ENTRADA':
            if current:
                if instant == current['start']: continue
                current['error'] = 'MARCACION_INCOMPLETA'
                result.append(current)
            current = dict(start=instant,end=None,raw=row,error='')
        elif kind in ('SALIDA','TIEMPO EXTRA'):
            if current:
                current['end'] = instant
                result.append(current)
                current = None
            elif not result or result[-1].get('end') != instant:
                result.append(dict(start=None,end=instant,raw=row,error='MARCACION_INCOMPLETA'))
    if current:
        current['error'] = current.get('error') or 'MARCACION_INCOMPLETA'
        result.append(current)
    return result


def session_alerts(item):
    alerts = [item['error']] if item['error'] else []
    if item['error'] == 'MARCACION_INCOMPLETA':
        if item['start'] is None: alerts.append('MARCACION_SIN_ENTRADA')
        if item['end'] is None: alerts.append('MARCACION_SIN_SALIDA')
    return alerts


def allocate(rows, schedule):
    grouped, unmatched = defaultdict(list), []
    by_employee = defaultdict(dict)
    for (employee,day), item in schedule.items():
        if item['turno_id'] != 'DESCANSO':
            by_employee[employee][day] = bounds(day,json.loads(item['turno_json']))
    for employee, records in rows.items():
        for item in sessions(records):
            instant = item['start'] or item['end']
            if instant is None:
                item['employee'] = employee
                unmatched.append(item)
                continue
            candidates = []
            for day,(a,b) in by_employee[employee].items():
                distance = abs(((item['start'] or instant)-a).total_seconds()) if item['start'] else abs((instant-b).total_seconds())
                intersects = item['start'] and item['end'] and overlap(item['start'],item['end'],a,b)>0
                inside = instant and a <= instant <= b
                if instant and (distance <= 4*3600 or intersects or inside):
                    candidates.append((distance,day))
            if candidates:
                candidates.sort()
                if len(candidates)>1 and candidates[0][0] == candidates[1][0]:
                    item['error'] = 'ASIGNACION_AMBIGUA'
                grouped[(employee,candidates[0][1])].append(item)
            else:
                item['employee'] = employee
                unmatched.append(item)
    return grouped, unmatched


def calculate(employee, day, assignment, attendance, decision, now, config=None):
    shift = json.loads(assignment['turno_json'])
    base = dict(id=employee, emp_id=employee, fecha=day, turno_id=assignment['turno_id'],
        turno_nombre=shift.get('nombre','Descanso'), entrada=None, salida=None, entrada_fecha='', salida_fecha='',
        horas_totales=0, horas_ordinarias=0, horas_programadas=0, horas_pagables=0, horas_equivalentes=0,
        ausencia_horas=0, descuento_horas=0, permiso_horas=0, tardanza_min=0, anticipacion_min=0,
        extra_horas=0, extra_aprobadas=0, conceptos=[], alertas=[], intervalos_extra=[],
        cod_ausencia=decision.get('cod_ausencia',''), he_aprobadas=decision.get('he_aprobadas',False),
        remunerada=decision.get('remunerada'), incluir_anticipadas=decision.get('incluir_anticipadas',False),
        nota=decision.get('nota',''), jornada='', ausencia=False, estado='DESCANSO')
    base['tipo_dia'] = decision.get('tipo_dia','normal')
    base.update(he_estado=decision.get('he_estado','aprobada' if decision.get('he_aprobadas') else 'pendiente'),motivo_he=decision.get('motivo_he',''))
    base.update(tardanza_estado=decision.get('tardanza_estado','pendiente'),motivo_tardanza=decision.get('motivo_tardanza',''),tardanza_computable_min=0)
    if assignment['turno_id'] == 'DESCANSO': return base
    a,b = bounds(day,shift)
    base['inicio_programado'],base['fin_programado'] = a.isoformat(' '),b.isoformat(' ')
    details = shift_details(shift)
    base.update(jornada=details['jornada'], horas_programadas=details['horas_ordinarias'])
    if not shift.get('configurado'):
        base['alertas'].append('TURNO_SIN_VALIDAR_RH')
    if details['horas_programadas'] > details['limite']:
        base['alertas'].append('HORARIO_EXCEDE_LIMITE_ORDINARIO')
    closed_sunday=date.fromisoformat(day).weekday()==6 and any(s['start'] and s['end'] and s['start'].date().isoformat()==day and s['end']<=now for s in attendance)
    valid = [(s['start'],s['end']) for s in attendance if s['start'] and s['end'] and not s['error']]
    for item in attendance:
        base['alertas'].extend(session_alerts(item))
    starts = [s['start'] for s in attendance if s['start']]
    ends = [s['end'] for s in attendance if s['end']]
    if starts:
        entry = min(starts)
        base.update(entrada=entry.strftime('%H:%M:%S'), entrada_fecha=entry.isoformat(' '),
            tardanza_min=max(0,(entry-a).total_seconds()/60), anticipacion_min=max(0,(a-entry).total_seconds()/60))
    if ends:
        end = max(ends)
        base.update(salida=end.strftime('%H:%M:%S'),salida_fecha=end.isoformat(' '))
    if now < b and not closed_sunday:
        base['estado'] = 'EN_CURSO' if now>=a else 'PROGRAMADO'
        # No absence or deduction is determined before the shift ends.
        return base
    if base['alertas'] and any(x.startswith('MARCACION') or x=='ASIGNACION_AMBIGUA' for x in base['alertas']):
        base.update(estado='REVISAR',horas_totales='Incompleto')
        return base
    removed = [] if shift.get('descanso_remunerado') else breaks(day,shift)
    work = subtract(valid,removed)
    if closed_sunday and seconds(work)>0:
        import sunday
        return sunday.calculate(base,shift,work,decision,config)
    planned = subtract([(a,b)],removed)
    # Freeze the ordinary scheduled slots before considering actual attendance.
    # Late arrivals cannot move the legal/contractual end of ordinary work.
    ordinary_plan = []
    remaining = details['horas_ordinarias']*3600
    for x,y in planned:
        duration = min((y-x).total_seconds(),remaining)
        if duration>0: ordinary_plan.append((x,x+timedelta(seconds=duration)))
        remaining -= duration
    ordinary = [(max(x,c),min(y,d)) for x,y in work for c,d in ordinary_plan if min(y,d)>max(x,c)]
    considered = work if decision.get('incluir_anticipadas') else [(max(x,a),y) for x,y in work if y>a]
    extra = subtract(considered,ordinary_plan)
    worked = seconds(work)/3600
    normal = seconds(ordinary)/3600
    missing = max(0,details['horas_ordinarias']-normal)
    late_hours = min(missing, base['tardanza_min']/60)
    absence = max(0, missing-late_hours)
    if not attendance:
        absence,late_hours = details['horas_ordinarias'],0
    raw_missing = missing
    justified_late = late_hours if decision.get('tardanza_estado')=='invalidada' else 0
    missing -= justified_late
    if missing<1e-9: missing=0
    if absence<1e-9: absence=0
    late_hours -= justified_late
    base['tardanza_computable_min'] = 0 if decision.get('tardanza_estado')=='invalidada' else base['tardanza_min']
    if base['tardanza_min']>0 and decision.get('tardanza_estado','pendiente')=='pendiente':
        base['alertas'].append('TARDANZA_PENDIENTE')
    code = decision.get('cod_ausencia','')
    policy = (config or {}).get('politicas_ausencia', {})
    paid = PAID_DEFAULTS.get(code,policy.get(code,decision.get('remunerada')))
    # Missing time and lateness are separate incidences. A missing-time code
    # can never justify or deduct the lateness portion a second time.
    permission = justified_late + (absence if code and paid else 0)
    base.update(horas_totales=worked,horas_ordinarias=normal, ausencia_horas=absence,
        ausencia=absence>1e-9, permiso_horas=permission, descuento_horas=round(max(0,raw_missing-permission),12),
        horas_pagables=normal+permission, extra_horas=seconds(extra)/3600, intervalos_extra=extra,
        extra_aprobadas=seconds(extra)/3600 if decision.get('he_aprobadas') else 0,
        estado='AUSENCIA' if not attendance else 'COMPLETO', remunerada=paid)
    base['horas_equivalentes'] = base['horas_pagables']*(8/LIMITS[details['jornada']])
    def concept(code, hours, treatment):
        if hours>1e-9:
            base['conceptos'].append(dict(codigo_colaborador=employee,con_codigo=code,
                con_nombre=CODIGOS_JUSTIFICACION[code],cantidad_horas=hours,tratamiento=treatment,factor=1))
    concept('310',justified_late,'TARDANZA_INVALIDADA_REMUNERADA')
    concept('732',late_hours,'DESCUENTO')
    if absence>1e-9:
        if not code:
            base['alertas'].append('AUSENCIA_PENDIENTE_CODIGO')
        if code and paid is None:
            base['alertas'].append('DEFINIR_REMUNERACION_PERMISO')
            base['descuento_horas'] = late_hours
        concept(code or '730',absence,'REMUNERADO' if paid else ('REVISAR' if code and paid is None else 'DESCUENTO'))
    if extra and base['he_estado']=='pendiente': base['alertas'].append('HE_PENDIENTE')
    # Ordinary premium by actual calendar segment, not just the shift's start date.
    for x,y in split(ordinary):
        special = holiday(x.date(), config)
        individual = base['tipo_dia'] if x.date().isoformat()==day else 'normal'
        code = '650' if special=='feriado' else ('652' if special=='descanso_compensatorio' or x.weekday()==6 or individual!='normal' else '')
        if code:
            base['conceptos'].append(dict(codigo_colaborador=employee,con_codigo=code,
                con_nombre=CONCEPTOS_PANAMA[code]['nombre'],cantidad_horas=(y-x).total_seconds()/3600,
                tratamiento='RECARGO',factor=2.5 if code=='650' else (1.75 if individual=='libre' and not 6<=x.hour<18 else 1.5)))
    return base


def add_overtime(days, config=None):
    weekly, daily = defaultdict(float), defaultdict(float)
    for day in sorted(days,key=lambda d:(d['fecha'],d['id'])):
        if not day.get('intervalos_extra'): continue
        start = datetime.fromisoformat(day['inicio_programado'])
        for a,b in split(day['intervalos_extra']):
            cursor = a
            while cursor<b:
                monday = (cursor.date()-timedelta(days=cursor.weekday())).isoformat()
                wk = (day['id'],monday)
                dk = (day['id'],day['fecha'])
                available = min(max(0,3*3600-daily[dk]),max(0,9*3600-weekly[wk]))
                excess = available<=0
                end = b if excess else min(b,cursor+timedelta(seconds=available))
                duration = (end-cursor).total_seconds()
                nocturnal = not 6<=cursor.hour<18
                # Art 33: extension of a night shift or a mixed shift started at night is 75%.
                if day['jornada']=='NOCTURNA' or (day['jornada']=='MIXTA' and not 6<=start.hour<18):
                    family,factor = ('night' if nocturnal else 'night_day'),1.75
                elif day['jornada']=='MIXTA' or nocturnal:
                    family,factor = 'day_night',1.5
                else:
                    family,factor = 'day',1.25
                special = holiday(cursor.date(), config)
                individual = day['tipo_dia'] if cursor.date().isoformat()==day['fecha'] else 'normal'
                premium = 2.5 if special=='feriado' else (1.5 if cursor.weekday()==6 or special=='descanso_compensatorio' or individual!='normal' else 1)
                if special!='feriado' and individual=='libre' and nocturnal:
                    premium=1.75
                if day.get('dia_descanso_trabajado'):
                    premium=max(1.5,premium)
                mapping = {
                    1: {'day':('450','454'),'night_day':('452','456'),'night':('550','554'),'day_night':('552','556')},
                    1.5: {'day':('858','862'),'night_day':('860','864'),'night':('958','962'),'day_night':('960','964')},
                    2.5: {'day':('866','854'),'night_day':('852','856'),'night':('950','954'),'day_night':('952','956')}}
                code = mapping[1.5 if premium==1.75 else premium][family][int(excess)]
                if day['he_aprobadas']:
                    day['conceptos'].append(dict(codigo_colaborador=day['id'],con_codigo=code,
                        con_nombre=CONCEPTOS_PANAMA[code]['nombre'],cantidad_horas=duration/3600,
                        tratamiento='HE',factor=factor*premium*(1.75 if excess else 1)))
                daily[dk] += duration
                weekly[wk] += duration
                if excess and 'EXCESO_HE_LEGAL' not in day['alertas']: day['alertas'].append('EXCESO_HE_LEGAL')
                cursor = end


@database.consistent_read
def report(area, employee='', start='', end='', now=None):
    now = now or today()
    config = database.read_catalog('config')
    if not start or not end:
        existing = database.marks(area,employee)
        starts = [r['Fecha_Hora'][:10] for r in existing if len(r['Fecha_Hora'])>=10]
        start = min(starts) if starts else (now.date()-timedelta(days=14)).isoformat()
        end = max(max(starts) if starts else now.date().isoformat(),now.date().isoformat())
    dates(start,end)
    # Include the full Monday-based weeks preceding the export for the nine-hour limit.
    context_start = date.fromisoformat(start)-timedelta(days=date.fromisoformat(start).weekday()+1)
    context_end = date.fromisoformat(end)+timedelta(days=1)
    schedule = assignments(context_start.isoformat(),context_end.isoformat())
    decisions_by_day = decisions(context_start.isoformat(),context_end.isoformat())
    import terminal
    employees = {k:v for k,v in terminal.payroll_employees().items()
                 if (not employee or k==employee) and (area=='TODAS' or str(v.get('area','')).upper().replace('Í','I')==area)}
    rows = defaultdict(list)
    for item in database.marks(employee=employee,start=context_start.isoformat(),end=(context_end+timedelta(days=1)).isoformat()):
        if item['ID_Personal'] in employees: rows[item['ID_Personal']].append(item)
    grouped, unmatched = allocate(rows,schedule)
    import sunday
    unmatched=sunday.attach_rest_work(schedule,grouped,unmatched,employees,database.read_catalog('turnos'))
    result = []
    for (emp,day),assignment in schedule.items():
        if emp not in employees: continue
        if employees[emp].get('_fecha_baja') and day>employees[emp]['_fecha_baja']: continue
        item = calculate(emp,day,assignment,grouped[(emp,day)],decisions_by_day.get((emp,day),{}),now,config)
        item.update(nombre=f"{employees[emp].get('nombre','')} {employees[emp].get('apellido','')}".strip(),area=employees[emp].get('area',''))
        result.append(item)
    add_overtime(result,config)
    weekly = defaultdict(list)
    for item in result:
        if item['jornada'] and not item.get('dia_descanso_trabajado'):
            monday = (date.fromisoformat(item['fecha'])-timedelta(days=date.fromisoformat(item['fecha']).weekday())).isoformat()
            weekly[(item['id'],monday)].append(item)
    for week in weekly.values():
        # Mixed weeks are held for RH review if they exceed six equivalent days.
        if sum(item['horas_ordinarias']/LIMITS[item['jornada']] for item in week)>6+1e-9:
            for item in week:
                item['alertas'].append('REVISAR_LIMITE_ORDINARIO_SEMANAL')
    result = [r for r in result if start<=r['fecha']<=end]
    for item in unmatched:
        stamp = item['start'] or item['end']
        day = stamp.date().isoformat() if stamp else item['raw']['Fecha_Hora'][:10]
        if not start<=day<=end: continue
        emp = item['employee']
        result.append(dict(id=emp,emp_id=emp,nombre=f"{employees[emp].get('nombre','')} {employees[emp].get('apellido','')}".strip(),
            area=employees[emp].get('area',''),fecha=day,entrada=item['start'].strftime('%H:%M:%S') if item['start'] else None,
            salida=item['end'].strftime('%H:%M:%S') if item['end'] else None,entrada_fecha=str(item['start'] or ''),salida_fecha=str(item['end'] or ''),
            turno_id='',turno_nombre='',jornada='',estado='SIN_TURNO',horas_totales='Incompleto',horas_ordinarias=0,
            horas_programadas=0,horas_pagables=0,horas_equivalentes=0,ausencia_horas=0,descuento_horas=0,permiso_horas=0,
            tardanza_min=0,anticipacion_min=0,extra_horas=0,extra_aprobadas=0,conceptos=[],alertas=['MARCACION_SIN_TURNO']+session_alerts(item),ausencia=False,
            cod_ausencia='',he_aprobadas=False,remunerada=None,nota=''))
    for emp,info in employees.items():
        for day in dates(start,end):
            if (emp,day) in schedule or (info.get('fecha_ingreso') and day<info['fecha_ingreso']) or (info.get('_fecha_baja') and day>info['_fecha_baja']):
                continue
            sunday = date.fromisoformat(day).weekday()==6
            result.append(dict(id=emp,emp_id=emp,nombre=f"{info.get('nombre','')} {info.get('apellido','')}".strip(),area=info.get('area',''),
                fecha=day,turno_id='DESCANSO' if sunday else '',turno_nombre='Descanso dominical' if sunday else '',jornada='',estado='DESCANSO' if sunday else 'SIN_PLAN',entrada=None,salida=None,entrada_fecha='',salida_fecha='',
                horas_totales=0,horas_programadas=0,horas_ordinarias=0,horas_pagables=0,horas_equivalentes=0,ausencia_horas=0,
                descuento_horas=0,permiso_horas=0,tardanza_min=0,anticipacion_min=0,extra_horas=0,extra_aprobadas=0,conceptos=[],
                alertas=[] if sunday else ['PLANIFICACION_PENDIENTE'],ausencia=False,cod_ausencia='',he_aprobadas=False,remunerada=None,nota=''))
    pending={e['employee_id'] for e in terminal.review_events(area,employee,start,end) if e['kind']=='mark'}
    for item in result:
        if item['id'] in pending: item['alertas'].append('MARCACION_TERMINAL_PENDIENTE')
    return sorted(result,key=lambda r:(r['fecha'],r['nombre']),reverse=True)


@database.consistent_read
def monthly(area, month, employee='', now=None):
    now = now or today()
    first = date.fromisoformat(month+'-01')
    last = first.replace(day=calendar.monthrange(first.year,first.month)[1])
    rows = report(area,employee,first.isoformat(),last.isoformat(),now)
    grouped = defaultdict(list)
    for item in rows: grouped[item['id']].append(item)
    import terminal
    employees = {k:v for k,v in terminal.payroll_employees().items() if (not employee or k==employee) and (area=='TODAS' or str(v.get('area','')).upper().replace('Í','I')==area) and (not v.get('_fecha_baja') or v['_fecha_baja']>=first.isoformat()) and (not v.get('fecha_ingreso') or v['fecha_ingreso']<=last.isoformat())}
    result = []
    for emp,info in employees.items():
        days = grouped[emp]
        late = sum(d.get('tardanza_computable_min',d['tardanza_min']) for d in days)
        real_late = sum(d['tardanza_min'] for d in days)
        absences = sum(bool(d['ausencia']) for d in days)
        elapsed = min(last,now.date()-timedelta(days=1))
        if info.get('_fecha_baja'): elapsed=min(elapsed,date.fromisoformat(info['_fecha_baja']))
        hiring = date.fromisoformat(info.get('fecha_ingreso') or first.isoformat())
        expected_days = max(0,(elapsed-max(first,hiring)).days+1)
        recorded = len({d['fecha'] for d in days if d['fecha']<=elapsed.isoformat() and d['estado'] not in ('SIN_TURNO','SIN_PLAN')})
        unresolved = any((d['estado'] in ('REVISAR','SIN_TURNO') or 'TURNO_SIN_VALIDAR_RH' in d['alertas']) and d['fecha']<=now.date().isoformat() for d in days)
        unresolved = unresolved or any(d['estado'] in ('EN_CURSO','PROGRAMADO') and d['fecha']<=elapsed.isoformat() for d in days)
        unresolved = unresolved or any('TARDANZA_PENDIENTE' in d['alertas'] for d in days)
        unresolved = unresolved or any('MARCACION_TERMINAL_PENDIENTE' in d['alertas'] for d in days)
        state = 'NO_APLICA' if absences or late>30 else ('PENDIENTE' if unresolved or recorded<expected_days or not days else ('PROVISIONAL' if now.date()<=last else 'APLICA'))
        fingerprint = hashlib.sha256(json.dumps(days,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()
        with database.reading() as db:
            saved = db.execute('SELECT * FROM validaciones_bono WHERE empleado_id=? AND mes=?',(emp,month)).fetchone()
        current = saved and saved['huella']==fingerprint
        result.append(dict(id=emp,nombre=f"{info.get('nombre','')} {info.get('apellido','')}".strip(),minutos_tarde=late,minutos_tarde_reales=real_late,ausencias=absences,
                           dias_sin_plan=max(0,expected_days-recorded),estado=state,huella=fingerprint,
                           validacion=saved['decision'] if current else 'PENDIENTE',
                           validado_por=saved['usuario'] if current else '',motivo_bono=saved['motivo'] if current else ''))
    return result


def validate_bonus(area, employee, month, decision, reason, user):
    if decision not in ('APROBADO','RECHAZADO'):
        raise ValueError('Decisión de bono inválida')
    reason = str(reason).strip()[:1000]
    if decision=='RECHAZADO' and not reason:
        raise ValueError('Indique el motivo del rechazo')
    with database.transaction() as db:
        results = monthly(area,month,employee)
        if not results: raise ValueError('Colaborador fuera del alcance')
        result=results[0]
        if decision=='APROBADO' and result['estado']!='APLICA':
            raise ValueError('El mes debe estar cerrado y cumplir los requisitos del bono')
        previous=db.execute('SELECT * FROM validaciones_bono WHERE empleado_id=? AND mes=?',(employee,month)).fetchone()
        db.execute('INSERT INTO validaciones_bono VALUES (?,?,?,?,?,?,?) ON CONFLICT(empleado_id,mes) DO UPDATE SET decision=excluded.decision,motivo=excluded.motivo,huella=excluded.huella,usuario=excluded.usuario,actualizado=excluded.actualizado',
                   (employee,month,decision,reason,result['huella'],user,today().isoformat()))
        audit(db,employee,month+'-01','VALIDAR_BONO',dict(previous) if previous else None,
              dict(decision=decision,motivo=reason,huella=result['huella']),user)
