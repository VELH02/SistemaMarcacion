# Presentación de noviembre de 2026

La demostración usa una copia independiente de la base, con los mismos
colaboradores, áreas, usuarios y permisos. No modifica la base original.
Cada marcación generada tiene ID `DEMO-…`, origen `SIMULACION`, una nota del
escenario y una entrada en la auditoría SQL con usuario `DEMO`.

Para generar una nueva copia desde la base original:

```powershell
.venv/Scripts/python.exe Server/manage.py backup
.venv/Scripts/python.exe Server/manage.py demo --start 2026-11-09 --end 2026-11-30 --output Server/data/alicapsa_demo_2026_11_09_30.db
```

El archivo de salida debe ser nuevo: nunca se sobrescribe uno existente.
Se genera también un archivo `.casos.json` con la guía por persona y fecha.
Los nombres y datos personales de esta guía no deben publicarse con el código.

Para abrir esa copia, entrar en **Administración → Configuración → Base de datos
SQLite**, elegir la ruta absoluta de `alicapsa_demo_2026_11_09_30.db`, pulsar
**Validar y guardar ruta** y reiniciar el servidor. Desde `Server`, en PowerShell:

```powershell
../.venv/Scripts/python.exe -B -m waitress --listen=0.0.0.0:5000 --call run:create_app
```

La web muestra un aviso de demostración. La fecha de evaluación se fija al
1 de diciembre de 2026 al mediodía, exclusivamente en esa copia, para cerrar
las jornadas hasta el día 30, incluidas las salidas nocturnas del 1 de diciembre.
El reloj visible del equipo conserva la fecha real.

Los turnos `DEMO-D` y `DEMO-N` son ejemplos: 06:00–14:30 con pausa 12:00–12:30,
y 22:00–06:00 con pausa 02:00–03:00, respectivamente. Sus pausas son supuestos
para presentar el programa; no representan una validación de los horarios reales.
Los domingos quedan como descanso, salvo dos ejemplos de domingo trabajado.
La generación conserva las fichas y las definiciones originales de los turnos.

Hay asistencias normales, anticipaciones, tardanzas, permisos remunerados (310),
ausencias no justificadas (730), permisos no remunerados (750), horas extra,
domingos de 4 y 10 horas efectivas y entradas/salidas incompletas. Algunas
incidencias quedan pendientes para mostrar la intervención del coordinador.
La exportación de nómina seguirá bloqueada cuando corresponda por esos pendientes;
la exportación de asistencias permite verlos. Los Excel se identifican como DEMO.
El bono exige el mes completo: no se inventan jornadas del 1 al 8 para hacerlo
aprobar con una simulación parcial que empieza el día 9.

Mientras esta copia esté servida, los POST del API de terminales responden 503,
sin confirmar persistencia. El cliente conserva sus envíos pendientes para
reintentarlos cuando vuelva la base original; no se mezclan marcaciones reales
con datos ficticios. Las validaciones y ajustes de la web funcionan en la copia.

Para volver a los datos originales, seleccionar la ruta de `alicapsa.sqlite3`
en el mismo apartado de Administración, guardarla y reiniciar Waitress:

```powershell
../.venv/Scripts/python.exe -B -m waitress --listen=0.0.0.0:5000 --call run:create_app
```

Los cambios realizados durante la presentación permanecen en la copia DEMO y
no se trasladan automáticamente a la base original.
La selección de Administración se guarda fuera de ambas bases y tiene prioridad
sobre la variable `ALICAPSA_DB`. No hay que modificar ni reemplazar las bases a mano.
