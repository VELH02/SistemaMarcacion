"""Durable terminal journal. Acknowledged events are retained, never deleted."""
import csv
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
import config


def path():
    return Path(config.CLIENT_DB)


@contextmanager
def connection():
    path().parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path(),timeout=30)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        db.execute('''CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'PENDING', server_id TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, updated TEXT NOT NULL)''')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally: db.close()


def now():
    return datetime.now(timezone(timedelta(hours=-5))).strftime('%Y-%m-%d %H:%M:%S')


def device_id():
    with connection() as db:
        row=db.execute("SELECT value FROM metadata WHERE key='device_id'").fetchone()
        if row: return row[0]
        value=uuid.uuid4().hex
        db.execute("INSERT INTO metadata VALUES ('device_id',?)",(value,))
        return value


def enqueue(kind,payload,event_id=None):
    payload=dict(payload)
    identifier=event_id or uuid.uuid4().hex
    payload.update(event_id=identifier,device_id=device_id())
    encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,allow_nan=False)
    with connection() as db:
        existing=db.execute('SELECT payload,kind FROM events WHERE event_id=?',(identifier,)).fetchone()
        if existing and (existing[0]!=encoded or existing[1]!=kind): raise ValueError('El identificador del evento ya tiene otros datos o tipo')
        db.execute('INSERT OR IGNORE INTO events(event_id,kind,payload,created,updated) VALUES (?,?,?,?,?)',
                   (identifier,kind,encoded,now(),now()))
    return identifier


def events(kind=None,state='PENDING'):
    with connection() as db:
        where,params=['state=?'],[state]
        if kind: where.append('kind=?');params.append(kind)
        return [dict(row,payload=json.loads(row['payload'])) for row in db.execute(
            'SELECT * FROM events WHERE '+' AND '.join(where)+' ORDER BY created,rowid',params)]


def update(identifier,state,server_id='',error=''):
    if state not in ('PENDING','DELIVERED','REVIEW'): raise ValueError('Estado inválido')
    with connection() as db:
        db.execute('UPDATE events SET state=?,server_id=?,last_error=?,updated=? WHERE event_id=?',
                   (state,str(server_id),str(error)[:2000],now(),identifier))


def get(identifier):
    with connection() as db:
        row=db.execute('SELECT * FROM events WHERE event_id=?',(identifier,)).fetchone()
        return dict(row,payload=json.loads(row['payload'])) if row else None


def migrate_legacy():
    """All-or-nothing import, retaining original CSV/JSON for recovery."""
    with connection() as db:
        if db.execute("SELECT 1 FROM metadata WHERE key='legacy_v1'").fetchone(): return
        pending=[]
        source=Path(config.MARCACIONES_PENDIENTES_FILE)
        if source.exists() and source.stat().st_size:
            with source.open(encoding='utf-8-sig',newline='') as stream:
                reader=csv.DictReader(stream)
                if not {'Empleado_ID','Fecha_Hora','Tipo_Marcacion'}.issubset(reader.fieldnames or []):
                    raise ValueError('La cola CSV tiene un formato inválido; no se importó ni sobrescribió')
                for row in reader:
                    if None in row or not row.get('Empleado_ID'): raise ValueError('Fila inválida en la cola CSV')
                    pending.append(('mark',dict(empleado_id=row['Empleado_ID'],tipo_marcacion=row['Tipo_Marcacion'],
                        fecha_hora=row['Fecha_Hora'],nfc=row.get('NFC_UID',''),nota=row.get('Nota',''),origen='legacy_offline')))
        source=Path(config.ENROLAMIENTOS_PENDIENTES_FILE)
        if source.exists() and source.stat().st_size:
            data=json.loads(source.read_text(encoding='utf-8-sig'))
            if not isinstance(data,dict): raise ValueError('Cola de enrolamientos inválida')
            pending.extend(('enrol',dict(value,empleado_id=key)) for key,value in data.items())
        row=db.execute("SELECT value FROM metadata WHERE key='device_id'").fetchone()
        device=row[0] if row else uuid.uuid4().hex
        db.execute("INSERT OR IGNORE INTO metadata VALUES ('device_id',?)",(device,))
        for kind,payload in pending:
            identifier=uuid.uuid4().hex
            payload.update(event_id=identifier,device_id=device)
            db.execute('INSERT INTO events(event_id,kind,payload,created,updated) VALUES (?,?,?,?,?)',
                (identifier,kind,json.dumps(payload,ensure_ascii=False,allow_nan=False),now(),now()))
        db.execute("INSERT INTO metadata VALUES ('legacy_v1',?)",(now(),))
