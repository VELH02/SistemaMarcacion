"""Authenticated, durable and idempotent terminal protocol v2."""
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta
import database


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS terminal_events (
        event_id TEXT PRIMARY KEY, device_id TEXT NOT NULL, kind TEXT NOT NULL,
        fingerprint TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
        reason TEXT NOT NULL, employee_id TEXT NOT NULL, record_id TEXT NOT NULL,
        received TEXT NOT NULL, reviewed_by TEXT NOT NULL DEFAULT '', reviewed_at TEXT NOT NULL DEFAULT '')''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_terminal_review ON terminal_events(status,received)')
    db.execute('''CREATE TABLE IF NOT EXISTS empleados_baja (
        empleado_id TEXT PRIMARY KEY, datos TEXT NOT NULL, fecha_baja TEXT NOT NULL, usuario TEXT NOT NULL)''')
    # Recover tombstones from the existing audit, never recreate active employees.
    if not db.execute("SELECT 1 FROM metadata WHERE clave='terminal_v2'").fetchone():
        for row in db.execute("SELECT * FROM auditoria_planificacion WHERE accion='BAJA_COLABORADOR' ORDER BY id"):
            db.execute('INSERT OR REPLACE INTO empleados_baja VALUES (?,?,?,?)',
                (row['empleado_id'],row['antes'],row['fecha'],row['usuario']))
        db.execute("INSERT INTO metadata VALUES ('terminal_v2','1')")


def secret(kind):
    override=os.environ.get('ALICAPSA_TERMINAL_TOKEN' if kind=='terminal' else 'ALICAPSA_SECRET_KEY')
    if override: return override
    with database.reading() as db:
        row=db.execute('SELECT valor FROM metadata WHERE clave=?',('secret.'+kind,)).fetchone()
        if row: return row[0]
    with database.transaction() as db:
        row=db.execute('SELECT valor FROM metadata WHERE clave=?',('secret.'+kind,)).fetchone()
        if row: return row[0]
        value=secrets.token_urlsafe(48)
        db.execute('INSERT INTO metadata VALUES (?,?)',('secret.'+kind,value))
        return value


def authorized(header):
    return bool(header) and hmac.compare_digest(header,'Bearer '+secret('terminal'))


def uid(value):
    return re.sub(r'[\s:\-]','',str(value or '')).upper()


def validate_card(employee_id,card,employees):
    clean=uid(card)
    if clean and any(key!=employee_id and uid(info.get('rfid',''))==clean for key,info in employees.items()):
        raise ValueError('La tarjeta ya pertenece a otro colaborador; no se reasigna automáticamente')
    return clean


def identity_revision(info):
    data=[uid(info.get('rfid')),info.get('vector_facial',[])]
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def receipt(row,duplicate=False):
    return dict(event_id=row['event_id'],persistido=True,status=row['status'],duplicado=duplicate,
                record_id=row['record_id'],motivo=row['reason'],mensaje='Registro recibido' if row['status']=='accepted' else 'Registro conservado para revisión')


def employee_for_mark(employee_id,stamp):
    employee=database.read_catalog('empleados').get(employee_id)
    if employee: return employee
    with database.reading() as db:
        row=db.execute('SELECT * FROM empleados_baja WHERE empleado_id=?',(employee_id,)).fetchone()
    if row and stamp[:10]<=row['fecha_baja']:
        return json.loads(row['datos'])
    return None


def ingest(kind,data,ip=''):
    import time_sync
    if not isinstance(data,dict): raise ValueError('Se requiere un objeto JSON')
    event_id=str(data.get('event_id',''))
    device_id=str(data.get('device_id',''))
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',event_id) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',device_id):
        raise ValueError('El terminal debe enviar event_id y device_id estables (protocolo v2)')
    encoded=json.dumps(data,ensure_ascii=False,sort_keys=True,allow_nan=False)
    fingerprint=hashlib.sha256(encoded.encode()).hexdigest()
    with database.transaction() as db:
        prior=db.execute('SELECT * FROM terminal_events WHERE event_id=?',(event_id,)).fetchone()
        if prior:
            if prior['fingerprint']!=fingerprint or prior['device_id']!=device_id or prior['kind']!=kind:
                return dict(event_id=event_id,persistido=False,error='EVENT_ID_CONFLICT',mensaje='El ID ya corresponde a otro contenido'),409
            return receipt(prior,True),200 if prior['status'] in ('accepted','rejected') else 202
        employee_id=str(data.get('empleado_id','')).strip().upper()
        reason=''
        record_id=''
        employees=database.read_catalog('empleados')
        if not re.fullmatch(r'[A-Z0-9_-]{1,64}',employee_id): reason='ID_COLABORADOR_INVALIDO'
        elif kind=='enrol':
            if employee_id not in employees: reason='ALTA_PREVIA_REQUERIDA_EN_SERVIDOR'
            elif data.get('revision_biometrica')!=identity_revision(employees[employee_id]):
                reason='BIOMETRIA_MODIFICADA_O_SIN_REVISION_PREVIA; SINCRONICE_Y_REPITA_ENROLAMIENTO'
            else:
                vector=data.get('vector_facial')
                if not isinstance(vector,list) or len(vector)!=128 or any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for v in vector):
                    reason='VECTOR_FACIAL_INVALIDO'
                else:
                    try: card=validate_card(employee_id,data.get('rfid') or data.get('nfc'),employees)
                    except ValueError: reason='TARJETA_ASIGNADA_A_OTRO_COLABORADOR'
                    if not reason and not card: reason='TARJETA_REQUERIDA'
                    if not reason:
                        employee=dict(employees[employee_id],rfid=card,vector_facial=vector)
                        employees[employee_id]=employee
                        database.write_catalog('empleados',employees)
        else:
            stamp=str(data.get('fecha_hora') or data.get('timestamp') or '')
            mark_type=str(data.get('tipo_marcacion','')).strip().upper()
            try: instant=datetime.strptime(stamp,'%Y-%m-%d %H:%M:%S')
            except ValueError: reason='FECHA_INVALIDA'; instant=None
            employee=employee_for_mark(employee_id,stamp) if instant else None
            if not reason and mark_type not in ('ENTRADA','SALIDA','TIEMPO EXTRA'): reason='TIPO_INVALIDO'
            if not reason and not employee: reason='COLABORADOR_NO_ACTIVO_EN_FECHA'
            if not reason and instant>time_sync.get_current_time()+timedelta(minutes=5): reason='RELOJ_ADELANTADO'
            if not reason and data.get('reloj_sincronizado') is not True: reason='HORA_PENDIENTE_VERIFICACION'
            if not reason and data.get('permiso_admin'): reason='AUTORIZACION_PERSONAL_PENDIENTE_VERIFICACION'
            if not reason:
                actual=uid(data.get('nfc') or data.get('rfid'))
                expected=uid(employee.get('rfid'))
                owners=[key for key,info in employees.items() if expected and uid(info.get('rfid'))==expected]
                if not actual or actual!=expected or len(owners)>1: reason='TARJETA_NO_COINCIDE_O_AMBIGUA'
            if not reason:
                record_id=uuid.uuid4().hex
                database.insert_mark(dict(ID_Registro=record_id,ID_Personal=employee_id,
                    Nombre=f"{employee.get('nombre','')} {employee.get('apellido','')}".strip(),
                    Area=str(employee.get('area','')).upper().replace('Í','I'),Tipo=mark_type,Fecha_Hora=stamp,
                    IP_Origen=ip or '',Estado='Aprobado',Nota=str(data.get('nota',''))))
        status='review' if reason else 'accepted'
        db.execute('INSERT INTO terminal_events(event_id,device_id,kind,fingerprint,payload,status,reason,employee_id,record_id,received) VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (event_id,device_id,kind,fingerprint,encoded,status,reason,employee_id,record_id,time_sync.get_time_str()))
        row=db.execute('SELECT * FROM terminal_events WHERE event_id=?',(event_id,)).fetchone()
        return receipt(row),202 if reason else (201 if kind=='enrol' else 200)


def archive(employee_id,employee,user):
    import time_sync
    with database.transaction() as db:
        db.execute('INSERT OR REPLACE INTO empleados_baja VALUES (?,?,?,?)',
            (employee_id,json.dumps(employee,ensure_ascii=False),time_sync.get_time_str('%Y-%m-%d'),user))


def payroll_employees():
    result=database.read_catalog('empleados')
    with database.reading() as db:
        for row in db.execute('SELECT * FROM empleados_baja'):
            if row['empleado_id'] not in result:
                result[row['empleado_id']]=dict(json.loads(row['datos']),_fecha_baja=row['fecha_baja'])
    return result


def review_events(scope='TODAS',employee='',start='',end=''):
    """Only the owning area sees a record; unknown identities require an admin."""
    employees=payroll_employees()
    first=(datetime.fromisoformat(start)-timedelta(days=1)).date().isoformat() if start else ''
    last=(datetime.fromisoformat(end)+timedelta(days=1)).date().isoformat() if end else ''
    result=[]
    with database.reading() as db:
        for row in db.execute("SELECT * FROM terminal_events WHERE status='review' ORDER BY received DESC"):
            if employee and row['employee_id']!=employee: continue
            info=employees.get(row['employee_id'],{})
            if scope!='TODAS' and str(info.get('area','')).strip().upper().replace('Í','I')!=scope: continue
            payload=json.loads(row['payload'])
            stamp=str(payload.get('fecha_hora') or payload.get('timestamp') or '')
            try: day=datetime.strptime(stamp,'%Y-%m-%d %H:%M:%S').date().isoformat()
            except ValueError: day=''
            if row['kind']=='mark' and day and (first and day<first or last and day>last): continue
            result.append(dict(row,payload=payload,nombre=f"{info.get('nombre','')} {info.get('apellido','')}".strip()))
    return result


def resolve(identifier,decision,reason,user,scope,employee='',stamp='',mark_type=''):
    """Keep the original receipt intact; record the human decision and resulting mark."""
    import planning
    import time_sync
    reason=str(reason).strip()
    if decision not in ('accepted','rejected') or not reason or len(reason)>1000:
        raise ValueError('Seleccione una decisión e indique el motivo (máximo 1000 caracteres)')
    with database.transaction() as db:
        original=db.execute('SELECT * FROM terminal_events WHERE event_id=?',(identifier,)).fetchone()
        if not original: raise ValueError('Evento inexistente')
        before={key:original[key] for key in ('event_id','employee_id','status','reason','record_id')}
        owners=payroll_employees()
        owner=owners.get(original['employee_id'],{})
        if scope!='TODAS' and str(owner.get('area','')).upper().replace('Í','I')!=scope:
            raise PermissionError('Evento fuera del área del coordinador')
        if original['status']!='review': raise ValueError('El evento ya tiene una decisión; recargue la página')
        payload=json.loads(original['payload'])
        record_id=''
        target=employee.strip().upper() or original['employee_id']
        timestamp=stamp.strip().replace('T',' ') or str(payload.get('fecha_hora') or payload.get('timestamp') or '')
        if len(timestamp)==16: timestamp+=':00'
        if decision=='accepted':
            if original['kind']!='mark': raise ValueError('Corrija el enrolamiento y repítalo desde el terminal; no se aprueba una identidad dudosa')
            instant=datetime.strptime(timestamp,'%Y-%m-%d %H:%M:%S')
            if instant>time_sync.get_current_time()+timedelta(minutes=5): raise ValueError('La marcación no puede estar en el futuro')
            info=employee_for_mark(target,timestamp)
            if not info: raise ValueError('El colaborador debe estar registrado en esa fecha')
            if scope!='TODAS' and str(info.get('area','')).upper().replace('Í','I')!=scope: raise PermissionError('Colaborador fuera del área')
            kind=mark_type.strip().upper() or str(payload.get('tipo_marcacion','')).upper()
            if kind not in ('ENTRADA','SALIDA','TIEMPO EXTRA'): raise ValueError('Tipo de marcación inválido')
            record_id=uuid.uuid4().hex
            database.insert_mark(dict(ID_Registro=record_id,ID_Personal=target,
                Nombre=f"{info.get('nombre','')} {info.get('apellido','')}".strip(),Area=str(info.get('area','')).upper().replace('Í','I'),
                Tipo=kind,Fecha_Hora=timestamp,IP_Origen='REVISION_TERMINAL',Estado='Aprobado',
                Nota='Evento '+identifier+'; '+reason))
        db.execute('UPDATE terminal_events SET status=?,reason=?,record_id=?,reviewed_by=?,reviewed_at=? WHERE event_id=?',
            (decision,reason,record_id,user,time_sync.get_time_str(),identifier))
        planning.audit(db,target,timestamp[:10], 'REVISAR_EVENTO_TERMINAL',before,
            dict(event_id=identifier,decision=decision,motivo=reason,record_id=record_id,empleado_id=target,fecha_hora=timestamp,usuario=user),user)
        return record_id
