# Compilación del servidor Windows x64

La entrega portable contiene `ALICAPSA_Servidor.exe`, `_internal`, recursos web
y una copia consistente de SQLite en `data/alicapsa.sqlite3`. No requiere Python
instalado. La interfaz y el motor de cálculo son los mismos del proyecto.

Se compila con Python oficial **3.13.17 de 64 bits** y PyInstaller **6.22.3**,
en `.build-server-x64`, separado del entorno de desarrollo y del cliente x86.
El origen y SHA-256 de Python se conservan en `PYTHON_ORIGEN.json`.
Python es el paquete oficial NuGet `python`, no `pythonx86`.

Instalar las dependencias fijadas de `requirements-windows-x64.txt` en ese
Python y ejecutar desde la raíz del proyecto:

```powershell
.build-server-x64/python-package/tools/python.exe -B Server/build_windows.py --database C:/ruta/alicapsa.sqlite3 --demo C:/ruta/demo.db
```

`--demo` es opcional. No copiar una DB activa con una copia de archivos normal:
el constructor abre el origen en solo lectura y utiliza SQLite Backup API.
La selección original `database_location.json` no se distribuye porque contiene
una ruta absoluta del equipo de desarrollo. No se alteran usuarios ni credenciales
de la copia de producción. Esto permite conservar la autenticación de clientes.
El archivo demo, si se incluye, queda separado y no se activa al compilar.

Antes de publicar en `Entrega/ALICAPSA_Servidor_Windows_x64`, se valida la
arquitectura AMD64 de todos los binarios y se ejecuta el EXE desde un directorio
temporal sin PYTHONHOME ni PYTHONPATH. La autoprueba verifica páginas, recursos,
autenticación de API, cuatro terminales simultáneos, reintentos, historial,
exportación XLSX, respaldo e integridad. También rechaza una segunda instancia
que intente ocupar el mismo puerto en Windows. Opera con otra copia temporal de SQLite.
También se comprueba que una DB faltante impida iniciar sin crear una base vacía.
La entrega incluye versiones, licencias, sumas SHA-256 y ZIP comprobado por CRC.

El arranque de producción mantiene un mutex global de Windows: solo una
instancia por equipo, incluso con otra carpeta, otro puerto o sesión de Windows.
Windows libera el identificador al terminar el proceso. El respaldo y los otros
comandos de administración siguen disponibles con el servidor abierto. `run.py`
usa el mismo lanzador en ejecución desde código. La autoprueba aislada no toma
el bloqueo de producción.

El constructor rechaza sobrescribir una entrega ya existente para proteger sus
datos. Para otra versión, conservar la entrega anterior y cambiar el nombre de
la carpeta de destino del constructor. En una instalación que ya recibe marcas,
conservar su `data`, respaldos y perfiles al actualizar EXE y `_internal`.

Las rutas dentro de la carpeta del EXE se guardan también como relativas en el
modo compilado para poder trasladar la carpeta completa. Una DB externa mantiene
su ruta absoluta. `ALICAPSA_SERVER_HOME` permite elegir la carpeta de datos y
logs explícitamente; está destinado a despliegues administrados y pruebas.
`ALICAPSA_DB` sigue siendo la selección inicial cuando no hay una selección web.

Ver [instrucciones de despliegue](DESPLIEGUE_WINDOWS.txt). La comprobación local
se realizó en Windows 11 x64; el equipo de destino debe probarse antes de planilla.
