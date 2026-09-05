# Análisis del requerimiento

## 1. Ambigüedades, vacíos, riesgos y conflictos detectados

Cada ambigüedad tiene un ID estable para poder referenciarla desde reglas de
negocio, supuestos, matriz de trazabilidad, Issues y casos de prueba.

| ID | Texto ambiguo o incompleto del enunciado | Tipo | Por que es ambiguo | Riesgo si no se resuelve | Pregunta al cliente | Supuesto adoptado |
| --- | --- | --- | --- | --- | --- | --- |
| AMB-01 | "Datos obligatorios de usuarios" | Vacio | No define los datos en especifico | Usuarios incompletos, duplicados o imposibles de auditar/contactar ya que se tienen datos distintos. | Que datos minimos debe tener una persona autorizada? | Un usuario requiere ID unico, nombre, correo institucional, rol, estado activo/inactivo y contrasena. |
| AMB-02 | "Existen, al menos, dos tipos de usuario" | Ambiguedad | La frase "al menos" deja abierta la existencia de mas roles y no define permisos exactos. | Acciones administrativas podrian quedar disponibles para solicitantes o bloqueadas para encargados. | Que roles existen y que permisos tiene cada uno? | El sistema implementara solamente dos roles: solicitante y encargado. |
| AMB-03 | "Registrar y consultar equipos"  | Vacio | No indica los campos minimos de un equipo ni su identificador unico. | La disponibilidad podria calcularse mal si dos equipos tienen nombres parecidos. | Que atributos debe registrar cada equipo y cual sera su identificador unico? | Cada equipo tendra codigo unico, nombre, tipo, descripcion breve y estado operativo. |
| AMB-04 | "Consultar equipos" | Vacio | No define estados operativos del equipo, como mantencion o baja. | Un equipo no apto podria aparecer disponible y terminar prestado. | Que estados de equipo impiden solicitar o prestar un equipo? | Un equipo podra estar disponible, reservado, prestado, en mantencion o dado de baja. Solo disponible podra solicitarse. |
| AMB-05 | "Solicitar la reserva o prestamo de uno o mas equipos" | Vacio | No especifica cuantos equipos puede incluir una solicitud ni cuantos puede acumular una persona. | Un solicitante podria acaparar equipos y afectar a otros usuarios. | Cual es el maximo de equipos por solicitud y por persona? | Una solicitud podra incluir entre 1 y 3 equipos; una persona no podra tener mas de 3 equipos activos entre reservas aprobadas y prestamos vigentes. |
| AMB-06 | "Solicitar la reserva o prestamo" | Vacio | No se define el plazo maximo de reserva o prestamo. | Prestamos demasiado largos reducirian disponibilidad y harian dificil recuperar equipos. | Cual es la duracion maxima permitida para un prestamo? | La duracion maxima sera de 5 dias habiles . |
| AMB-07 | "Reserva"  | Vacio | No indica con cuanto tiempo de anticipacion se aceptan reservas futuras. | Se podrian bloquear equipos con demasiada anticipacion o rechazar reservas utiles. | Con cuantos dias de anticipacion se puede reservar? | Las reservas podran solicitarse desde el dia actual y hasta 20 dias laborales. |
| AMB-08 | "Aprobar o rechazar solicitudes" | Vacio | No define los criterios objetivos para aprobar o rechazar. | Se aprobarian solicitudes que violan reglas de disponibilidad, plazo o permisos. | Que condiciones debe revisar el encargado antes de aprobar? | Para aprobar se validara solicitante activo, equipo disponible, fechas validas, plazo maximo y limite de equipos activos. |
| AMB-09 | "Registrar entregas, devoluciones y cancelaciones"| Vacio | No existe una maquina de estados oficial para la solicitud/prestamo. | Podrian registrarse devoluciones sin entrega, entregas de solicitudes rechazadas o cancelaciones invalidas. | Cuales son los estados y transiciones permitidas? | Los estados seran solicitada, aprobada, rechazada, cancelada, entregada, devuelta y atrasada. |
| AMB-10 | "Solicitante: administra sus propias solicitudes" | Conflicto | No aclara si un solicitante puede cancelar despues de la aprobacion o despues de la entrega. | Cancelaciones tardias podrian ocultar prestamos reales o romper el control del inventario. | Hasta que momento puede cancelar una solicitud el solicitante? | El solicitante podra cancelar solicitudes solicitadas o aprobadas antes de la entrega. No podra cancelar prestamos entregados. |
| AMB-11 | "Consultar prestamos vigentes, futuros y atrasados" | Ambiguedad | No define criterios temporales para clasificar cada consulta. | Los reportes podrian mostrar prestamos en categorias incorrectas. | Como se clasifican prestamos vigentes, futuros y atrasados? | Futuro: aprobado con fecha de inicio posterior a hoy. Vigente: entregado y dentro del plazo. Atrasado: entregado con fecha de termino vencida. |
| AMB-12 | "Proteger el acceso mediante inicio de sesion" | Vacio | No especifica politica de autenticacion, contrasenas ni credenciales demo. | Se podrian publicar secretos reales o aceptar accesos inseguros sin control. | Que nivel de seguridad se espera para esta tarea? | Se usara autenticacion local basica con contrasenas. |
| AMB-13 | "Manejo de errores y entradas invalidas" | Vacio | No indica que errores deben detectarse ni como debe responder la aplicacion CLI. | Entradas invalidas podrian corromper datos o terminar la ejecucion abruptamente. | Que entradas invalidas deben controlarse obligatoriamente? | Se validaran campos obligatorios, formatos de fecha, rangos, roles, estados, duplicados e IDs inexistentes, mostrando mensajes claros. |
| AMB-14 | "Logs de eventos relevantes"| Vacio | No define que eventos son relevantes ni que datos no deben registrarse. | La auditoria podria ser insuficiente o filtrar informacion sensible. | Que eventos deben quedar auditados y que datos deben excluirse? | Se registraran login exitoso/fallido, solicitudes, aprobaciones, rechazos, entregas, devoluciones, cancelaciones y errores; no se registraran contrasenas. |

## 2. Preguntas al cliente

Las preguntas corresponden a la columna "Pregunta al cliente" de la tabla
anterior, presentadas como listado para facilitar su revisión.

1. ¿Qué datos mínimos debe tener una persona autorizada?
2. ¿Qué roles existen y qué permisos tiene cada uno?
3. ¿Qué atributos debe registrar cada equipo y cuál será su identificador único?
4. ¿Qué estados de equipo impiden solicitar o prestar un equipo?
5. ¿Cuál es el máximo de equipos por solicitud y por persona?
6. ¿Cuál es la duración máxima permitida para un préstamo?
7. ¿Con cuántos días de anticipación se puede reservar?
8. ¿Qué condiciones debe revisar el encargado antes de aprobar?
9. ¿Cuáles son los estados y transiciones permitidas?
10. ¿Hasta qué momento puede cancelar una solicitud el solicitante?
11. ¿Cómo se clasifican préstamos vigentes, futuros y atrasados?
12. ¿Qué nivel de seguridad se espera para esta tarea?
13. ¿Qué entradas inválidas deben controlarse obligatoriamente?
14. ¿Qué eventos deben quedar auditados y qué datos deben excluirse?

## 3. Requerimiento mejorado

El laboratorio universitario requiere una aplicación de línea de comando para
administrar el préstamo de equipos tecnológicos a estudiantes y profesores. El
sistema deberá mantener datos persistentes en archivos JSON, permitir el inicio
de sesión de usuarios autorizados y registrar eventos relevantes para auditoría.

El sistema tendrá solamente dos roles: solicitante y encargado. Los solicitantes
podrán consultar equipos disponibles, crear solicitudes de reserva o préstamo de
uno a tres equipos, consultar sus propias solicitudes y cancelarlas mientras
estén en estado solicitada o aprobada y aún no hayan sido entregadas. Los
encargados podrán administrar usuarios y equipos, revisar solicitudes,
aprobarlas o rechazarlas, registrar entregas, devoluciones y consultar préstamos
futuros, vigentes y atrasados.

Cada usuario deberá tener ID único, nombre, correo institucional, rol, estado
activo/inactivo y contraseña. Cada equipo deberá tener código único, nombre,
tipo, descripción breve y estado operativo. Un equipo solo podrá ser solicitado
si está disponible y no tiene reservas o préstamos que se solapen con el período
solicitado. Las solicitudes deberán indicar solicitante, lista de equipos, fecha
de inicio, fecha de término y motivo.

Una solicitud podrá pasar por los estados solicitada, aprobada, rechazada,
cancelada, entregada, devuelta y atrasada. La duración máxima de un préstamo
será de 5 días hábiles y las reservas futuras podrán realizarse desde el día
actual y hasta 20 días laborales hacia el futuro. Una persona no podrá tener más
de 3 equipos activos considerando reservas aprobadas y préstamos vigentes.

La aplicación deberá validar entradas obligatorias, formatos de fecha, rangos,
IDs inexistentes, roles, estados, duplicados y operaciones no permitidas. Ante
entradas inválidas deberá mostrar mensajes claros sin corromper los datos ni
terminar inesperadamente. El README deberá permitir instalar y ejecutar la
aplicación siguiendo solo sus instrucciones.

## 4. Requerimientos funcionales

IDs RF-XX. Deben coincidir con la matriz de trazabilidad, el código y los tests.

| ID | Requerimiento | Rol | Prioridad | Criterio de aceptación verificable |
| --- | --- | --- | --- | --- |
| RF-01 | Registrar usuarios autorizados con datos obligatorios y rol. | Encargado | Alta | Dado un usuario con ID, nombre, correo, rol, estado y contraseña válidos, el sistema lo persiste; si falta un dato obligatorio o el ID/correo ya existe, rechaza el registro. |
| RF-02 | Autenticar usuarios antes de permitir operaciones del sistema. | Solicitante / Encargado | Alta | Dadas credenciales válidas de un usuario activo, se inicia sesión; dadas credenciales inválidas o usuario inactivo, se rechaza el acceso sin mostrar contraseñas. |
| RF-03 | Registrar equipos con código único y estado operativo. | Encargado | Alta | Dado un equipo con código, nombre, tipo, descripción y estado válido, se guarda; si el código ya existe o falta un campo obligatorio, se rechaza. |
| RF-04 | Consultar equipos y su disponibilidad. | Solicitante / Encargado | Alta | Al consultar equipos, el sistema muestra equipos registrados y permite identificar si están disponibles para un período solicitado. |
| RF-05 | Crear solicitudes de reserva o préstamo de uno a tres equipos. | Solicitante | Alta | Dada una solicitud con solicitante activo, 1 a 3 equipos, fechas válidas y motivo, el sistema la crea en estado solicitada. |
| RF-06 | Validar plazo máximo y anticipación de solicitudes. | Sistema | Alta | Si la solicitud supera 5 días hábiles o empieza a más de 20 días laborales, el sistema la rechaza con mensaje claro. |
| RF-07 | Validar límite de equipos activos por solicitante. | Sistema | Alta | Si el solicitante supera 3 equipos activos al sumar reservas aprobadas y préstamos vigentes, el sistema rechaza la nueva solicitud o aprobación. |
| RF-08 | Aprobar o rechazar solicitudes aplicando reglas de disponibilidad. | Encargado | Alta | Un encargado puede aprobar una solicitud solicitada solo si cumple reglas; también puede rechazarla indicando motivo. |
| RF-09 | Registrar entrega de equipos aprobados. | Encargado | Alta | Una solicitud aprobada puede pasar a entregada; una solicitud rechazada, cancelada, devuelta o sin aprobar no puede entregarse. |
| RF-10 | Registrar devolución de préstamos entregados. | Encargado | Alta | Una solicitud entregada puede pasar a devuelta y liberar sus equipos; otro estado no puede devolverse. |
| RF-11 | Cancelar solicitudes antes de la entrega. | Solicitante / Encargado | Media | Una solicitud solicitada o aprobada puede cancelarse antes de la entrega; una solicitud entregada o devuelta no puede cancelarse. |
| RF-12 | Consultar préstamos futuros, vigentes y atrasados. | Encargado | Media | El sistema clasifica futuros, vigentes y atrasados según fecha actual, estado y fecha de término. |
| RF-13 | Registrar eventos relevantes en logs. | Sistema | Media | Login exitoso/fallido, creación, aprobación, rechazo, entrega, devolución, cancelación y errores quedan registrados sin incluir contraseñas. |
| RF-14 | Cargar datos de demostración. | Encargado / Revisor | Media | El comando de carga demo crea usuarios, equipos y datos suficientes para probar el flujo principal desde solicitud hasta devolución. |

## 5. Requerimientos no funcionales

| ID | Requerimiento | Cómo se verifica |
| --- | --- | --- |
| RNF-01 | La aplicación debe ejecutarse por línea de comando. | Siguiendo el README se ejecuta `python -m prestamos` y se accede al menú o subcomandos. |
| RNF-02 | La persistencia debe realizarse sin base de datos externa. | Los datos se guardan y leen desde archivos JSON del proyecto o ruta configurada. |
| RNF-03 | La instalación debe ser reproducible por el revisor. | En una carpeta limpia se siguen solo las instrucciones del README y la aplicación corre. |
| RNF-04 | El sistema no debe publicar secretos reales. | Revisión de repo, `.env.example`, logs y README confirma que no hay tokens, DSN reales ni contraseñas reales. |
| RNF-05 | Las reglas críticas deben estar cubiertas por pruebas automatizadas. | `pytest -v` ejecuta casos funcionales, borde, negativos y de escenario completo asociados a los RF/RN. |
