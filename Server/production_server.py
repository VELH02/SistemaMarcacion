"""Waitress lifecycle with exclusive Windows port ownership."""
import os
import socket
from contextlib import contextmanager
from waitress import create_server,wasyncore
from waitress.task import ThreadedTaskDispatcher


@contextmanager
def single_instance(name='Global\\ALICAPSA.Servidor.Produccion'):
    """One production server per Windows machine, regardless of folder or port."""
    if os.name!='nt':
        yield
        return
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=(ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR)
    kernel.CreateMutexW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
    kernel.CloseHandle.restype=wintypes.BOOL
    handle=kernel.CreateMutexW(None,False,name)
    error=ctypes.get_last_error()
    if not handle:
        raise RuntimeError('No se pudo comprobar la instancia única del servidor: '+str(error))
    try:
        if error==183:
            raise RuntimeError('El servidor ALICAPSA ya está abierto en este equipo. Use la instancia activa o ciérrela antes de iniciar otra.')
        yield
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def serving(app,host='0.0.0.0',port=5000,threads=4):
    # SO_REUSEADDR can let two Windows servers bind the same address. Bind an
    # exclusive socket first, then hand that socket to Waitress's public API.
    listener=socket.socket(socket.AF_INET6 if ':' in host else socket.AF_INET,socket.SOCK_STREAM)
    socket_map={}
    dispatcher=None
    try:
        if os.name=='nt':
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        else:
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind((host,port))
        dispatcher=ThreadedTaskDispatcher()
        dispatcher.set_thread_count(threads)
        server=create_server(app,sockets=[listener],threads=threads,map=socket_map,_dispatcher=dispatcher)
        yield server,socket_map
    finally:
        if dispatcher is not None: dispatcher.shutdown()
        wasyncore.close_all(map=socket_map)
        listener.close()
