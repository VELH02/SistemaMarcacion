"""Portable entry point. Keep multiprocessing diversion before GUI imports."""
import multiprocessing as mp
import sys


def configure_terminal():
    import tkinter as tk
    from tkinter import simpledialog,messagebox
    from urllib.parse import urlsplit
    from storage import cargar_configuracion,guardar_pin_administrativo,tiene_pin_administrativo,verificar_pin_administrativo
    root=tk.Tk();root.withdraw()
    try:
        current=cargar_configuracion()
        if tiene_pin_administrativo():
            existing=simpledialog.askstring('Acceso administrativo','Ingrese el PIN actual para cambiar la configuración.',show='*',parent=root)
            if existing is None: return
            if not verificar_pin_administrativo(existing): raise ValueError('PIN actual incorrecto; no se modificó la configuración')
        address=simpledialog.askstring('Configurar ALICAPSA','Dirección del servidor (ejemplo: http://192.168.1.112:5000/api)',
            initialvalue=current.get('server_url',''),parent=root)
        if address is None: return
        parsed=urlsplit(address.strip())
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path.rstrip('/') not in ('','/api'):
            raise ValueError('Indique una dirección HTTP/HTTPS válida del servidor, sin usuario ni contraseña')
        port=parsed.port
        if port is not None and not 1<=port<=65535: raise ValueError('Puerto del servidor inválido')
        pin=simpledialog.askstring('PIN administrativo','Elija un PIN administrativo de 6 a 8 dígitos para este terminal.',show='*',parent=root)
        if pin is None: return
        repeated=simpledialog.askstring('Confirmar PIN','Repita el PIN.',show='*',parent=root)
        if repeated is None: return
        if pin!=repeated: raise ValueError('Los PIN no coinciden; no se guardó la configuración')
        if not pin.isascii() or not pin.isdigit() or not 6<=len(pin)<=8: raise ValueError('El PIN debe tener de 6 a 8 dígitos')
        host=parsed.hostname
        if ':' in host: host='['+host+']'
        base=parsed.scheme+'://'+host
        full_url=base+(':'+str(port) if port else '')+'/api'
        guardar_pin_administrativo(pin,dict(server_ip=base,server_port=str(port) if port else '',server_url=full_url))
        messagebox.showinfo('ALICAPSA','Configuración guardada. Abra ALICAPSA_Cliente.exe. El PIN se almacena protegido, sin texto plano.',parent=root)
    except (ValueError,OSError) as error:
        messagebox.showerror('Configurar ALICAPSA',str(error),parent=root)
    finally: root.destroy()


def self_test(destination):
    import ctypes
    import json
    import os
    import tempfile
    from pathlib import Path
    report=dict(ok=False,bits=ctypes.sizeof(ctypes.c_void_p)*8,python=sys.version.split()[0])
    try:
        with tempfile.TemporaryDirectory(prefix='alicapsa-prueba-') as folder:
            os.environ['ALICAPSA_CLIENT_DATA']=folder
            import numpy as np
            import cv2,dlib,face_recognition,tkinter
            import outbox
            from biometria import worker_reconocimiento
            tcl=tkinter.Tcl()
            report.update(numpy=np.__version__,opencv=cv2.__version__,dlib=dlib.__version__,tcl=tcl.eval('info patchlevel'))
            ctypes.WinDLL('winscard.dll')
            image=np.zeros((160,160,3),dtype=np.uint8)
            encodings=face_recognition.face_encodings(image,[(10,150,150,10)],model='small')
            if len(encodings)!=1 or encodings[0].shape!=(128,) or not np.isfinite(encodings[0]).all(): raise RuntimeError('Falló la extracción biométrica nativa')
            report['vector_facial_dimensiones']=len(encodings[0])
            incoming,outgoing=mp.Queue(),mp.Queue()
            worker=mp.Process(target=worker_reconocimiento,args=(incoming,outgoing),daemon=True)
            worker.start()
            try:
                incoming.put(('RESET','autoprueba'))
                incoming.put(('autoprueba',image,np.zeros(128)))
                result=outgoing.get(timeout=60)
                if result.get('session_id')!='autoprueba' or result.get('verificado'): raise RuntimeError('Falló el aislamiento de sesión biométrica')
                incoming.put(None);worker.join(timeout=10)
                if worker.is_alive() or worker.exitcode!=0: raise RuntimeError('El proceso biométrico no terminó correctamente')
            finally:
                if worker.is_alive(): worker.terminate();worker.join(timeout=5)
                incoming.close();outgoing.close()
            identifier=outbox.enqueue('mark',dict(empleado_id='AUTOPRUEBA',tipo_marcacion='ENTRADA'))
            if outbox.get(identifier)['state']!='PENDING': raise RuntimeError('Falló la persistencia local')
            report.update(pcsc=True,multiprocessing=True,sqlite=True,ok=True)
    except Exception as error:
        import traceback
        report.update(error=str(error),detalle=traceback.format_exc())
    Path(destination).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['ok'] else 1


def portable_main():
    import ctypes
    import hashlib
    import logging
    from logging.handlers import RotatingFileHandler
    import os
    from pathlib import Path
    if '--autoprueba' in sys.argv:
        index=sys.argv.index('--autoprueba')
        return self_test(sys.argv[index+1])
    try:
        import config
        os.makedirs(config.DATA_DIR,exist_ok=True)
        logs=Path(config.DATA_DIR)/'logs';logs.mkdir(exist_ok=True)
    except (OSError,ValueError) as error:
        from tkinter import messagebox
        messagebox.showerror('ALICAPSA','No se pudo preparar la carpeta de datos. Use una carpeta con permiso de escritura.\n'+str(error))
        return 1
    handler=RotatingFileHandler(logs/'cliente.log',maxBytes=2_000_000,backupCount=2,encoding='utf-8')
    logging.basicConfig(level=logging.INFO,handlers=[handler],format='%(asctime)s %(levelname)s %(message)s')
    class LogStream:
        def write(self,value):
            if value.strip(): logging.info(value.rstrip())
            return len(value)
        def flush(self): handler.flush()
        def isatty(self): return False
    if sys.stdout is None: sys.stdout=LogStream()
    if sys.stderr is None: sys.stderr=LogStream()
    mutex=None
    kernel=None
    try:
        if os.name=='nt':
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p]
            kernel.CreateMutexW.restype=ctypes.c_void_p
            kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            name='Local\\ALICAPSA_Cliente_'+hashlib.sha256(str(Path(config.DATA_DIR).resolve()).casefold().encode()).hexdigest()[:24]
            mutex=kernel.CreateMutexW(None,False,name)
            if not mutex: raise ctypes.WinError(ctypes.get_last_error())
            if ctypes.get_last_error()==183:
                from tkinter import messagebox
                messagebox.showinfo('ALICAPSA','El cliente ya está abierto. Ciérrelo antes de abrir otra instancia o cambiar su configuración.')
                return 0
        if '--configurar' in sys.argv or Path(sys.executable).stem.casefold()=='configurar_cliente':
            configure_terminal()
        else:
            import outbox
            outbox.migrate_legacy()
            from main import SistemaMarcacionApp
            app=SistemaMarcacionApp()
            app.mainloop()
        return 0
    except Exception:
        logging.exception('No se pudo iniciar el cliente')
        from tkinter import messagebox
        messagebox.showerror('ALICAPSA','No se pudo iniciar. Sus datos locales se conservan. Revise datos/logs/cliente.log o contacte a TI.')
        return 1
    finally:
        if mutex and kernel: kernel.CloseHandle(mutex)


if __name__=='__main__':
    mp.freeze_support()
    raise SystemExit(portable_main())
