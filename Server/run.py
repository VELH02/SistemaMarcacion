from flask import Flask
import os
from config import SECRET_KEY, CONFIG_FILE, RESOURCE_DIR
from storage import init_storage, load_catalog
from logger import log_event
from routes.web import web_bp
from routes.api import api_bp
from routes.planning import planning_bp
from routes.batch import batch_bp

def create_app():
    app = Flask(__name__, template_folder=os.path.join(RESOURCE_DIR,'Templates'),
                static_folder=os.path.join(RESOURCE_DIR,'Static'))


    # Inicialización de archivos y carpetas
    init_storage()
    from terminal import secret
    app.secret_key = SECRET_KEY or secret('session')

    # Registro de módulos
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(planning_bp)
    app.register_blueprint(batch_bp)

    @app.before_request
    def refresh_permissions():
        from flask import session
        from config import USUARIOS_FILE
        username = session.get('usuario')
        if username:
            user = load_catalog(USUARIOS_FILE).get(username)
            if user is None:
                session.clear()
            else:
                session['area'] = user.get('area','').strip().upper().replace('Í','I')
                session['rol'] = user.get('rol','admin' if username=='admin' or session['area']=='TODAS' else 'coordinador')

    @app.context_processor
    def role_context():
        from flask import session
        from routes.planning import role
        from demo_data import status
        return {'rol_actual': role() if session.get('usuario') else '', 'demo_actual': status()}

    # Serialize read/modify/write operations as a single SQLite transaction.
    from functools import wraps
    from flask import request
    from database import transaction
    def transactional_view(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and request.endpoint!='web.seleccionar_base_datos':
                with transaction():
                    return view(*args, **kwargs)
            return view(*args, **kwargs)
        return wrapped
    for endpoint, view in list(app.view_functions.items()):
        app.view_functions[endpoint] = transactional_view(view)
    import time_sync
    time_sync.sincronizar_ntp(load_catalog(CONFIG_FILE).get('servidor_ntp', 'pool.ntp.org'))
    return app

if __name__ == '__main__':
    # Same production launcher as the portable EXE, including instance guard.
    from launcher import main
    raise SystemExit(main())
