"""Reliable terminal v2 transport. Persist first; acknowledge exact event IDs only."""
import json
import hashlib
import math
import os
import re
import sqlite3
import threading
import time
from urllib.parse import quote
import numpy as np
import requests
import config
import outbox
from storage import (ARCHIVOS_LOCK,cargar_configuracion,get_server_url,normalizar_uid_nfc,invertir_bytes_uid,
    extraer_nfc_de_info,cargar_empleados_locales,guardar_empleados_locales,reconstruir_mapa_nfc_local,
    registrar_log_incidente)

SYNC_LOCK=threading.RLock()
_clock_lock=threading.Lock()
_clock_anchor=None


def _safe_json(response):
    try:
        result=response.json()
        return result if isinstance(result,dict) else {}
    except ValueError: return {}


def _headers():
    token=os.environ.get('ALICAPSA_TERMINAL_TOKEN') or cargar_configuracion().get('api_token','')
    return {'Authorization':'Bearer '+token,'Accept':'application/json'}


def _request(method,path,**kwargs):
    return requests.request(method,get_server_url().rstrip('/')+path,headers=_headers(),
        timeout=kwargs.pop('timeout',(3,8)),verify=True,**kwargs)


def _sync_clock():
    global _clock_anchor
    try:
        started=time.monotonic()
        response=_request('GET','/hora')
        result=_safe_json(response)
        epoch=result.get('epoch')
        if response.status_code==200 and isinstance(epoch,(float,int)) and math.isfinite(epoch):
            with _clock_lock: _clock_anchor=(epoch+(time.monotonic()-started)/2,time.monotonic())
            return True
    except requests.exceptions.RequestException: pass
    return False


def _timestamp():
    from datetime import datetime,timezone,timedelta
    with _clock_lock: anchor=_clock_anchor
    valid=bool(anchor and 0<=time.monotonic()-anchor[1]<=86400)
    epoch=anchor[0]+time.monotonic()-anchor[1] if valid else time.time()
    stamp=datetime.fromtimestamp(epoch,timezone(timedelta(hours=-5))).strftime('%Y-%m-%d %H:%M:%S')
    return stamp,valid


def servidor_disponible(timeout=3):
    try:
        response=_request('GET','/ping',timeout=(timeout,timeout))
        return response.status_code==200 and _safe_json(response).get('protocol_version')==2
    except requests.exceptions.RequestException: return False


def _send(event):
    identifier=event['event_id']
    endpoint='/marcaciones' if event['kind']=='mark' else '/empleados/enrolar'
    try:
        response=_request('POST',endpoint,json=event['payload'])
        result=_safe_json(response)
        acknowledged=(result.get('event_id')==identifier and result.get('persistido') is True)
        if acknowledged and response.status_code in (200,201,202) and result.get('status') in ('accepted','review','rejected'):
            state='DELIVERED' if result['status']=='accepted' else 'REVIEW'
            reason=('RECHAZADO: ' if result['status']=='rejected' else '')+str(result.get('motivo',''))
            outbox.update(identifier,state,result.get('record_id',''),reason)
            return True
        reason=result.get('mensaje') or result.get('error') or f'HTTP {response.status_code}; sin confirmación válida'
        # Conflicts and validation failures never count as success or disappear.
        state='REVIEW' if response.status_code in (400,403,404,409,413,422,426) else 'PENDING'
        outbox.update(identifier,state,error=reason)
        return False
    except requests.exceptions.RequestException as error:
        outbox.update(identifier,'PENDING',error=str(error))
        return False


def _flush(kind):
    with SYNC_LOCK:
        outbox.migrate_legacy()
        success=True
        for event in outbox.events(kind):
            if not _send(event): success=False
        return success


def sincronizar_enrolamientos_pendientes(): return _flush('enrol')
def sincronizar_marcaciones_pendientes(): return _flush('mark')


def _valid_catalog(result):
    if result.get('protocol_version')!=2 or result.get('complete') is not True or not isinstance(result.get('empleados'),dict) or not isinstance(result.get('bajas'),list):
        raise ValueError('Catálogo incompleto o incompatible; la caché anterior se conserva')
    employees={}
    for key,value in result['empleados'].items():
        identifier=str(key).strip().upper()
        if not re.fullmatch(r'[A-Z0-9_-]{1,64}',identifier) or not isinstance(value,dict):
            raise ValueError('Registro inválido en catálogo')
        vector=value.get('vector_facial',[])
        if not isinstance(vector,list) or (vector and (len(vector)!=128 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in vector))):
            raise ValueError('Vector inválido en catálogo; se requiere revisión del servidor')
        card=normalizar_uid_nfc(value.get('rfid',''))
        employees[identifier]=dict(value,nfc=card,rfid=card)
    cards=[e['rfid'] for e in employees.values() if e['rfid']]
    if len(cards)!=len(set(cards)): raise ValueError('El servidor tiene tarjetas duplicadas; no se activa un mapa ambiguo')
    return employees


def sincronizar_empleados_servidor():
    try:
        with SYNC_LOCK:
            response=_request('GET','/sync/catalogo')
            if response.status_code!=200: return False,f'Sincronización pendiente: HTTP {response.status_code}'
            employees=_valid_catalog(_safe_json(response))
            with ARCHIVOS_LOCK:
                # Authoritative replacement. Deleted staff and cleared cards/vectors do not survive.
                guardar_empleados_locales(employees)
                reconstruir_mapa_nfc_local(employees)
            _sync_clock()
            return True,f'✓ Sincronizados {len(employees)} colaboradores activos.'
    except (requests.exceptions.RequestException,ValueError,OSError,sqlite3.Error) as error:
        return False,f'Sincronización pendiente: {error}'


def _refresh_reviews():
    for event in outbox.events(state='REVIEW'):
        try:
            response=_request('GET','/eventos/'+quote(event['event_id'],safe=''))
            result=_safe_json(response)
            if response.status_code==200 and result.get('event_id')==event['event_id'] and result.get('persistido') is True and result.get('status')=='accepted':
                outbox.update(event['event_id'],'DELIVERED',result.get('record_id',''))
            elif response.status_code==200 and result.get('event_id')==event['event_id'] and result.get('persistido') is True and result.get('status')=='rejected':
                outbox.update(event['event_id'],'REVIEW',error='RECHAZADO: '+str(result.get('motivo','')))
        except requests.exceptions.RequestException: return


def sincronizar_todo(descargar_empleados=True):
    if not SYNC_LOCK.acquire(blocking=False): return False
    try:
        outbox.migrate_legacy()
        enrol_ok=sincronizar_enrolamientos_pendientes()
        marks_ok=sincronizar_marcaciones_pendientes()
        _refresh_reviews()
        if descargar_empleados:
            catalog_ok,_=sincronizar_empleados_servidor()
        else: catalog_ok=True
        _sync_clock()
        return enrol_ok and marks_ok and catalog_ok
    except (OSError,ValueError,sqlite3.Error) as error:
        registrar_log_incidente('SISTEMA','SINCRONIZACION','Persistencia pendiente',str(error))
        return False
    finally: SYNC_LOCK.release()


def _disparar_sync_async(descargar_empleados=False):
    threading.Thread(target=sincronizar_todo,kwargs=dict(descargar_empleados=descargar_empleados),daemon=True).start()


def obtener_vector_biometrico(identificador):
    raw=str(identificador).strip().upper()
    card=normalizar_uid_nfc(raw)
    candidates={card,invertir_bytes_uid(card)}-{''}
    for attempt in range(2):
        with ARCHIVOS_LOCK: employees=cargar_empleados_locales()
        owners={key for key,info in employees.items() if extraer_nfc_de_info(info) in candidates}
        if len(owners)>1: return False,raw,'',None,'Tarjeta ambigua: requiere revisión'
        employee_id=next(iter(owners),raw)
        employee=employees.get(employee_id)
        if employee:
            vector=employee.get('vector_facial',[])
            if isinstance(vector,list) and len(vector)==128 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in vector):
                return True,employee_id,employee.get('area',''),np.array(vector,dtype=np.float64),'✓ Identidad cargada desde catálogo activo'
            return False,employee_id,employee.get('area',''),None,'El colaborador no tiene biometría válida'
        if attempt==0: sincronizar_empleados_servidor()
    return False,raw,'',None,'Tarjeta o colaborador no activo en el catálogo'


def api_guardar_nuevo_empleado(emp_id,departamento,nfc_uid,vector_np):
    identifier=str(emp_id).strip().upper()
    card=normalizar_uid_nfc(nfc_uid)
    if not re.fullmatch(r'[A-Z0-9_-]{1,64}',identifier) or not card:
        return False,'ID o tarjeta inválidos'
    try: vector=np.asarray(vector_np,dtype=np.float64)
    except (ValueError,TypeError): return False,'Vector facial inválido'
    if vector.shape!=(128,) or not np.isfinite(vector).all(): return False,'Vector facial inválido'
    event_id=None
    try:
        with ARCHIVOS_LOCK:
            employees=cargar_empleados_locales()
            previous=employees.get(identifier,{})
            if any(key!=identifier and extraer_nfc_de_info(info)==card for key,info in employees.items()):
                return False,'La tarjeta pertenece a otro colaborador. No se reasigna automáticamente.'
        revision=hashlib.sha256(json.dumps([normalizar_uid_nfc(previous.get('rfid')),previous.get('vector_facial',[])],sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        event_id=outbox.enqueue('enrol',dict(empleado_id=identifier,area=departamento,rfid=card,nfc=card,vector_facial=vector.tolist(),revision_biometrica=revision))
        # Pending enrolment is journaled but never overwrites the authoritative identity cache.
        with SYNC_LOCK: _send(outbox.get(event_id))
        result=outbox.get(event_id)
        if result['state']=='DELIVERED':
            sincronizar_empleados_servidor()
            return True,'Colaborador actualizado en el servidor.'
        if result['state']=='REVIEW': return True,'Enrolamiento conservado para revisión; aún no está activo. '+result['last_error']
        return True,'Enrolamiento guardado en el equipo; pendiente de confirmación del servidor.'
    except (OSError,ValueError,sqlite3.Error) as error:
        if event_id: return True,f'Enrolamiento guardado localmente ({event_id}); PENDIENTE de conciliación: {error}'
        return False,f'NO GUARDADO: {error}. Solicite registro manual al coordinador.'


def api_registrar_marcacion(emp_id,tipo_marcacion,nota='',nfc_uid='',permiso_admin=False):
    identifier=None
    try:
        timestamp,clock_valid=_timestamp()
        card=normalizar_uid_nfc(nfc_uid)
        if not card and not permiso_admin:
            card=extraer_nfc_de_info(cargar_empleados_locales().get(str(emp_id).strip().upper(),{}))
        identifier=outbox.enqueue('mark',dict(empleado_id=str(emp_id).strip().upper(),tipo_marcacion=tipo_marcacion,
            fecha_hora=timestamp,nfc=card,rfid=card,permiso_admin=bool(permiso_admin),nota=nota,
            reloj_sincronizado=clock_valid,origen='servidor_estimado' if clock_valid else 'hora_local_sin_validar'))
        with SYNC_LOCK: _send(outbox.get(identifier))
        result=outbox.get(identifier)
        if result['state']=='DELIVERED': return True,f'Marcación confirmada por el servidor ({timestamp}).'
        if result['state']=='REVIEW': return True,f'Marcación conservada para REVISIÓN ({timestamp}). '+result['last_error']
        return True,f'Marcación guardada en el equipo ({timestamp}); PENDIENTE de envío. No cerrar la jornada sin sincronizar.'
    except (OSError,ValueError,sqlite3.Error) as error:
        if identifier: return True,f'Marcación guardada localmente ({identifier}); PENDIENTE de conciliación: {error}'
        return False,f'NO GUARDADA: {error}. Avise al coordinador para registrar la incidencia.'


def api_obtener_historial(emp_id):
    try:
        response=_request('GET','/historial/'+quote(str(emp_id),safe=''))
        if response.status_code==200: return _safe_json(response).get('historial',[])
    except requests.exceptions.RequestException: pass
    return []


def probar_conexion_servidor(base_url):
    try:
        base_url=base_url.rstrip('/')
        if not base_url.endswith('/api'): base_url+='/api'
        response=requests.get(base_url+'/ping',timeout=(3,5),verify=True)
        if response.status_code==200 and _safe_json(response).get('protocol_version')==2:
            return True,'Servidor v2 disponible. La sincronización también requiere el perfil autorizado.'
    except requests.exceptions.RequestException: pass
    return False,'No se confirmó un servidor compatible.'
