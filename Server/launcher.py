"""Portable production entry point. Import application only after CLI dispatch."""
import argparse
import signal
import sys
from pathlib import Path


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--autoprueba':
        from package_selftest import run
        return run(Path(sys.argv[2]).resolve())
    if len(sys.argv)>1 and sys.argv[1]=='administrar':
        import database
        database.validate_location(database.DATABASE_PATH)
        import manage
        sys.argv=[sys.argv[0],*sys.argv[2:]]
        manage.main()
        return 0
    parser=argparse.ArgumentParser(description='Servidor ALICAPSA de 64 bits (Waitress)')
    parser.add_argument('--host',default='0.0.0.0',help='Dirección de escucha (predeterminada: toda la red local)')
    parser.add_argument('--port',type=int,help='Puerto; utiliza el configurado en la base de datos')
    parser.add_argument('--threads',type=int,default=4,help='Solicitudes simultáneas (predeterminado: 4)')
    args=parser.parse_args()
    if args.threads<1 or (args.port is not None and not 1<=args.port<=65535):
        parser.error('Utilice un puerto entre 1 y 65535 y al menos un hilo')
    from production_server import single_instance
    with single_instance():
        return start(args)


def start(args):
    import database
    # Missing portable data is an error, never a reason to create an empty payroll.
    database.validate_location(database.DATABASE_PATH)
    from run import create_app
    from production_server import serving
    app=create_app()
    port=args.port or int(database.read_catalog('config').get('puerto_escucha',5000))
    if not 1<=port<=65535: raise ValueError('Puerto de escucha inválido en la configuración')
    with serving(app,host=args.host,port=port,threads=args.threads) as (server,_):
        print('\nALICAPSA - Servidor Windows 64 bits',flush=True)
        print('Base de datos: '+str(database.DATABASE_PATH.resolve()),flush=True)
        print(f'Abra http://127.0.0.1:{port}/ en este equipo.',flush=True)
        print(f'En otros equipos use http://IP_DEL_SERVIDOR:{port}/',flush=True)
        print('Mantenga esta ventana abierta. Para detener: Ctrl+C.\n',flush=True)
        if hasattr(signal,'SIGBREAK'):
            def stop(signum,frame): raise KeyboardInterrupt
            signal.signal(signal.SIGBREAK,stop)
        try:
            server.run()
        except KeyboardInterrupt:
            print('\nDeteniendo servidor...',flush=True)
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('\nNo se pudo iniciar el servidor: '+str(error),file=sys.stderr,flush=True)
        print('Revise la base de datos seleccionada, permisos y que el puerto esté libre.',file=sys.stderr)
        if len(sys.argv)==1 and sys.stdin and sys.stdin.isatty():
            input('Presione Enter para cerrar...')
        raise SystemExit(1)
