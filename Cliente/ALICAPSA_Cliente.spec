# Build with the isolated 32-bit Python runtime.
from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_data_files,copy_metadata

root=Path(SPECPATH)
binaries=[]
redist=os.environ.get('ALICAPSA_VC_REDIST_DIR')
if redist:
    binaries=[(str(file),'.') for file in Path(redist).glob('*.dll')]
datas=collect_data_files('face_recognition_models')
for package in ('face-recognition-models','face-recognition','dlib'):
    datas+=copy_metadata(package)
for filename in ('logo.png','entrada.png','salida.png'):
    if (root/filename).is_file(): datas.append((str(root/filename),'.'))
a=Analysis([str(root/'launcher.py')],pathex=[str(root)],binaries=binaries,datas=datas,
    hiddenimports=['_dlib_pybind11','face_recognition_models','PIL.ImageTk'],
    hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['pip','cmake','ninja','PyInstaller','idlelib'],
    noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='ALICAPSA_Cliente',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=False,icon='NONE')
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='ALICAPSA_Cliente_Win10_x86')
