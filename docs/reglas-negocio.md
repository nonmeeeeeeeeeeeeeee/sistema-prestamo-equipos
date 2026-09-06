# Reglas de negocio, alcance y exclusiones

## 1. Reglas de negocio

IDs RN-XX. Toda regla debe ser implementable en código y verificable mediante al
menos un caso de prueba.

| ID | Regla | Condición de disparo | Efecto esperado | Origen (AMB/RF) | Implementación prevista | Prueba prevista |
| --- | --- | --- | --- | --- | --- | --- |
| RN-01 | Solo existen dos roles operativos: solicitante y encargado. | Al registrar, autenticar o autorizar una operación. | Si el rol no es solicitante o encargado, la operación se rechaza. | AMB-02 / RF-01 / RF-02 | `src/prestamos/auth.py`, `src/prestamos/reglas.py` | CP-01, CP-02 |
| RN-02 | Solo usuarios activos pueden iniciar sesión y operar en el sistema. | Al iniciar sesión o ejecutar una acción autenticada. | Usuarios inactivos o inexistentes no pueden acceder ni crear operaciones. | AMB-01 / AMB-12 / RF-02 | `src/prestamos/auth.py` | CP-02, CP-03 |
| RN-03 | Todo usuario debe tener ID único, nombre, correo institucional, rol, estado y contraseña. | Al registrar o actualizar usuarios. | Si falta un campo obligatorio o el ID/correo ya existe, el registro se rechaza. | AMB-01 / RF-01 | `src/prestamos/servicios/usuarios.py` | CP-01, CP-04 |
| RN-04 | Todo equipo debe tener código único, nombre, tipo, descripción breve y estado operativo. | Al registrar o actualizar equipos. | Si falta un campo obligatorio o el código ya existe, el registro se rechaza. | AMB-03 / RF-03 | `src/prestamos/servicios/equipos.py` | CP-05, CP-06 |
| RN-05 | Solo equipos disponibles pueden ser solicitados o prestados. | Al crear o aprobar una solicitud. | Equipos en mantención, dados de baja, reservados o prestados no pueden agregarse a una nueva solicitud disponible para el mismo período. | AMB-04 / RF-04 / RF-05 / RF-08 | `src/prestamos/reglas.py`, `src/prestamos/servicios/solicitudes.py` | CP-07, CP-08 |
| RN-06 | Una solicitud debe incluir entre 1 y 3 equipos. | Al crear una solicitud. | Solicitudes sin equipos o con más de 3 equipos se rechazan. | AMB-05 / RF-05 | `src/prestamos/modelos.py` (invariante estructural), `src/prestamos/servicios/solicitudes.py` | CP-09, CP-10 |
| RN-07 | Un solicitante no puede tener más de 3 equipos activos al mismo tiempo. | Al crear o aprobar una solicitud. | Si al sumar reservas aprobadas y préstamos vigentes se supera el límite, la operación se rechaza. | AMB-05 / RF-07 | `src/prestamos/reglas.py` | CP-11, CP-12 |
| RN-08 | La duración máxima de un préstamo es de 5 días hábiles. | Al crear o aprobar una solicitud con fecha de inicio y término. | Si el período solicitado supera 5 días hábiles, la solicitud se rechaza. | AMB-06 / RF-06 | `src/prestamos/reglas.py` | CP-13, CP-14 |
| RN-09 | Las reservas futuras solo pueden solicitarse desde el día actual y hasta 20 días laborales hacia el futuro. | Al crear una solicitud con fecha de inicio futura. | Si la fecha de inicio está en el pasado o excede 20 días laborales, la solicitud se rechaza. | AMB-07 / RF-06 | `src/prestamos/reglas.py` | CP-15, CP-16 |
| RN-10 | No se puede aprobar una solicitud si existe solapamiento de fechas con otra reserva aprobada, préstamo entregado o préstamo atrasado del mismo equipo. | Al aprobar una solicitud o consultar disponibilidad. | El sistema considera el equipo no disponible para el período solicitado. | AMB-08 / RF-04 / RF-08 | `src/prestamos/reglas.py`, `src/prestamos/servicios/prestamos.py` | CP-17, CP-18 |
| RN-11 | Solo el encargado puede aprobar o rechazar solicitudes. | Al intentar aprobar o rechazar una solicitud. | Si el usuario no tiene rol encargado, la operación se rechaza. | AMB-02 / AMB-08 / RF-08 | `src/prestamos/auth.py`, `src/prestamos/servicios/solicitudes.py` | CP-19, CP-20 |
| RN-12 | Una solicitud solo puede aprobarse o rechazarse si está en estado solicitada. | Al aprobar o rechazar solicitudes. | Solicitudes aprobadas, rechazadas, canceladas, entregadas, devueltas o atrasadas no pueden aprobarse/rechazarse nuevamente. | AMB-09 / RF-08 | `src/prestamos/reglas.py` | CP-21, CP-22 |
| RN-13 | La entrega solo puede registrarse sobre solicitudes aprobadas. | Al registrar entrega. | La solicitud pasa a estado entregada; si no estaba aprobada, la operación se rechaza. | AMB-09 / RF-09 | `src/prestamos/servicios/prestamos.py` | CP-23, CP-24 |
| RN-14 | La devolución solo puede registrarse sobre préstamos entregados o atrasados. | Al registrar devolución. | La solicitud pasa a estado devuelta y los equipos quedan liberados para nuevas solicitudes. | AMB-09 / RF-10 | `src/prestamos/servicios/prestamos.py` | CP-25, CP-26 |
| RN-15 | Una solicitud puede cancelarse solo antes de la entrega. | Al cancelar una solicitud. | Solicitudes solicitadas o aprobadas pasan a cancelada; préstamos entregados, atrasados o devueltos no pueden cancelarse. | AMB-10 / RF-11 | `src/prestamos/servicios/solicitudes.py` | CP-27, CP-28 |
| RN-16 | Los préstamos se clasifican como futuros, vigentes o atrasados según estado y fecha actual. | Al consultar préstamos. | Futuro: aprobado con fecha de inicio posterior a hoy. Vigente: entregado y dentro del plazo. Atrasado: entregado con fecha de término vencida. | AMB-11 / RF-12 | `src/prestamos/servicios/prestamos.py` | CP-29, CP-30 |
| RN-17 | El sistema debe validar entradas inválidas antes de persistir cambios. | Al recibir datos desde CLI o servicios. | Campos vacíos, fechas inválidas, IDs inexistentes, roles inválidos, estados inválidos y duplicados se rechazan con mensaje claro. | AMB-13 / RF-01 / RF-03 / RF-05 | `src/prestamos/cli.py`, `src/prestamos/reglas.py` | CP-31, CP-32 |
| RN-18 | Los eventos relevantes se registran en logs sin incluir contraseñas. | Al iniciar sesión, crear solicitudes, aprobar, rechazar, entregar, devolver, cancelar o detectar errores. | Se registra el evento y contexto no sensible; las contraseñas y secretos no se escriben en logs. | AMB-14 / RF-13 | `src/prestamos/logging_conf.py`, `src/prestamos/observabilidad.py` | CP-33, CP-34 |
| RN-19 | El Solicitante solo puede consultar préstamos propios y el Encargado puede consultar todos, con filtros por usuario o equipo. | Al consultar préstamos futuros, vigentes o atrasados. | Si un solicitante intenta consultar préstamos de otro usuario, la operación se rechaza; el encargado puede consultar todos los préstamos o aplicar filtros por usuario/equipo. | AMB-02 / AMB-11 / RF-12 | `src/prestamos/servicios/prestamos.py` | CP-29, CP-30 |

## 2. Alcance

El sistema sí contempla:

- Aplicación de línea de comando para gestionar préstamos de equipos de
  laboratorio.
- Persistencia de usuarios, equipos, solicitudes y préstamos mediante archivos
  JSON.
- Inicio de sesión básico para usuarios autorizados.
- Dos roles operativos: solicitante y encargado.
- Registro y consulta de usuarios autorizados.
- Registro y consulta de equipos.
- Creación de solicitudes de reserva o préstamo.
- Aprobación y rechazo de solicitudes por parte del encargado.
- Registro de entregas, devoluciones y cancelaciones.
- Consulta de préstamos futuros, vigentes y atrasados con visibilidad según rol.
- Validación de reglas críticas antes de persistir cambios.
- Logs de eventos relevantes y errores sin registrar contraseñas.
- Datos de demostración para que el revisor pueda ejecutar el flujo principal.

## 3. Exclusiones

El sistema no contempla:

- Interfaz web o móvil, porque el enunciado indica que basta una aplicación de
  línea de comando.
- Base de datos externa, porque la persistencia en archivos es suficiente para
  el alcance de la tarea.
- Integración real con correo, WhatsApp o calendarios externos, porque el foco
  está en reemplazar el control manual por reglas verificables, no en
  automatizar comunicaciones.
- Autenticación institucional, OAuth, recuperación de contraseña o doble factor,
  porque se implementará autenticación local básica para datos de demostración.
- Gestión de multas, sanciones o cobros por atraso, porque el enunciado solo
  exige detectar y consultar préstamos atrasados.
- Reservas recurrentes o renovaciones automáticas, porque no fueron solicitadas
  y aumentarían la complejidad de disponibilidad.
- Cálculo de feriados institucionales o nacionales, porque la regla de días
  hábiles/laborales se interpretará como lunes a viernes.
- Inventario físico avanzado, como ubicación exacta, accesorios por equipo o
  historial de mantenciones, porque el alcance se limita a disponibilidad y
  préstamo.
- Registro de contraseñas reales, tokens o secretos en el repositorio, logs o
  documentación pública.

## 4. Supuestos documentados

| ID | Supuesto | Justificación | Riesgo si es incorrecto |
| --- | --- | --- | --- |
| SUP-01 | Un usuario requiere ID único, nombre, correo institucional, rol, estado activo/inactivo y contraseña. | Resuelve AMB-01 y permite identificar, autenticar y auditar usuarios. | Si el cliente requiere otros datos, el modelo de usuario deberá ajustarse. |
| SUP-02 | El sistema implementará solamente dos roles: solicitante y encargado. | Resuelve AMB-02 y simplifica permisos para un equipo pequeño y una tarea corta. | Si existen más roles, habría que ampliar autorización y pruebas. |
| SUP-03 | Cada equipo tendrá código único, nombre, tipo, descripción breve y estado operativo. | Resuelve AMB-03 y evita confundir equipos similares. | Si se requiere inventario más detallado, podrían faltar campos. |
| SUP-04 | Solo equipos disponibles pueden solicitarse; mantención, baja, reservado o prestado impiden disponibilidad. | Resuelve AMB-04 y evita prestar equipos no aptos. | Si el cliente permite excepciones, algunas solicitudes válidas serían rechazadas. |
| SUP-05 | Una solicitud puede incluir entre 1 y 3 equipos. | Resuelve AMB-05 y evita solicitudes vacías o acaparamiento. | Si el laboratorio permite más equipos, el límite sería demasiado restrictivo. |
| SUP-06 | Una persona no puede tener más de 3 equipos activos entre reservas aprobadas y préstamos vigentes. | Resuelve AMB-05 y protege disponibilidad para otros usuarios. | Si el límite real es distinto, se aprobarían o rechazarían solicitudes incorrectamente. |
| SUP-07 | La duración máxima de un préstamo es de 5 días hábiles. | Resuelve AMB-06 y acota el tiempo de uso. | Si el laboratorio requiere préstamos más largos, habría que ajustar reglas y pruebas. |
| SUP-08 | Las reservas pueden solicitarse desde el día actual y hasta 20 días laborales hacia el futuro. | Resuelve AMB-07 y evita bloqueos excesivamente anticipados. | Si se necesita más anticipación, el sistema limitaría reservas legítimas. |
| SUP-09 | Para aprobar se valida solicitante activo, equipo disponible, fechas válidas, plazo máximo y límite de equipos activos. | Resuelve AMB-08 y define criterios objetivos para el encargado. | Si el cliente usa criterios adicionales, el flujo de aprobación quedaría incompleto. |
| SUP-10 | Los estados de solicitud/préstamo serán solicitada, aprobada, rechazada, cancelada, entregada, devuelta y atrasada. | Resuelve AMB-09 y habilita una máquina de estados verificable. | Si faltan estados, algunas situaciones reales no se representarían bien. |
| SUP-11 | El solicitante puede cancelar solicitudes solicitadas o aprobadas antes de la entrega, pero no préstamos entregados. | Resuelve AMB-10 y evita cancelar préstamos físicos ya retirados. | Si el laboratorio permite cancelaciones tardías, habría que modelarlas como otro flujo. |
| SUP-12 | Futuro significa aprobado con fecha de inicio posterior a hoy; vigente significa entregado dentro del plazo; atrasado significa entregado con fecha de término vencida; la visibilidad de esas consultas depende del rol. | Resuelve AMB-11 y RN-19 al hacer verificables las consultas y sus permisos. | Si el cliente clasifica distinto o requiere otros permisos, los reportes podrían ser confusos o demasiado restrictivos. |
| SUP-13 | La autenticación será local y básica, con contraseñas de datos de demostración. | Resuelve AMB-12 y evita depender de sistemas externos. | Si se exige autenticación institucional, habría que cambiar el diseño. |
| SUP-14 | Se validarán campos obligatorios, fechas, rangos, roles, estados, duplicados e IDs inexistentes antes de persistir. | Resuelve AMB-13 y reduce corrupción de datos. | Si se omite una validación crítica, podrían guardarse datos inconsistentes. |
| SUP-15 | Se registrarán eventos de login, solicitudes, aprobaciones, rechazos, entregas, devoluciones, cancelaciones y errores, sin contraseñas. | Resuelve AMB-14 y permite auditoría básica sin exponer secretos. | Si el cliente requiere auditoría más detallada, los logs podrían ser insuficientes. |
