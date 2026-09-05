# Trabajo colaborativo

Equipo de 2 personas. Repositorio público:
https://github.com/nonmeeeeeeeeeeeeeee/sistema-prestamo-equipos

## 1. Flujo de trabajo Git elegido y justificación

El equipo utiliza un **GitFlow simplificado**, adaptado a un proyecto académico de dos integrantes y una única entrega final.

Se mantienen dos ramas principales:

- `main`: versión estable y entregable del proyecto.
- `develop`: rama de integración donde se incorpora y verifica el trabajo realizado por ambos integrantes.

Las tareas se desarrollan en ramas cortas creadas desde `develop` y se integran nuevamente mediante Pull Requests.

El flujo general es:

```text
feat/*  ─────┐
fix/*   ─────┤
docs/*  ─────┼── PR + revisión + CI ──> develop ── PR de integración ──> main
test/*  ─────┤
chore/* ─────┘
```

### Justificación

Inicialmente se consideró un GitHub Flow simplificado con integración directa en `main`. Durante el trabajo paralelo del equipo se decidió incorporar `develop` como rama común de integración.

La decisión permite separar dos conceptos:

- `develop` contiene funcionalidades terminadas individualmente e integradas entre sí.
- `main` conserva una versión estable adecuada para una entrega o hito.

Esta separación permite que ambos integrantes trabajen simultáneamente sin incorporar cambios parciales directamente a la versión estable.

No se utiliza GitFlow completo porque el proyecto no necesita ramas `release/*` ni `hotfix/*`, destinadas principalmente a proyectos que mantienen múltiples versiones en producción.

Tampoco se utiliza Trunk Based Development, ya que los Pull Requests son una parte importante de la evidencia de revisión, verificación y trabajo colaborativo exigida por la tarea.

El Pull Request se mantiene como punto obligatorio de integración entre pares.

Regla práctica: una rama debería corresponder a una tarea concreta y mantenerse lo más corta posible. Si una tarea crece demasiado, debe dividirse en varios issues.

### Integración hacia `main`

El trabajo cotidiano no se integra directamente a `main`.

Cuando `develop` contiene una versión integrada y estable, se abre un Pull Request:

```text
develop -> main
```

Antes de integrarlo se verifica que las pruebas estén en verde y que la versión pueda considerarse estable.

De esta forma, `main` representa el estado entregable del sistema y `develop` representa el estado de integración del trabajo del equipo.

## 2. Convención de ramas

Formato:

```text
<tipo>/<descripcion-en-kebab-case>
```

| Prefijo | Uso |
| --- | --- |
| `feat/` | Nueva funcionalidad de la aplicación |
| `test/` | Casos de prueba y pruebas cruzadas |
| `docs/` | Documentos de la entrega |
| `fix/` | Corrección de un defecto |
| `chore/` | CI, configuración y tooling |

Cada rama corresponde a **un issue o una tarea claramente identificable**.

Cuando el issue ya tiene definida una rama, el nombre aparece al final de su descripción.

Las ramas de trabajo se crean desde `develop` actualizado:

```bash
git checkout develop
git pull
git checkout -b feat/solicitudes
```

Antes de comenzar una nueva tarea se debe actualizar `develop` para reducir conflictos de integración.

Las ramas de corrección de defectos pueden incorporar el número del issue:

```text
fix/<numero-issue>-<descripcion>
```

Una vez fusionada una rama, se elimina en GitHub cuando ya no es necesaria.

No se realizan cambios de funcionalidad directamente sobre `main`.

## 3. Convención de commits

Se utiliza [Conventional Commits](https://www.conventionalcommits.org/):

```text
<tipo>(<alcance>): <descripción en imperativo, minúscula, sin punto final>

[cuerpo opcional]

Refs #<número de issue>
```

Tipos utilizados:

- `feat`
- `fix`
- `test`
- `docs`
- `refactor`
- `chore`

Ejemplos:

```text
feat(solicitudes): rechazar solapamiento de reservas sobre el mismo equipo

Refs #11
```

```text
test(borde): agregar CP-08 devolución en el último día del plazo

Refs #17
```

```text
fix(prestamos): impedir devolución de un préstamo nunca entregado

Refs #<issue-defecto>
```

```text
docs(estados): completar contrato y transiciones

Refs #3
```

Los commits deben ser descriptivos y atribuibles al integrante que realizó el cambio.

Cuando un cambio necesita más de un commit, se conservan los commits intermedios siempre que representen unidades de trabajo comprensibles.

`Refs #N` se utiliza para relacionar los commits con el issue correspondiente.

La tarea considera la cantidad, calidad, trazabilidad y atribución de los commits como parte de la evidencia de trabajo. Por esta razón, el equipo **no utiliza squash merge como estrategia general**, ya que eliminaría del historial de la rama destino los commits individuales realizados durante el desarrollo.

## 4. Política de Pull Requests

Todo cambio realizado desde una rama de trabajo hacia `develop` se integra mediante Pull Request.

### Reglas

1. El PR utiliza la plantilla de `.github/pull_request_template.md`.

2. El PR debe estar relacionado con el issue correspondiente mediante `Refs #N` o mediante el enlace correspondiente de GitHub.

3. El PR debe referenciar los identificadores relacionados con el cambio cuando existan:

   - `RF-XX`
   - `RN-XX`
   - `CP-XX`
   - `DEF-XX`

4. La matriz de trazabilidad definitiva se completa mediante el issue #23. Mientras ese issue esté pendiente, los identificadores utilizados deben ser consistentes con los documentos de requerimientos, reglas de negocio y casos de prueba existentes.

5. El otro integrante debe revisar el Pull Request antes de su integración.

   La revisión habitual se registra mediante el checkbox:

   ```text
   [x] Revisado por el otro integrante
   ```

   No se exige utilizar obligatoriamente la función formal `Approve` de GitHub como mecanismo de registro interno del equipo.

6. Cuando una revisión detecta un problema o propone una modificación, el revisor deja un comentario en el Pull Request.

   El autor realiza posteriormente el cambio correspondiente y el comentario queda como evidencia de que la revisión produjo una modificación real.

7. El workflow `Pruebas` (`.github/workflows/pruebas.yml`) debe finalizar correctamente.

   Un fallo de `pytest` debe resolverse antes de fusionar el Pull Request.

8. En PRs de implementación, el revisor no se limita a leer el diff. También debe ejecutar las pruebas pertinentes al menos una vez cuando corresponda.

9. La estrategia habitual de integración es **merge commit**.

   Esto permite conservar los commits individuales del autor, su atribución y su relación con el proceso de desarrollo, además de dejar registrada explícitamente la integración realizada mediante Pull Request.

10. Después de integrar una rama de trabajo en `develop`, la rama puede eliminarse.

### Cierre de issues

Los Pull Requests de trabajo normal apuntan a `develop`.

Como `main` es la rama estable y predeterminada del repositorio, el cierre automático mediante palabras como `Closes #N` puede no aplicarse al integrar un PR en `develop`.

Por esta razón, el procedimiento del equipo es:

1. abrir el PR asociado al issue;
2. revisar el cambio;
3. verificar CI;
4. integrar el PR en `develop`;
5. cerrar el issue cuando se haya confirmado la integración;
6. mover su tarjeta a `Hecho`.

Esto evita marcar como terminado un trabajo cuyo Pull Request todavía no ha sido integrado.

### Aspectos que revisa el compañero

Dependiendo del tipo de cambio, se verifica:

- que la implementación corresponda con los requerimientos y reglas documentadas;
- que las transiciones respeten [estados-transiciones.md](estados-transiciones.md);
- que existan pruebas relacionadas cuando corresponda;
- que las entradas inválidas se manejen de forma controlada;
- que no aparezcan tracebacks crudos al usuario;
- que no se incorporen contraseñas, tokens, DSN de Sentry u otros secretos;
- que los identificadores RF, RN, CP y DEF se utilicen de forma consistente.

## 5. Herramienta de organización

El equipo utiliza **GitHub Projects + Issues + Milestones** dentro del mismo repositorio.

Tablero utilizado:

[Workflow sistema-prestamo-equipos](https://github.com/users/nonmeeeeeeeeeeeeeee/projects/5)

Se eligió GitHub Projects en lugar de mantener una herramienta externa como JIRA o Trello porque los Issues, ramas, Pull Requests y commits utilizados como evidencia ya se encuentran en GitHub.

Esto permite mantener la organización y la evidencia del proyecto en un mismo lugar.

### Estructura del tablero

Estados utilizados:

```text
Backlog -> En progreso -> En revisión -> Hecho
```

El significado de cada estado es:

- **Backlog:** issue identificado pero todavía no iniciado.
- **En progreso:** un integrante comenzó a trabajar activamente en el issue.
- **En revisión:** existe un Pull Request abierto con el trabajo realizado.
- **Hecho:** el Pull Request fue revisado e integrado correctamente en `develop` y el issue puede considerarse terminado.

Cuando un integrante comienza a trabajar en un issue, lo mueve desde `Backlog` a `En progreso`.

Cuando abre el Pull Request correspondiente, lo mueve a `En revisión`.

Solo después de integrar el PR correctamente en `develop` pasa a `Hecho`.

Nadie debería mantener más de dos tarjetas simultáneamente en `En progreso`.

### Etiquetas

| Etiqueta | Significado |
| --- | --- |
| `area:analisis` | Requerimientos y reglas de negocio |
| `area:implementacion` | Código de la aplicación |
| `area:pruebas` | Casos de prueba y ejecución |
| `area:documentacion` | Documentos de la entrega |
| `area:infra` | CI, tooling, configuración |
| `tipo:defecto` | Defecto encontrado durante las pruebas |
| `prueba-cruzada` | Revisión de funcionalidad implementada por el compañero |
| `prioridad:alta` / `media` / `baja` | Orden de atención |

### Hitos

| Hito | Contenido |
| --- | --- |
| M1 - Análisis y diseño | Ambigüedades, reglas de negocio, máquina de estados, flujo de trabajo |
| M2 - Núcleo del sistema | Modelos, persistencia, autenticación, errores/logs, motor de reglas |
| M3 - Casos de uso y CLI | Solicitud, aprobación, entrega, devolución, consultas, menú, datos demo |
| M4 - Pruebas y pruebas cruzadas | 15+ casos ejecutados, defectos registrados y corregidos |
| M5 - Entrega final | V&V, trazabilidad, documento principal, IA, reflexiones, README |

M1 es bloqueante porque la máquina de estados y las reglas de negocio funcionan como contrato para la implementación posterior.

La implementación del motor de reglas y las pruebas deben respetar estas definiciones.

## 6. Reparto de trabajo

El criterio de reparto no es dividir simplemente los archivos por la mitad, sino permitir que **cada integrante sea responsable principalmente de un conjunto de funcionalidades que el otro pueda revisar y probar**.

Esto permite cumplir con las pruebas cruzadas requeridas por la tarea.

### Por rebanada vertical, no por capa

Inicialmente se consideró dividir el trabajo por capas.

Al analizar las dependencias en [dag-dependencias.md](dag-dependencias.md), se observó que esa estrategia generaba múltiples puntos donde un integrante debía esperar el trabajo del otro.

Se optó por repartir el trabajo mediante rebanadas verticales, donde cada integrante se responsabiliza principalmente de una parte completa del dominio.

| | **Benjamin Olguín (@nonmeeeeeeeeeeeeeee)** - Identidad y solicitud | **Isaías Carte (@IsaiasACF)** - Ciclo de vida y visibilidad |
| --- | --- | --- |
| Pregunta que responde | quién existe, qué equipos hay, quién pide qué | qué le pasa al préstamo y cómo se consulta |
| Cimientos | #5 modelos, #6 persistencia, #7 auth | #8 errores/logs/Sentry, #9 motor de reglas |
| Funcionalidad | #10 usuarios y equipos, #11 solicitud/aprobación/rechazo | #12 entrega/devolución, #13 consultas, #14 CLI, #15 datos demo |
| Pruebas | #18 negativos, #19 combinados + escenario, #20 cruzadas | #16 funcionales, #17 borde, #21 cruzadas |
| Documentos | #23 trazabilidad, #28 README final | #24 estrategia de pruebas |

Los issues compartidos son:

- #1 ambigüedades;
- #2 reglas de negocio;
- #3 máquina de estados;
- #4 metodología de trabajo colaborativo;
- #22 actividades de verificación y validación;
- #25 documento principal;
- #26 declaración de uso de IA.

El issue #27 corresponde a las reflexiones individuales y debe ser desarrollado de forma independiente por cada integrante.

### Cómo se trabaja en paralelo

El trabajo se organiza utilizando como contrato común los requerimientos, reglas de negocio y máquina de estados.

Por ejemplo, #12 (entrega y devolución) no necesita esperar necesariamente la implementación completa de #11 (solicitudes), siempre que ambos respeten el contrato definido para los estados y transiciones.

Esto reduce bloqueos entre integrantes y permite desarrollar y probar partes del sistema en paralelo.

### Pruebas cruzadas

Como regla general, cada integrante diseña y ejecuta una parte de las pruebas sobre funcionalidades desarrolladas principalmente por su compañero.

Isaías desarrolla principalmente los casos funcionales y de borde asociados a la funcionalidad de Benjamin.

Benjamin desarrolla principalmente los casos negativos, combinados y el escenario asociado a la funcionalidad de Isaías.

Los casos deben diseñarse principalmente a partir de los requerimientos y reglas de negocio, evitando depender exclusivamente de la lectura del código del compañero.

Esto permite que las pruebas funcionen como una revisión independiente de la implementación.

Los defectos detectados durante estas pruebas deben registrarse como Issues incluyendo:

- pasos para reproducir;
- resultado esperado;
- resultado obtenido;
- severidad justificada;
- evidencia;
- referencia a la corrección;
- resultado de la reejecución.

`#28` (README final) es realizado por Benjamin porque no desarrolla los datos demo.

Seguir el README sin conocer internamente esa parte del sistema permite verificar que las instrucciones de instalación y ejecución realmente son suficientes para un revisor externo.

La evidencia de esa ejecución se documenta como parte de las actividades de validación del issue #22.

## 7. Evidencia de cambios originados por una revisión

La tarea solicita demostrar cambios que hayan sido originados por la revisión de otro integrante.

Para estos casos no basta únicamente con marcar el checkbox de revisión.

Cuando el revisor detecta un problema o propone una mejora:

1. deja un comentario en el Pull Request;
2. el autor analiza la observación;
3. si corresponde, realiza un nuevo commit con la corrección;
4. se reejecutan las pruebas correspondientes;
5. el comentario y el commit quedan enlazados como evidencia.

Los casos reales se registran en la siguiente tabla:

| PR | Comentario de la revisión | Cambio que produjo |
| --- | --- | --- |
| _(pendiente)_ | | |

Esta tabla se completa a medida que las revisiones entre ambos integrantes produzcan cambios reales en código, documentación o pruebas.