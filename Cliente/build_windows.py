"""Build and validate the portable x86 client; never package employee databases."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--server-url',required=True)
    args=parser.parse_args()
    if os.name!='nt' or struct.calcsize('P')!=4: raise SystemExit('Use Python de Windows de 32 bits para generar este ejecutable')
    root=Path(__file__).resolve().parent.parent
    build=root/'.build-client-x86'
    delivery=root/'Entrega'/'ALICAPSA_Cliente_Win10_x86'
    if delivery.exists(): raise SystemExit('La carpeta de entrega ya existe. Consérvela y use otra versión; no se sobrescriben datos de terminales.')
    url=urlsplit(args.server_url.rstrip('/'))
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('','/api'):
        raise SystemExit('Dirección de servidor inválida')
    profile=json.loads((root/'Cliente'/'config.json').read_text(encoding='utf-8-sig'))
    if not profile.get('api_token'): raise SystemExit('Genere primero el perfil privado con Server/manage.py client-profile')
    vc=build/'msvc'/'VC'/'Redist'/'MSVC'/'14.44.35112'/'x86'/'Microsoft.VC143.CRT'
    if not (vc/'msvcp140.dll').exists(): raise SystemExit('Faltan las bibliotecas redistribuibles oficiales x86')
    env=dict(os.environ,ALICAPSA_VC_REDIST_DIR=str(vc))
    stage=build/'dist'/'ALICAPSA_Cliente_Win10_x86'
    for output in (build/'dist',build/'pyinstaller',delivery):
        if not output.resolve().is_relative_to(root): raise SystemExit('Ruta de compilación fuera del proyecto')
    subprocess.run([sys.executable,'-B','-m','PyInstaller','--noconfirm','--distpath',str(build/'dist'),
        '--workpath',str(build/'pyinstaller'),str(root/'Cliente'/'ALICAPSA_Cliente.spec')],env=env,check=True)
    exe=stage/'ALICAPSA_Cliente.exe'
    # Check architecture in the EXE and every bundled native library.
    native=[]
    for file in stage.rglob('*'):
        if not file.is_file() or file.suffix.casefold() not in ('.exe','.pyd','.dll'): continue
        with file.open('rb') as stream:
            header=stream.read(64)
            if header[:2]!=b'MZ': continue
            stream.seek(struct.unpack_from('<I',header,60)[0])
            signature,machine=struct.unpack('<4sH',stream.read(6))
        if signature!=b'PE\0\0' or machine!=0x14c: raise RuntimeError('Biblioteca que no es x86: '+str(file))
        native.append(str(file.relative_to(stage)))
    result_path=build/'autoprueba_exe_x86.json'
    subprocess.run([str(exe),'--autoprueba',str(result_path)],check=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    result=json.loads(result_path.read_text(encoding='utf-8'))
    if not result.get('ok') or result.get('bits')!=32: raise RuntimeError('Falló la autoprueba del ejecutable')
    if list(stage.rglob('terminal.sqlite3*')) or list(stage.rglob('empleados.json')): raise RuntimeError('La distribución contiene datos de prueba o empleados')
    delivery.parent.mkdir(exist_ok=True)
    shutil.copytree(stage,delivery)
    shutil.copy2(delivery/'ALICAPSA_Cliente.exe',delivery/'Configurar_Cliente.exe')
    data=delivery/'datos';data.mkdir()
    host=url.hostname
    if ':' in host: host='['+host+']'
    port=url.port
    base=url.scheme+'://'+host
    settings=dict(server_ip=base,server_port=str(port) if port else '',server_url=base+(':'+str(port) if port else '')+'/api',api_token=profile['api_token'])
    (data/'config.json').write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copy2(root/'Cliente'/'DESPLIEGUE_WINDOWS.txt',delivery/'LEEME.txt')
    shutil.copy2(result_path,delivery/'AUTOPRUEBA_COMPILACION.json')
    dependencies=['numpy','opencv-python','Pillow','requests','dlib','face-recognition','face-recognition-models','certifi','pyinstaller','setuptools']
    versions={name:importlib.metadata.version(name) for name in dependencies}
    (delivery/'VERSIONES.json').write_text(json.dumps(dict(python=sys.version,arquitectura='x86',dependencias=versions,bibliotecas_nativas=native),indent=2),encoding='utf-8')
    licenses=delivery/'licencias';licenses.mkdir()
    for name in dependencies:
        distribution=importlib.metadata.distribution(name)
        for file in distribution.files or []:
            lower=str(file).casefold()
            if not any(token in lower for token in ('license','licence','copying','notice')): continue
            source=Path(distribution.locate_file(file))
            if source.is_file():
                relative=Path(str(file))
                if relative.is_absolute() or '..' in relative.parts: continue
                target=licenses/name/relative;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
    python_license=Path(sys.executable).parent/'LICENSE.txt'
    if python_license.exists(): shutil.copy2(python_license,licenses/'PYTHON_LICENSE.txt')
    (licenses/'MICROSOFT_VC_RUNTIME.txt').write_text('Bibliotecas redistribuibles oficiales de Microsoft Visual C++ 2022 x86.\nTérminos: https://visualstudio.microsoft.com/license-terms/vs2022-cruntime/\n',encoding='utf-8')
    checks=[]
    for file in sorted(delivery.rglob('*')):
        if file.is_file(): checks.append(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+file.relative_to(delivery).as_posix())
    (delivery/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n',encoding='utf-8')
    archive=shutil.make_archive(str(delivery),'zip',root_dir=delivery.parent,base_dir=delivery.name)
    size=sum(file.stat().st_size for file in delivery.rglob('*') if file.is_file())
    print(json.dumps(dict(carpeta=str(delivery),zip=archive,bytes_carpeta=size,bytes_zip=Path(archive).stat().st_size,autoprueba=result),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
