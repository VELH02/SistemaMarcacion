import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Archivos de datos y almacenamiento
DATA_FILE = os.path.join(BASE_DIR, 'marcaciones.csv')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
EMPLEADOS_FILE = os.path.join(BASE_DIR, 'empleados.json')
AREAS_FILE = os.path.join(BASE_DIR, 'areas.json')
USUARIOS_FILE = os.path.join(BASE_DIR, 'usuarios.json')
BIOMETRIA_FOLDER = os.path.join(BASE_DIR, 'biometria')

# Clave secreta para cookies de sesión
SECRET_KEY = 'super_secreto_alicapsa_cambiar_en_produccion'