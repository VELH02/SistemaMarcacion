"""SQLite persistence, one-time legacy import and online backups (stdlib only)."""
import csv
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager, closing
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get('ALICAPSA_DB', str(BASE_DIR / 'data' / 'alicapsa.sqlite3')))
TABLES = {'empleados', 'usuarios', 'areas', 'turnos', 'aprobaciones', 'config'}
FIELDS = ('ID_Registro', 'ID_Personal', 'Nombre', 'Area', 'Tipo', 'Fecha_Hora', 'IP_Origen', 'Estado', 'Nota')
_active = ContextVar('database_connection', default=None)

def connect():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=30000')
    return db

@contextmanager
def reading():
    existing = _active.get()
    if existing is not None:
        yield existing
    else:
        with closing(connect()) as db:
            yield db

def consistent_read(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if _active.get() is not None:
            return function(*args, **kwargs)
        with closing(connect()) as db:
            db.execute('BEGIN')
            token = _active.set(db)
            try:
                return function(*args, **kwargs)
            finally:
                db.rollback()
                _active.reset(token)
    return wrapped

@contextmanager
def transaction():
    existing = _active.get()
    if existing is not None:
        name = 'sp_' + uuid.uuid4().hex
        existing.execute(f'SAVEPOINT {name}')
        try:
            yield existing
            existing.execute(f'RELEASE SAVEPOINT {name}')
        except BaseException:
            existing.execute(f'ROLLBACK TO SAVEPOINT {name}')
            existing.execute(f'RELEASE SAVEPOINT {name}')
            raise
        return
    db = connect()
    token = _active.set(db)
    try:
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        _active.reset(token)
        db.close()

def read_catalog(table):
    if table not in TABLES:
        raise ValueError('Catálogo desconocido')
    with reading() as db:
        rows = db.execute(f'SELECT clave, datos FROM {table} ORDER BY rowid').fetchall()
    if table == 'areas':
        return [row['clave'] for row in rows]
    if table == 'aprobaciones':
        result = {}
        for row in rows:
            employee, date = json.loads(row['clave'])
            result.setdefault(employee, {})[date] = json.loads(row['datos'])
        return result
    return {row['clave']: json.loads(row['datos']) for row in rows}

def write_catalog(table, data):
    if table not in TABLES:
        raise ValueError('Catálogo desconocido')
    if table == 'areas':
        entries = [(name, None) for name in data]
    elif table == 'aprobaciones':
        entries = [(json.dumps([emp, date]), value) for emp, days in data.items() for date, value in days.items()]
    else:
        entries = list(data.items())
    with transaction() as db:
        db.execute(f'DELETE FROM {table}')
        db.executemany(f'INSERT INTO {table}(clave, datos) VALUES (?, ?)',
                       [(key, json.dumps(value, ensure_ascii=False)) for key, value in entries])

def find_employee(identifier):
    """Fetch only the matching employee, without loading every facial vector."""
    with reading() as db:
        row = db.execute('SELECT clave, datos FROM empleados WHERE clave=?', (identifier,)).fetchone()
        if row is None:
            row = db.execute("SELECT clave, datos FROM empleados WHERE upper(trim(json_extract(datos, '$.rfid')))=? ORDER BY rowid LIMIT 1",
                             (identifier,)).fetchone()
    return (row['clave'], json.loads(row['datos'])) if row else (None, None)

def initialize(defaults):
    """Import all sources atomically; invalid files abort instead of losing data."""
    with transaction() as db:
        db.execute('CREATE TABLE IF NOT EXISTS metadata (clave TEXT PRIMARY KEY, valor TEXT NOT NULL)')
        for table in TABLES:
            db.execute(f'CREATE TABLE IF NOT EXISTS {table} (clave TEXT PRIMARY KEY, datos TEXT NOT NULL)')
        db.execute("CREATE INDEX IF NOT EXISTS idx_empleados_rfid ON empleados(upper(trim(json_extract(datos, '$.rfid'))))")
        db.execute('CREATE TABLE IF NOT EXISTS marcaciones (secuencia INTEGER PRIMARY KEY, ' +
                   ', '.join(f'"{field}" TEXT NOT NULL' for field in FIELDS) + ')')
        db.execute('CREATE INDEX IF NOT EXISTS idx_marcaciones_empleado_fecha ON marcaciones(ID_Personal, Fecha_Hora)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_marcaciones_area_fecha ON marcaciones(Area, Fecha_Hora)')
        if db.execute("SELECT 1 FROM metadata WHERE clave='legacy_import_v1'").fetchone():
            initialize_planning(db)
            return
        for table, default in defaults.items():
            path = BASE_DIR / f'{table}.json'
            data = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() and path.stat().st_size else default
            if table == 'empleados':
                for emp, info in data.items():
                    info.setdefault('rfid', '')
                    vector = BASE_DIR / 'biometria' / f'{emp}.npy'
                    if not info.get('vector_facial') and vector.exists():
                        import numpy as np
                        info['vector_facial'] = np.load(vector, allow_pickle=False).tolist()
            write_catalog(table, data)
        source = BASE_DIR / 'marcaciones.csv'
        if source.exists() and source.stat().st_size:
            with source.open(newline='', encoding='utf-8-sig') as stream:
                reader = csv.DictReader(stream)
                if not set(FIELDS).issubset(reader.fieldnames or []):
                    raise ValueError('Columnas inválidas en marcaciones.csv; importación cancelada')
                for row in reader:
                    if None in row or any(row[field] is None for field in FIELDS):
                        raise ValueError(f'Fila CSV inválida: {reader.line_num}')
                    insert_mark(row)
        db.execute("INSERT INTO metadata VALUES ('legacy_import_v1', ?)", (datetime.now().isoformat(),))
        db.execute('PRAGMA user_version=1')
        initialize_planning(db)

def initialize_incidents(db):
    parent_sql='''CREATE TABLE IF NOT EXISTS incidencias (
        id INTEGER PRIMARY KEY, empleado_id TEXT NOT NULL, fecha TEXT NOT NULL,
        tipo TEXT NOT NULL CHECK(tipo IN ('HE','TARDANZA','FALTANTE','DOMINGO')),
        segundos_detectados INTEGER NOT NULL, codigo TEXT NOT NULL, estado TEXT NOT NULL,
        motivo TEXT NOT NULL, usuario TEXT NOT NULL, actualizado TEXT NOT NULL,
        activa INTEGER NOT NULL DEFAULT 1, fuente_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(empleado_id,fecha,tipo))'''
    child_sql='''CREATE TABLE IF NOT EXISTS incidencia_conceptos (
        id INTEGER PRIMARY KEY, incidencia_id INTEGER NOT NULL REFERENCES incidencias(id),
        ordinal INTEGER NOT NULL, codigo TEXT NOT NULL, horas REAL NOT NULL,
        factor REAL NOT NULL, tratamiento TEXT NOT NULL, UNIQUE(incidencia_id,ordinal))'''
    existing=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='incidencias'").fetchone()
    if existing and "'DOMINGO'" not in existing[0]:
        # Preserve stable identifiers and FK relationships while extending the type check.
        db.execute('ALTER TABLE incidencias RENAME TO incidencias_v4')
        db.execute('ALTER TABLE incidencia_conceptos RENAME TO incidencia_conceptos_v4')
        db.execute(parent_sql)
        db.execute(child_sql)
        columns='id,empleado_id,fecha,tipo,segundos_detectados,codigo,estado,motivo,usuario,actualizado,activa'
        db.execute(f'INSERT INTO incidencias({columns}) SELECT {columns} FROM incidencias_v4')
        db.execute('INSERT INTO incidencia_conceptos SELECT * FROM incidencia_conceptos_v4')
        db.execute('DROP TABLE incidencia_conceptos_v4')
        db.execute('DROP TABLE incidencias_v4')
    else:
        db.execute(parent_sql)
        db.execute(child_sql)
    if 'fuente_json' not in {r['name'] for r in db.execute('PRAGMA table_info(incidencias)')}:
        db.execute("ALTER TABLE incidencias ADD COLUMN fuente_json TEXT NOT NULL DEFAULT '{}'")


def initialize_planning(db):
    initialize_incidents(db)
    db.execute('''CREATE TABLE IF NOT EXISTS validaciones_bono (
        empleado_id TEXT NOT NULL, mes TEXT NOT NULL, decision TEXT NOT NULL,
        motivo TEXT NOT NULL, huella TEXT NOT NULL, usuario TEXT NOT NULL,
        actualizado TEXT NOT NULL, PRIMARY KEY(empleado_id,mes))''')
    db.execute('''CREATE TABLE IF NOT EXISTS asignaciones (
        empleado_id TEXT NOT NULL, fecha TEXT NOT NULL, turno_id TEXT NOT NULL,
        turno_json TEXT NOT NULL, usuario TEXT NOT NULL, actualizado TEXT NOT NULL,
        PRIMARY KEY (empleado_id, fecha))''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_asignaciones_fecha ON asignaciones(fecha, empleado_id)')
    db.execute('''CREATE TABLE IF NOT EXISTS decisiones (
        empleado_id TEXT NOT NULL, fecha TEXT NOT NULL, datos TEXT NOT NULL,
        usuario TEXT NOT NULL, actualizado TEXT NOT NULL, PRIMARY KEY(empleado_id, fecha))''')
    db.execute('''CREATE TABLE IF NOT EXISTS auditoria_planificacion (
        id INTEGER PRIMARY KEY, empleado_id TEXT NOT NULL, fecha TEXT NOT NULL,
        accion TEXT NOT NULL, antes TEXT NOT NULL, despues TEXT NOT NULL,
        usuario TEXT NOT NULL, actualizado TEXT NOT NULL)''')
    if not db.execute("SELECT 1 FROM metadata WHERE clave='planning_v2'").fetchone():
        shifts = read_catalog('turnos')
        for employee, days in read_catalog('aprobaciones').items():
            for date, approval in days.items():
                shift_id = approval.get('turno_id', '')
                if shift_id in shifts:
                    db.execute('INSERT OR IGNORE INTO asignaciones VALUES (?,?,?,?,?,?)',
                               (employee, date, shift_id, json.dumps(shifts[shift_id], ensure_ascii=False), 'Migración', datetime.now().isoformat()))
                db.execute('INSERT OR IGNORE INTO decisiones VALUES (?,?,?,?,?)',
                           (employee, date, json.dumps(approval), 'Migración', datetime.now().isoformat()))
        db.execute("INSERT INTO metadata VALUES ('planning_v2', ?)", (datetime.now().isoformat(),))
    db.execute('PRAGMA user_version=5')

def insert_mark(row):
    with transaction() as db:
        db.execute('INSERT INTO marcaciones (' + ','.join(FIELDS) + ') VALUES (' + ','.join('?' for _ in FIELDS) + ')',
                   [row.get(field, '') for field in FIELDS])

def marks(area='TODAS', employee='', start='', end=''):
    clauses, values = [], []
    for column, op, value in [('Area', '=', area if area != 'TODAS' else ''),
                              ('ID_Personal', '=', employee), ('Fecha_Hora', '>=', start),
                              ('Fecha_Hora', '<', end + ' 24:00:00' if end else '')]:
        if value:
            clauses.append(f'{column} {op} ?')
            values.append(value)
    with reading() as db:
        return [dict(row) for row in db.execute('SELECT * FROM marcaciones' +
                (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY Fecha_Hora, secuencia', values)]

def backup(destination=None):
    target = Path(destination) if destination else BASE_DIR / 'backups' / datetime.now().strftime('alicapsa_%Y%m%d_%H%M%S_%f.sqlite3')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects existing backups and the live database.
    with target.open('xb'):
        pass
    try:
        with closing(connect()) as source, closing(sqlite3.connect(target)) as copy:
            source.backup(copy)
            if copy.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Respaldo inválido')
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target.resolve()
