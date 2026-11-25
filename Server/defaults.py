DEFAULT_CONFIG = {
    "puerto_escucha": 5000,
    "ips_permitidas": [],
    "servidor_ntp": "pool.ntp.org"
}

DEFAULT_EMPLEADOS = {}

DEFAULT_AREAS = [
    "PRODUCCION",
    "MANTENIMIENTO",
    "SANEAMIENTO",
    "OPERACIONES",
    "LOGISTICA"
]

DEFAULT_USUARIOS = {
    "admin": {"pass": "admin", "area": "TODAS", "nombre": "Administrador General"},
    "produccion": {"pass": "1234", "area": "PRODUCCION", "nombre": "Jefe de Producción"},
    "mantenimiento": {"pass": "1234", "area": "MANTENIMIENTO", "nombre": "Jefe de Mantenimiento"},
    "saneamiento": {"pass": "1234", "area": "SANEAMIENTO", "nombre": "Jefe de Saneamiento"},
    "operaciones": {"pass": "1234", "area": "OPERACIONES", "nombre": "Jefe de Operaciones"},
    "logistica": {"pass": "1234", "area": "LOGISTICA", "nombre": "Jefe de Logística"}
}

DEFAULT_TURNOS = {
    "T1": {"nombre": "Turno Mañana", "entrada": "06:00:00", "salida": "14:30:00"},
    "T2": {"nombre": "Turno Tarde", "entrada": "14:00:00", "salida": "22:30:00"},
    "T3": {"nombre": "Turno Noche", "entrada": "22:00:00", "salida": "06:30:00"}
}

DEFAULT_APROBACIONES = {}

