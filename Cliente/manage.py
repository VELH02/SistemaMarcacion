"""Terminal journal inspection and consistent SQLite backup; no GUI dependencies."""
import argparse
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
import outbox


def main():
    parser=argparse.ArgumentParser(description='Respaldo y pendientes del terminal ALICAPSA')
    parser.add_argument('command',choices=['check','backup'])
    parser.add_argument('--output')
    args=parser.parse_args()
    source=outbox.path().resolve()
    if not source.exists(): raise SystemExit('El terminal aún no tiene un diario SQLite. No se creó una base vacía.')
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as db:
        integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity!='ok': raise RuntimeError(integrity)
        if args.command=='check':
            print(json.dumps(dict(integridad=integrity,estados=dict(db.execute('SELECT state,count(*) FROM events GROUP BY state'))),ensure_ascii=False,indent=2))
            return
        target=Path(args.output) if args.output else source.parent/'backups'/datetime.now().strftime('terminal_%Y%m%d_%H%M%S_%f.sqlite3')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb'): pass
        try:
            with closing(sqlite3.connect(target)) as destination:
                db.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise RuntimeError('Respaldo inválido')
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        print(target.resolve())


if __name__=='__main__': main()
