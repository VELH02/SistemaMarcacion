import os
import sys

RESOURCE_DIR = os.path.abspath(os.path.dirname(__file__))
# Bundled resources are read-only; databases, logs and backups travel beside EXE.
BASE_DIR = os.path.abspath(os.environ.get('ALICAPSA_SERVER_HOME') or
    (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else RESOURCE_DIR))

# Archivos de datos y almacenamiento
DATA_FILE = os.path.join(BASE_DIR, 'marcaciones.csv')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
EMPLEADOS_FILE = os.path.join(BASE_DIR, 'empleados.json')
AREAS_FILE = os.path.join(BASE_DIR, 'areas.json')
USUARIOS_FILE = os.path.join(BASE_DIR, 'usuarios.json')
TURNOS_FILE = os.path.join(BASE_DIR, 'turnos.json')
APROBACIONES_FILE = os.path.join(BASE_DIR, 'aprobaciones.json')
BIOMETRIA_FOLDER = os.path.join(BASE_DIR, 'biometria')
LOGS_FOLDER = os.path.join(BASE_DIR, 'logs')

# Clave secreta para cookies de sesión
SECRET_KEY = os.environ.get('ALICAPSA_SECRET_KEY')
