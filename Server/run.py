from flask import Flask
from config import SECRET_KEY, CONFIG_FILE
from storage import init_files, load_json
from logger import log_event
from routes.web import web_bp
from routes.api import api_bp

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.secret_key = SECRET_KEY

    # Inicialización de archivos y carpetas
    init_files()

    # Registro de módulos
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    return app

if __name__ == '__main__':
    app = create_app()
    config = load_json(CONFIG_FILE)
    puerto = config.get("puerto_escucha", 5000)
    
    log_event("Sistema", f"Servidor modular iniciado en puerto {puerto}")
    app.run(host='0.0.0.0', port=puerto, debug=True)