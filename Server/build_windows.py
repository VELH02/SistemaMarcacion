"""Build a standalone x64 server and validate before publishing a new delivery."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import uuid
import zipfile
from contextlib import closing
from pathlib import Path


def snapshot(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb'): pass
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=30)) as live, closing(sqlite3.connect(target)) as copy:
        live.backup(copy)
        if copy.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('Respaldo SQLite inválido')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',type=Path,required=True,help='Base existente para la copia de distribución')
    parser.add_argument('--demo',type=Path,help='DB de demostración opcional, separada de la predeterminada')
    args=parser.parse_args()
    if os.name!='nt' or struct.calcsize('P')!=8:
        raise SystemExit('Compile con Python de Windows de 64 bits')
    import database
    source=database.validate_location(args.database)
    demo=database.validate_location(args.demo) if args.demo else None
    root=Path(__file__).resolve().parent.parent
    build=root/'.build-server-x64'
    dist=build/('dist-'+uuid.uuid4().hex[:8])
    delivery=root/'Entrega'/'ALICAPSA_Servidor_Windows_x64'
    if delivery.exists() or delivery.with_suffix('.zip').exists():
        raise SystemExit('La entrega ya existe; consérvela y use otra versión. No se sobrescriben bases de servidores.')
    for target in (dist,build/'pyinstaller',delivery):
        if not target.resolve().is_relative_to(root): raise SystemExit('Ruta de compilación fuera del proyecto')
    subprocess.run([sys.executable,'-B','-m','PyInstaller','--noconfirm','--distpath',str(dist),
        '--workpath',str(build/'pyinstaller'),str(root/'Server'/'ALICAPSA_Servidor.spec')],check=True)
    stage=dist/delivery.name
    natives=[]
    for file in stage.rglob('*'):
        if not file.is_file() or file.suffix.casefold() not in ('.exe','.dll','.pyd'): continue
        with file.open('rb') as stream:
            header=stream.read(64)
            if header[:2]!=b'MZ': continue
            stream.seek(struct.unpack_from('<I',header,60)[0])
            signature,machine=struct.unpack('<4sH',stream.read(6))
        if signature!=b'PE\0\0' or machine!=0x8664: raise RuntimeError('Biblioteca que no es x64: '+str(file))
        natives.append(file.relative_to(stage).as_posix())
    data=stage/'data'
    snapshot(source,data/'alicapsa.sqlite3')
    if demo and demo!=source: snapshot(demo,data/'alicapsa_demostracion.db')
    result_path=build/'autoprueba_exe_x64.json'
    env=dict(os.environ)
    for variable in ('PYTHONHOME','PYTHONPATH','ALICAPSA_SERVER_HOME','ALICAPSA_DB'):
        env.pop(variable,None)
    exe=stage/'ALICAPSA_Servidor.exe'
    with tempfile.TemporaryDirectory(prefix='ALICAPSA build ') as folder:
        subprocess.run([str(exe),'--autoprueba',str(result_path)],env=env,cwd=folder,check=True,timeout=180)
        blank=Path(folder)/'sin datos'
        blank.mkdir()
        absent=subprocess.run([str(exe),'--host','127.0.0.1'],env=dict(env,ALICAPSA_SERVER_HOME=str(blank)),
            cwd=folder,capture_output=True,text=True,timeout=30)
        if absent.returncode!=1 or list(blank.rglob('*.sqlite3')):
            raise RuntimeError('El servidor debe rechazar una DB ausente sin crear una base vacía')
    result=json.loads(result_path.read_text(encoding='utf-8'))
    if not result.get('ok') or result['bits']!=64: raise RuntimeError('La autoprueba x64 falló')
    result['pruebas'].append('EXE sin Python externo y rechazo de DB faltante sin crear una base vacía')
    (stage/'AUTOPRUEBA_COMPILACION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copy2(root/'Server'/'DESPLIEGUE_WINDOWS.txt',stage/'LEEME.txt')
    # Fixed default URL; the console reports the actual configured port.
    with closing(sqlite3.connect((data/'alicapsa.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
        row=db.execute("SELECT datos FROM config WHERE clave='puerto_escucha'").fetchone()
        port=int(json.loads(row[0])) if row else 5000
    (stage/'Abrir_sistema.url').write_text('[InternetShortcut]\nURL=http://127.0.0.1:'+str(port)+'/\n',encoding='utf-8')
    dependencies=['Flask','Werkzeug','numpy','waitress','openpyxl','PyInstaller','Jinja2','MarkupSafe',
        'click','itsdangerous','blinker','et-xmlfile','packaging','altgraph','pefile','pywin32-ctypes',
        'setuptools','pyinstaller-hooks-contrib']
    versions={name:importlib.metadata.version(name) for name in dependencies}
    (stage/'VERSIONES.json').write_text(json.dumps(dict(python=sys.version,arquitectura='AMD64',
        dependencias=versions,bibliotecas_nativas=natives),indent=2),encoding='utf-8')
    provenance=build/'PYTHON_ORIGEN.json'
    if provenance.exists(): shutil.copy2(provenance,stage/'PYTHON_ORIGEN.json')
    licenses=stage/'licencias';licenses.mkdir(exist_ok=True)
    for name in dependencies:
        distribution=importlib.metadata.distribution(name)
        for file in distribution.files or []:
            if not any(token in str(file).casefold() for token in ('license','licence','notice','copying')): continue
            relative=Path(str(file))
            if relative.is_absolute() or '..' in relative.parts: continue
            file_source=Path(distribution.locate_file(file))
            if file_source.is_file():
                target=licenses/name/relative;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(file_source,target)
    python_license=Path(sys.executable).parent/'LICENSE.txt'
    if python_license.exists(): shutil.copy2(python_license,licenses/'PYTHON_LICENSE.txt')
    checks=[hashlib.sha256(file.read_bytes()).hexdigest()+'  '+file.relative_to(stage).as_posix()
        for file in sorted(stage.rglob('*')) if file.is_file() and file.name!='SHA256SUMS.txt']
    (stage/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n',encoding='utf-8')
    delivery.parent.mkdir(exist_ok=True)
    shutil.copytree(stage,delivery)
    archive=Path(shutil.make_archive(str(delivery),'zip',root_dir=delivery.parent,base_dir=delivery.name))
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None: raise RuntimeError('El ZIP no supera la prueba CRC')
    archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n',encoding='utf-8')
    print(json.dumps(dict(carpeta=str(delivery),zip=str(archive),bytes_zip=archive.stat().st_size,
        bytes_carpeta=sum(file.stat().st_size for file in delivery.rglob('*') if file.is_file()),autoprueba=result),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
