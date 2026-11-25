"""Atomic saving of explicitly edited forms using the existing permission checks."""
import json
import re
import uuid
from urllib.parse import urlsplit
from flask import Blueprint, current_app, request, session, jsonify, flash
from werkzeug.datastructures import MultiDict
import database
import planning
from .planning import authenticated

batch_bp = Blueprint('batch', __name__)
ALLOWED = re.compile(r'^/(?:turnos|planificacion|aprobaciones/(?:guardar_incidencia|terminal)|marcaciones/guardar_ajuste|bono/validar|colaboradores(?:/editar/[^/]+)?|admin/usuarios/(?:crear|editar/[^/]+|reset_password/[^/]+)|admin/areas/(?:crear|editar/[^/]+)|config|rrhh/calendario|admin/conceptos)$')


class BatchError(ValueError):
    pass


@batch_bp.route('/guardar_cambios', methods=['POST'])
@authenticated
def save_all():
    try:
        operations = json.loads(request.form.get('operaciones','[]'))
        if not isinstance(operations,list) or not 1<=len(operations)<=500:
            raise BatchError('No hay cambios válidos para guardar (máximo 500 formularios)')
        identity = dict(session)
        batch_id = uuid.uuid4().hex
        with database.transaction() as db:
            for index,operation in enumerate(operations):
                if not isinstance(operation,dict): raise BatchError('Formulario inválido')
                if not isinstance(operation.get('action'),str): raise BatchError('Dirección de formulario inválida')
                parts=urlsplit(operation.get('action',''))
                if parts.scheme or parts.netloc or parts.query or not ALLOWED.fullmatch(parts.path):
                    raise BatchError('Formulario no permitido')
                fields=operation.get('fields',[])
                if not isinstance(fields,list) or any(not isinstance(pair,list) or len(pair)!=2 or not all(isinstance(v,str) for v in pair) for pair in fields):
                    raise BatchError('Campos inválidos')
                data=MultiDict(fields)
                for field,file_key in operation.get('files',[]):
                    upload=request.files.get(file_key)
                    if upload is None: raise BatchError('Archivo adjunto incompleto')
                    data.add(field,(upload.stream,upload.filename))
                # Each form uses its normal route, current permissions and validations.
                with current_app.test_request_context(parts.path,method='POST',data=data):
                    session.update(identity)
                    session.pop('_flashes',None)
                    response=current_app.full_dispatch_request()
                    errors=[message for category,message in session.get('_flashes',[]) if category in ('danger','warning')]
                    try:
                        if response.status_code>=400 or errors or response.location and urlsplit(response.location).path=='/login':
                            detail='; '.join(errors) or response.get_data(as_text=True)
                            raise BatchError(f'Cambio {index+1}: {detail[:700]}')
                    finally:
                        response.close()
                # Never copy passwords, biometrics or file contents into the audit trail.
                safe={key:value for key,value in fields if not re.search(r'pass|password|vector|archivo',key,re.I)}
                planning.audit(db,data.get('emp_id',data.get('usuario','')),data.get('fecha',''),
                    'GUARDADO_FORMULARIO',None,dict(lote=batch_id,formulario=parts.path,campos=safe),identity['usuario'])
        flash(f'Se guardaron todos los cambios ({len(operations)} formularios).','success')
        return jsonify(ok=True,guardados=len(operations),lote=batch_id)
    except (ValueError,TypeError,KeyError) as error:
        return jsonify(ok=False,error=str(error)),400
