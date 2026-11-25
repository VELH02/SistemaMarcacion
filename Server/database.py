"""SQLite persistence, one-time legacy import and online backups (stdlib only)."""
import csv
import json
import os
import sqlite3
import sys
import tempfile
import uuid
from contextlib import contextmanager, closing
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from pathlib import Path

BASE_DIR = Path(os.environ.get('ALICAPSA_SERVER_HOME') or
    (Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent)).resolve()
DATABASE_SETTINGS_FILE = BASE_DIR / 'data' / 'database_location.json'


def saved_location():
    if not DATABASE_SETTINGS_FILE.exists(): return None
    data=json.loads(DATABASE_SETTINGS_FILE.read_text(encoding='utf-8-sig'))
    if not isinstance(data,dict) or not isinstance(data.get('database_path'),str) or not Path(data['database_path']).is_absolute():
        raise ValueError('El archivo de selección de base de datos no es válido')
    if getattr(sys,'frozen',False) and 'portable_relative_path' in data:
        relative=data['portable_relative_path']
        if not isinstance(relative,str) or not relative or Path(relative).is_absolute() or Path(relative).drive or '..' in Path(relative).parts:
            raise ValueError('La ruta portátil de la base de datos no es válida')
        candidate=(BASE_DIR/relative).resolve()
        if not candidate.is_relative_to(BASE_DIR): raise ValueError('La ruta portátil sale de la carpeta del servidor')
        data['database_path']=str(candidate)
    return data


_startup_selection=saved_location()
DATABASE_PATH = Path(_startup_selection['database_path'] if _startup_selection else
    os.environ.get('ALICAPSA_DB', str(BASE_DIR / 'data' / 'alicapsa.sqlite3')))
TABLES = {'empleados', 'usuarios', 'areas', 'turnos', 'aprobaciones', 'config'}
FIELDS = ('ID_Registro', 'ID_Personal', 'Nombre', 'Area', 'Tipo', 'Fecha_Hora', 'IP_Origen', 'Estado', 'Nota')
_active = ContextVar('database_connection', default=None)


def validate_location(value):
    """Inspect an existing ALICAPSA database without creating or modifying it."""
    try:
        candidate=Path(str(value).strip().strip('"')).expanduser()
        if not candidate.is_absolute(): raise ValueError('Indique la ruta absoluta del archivo en el servidor')
        if str(candidate).startswith(('\\\\','//')): raise ValueError('Utilice un disco local del servidor')
        if candidate.suffix.lower() not in ('.db','.sqlite','.sqlite3'): raise ValueError('Seleccione un archivo .db, .sqlite o .sqlite3')
        candidate=candidate.resolve(strict=True)
        if not candidate.is_file(): raise ValueError('La ruta debe corresponder a un archivo existente')
        if not os.access(candidate,os.R_OK | os.W_OK) or not os.access(candidate.parent,os.W_OK):
            raise ValueError('El servidor necesita lectura y escritura sobre el archivo y su carpeta')
        with closing(sqlite3.connect(candidate.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            db.execute('PRAGMA query_only=ON')
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('La base no supera la comprobación de integridad')
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (5,6): raise ValueError('La versión de la base no es compatible con este servidor')
            required={name:{'clave','datos'} for name in TABLES}
            required.update(metadata={'clave','valor'},marcaciones={'secuencia',*FIELDS},
                asignaciones={'empleado_id','fecha','turno_id','turno_json','usuario','actualizado'},
                decisiones={'empleado_id','fecha','datos','usuario','actualizado'},
                auditoria_planificacion={'id','empleado_id','fecha','accion','antes','despues','usuario','actualizado'},
                validaciones_bono={'empleado_id','mes','decision','motivo','huella','usuario','actualizado'},
                incidencias={'id','empleado_id','fecha','tipo','segundos_detectados','codigo','estado','motivo','usuario','actualizado','activa','fuente_json'},
                incidencia_conceptos={'id','incidencia_id','ordinal','codigo','horas','factor','tratamiento'})
            if version==6:
                required.update(terminal_events={'event_id','device_id','kind','fingerprint','payload','status','reason','employee_id','record_id','received','reviewed_by','reviewed_at'},
                    empleados_baja={'empleado_id','datos','fecha_baja','usuario'})
            for table,columns in required.items():
                found={row[1] for row in db.execute(f'PRAGMA table_info("{table}")')}
                if not columns.issubset(found): raise ValueError('El archivo no contiene una base ALICAPSA compatible')
            if not db.execute("SELECT 1 FROM metadata WHERE clave='legacy_import_v1'").fetchone():
                raise ValueError('El archivo no contiene una instalación ALICAPSA inicializada')
            if db.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('La base tiene referencias de auditoría inconsistentes')
            admins=[]
            for table in TABLES:
                for key,encoded in db.execute(f'SELECT clave,datos FROM {table}'):
                    data=json.loads(encoded)
                    if table not in ('areas','config') and not isinstance(data,dict): raise ValueError('Los catálogos de la base no son válidos')
                    if table=='usuarios':
                        role=data.get('rol','admin' if key=='admin' or data.get('area')=='TODAS' else 'coordinador')
                        if role=='admin' and isinstance(data.get('pass'),str) and data['pass']: admins.append(key)
            if not admins: raise ValueError('La base debe contener al menos un usuario administrador')
            marker=db.execute("SELECT valor FROM metadata WHERE clave='demostracion'").fetchone()
            if marker:
                demo=json.loads(marker[0])
                if not isinstance(demo,dict) or not all(key in demo for key in ('desde','hasta','evaluado_al')):
                    raise ValueError('Los datos de demostración de esta base no son válidos')
                datetime.fromisoformat(demo['evaluado_al'])
        return candidate
    except (OSError,sqlite3.Error) as error:
        raise ValueError('No se pudo abrir la base seleccionada: '+str(error)) from error


def save_location(path,user):
    """Atomic bootstrap setting; it never changes the live connection target."""
    candidate=validate_location(path)
    data=dict(database_path=str(candidate),previous_path=str(DATABASE_PATH.resolve()),
        selected_by=user,selected_at=datetime.now().isoformat())
    if getattr(sys,'frozen',False) and candidate.is_relative_to(BASE_DIR):
        data['portable_relative_path']=str(candidate.relative_to(BASE_DIR))
    DATABASE_SETTINGS_FILE.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temporary=tempfile.mkstemp(prefix='.database-',dir=DATABASE_SETTINGS_FILE.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            json.dump(data,stream,ensure_ascii=False,indent=2)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,DATABASE_SETTINGS_FILE)
    finally:
        if os.path.exists(temporary): os.remove(temporary)
    return data

def connect():
    if _startup_selection and DATABASE_PATH.resolve()==Path(_startup_selection['database_path']).resolve() and not DATABASE_PATH.is_file():
        raise ValueError('La base seleccionada ya no existe; no se creará una base vacía')
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
    if _startup_selection and DATABASE_PATH.resolve()==Path(_startup_selection['database_path']).resolve():
        validate_location(DATABASE_PATH)
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
    from terminal import initialize as initialize_terminal
    initialize_terminal(db)
    db.execute('PRAGMA user_version=6')

def insert_mark(row):
    with transaction() as db:
        # A late offline delivery must not inherit an approval for different data.
        # Compare only when a nearby decision exists; ordinary punches stay cheap.
        affected=[]
        previous={}
        try:
            day=datetime.strptime(row['Fecha_Hora'],'%Y-%m-%d %H:%M:%S').date()
            from datetime import timedelta
            first,last=(day-timedelta(days=2)).isoformat(),(day+timedelta(days=1)).isoformat()
            ready=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='decisiones'").fetchone()
            if ready:
                affected=db.execute('SELECT * FROM decisiones WHERE empleado_id=? AND fecha BETWEEN ? AND ?',
                    (row['ID_Personal'],first,last)).fetchall()
            if affected:
                import planning
                previous={r['fecha']:r for r in planning.report('TODAS',row['ID_Personal'],first,last)}
        except (ValueError,KeyError):
            affected=[]
        db.execute('INSERT INTO marcaciones (' + ','.join(FIELDS) + ') VALUES (' + ','.join('?' for _ in FIELDS) + ')',
                   [row.get(field, '') for field in FIELDS])
        if affected:
            current={r['fecha']:r for r in planning.report('TODAS',row['ID_Personal'],first,last)}
            for decision in affected:
                if previous.get(decision['fecha'])!=current.get(decision['fecha']):
                    db.execute('DELETE FROM decisiones WHERE empleado_id=? AND fecha=?',(row['ID_Personal'],decision['fecha']))
                    planning.audit(db,row['ID_Personal'],decision['fecha'],'REABRIR_VALIDACION_POR_MARCACION',
                        dict(decision),dict(marcacion=row['ID_Registro'],motivo='Nueva marcación; se requiere revisar los valores actualizados'),'Sistema')

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
