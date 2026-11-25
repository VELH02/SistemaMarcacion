# ======================================================================
# CONFIGURACIÓN GLOBAL, RUTAS Y PALETA DE COLORES (ALICAPSA)
# ======================================================================
import os
import sys

# Directorio base anclado a la ubicación real del proyecto
RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else RESOURCE_DIR
DATA_DIR = os.environ.get("ALICAPSA_CLIENT_DATA", os.path.join(BASE_DIR,'datos') if getattr(sys,'frozen',False) else BASE_DIR)
CLIENT_DB = os.path.join(DATA_DIR, "terminal.sqlite3")

# Archivos locales y directorios
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
EMPLEADOS_FILE_LOCAL = os.path.join(DATA_DIR, "empleados.json")
ENROLAMIENTOS_PENDIENTES_FILE = os.path.join(DATA_DIR, "enrolamientos_pendientes.json")
MARCACIONES_PENDIENTES_FILE = os.path.join(DATA_DIR, "marcaciones_pendientes.csv")
LOG_FILE = os.path.join(DATA_DIR, "log_incidentes.csv")
DIR_ROSTROS = os.path.join(DATA_DIR, "base_rostros")

# Parámetros de red, seguridad y biometría
DEFAULT_SERVER_URL = "http://127.0.0.1:5000/api"
ADMIN_PIN = os.environ.get("ALICAPSA_ADMIN_PIN", "")
if ADMIN_PIN and (not ADMIN_PIN.isascii() or not ADMIN_PIN.isdigit() or not 6 <= len(ADMIN_PIN) <= 8):
    raise ValueError("ALICAPSA_ADMIN_PIN debe contener de 6 a 8 dígitos")
INTERVALO_SYNC_SEGUNDOS = 15 * 60     # Actualiza colaboradores, tarjetas y biometría cada 15 minutos
UMBRAL_DISTANCIA_ESTRICTO = 0.48      # Umbral de comparación facial
TIMEOUT_INACTIVIDAD_SEGUNDOS = 30

DEPTOS_DISPONIBLES = [
    "OPERACIONES",
    "LOGÍSTICA",
    "DHO",
    "VENTAS",
    "MANTENIMIENTO",
    "PRODUCCION",
    "SANEAMIENTO",
    "IP",
    "SIG",
    "PLANEACION",
    "LABORATORIO",

]

# Tipografía principal según sistema operativo
FONT_PRIMARY = "Segoe UI" if sys.platform.startswith("win") else "Helvetica"

# Paleta de colores corporativa Alicapsa
COLOR_PRIMARY = "#184828"             # Verde Bosque Oscuro
COLOR_PRIMARY_HOVER = "#10331C"       # Verde Bosque Profundo (Hover)
COLOR_ACCENT = "#48A731"              # Verde Hoja Fresco
COLOR_ACCENT_HOVER = "#398A26"        # Verde Hoja Intenso (Hover)
COLOR_BG = "#F3F6F4"                  # Fondo General Claro
COLOR_CARD = "#FFFFFF"                # Tarjetas / Contenedores Blancos
COLOR_CARD_BORDER = "#D3DFD6"         # Bordes Sutiles Verdosos
COLOR_TEXT_DARK = "#122016"           # Texto Oscuro
COLOR_MUTED = "#586C5E"               # Texto Secundario
COLOR_SECONDARY = "#E6ECE8"           # Botones / Superficies Secundarias
COLOR_SECONDARY_HOVER = "#D1DDD5"     # Hover Botones Secundarios
COLOR_DANGER = "#D9383A"              # Rojo Alerta / Borrar
COLOR_DANGER_HOVER = "#B82A2C"        # Rojo Oscuro (Hover)
COLOR_WARNING = "#D9822B"             # Naranja Advertencia
COLOR_WARNING_HOVER = "#B86A1F"       # Naranja Oscuro (Hover)


def resolver_ruta_recurso(nombre_archivo, fallback_absoluto=""):
    """Busca primero en la carpeta del script (BASE_DIR) y luego en una ruta de respaldo."""
    ruta_local = os.path.join(RESOURCE_DIR, nombre_archivo)
    if os.path.exists(ruta_local):
        return ruta_local
    ruta_externa = os.path.join(BASE_DIR,nombre_archivo)
    if os.path.exists(ruta_externa): return ruta_externa
    if fallback_absoluto and os.path.exists(fallback_absoluto):
        return fallback_absoluto
    return ruta_local
