"""Administration commands. Run from any working directory."""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from contextlib import closing
import database
from storage import init_storage

def main():
    parser = argparse.ArgumentParser(description='Administración SQLite ALICAPSA')
    parser.add_argument('command', choices=['migrate', 'backup', 'check', 'client-profile', 'demo'])
    parser.add_argument('--output', help='Archivo de respaldo nuevo (opcional)')
    parser.add_argument('--start', help='Primera jornada de demostración (AAAA-MM-DD)')
    parser.add_argument('--end', help='Última jornada de demostración (AAAA-MM-DD)')
    args = parser.parse_args()
    init_storage()
    if args.command=='demo':
        if not args.output or not args.start or not args.end:
            parser.error('demo requiere --output, --start y --end')
        from demo_data import create
        result=create(args.output,args.start,args.end)
        manifest=Path(args.output).with_suffix('.casos.json')
        with manifest.open('x',encoding='utf-8') as stream: json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps({k:v for k,v in result.items() if k!='casos'},ensure_ascii=False,indent=2))
        print('Guía de casos: '+str(manifest.resolve()))
        return
    if args.command == 'client-profile':
        from terminal import secret
        default_profile=(database.BASE_DIR/'perfiles'/'config_cliente.json' if getattr(sys,'frozen',False)
            else Path(__file__).resolve().parent.parent/'Cliente'/'config.json')
        target=Path(args.output or default_profile).resolve()
        data=json.loads(target.read_text(encoding='utf-8-sig')) if target.exists() else {}
        if not isinstance(data,dict): raise ValueError('El perfil existente no es válido; se conserva')
        data.setdefault('server_url','http://127.0.0.1:5000/api')
        data['api_token']=secret('terminal')
        target.parent.mkdir(parents=True,exist_ok=True)
        descriptor,temporary=tempfile.mkstemp(dir=target.parent,prefix='.perfil-')
        try:
            with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
                json.dump(data,stream,ensure_ascii=False,indent=2)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary,target)
        finally:
            if os.path.exists(temporary): os.remove(temporary)
        print('Perfil del terminal guardado en '+str(target)+'. Contiene una credencial privada; no publicarlo.')
        return
    if args.command == 'backup':
        print(database.backup(args.output))
    else:
        with closing(database.connect()) as db:
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
            if integrity != 'ok':
                raise RuntimeError(integrity)
            counts = {name: db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
                      for name in sorted(database.TABLES | {'marcaciones', 'asignaciones', 'decisiones', 'auditoria_planificacion','validaciones_bono','incidencias','incidencia_conceptos','terminal_events','empleados_baja'})}
        print(json.dumps({'integridad': integrity, 'registros': counts}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
