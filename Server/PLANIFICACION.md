# Turnos, asistencia y novedades

Este flujo pertenece al servidor. No requiere cambios en el protocolo del cliente.

## Marcaciones incompletas

Una salida solo se empareja con una entrada anterior cuando transcurrieron menos
de 24 horas. A las 24 horas o más se conservan dos registros independientes:
entrada sin salida y salida sin entrada. Los turnos que cruzan medianoche siguen
emparejándose dentro de ese límite.

Una entrada nueva deja la anterior como incompleta e inicia otra jornada; no se
ignora por existir una entrada pendiente. Las repeticiones con la misma fecha y
hora conservan el tratamiento previo de duplicados. La falta de salida se marca
para revisión al terminar el turno asignado, sin esperar 24 horas. No se inventan
salidas ni cantidades de horas para una jornada incompleta. El coordinador debe
revisar y ajustar la marcación; mientras tanto se bloquea la nómina afectada.
El cálculo se aplica también a registros históricos, sin modificar sus originales.

## Responsabilidades

RH administra colaboradores y valida las definiciones de turnos. No puede abrir
las asistencias, planificación semanal, novedades, bono ni exportaciones, tampoco
enviando solicitudes directamente a esas rutas. El coordinador gestiona estas
operaciones exclusivamente para su área y puede agregar y eliminar colaboradores
de esa misma área. La edición de datos existentes continúa reservada a RH y al
administrador. Las altas y bajas quedan en la auditoría SQL. El administrador conserva acceso técnico global y al calendario.

El coordinador confirma o invalida tardanzas. Invalidar exige motivo; conserva
los minutos reales, pero los excluye de los minutos computables del bono y del
descuento. El tiempo justificado se informa con el concepto remunerado 310.
Las HE tienen decisiones separadas: pendientes, aprobadas o rechazadas; rechazar
exige motivo. Cambiar una marcación obliga a revisar nuevamente esas decisiones.

En Bono se distinguen el resultado calculado y la decisión del coordinador.
Solo se aprueba un mes cerrado que cumpla los requisitos; rechazar requiere
motivo. La decisión guarda usuario, fecha y una huella de los datos evaluados;
si cambian los datos del mes, vuelve a quedar pendiente de revisión.

## Guardado de todas las ediciones

Las pantallas con formularios editables muestran **Guardar todos los cambios**.
También los botones de guardado de cada fila envían todos los formularios
modificados de la pantalla, incluidos los de otros colaboradores y los adjuntos.
Las filas sin cambios no se vuelven a enviar. Si una validación falla, toda la
transacción se revierte y las ediciones permanecen en el navegador para corregirlas.
Los filtros se bloquean mientras hay cambios pendientes y salir de la página
muestra el aviso de cambios sin guardar. Las eliminaciones, descargas, inicio de
sesión y sincronización manual no se incluyen en un guardado de ediciones.

En **Validaciones** cada incidencia tiene su propia fila: HE, tardanza o tiempo
faltante. Solo hay controles para incidencias realmente detectadas. El servidor
repite esa comprobación al guardar y rechaza formularios que mezclen tipos,
modifiquen cantidades o envíen excepciones. Para tiempo faltante solo se elige
el código; su tratamiento procede de la definición central en **Conceptos**, que
administra el administrador. No hay remuneración individual ni excepciones de día
en estas filas. Una tardanza nunca se incluye otra vez dentro del tiempo faltante.

Las exportaciones conservan cada concepto por jornada e incidencia; no suman
jornadas distintas en una misma fila. Incluyen el identificador de incidencia
para consultar el registro en SQLite.

## Operación

1. El administrador crea un usuario con rol **Recursos Humanos** en Usuarios.
   RH y el administrador pueden registrar y validar turnos en **Turnos RH**.
2. RH ingresa entrada, salida y descansos reales. Puede registrar varios
   descansos separados o indicar que cuentan como tiempo de trabajo remunerado.
   Dejar descansos vacíos significa que no se descuenta ninguno. No se inventa
   una hora de descanso para hacer coincidir una jornada nocturna.
3. El coordinador entra en **Semana**, selecciona un lunes y asigna a cada
   colaborador de su área un turno o un descanso por día. Una casilla sin asignar
   representa planificación pendiente, nunca una ausencia automática.
   Puede seleccionar un **turno fijo** y pulsar **Aplicar lunes a sábado** para
   guardar los seis días juntos. El domingo queda como descanso predeterminado,
   también cuando no existe asignación explícita. No genera ausencia ni pendiente
   de planificación. Un trabajo dominical excepcional requiere un turno explícito
   y conserva los recargos correspondientes. La salida dominical de un turno
   iniciado el sábado sigue perteneciendo a la jornada del sábado.
4. En **Aprobaciones**, revisa las jornadas ya terminadas, selecciona el código
   de ausencia, selecciona el código aplicable y aprueba o rechaza HE.
5. Exporta **Asistencias** para inspeccionar todo el detalle. La exportación
   de **Nómina RRHH** exige resolver turnos sin validar, planificación pendiente,
   marcaciones incompletas, HE sin aprobar y permisos sin tratamiento definido.
   Las jornadas en curso o futuras tampoco se liquidan como terminadas.

Las marcaciones incompletas se corrigen desde Asistencias. Un ajuste de salida
de un turno nocturno utiliza la fecha siguiente cuando corresponde. Los ajustes
y las decisiones dejan una entrada de auditoría con usuario y valores anteriores.
Un ajuste manual invalida la aprobación anterior de HE para revisar de nuevo
las horas resultantes. La fecha de ingreso se puede registrar en Colaboradores.

## Ejemplo nocturno

Si RH registra 22:00–06:00 con descanso no remunerado 02:00–03:00, una marcación
del lunes a las 22:00 y salida del martes a las 06:00 corresponde al lunes:
7 horas ordinarias efectivas y 8 horas equivalentes diurnas de base pagable.

Si registra ese mismo horario sin descanso, se conservan 8 horas trabajadas:
7 ordinarias y 1 HE detectada. Su aprobación se revisa en Aprobaciones.
Entrar 10 minutos tarde produce 10 minutos de tardanza; quedarse después no
borra esa tardanza. Llegar antes queda registrado pero no genera HE por sí mismo:
el coordinador debe incluir expresamente ese trabajo anticipado y aprobarlo.

## Ausencias y bono

- Solo un turno asignado y terminado permite calcular una ausencia completa.
  Un descanso explícito no genera ausencia. Una marcación incompleta queda
  pendiente de revisión y no descuenta automáticamente el día completo.
- El código 310 conserva la base pagable del tiempo justificado. Los códigos
  730, 750, 760 y 720 se tratan como no remunerados por la empresa.
- Para otros códigos, incluidos subsidios e incapacidades, el administrador debe
  definir centralmente la cobertura aplicable: remunerado por la empresa o no remunerado
  por la empresa. El sistema no conoce saldos de licencias ni subsidios de CSS.
- Las ausencias parciales y completas invalidan el bono, incluso si son pagadas.
  Las tardanzas se acumulan con segundos, sin truncarlas a minutos enteros.
  Hasta 30 minutos en el mes satisface el límite; 30 minutos y un segundo no.
- El bono consulta el mes completo, aunque la exportación sea de una quincena.
  Un mes abierto es provisional. Los días pasados sin planificación y las
  marcaciones incompletas impiden confirmar elegibilidad. `fecha_ingreso` del
  empleado, cuando exista, delimita su primer período; en su ausencia se requiere
  planificar desde el inicio del mes. No se calcula el monto del bono.

## Domingo trabajado: convenio ALICAPSA

Una jornada iniciada el domingo y con marcaciones completas reconoce como mínimo
**8 horas de fin de semana**, aunque haya trabajado menos. No se registra ausencia
ni tiempo faltante por completar menos horas ese domingo. Las horas reales no
se modifican: se muestran aparte del complemento reconocido por convenio.

Para una jornada diurna, 4 horas reales reconocen 8 horas bajo el código 652;
10 horas reales reconocen 8 bajo 652 y 2 HE de fin de semana, pendientes de su
validación independiente. Las horas efectivas descuentan únicamente los descansos
que RH haya registrado como no remunerados.

La base de fin de semana tiene una fila propia **DOMINGO** en Validaciones y una
decisión independiente de las HE. El coordinador puede aprobar, rechazar con motivo
o dejar pendiente cada una, y guardarlas junto con otras ediciones. La nómina no
se cierra si el reconocimiento dominical sigue pendiente.

Si el domingo estaba marcado como descanso, el motor utiliza una referencia
validada por RH cercana a la hora de entrada, priorizando las asignaciones del
colaborador. La conserva en la fuente de cálculo auditada, sin convertir el
DESCANSO de la planificación en un turno obligatorio. Si no existe una referencia
válida cercana, se requiere revisar el turno; no se inventan descansos. No se
calcula tardanza respecto de un horario obligatorio cuando el domingo era descanso.

Las jornadas nocturnas y mixtas mantienen los límites legales de 7 y 7.5 horas
ordinarias efectivas: el mínimo de pago equivalente de 8 no retrasa las HE hasta
la octava hora efectiva. Las HE de una jornada dominical conservan el tratamiento
de fin de semana al cruzar medianoche; un feriado conserva su recargo superior.
El domingo sin trabajo sigue siendo descanso y no genera ese reconocimiento.
Una salida dominical de una jornada iniciada el sábado no genera otro mínimo de 8.

SQLite conserva cada DOMINGO y cada HE por separado, sus conceptos, cantidades,
estado y fuente JSON (regla, horario RH, entrada/salida, horas reales y reconocidas).
La migración v5 amplía los tipos conservando los identificadores e historial de
las incidencias existentes y sus conceptos relacionados.

## Base legal y conceptos

Se contrastaron los artículos 30–34, 36 y 48–50 del
[Código de Trabajo publicado por el Órgano Judicial](https://www.organojudicial.gob.pa/uploads/wp_repo/uploads/2016/11/c%C3%B3digo-detrabajo.pdf).
Los máximos ordinarios son 8/7.5/7 horas para jornadas diurna/mixta/nocturna.
Los recargos se segmentan por período y fecha real. El exceso de HE contempla
3 horas por jornada y 9 por semana de lunes a domingo, incluso si la exportación
comienza a mitad de semana. Un exceso se muestra como alerta y no como autorización
para exceder el límite. Si una semana homogénea excede su máximo ordinario,
la nómina se bloquea para revisar la planificación. Las semanas mixtas que
superen seis jornadas equivalentes también quedan retenidas para revisión RH.

Los identificadores de conceptos anteriores se conservan. Sus factores históricos
eran inconsistentes en algunos casos: el motor calcula el factor por tramo y lo
incluye en las hojas de novedades. La integración con otro sistema de planilla
debe respetar ese factor; no debe asumir que todo código 550 utiliza 1.50.
Por ejemplo, una prolongación nocturna sujeta al 75% se informa con factor 1.75;
si hay exceso, el factor adicional es multiplicativo, sin redondeo intermedio.
Las tablas históricas de códigos siguen en `panama_payroll.py`; el cálculo
vigente está exclusivamente en `planning.py`.

El calendario incluye feriados móviles y el 20 de diciembre según
[Ley 291 de 2022](https://www.gacetaoficial.gob.pa/storage/gacetas/2022/03/29507_B/90994.pdf).
El 4 de noviembre es ordinario en el sector privado, como aclara
[MITRADEL](https://www.mitradel.gob.pa/jornada-laboral-en-dias-nacionales-y-su-remuneracion-segun-el-codigo-de-trabajo/).
RH puede definir excepciones y días compensatorios desde **Calendario RH**.
Los ajustes históricos de condiciones especiales se conservan; la pantalla
de validaciones no permite introducir excepciones individuales.

No se calculan importes monetarios ni obligaciones de CSS, se modelan horas y
novedades para revisión de RH. Deben conciliarse convenio colectivo, descansos
compensatorios individuales, semanas con distintas clases de jornada, restricciones
de puestos peligrosos y reglas especiales aplicables antes de liquidar producción.
Los recargos ordinarios no se deben sumar íntegramente otra vez a una base ya pagada.

## Base SQLite

- `turnos`: catálogo RH con horarios, descansos y clasificación validada.
- `asignaciones`: clave `(empleado_id, fecha)` y copia histórica `turno_json`.
  La fecha es el día de inicio de la jornada. Editar el catálogo no altera esa copia.
  **Aplicar versión actual de RH** permite renovarla de forma explícita.
- `decisiones`: clave `(empleado_id, fecha)`, concepto, remuneración, aprobación HE,
  inclusión de tiempo anticipado, nota, usuario y fecha de modificación.
- `auditoria_planificacion`: historial de asignaciones, decisiones, turnos y ajustes.
- `validaciones_bono`: decisión mensual del coordinador, motivo, usuario y huella
  de los datos evaluados. Las decisiones anteriores quedan en la auditoría.
- `incidencias`: una fila por empleado, jornada y tipo, con cantidad detectada en
  segundos, código, decisión, motivo, usuario y fecha. Si deja de detectarse, se
  desactiva y se conserva el historial; no se elimina la incidencia.
- `incidencia_conceptos`: conceptos individuales de cada incidencia, sin fusionar
  los de distintos empleados, jornadas o tipos. Los cambios anteriores y los
  nuevos se conservan en la auditoría.
- `marcaciones`: conserva cada fecha/hora original; el motor las empareja antes
  de agruparlas. Una misma salida no se utiliza como entrada del día siguiente.
- `config.calendario`: excepciones RH a las fechas nacionales.

La migración v2 conserva los turnos y aprobaciones anteriores, copiando las
asignaciones que tengan turno. Los turnos heredados quedan **sin validar RH**:
no es posible deducir de los archivos originales cómo se tomaban sus descansos.
No se asignan semanas ni se corrigen horas históricas de forma automática.

Las exportaciones leen una instantánea consistente de SQLite. La pantalla de
asistencia, las aprobaciones, el bono y Excel utilizan el mismo motor.
El historial del cliente conserva sus campos de respuesta y utiliza el mismo
motor. El transporte v2 requiere el perfil privado del terminal y un ID estable
por evento; consultar el README de la raíz.

## Validación

Desde la raíz del proyecto:

```powershell
.venv/Scripts/python.exe Server/manage.py check
.venv/Scripts/python.exe Server/manage.py backup
```

Los respaldos incluyen todas las tablas nuevas y la auditoría.

## Limpieza de la distribución

Las 54 pruebas pasaron antes de retirar sus archivos por solicitud del usuario.
Los JSON/CSV anteriores se conservan en `backups/fuentes_migracion_originales.zip`,
verificado antes de eliminarlos del directorio activo. SQLite, sus respaldos y
la auditoría permanecen. La revisión posterior de integración sí incluye el
cliente y añade pruebas pequeñas en `tests`, sin bases ni capturas de prueba en
la distribución. Las dependencias de `.venv` son necesarias y se conservan.
