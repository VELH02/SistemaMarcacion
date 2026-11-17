import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

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
SECRET_KEY = 'super_secreto_alicapsa_cambiar_en_produccion'