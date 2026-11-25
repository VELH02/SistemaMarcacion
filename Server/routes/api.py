"""Terminal API v2: authenticated receipt and full authoritative catalog."""
import hashlib
import json
import time
from datetime import timedelta
from flask import Blueprint,request,jsonify,session
import database
import terminal
import time_sync
from logger import console_logs

api_bp=Blueprint('api',__name__,url_prefix='/api')

@api_bp.before_request
def authenticate_terminal():
    if request.endpoint in ('api.api_ping','api.api_hora','api.get_logs'): return
    if not terminal.authorized(request.headers.get('Authorization','')):
        return jsonify(error='TERMINAL_NO_AUTORIZADO',mensaje='Configure el perfil del terminal'),401
    if request.method=='POST':
        from demo_data import status
        if status():
            return jsonify(error='MODO_DEMOSTRACION',persistido=False,
                mensaje='Servidor en demostración web; conserve el evento pendiente hasta volver a la base original'),503

@api_bp.route('/ping')
@api_bp.route('')
def api_ping():
    return jsonify(status='ok',protocol_version=2)

@api_bp.route('/hora')
def api_hora():
    now=time_sync.get_current_time()
    return jsonify(fecha=now.strftime('%d/%m/%Y'),hora=now.strftime('%H:%M:%S'),
        epoch=time.time()+time_sync.ntp_offset,zona='America/Panama',estado_sync=time_sync.estado_sync)

@api_bp.route('/sync/catalogo')
def catalog():
    employees=database.read_catalog('empleados')
    employees={key:dict(info,revision_biometrica=terminal.identity_revision(info)) for key,info in employees.items()}
    with database.reading() as db:
        retired=[r[0] for r in db.execute('SELECT empleado_id FROM empleados_baja') if r[0] not in employees]
    digest=hashlib.sha256(json.dumps([employees,sorted(retired)],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return jsonify(protocol_version=2,complete=True,empleados=employees,bajas=retired,revision=digest)

@api_bp.route('/empleados')
@api_bp.route('/sync/empleados.json')
@api_bp.route('/empleados/json')
def api_obtener_todos_empleados():
    return jsonify(database.read_catalog('empleados'))

@api_bp.route('/empleados/<emp_id>')
def api_obtener_empleado(emp_id):
    employees=database.read_catalog('empleados')
    key=emp_id.strip().upper()
    if key not in employees:
        candidates=[k for k,v in employees.items() if terminal.uid(v.get('rfid'))==terminal.uid(emp_id)]
        if len(candidates)!=1: return jsonify(error='NO_REGISTRADO_O_TARJETA_AMBIGUA'),404
        key=candidates[0]
    info=employees[key]
    return jsonify(dict(info,empleado_id=key,nfc=terminal.uid(info.get('rfid'))))

@api_bp.route('/empleados/enrolar',methods=['POST'])
def api_enrolar_empleado():
    return receive('enrol')

@api_bp.route('/marcaciones',methods=['POST'])
def api_registrar_marcacion_json():
    return receive('mark')

def receive(kind):
    try:
        result,status=terminal.ingest(kind,request.get_json(silent=True),request.remote_addr)
        return jsonify(result),status
    except (ValueError,TypeError) as error:
        return jsonify(error='SOLICITUD_INVALIDA',mensaje=str(error),persistido=False),400

@api_bp.route('/eventos/<identifier>')
def receipt_status(identifier):
    with database.reading() as db:
        row=db.execute('SELECT * FROM terminal_events WHERE event_id=?',(identifier,)).fetchone()
    if not row: return jsonify(error='NO_RECIBIDO'),404
    return jsonify(terminal.receipt(row))

@api_bp.route('/historial/<emp_id>')
def api_historial_empleado(emp_id):
    import planning
    now=planning.today().date()
    first=request.args.get('fecha_inicio') or (now-timedelta(days=89)).isoformat()
    last=request.args.get('fecha_fin') or now.isoformat()
    try: rows=planning.report('TODAS',emp_id.strip().upper(),first,last)
    except ValueError as error: return jsonify(error=str(error)),400
    result=[]
    for row in rows:
        if row['estado'] in ('SIN_PLAN','PROGRAMADO','DESCANSO'): continue
        hours=row['horas_totales']
        result.append(dict(fecha=row['fecha'],entrada=row['entrada'] or '--:--:--',salida=row['salida'] or '--:--:--',
            horas=f'{hours:.2f} hrs' if isinstance(hours,(int,float)) else str(hours),
            tarde=str(round(row.get('tardanza_computable_min',row['tardanza_min']),2)),estado=row['estado']))
    return jsonify(historial=result)

@api_bp.route('/logs')
def get_logs():
    from .planning import role
    if not session.get('usuario') or role()!='admin': return jsonify([])
    return jsonify(list(console_logs))

@api_bp.route('/marcar',methods=['POST'])
def legacy_mark():
    return jsonify(error='ACTUALIZAR_TERMINAL',mensaje='Utilice /api/marcaciones con protocolo v2 e identificador de evento'),426
