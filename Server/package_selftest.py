"""Exercise the bundled application over HTTP against a disposable database copy."""
import hashlib
import io
import json
import logging
import os
import secrets
import sqlite3
import struct
import sys
import tempfile
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor, ProxyHandler
from unittest.mock import patch


def run(output):
    report={'ok':False,'bits':struct.calcsize('P')*8,'python':sys.version,'pruebas':[]}
    home=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    original=home/'data'/'alicapsa.sqlite3'
    original_hash=hashlib.sha256(original.read_bytes()).hexdigest()
    server=None
    server_scope=None
    thread=None
    folder=tempfile.TemporaryDirectory(prefix='ALICAPSA servidor prueba ')
    try:
        isolated=Path(folder.name)
        (isolated/'data').mkdir()
        target=isolated/'data'/'alicapsa.sqlite3'
        with closing(sqlite3.connect(original.as_uri()+'?mode=ro',uri=True)) as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
        # Set paths before importing any module that can write data or logs.
        os.environ['ALICAPSA_SERVER_HOME']=str(isolated)
        os.environ['ALICAPSA_DB']=str(target)
        os.environ.pop('ALICAPSA_TERMINAL_TOKEN',None)
        import database
        database.validate_location(target)
        with database.transaction() as db:
            db.execute("DELETE FROM metadata WHERE clave='demostracion'")
        from run import create_app
        import time_sync
        import planning
        import terminal
        with patch.object(time_sync,'sincronizar_ntp'):
            app=create_app()
        user='prueba_'+uuid.uuid4().hex[:12]
        password=secrets.token_urlsafe(24)
        prefix='TEST-'+uuid.uuid4().hex[:8].upper()
        employees={prefix+str(i):dict(nombre='Prueba',apellido=str(i),area='AUTOPRUEBA',
            rfid='C0FFEE'+str(i)+'0',vector_facial=[],fecha_ingreso='2020-01-01') for i in range(4)}
        users=database.read_catalog('usuarios')
        users[user]=dict(area='TODAS',rol='admin',**{'pass':password})
        database.write_catalog('usuarios',users)
        database.write_catalog('empleados',employees)
        database.write_catalog('areas',['AUTOPRUEBA'])
        shift=planning.validate_shift(dict(nombre='Autoprueba',entrada='06:00',salida='14:30',
            descansos=[['12:00','12:30']],descanso_remunerado=False))
        shifts=database.read_catalog('turnos');shifts['TEST']=shift
        database.write_catalog('turnos',shifts)
        now=planning.today().date()
        monday=(now-timedelta(days=now.weekday()+7)).isoformat()
        for employee in employees:
            planning.assign_week(employee,monday,['TEST']*6+['DESCANSO'],user)
        from production_server import serving,single_instance
        if os.name=='nt':
            name='Global\\ALICAPSA.Autoprueba.'+uuid.uuid4().hex
            with single_instance(name):
                try:
                    with single_instance(name):
                        raise AssertionError('Se admitieron dos instancias')
                except RuntimeError as error:
                    assert 'ya está abierto' in str(error)
            with single_instance(name): pass
            report['pruebas'].append('Instancia única de Windows y liberación automática al cerrar')
        from waitress import wasyncore
        server_scope=serving(app,host='127.0.0.1',port=0,threads=4)
        server,socket_map=server_scope.__enter__()
        try:
            with serving(app,host='127.0.0.1',port=int(server.effective_port)):
                raise AssertionError('Dos servidores pudieron abrir el mismo puerto')
        except OSError:
            pass
        report['pruebas'].append('Puerto exclusivo: segunda instancia rechazada')
        # Own the loop so shutdown does not depend on the production Ctrl+C path.
        stopping=threading.Event()
        def loop():
            while not stopping.is_set():
                wasyncore.loop(timeout=.05,count=1,map=socket_map)
        thread=threading.Thread(target=loop,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.effective_port)
        anonymous=build_opener(ProxyHandler({}))
        browser=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
        def request(path,payload=None,opener=None,auth=False,form=False):
            headers={}
            if auth: headers['Authorization']='Bearer '+terminal.secret('terminal')
            data=None
            if payload is not None:
                data=(urlencode(payload).encode() if form else json.dumps(payload).encode())
                headers['Content-Type']='application/x-www-form-urlencoded' if form else 'application/json'
            try:
                with (opener or anonymous).open(Request(base+path,data=data,headers=headers),timeout=30) as response:
                    return response.status,response.read()
            except HTTPError as error:
                return error.code,error.read()
        assert request('/login')[0]==200
        status,body=request('/api/ping');assert status==200 and json.loads(body)['protocol_version']==2
        assert request('/api/sync/catalogo')[0]==401
        assert request('/api/sync/catalogo',auth=True)[0]==200
        assert request('/login',dict(usuario=user,password=password),browser,form=True)[0]==200
        params=urlencode(dict(fecha_inicio=monday,fecha_fin=monday,emp_id=next(iter(employees))))
        for page in ('/','/colaboradores','/turnos','/planificacion','/aprobaciones','/bono',
                     '/admin/usuarios','/admin/areas','/config','/rrhh/calendario','/admin/conceptos','/consola'):
            status,body=request(page+'?'+params,opener=browser)
            assert status==200,(page,status,body[:160])
            if page=='/config': assert b'ruta_db' in body
        with app.test_request_context():
            from flask import url_for
            for resource in ('logo.png','save-all.js'):
                status,body=request(url_for('static',filename=resource));assert status==200 and body
        report['pruebas'].append('Login, 12 páginas y recursos web incluidos')
        def send(index,employee):
            for kind,clock in (('ENTRADA','06:00:00'),('SALIDA','14:30:00')):
                event=dict(event_id=uuid.uuid4().hex,device_id='autoprueba-device-'+str(index),empleado_id=employee,
                    fecha_hora=monday+' '+clock,tipo_marcacion=kind,nfc=employees[employee]['rfid'],reloj_sincronizado=True)
                status,body=request('/api/marcaciones',event,auth=True)
                receipt=json.loads(body)
                assert status==200 and receipt['status']=='accepted',(status,receipt)
                status,repeated=request('/api/marcaciones',event,auth=True)
                retry=json.loads(repeated)
                assert status==200 and retry['duplicado'] and retry['record_id']==receipt['record_id']
                assert request('/api/eventos/'+event['event_id'],auth=True)[0]==200
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures=[executor.submit(send,i,employee) for i,employee in enumerate(employees)]
            for future in futures: future.result()
        with database.reading() as db:
            assert db.execute('SELECT COUNT(*) FROM marcaciones WHERE ID_Personal LIKE ?',(prefix+'%',)).fetchone()[0]==8
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        report['pruebas'].append('4 terminales simultáneos: 8 marcaciones, reintentos sin duplicados e integridad SQLite')
        employee=next(iter(employees))
        status,body=request('/api/historial/'+employee+'?'+params,auth=True)
        history=json.loads(body)['historial']
        assert status==200 and history and history[0]['horas']=='8.00 hrs',history
        status,body=request('/exportar?'+params,opener=browser)
        assert status==200 and body[:2]==b'PK'
        from openpyxl import load_workbook
        book=load_workbook(io.BytesIO(body),read_only=True)
        assert book.active.max_row>1
        book.close()
        report['pruebas'].append('Historial de 8 horas efectivas y exportación XLSX legible')
        backup=database.backup(isolated/'respaldo.db')
        database.validate_location(backup)
        database.save_location(backup,user)
        assert database.DATABASE_PATH==target
        assert database.saved_location()['database_path']==str(backup)
        if getattr(sys,'frozen',False):
            assert database.saved_location()['portable_relative_path']=='respaldo.db'
        report['pruebas'].append('Respaldo consistente y selección de DB para el próximo reinicio')
        assert hashlib.sha256(original.read_bytes()).hexdigest()==original_hash
        report['pruebas'].append('Base de distribución intacta; prueba ejecutada en copia temporal')
        report['ok']=True
    except Exception:
        report['error']=traceback.format_exc()
    finally:
        if thread:
            stopping.set();thread.join(timeout=5)
        if server_scope and server:
            server_scope.__exit__(None,None,None)
        logging.shutdown()
        folder.cleanup()
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return 0 if report['ok'] else 1
