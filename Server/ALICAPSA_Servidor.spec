# Build using Windows Python x64; never embed databases or private bootstrap files.
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root=Path(SPECPATH)
datas=[(str(root/'Templates'),'Templates'),(str(root/'Static'),'Static')]
for package in ('flask','waitress','openpyxl'):
    datas+=copy_metadata(package)
a=Analysis([str(root/'launcher.py')],pathex=[str(root)],binaries=[],datas=datas,
    hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],
    excludes=['pip','PyInstaller','tkinter','idlelib','pytest'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='ALICAPSA_Servidor',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=True,icon='NONE')
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='ALICAPSA_Servidor_Windows_x64')
