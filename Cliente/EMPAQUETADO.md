# Cliente Windows 10 x86

La entrega está en `Entrega/ALICAPSA_Cliente_Win10_x86`, con una copia comprimida
del mismo nombre. Contiene el ejecutable sin consola, un configurador, las
bibliotecas nativas x86, los modelos faciales y el perfil privado del terminal.
Se copia la carpeta completa al equipo de destino. Consultar `LEEME.txt`.

El ejecutable usa Python 3.13.17 de 32 bits y PyInstaller 6.22.3. La dependencia
dlib 20.0.1 se compiló desde el código oficial de PyPI con MSVC x64 apuntando a
x86 y Windows SDK 10.0.19041. No se requiere CUDA, BLAS, AVX ni SSE4 en el terminal;
se conserva SSE2. Los cambios en la construcción de dlib permiten Ninja con MSVC
y limitan el paralelismo; no modifican sus algoritmos de reconocimiento.
El motor sigue produciendo vectores faciales de 128 dimensiones.

Se preparó un entorno aislado en `.build-client-x86`, separado del entorno del
servidor. La aplicación de destino no necesita ese entorno ni instalar Python.
Para regenerar con el entorno de compilación preparado y una carpeta de entrega
que aún no exista:

```powershell
.build-client-x86/python-package/tools/python.exe -B Cliente/build_windows.py --server-url http://192.168.1.112:5000/api
```

El script rechaza un intérprete de 64 bits, comprueba la arquitectura PE de todas
las bibliotecas y ejecuta la autoprueba antes de crear la carpeta de entrega.
El perfil de entrada es `Cliente/config.json`; solo se incluyen su credencial
API y la dirección indicada. No se distribuyen bases locales, cachés de empleados,
marcaciones ni PIN administrativos del equipo de compilación.
El entorno del servidor y sus bases no se empaquetan.

El configurador solicita un PIN nuevo para la instalación inicial. Después exige
el PIN actual para cambiarlo y conserva un hash PBKDF2 con sal aleatoria; no guarda
el PIN en texto plano. La variable ALICAPSA_ADMIN_PIN mantiene su prioridad por
compatibilidad. Configurar y marcar requieren una única instancia por carpeta.

Las pruebas del EXE comprueban la carga de modelos, una extracción nativa de
128 dimensiones sobre una imagen de prueba sin identidad, Tcl/Tk, PC/SC, SQLite
y el proceso biométrico separado. Se ejecutan con un directorio temporal y sin
comunicación con el servidor ni creación de marcaciones reales. Se probaron en
Windows 11 mediante ejecución x86; queda verificar Windows 10, la cámara y el
lector físicos del equipo de destino. La autoprueba no certifica precisión facial.

La carpeta incluye versiones, licencias, sumas SHA-256 y el resultado de esa
autoprueba. El ejecutable no tiene firma de código comercial. La carpeta y el ZIP
contienen una credencial privada del terminal y no deben publicarse.

Documentación de referencia:

- [Distribución de Python para compilación](https://docs.python.org/3/using/windows.html#the-nuget-org-packages).
- [dlib: construcción del módulo Python](https://dlib.net/compile.html).
- [PyInstaller: rutas de los archivos empaquetados](https://pyinstaller.org/en/stable/runtime-information.html).
