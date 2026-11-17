"""Administration commands. Run from any working directory."""
import argparse
import json
from contextlib import closing
import database
from storage import init_storage

def main():
    parser = argparse.ArgumentParser(description='Administración SQLite ALICAPSA')
    parser.add_argument('command', choices=['migrate', 'backup', 'check'])
    parser.add_argument('--output', help='Archivo de respaldo nuevo (opcional)')
    args = parser.parse_args()
    init_storage()
    if args.command == 'backup':
        print(database.backup(args.output))
    else:
        with closing(database.connect()) as db:
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
            if integrity != 'ok':
                raise RuntimeError(integrity)
            counts = {name: db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
                      for name in sorted(database.TABLES | {'marcaciones', 'asignaciones', 'decisiones', 'auditoria_planificacion','validaciones_bono','incidencias','incidencia_conceptos'})}
        print(json.dumps({'integridad': integrity, 'registros': counts}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
