# Trabajo colaborativo

Equipo de 2 personas. Repositorio publico:
https://github.com/nonmeeeeeeeeeeeeeee/sistema-prestamo-equipos

## 1. Flujo de trabajo Git elegido y justificacion

**GitHub Flow simplificado**: `main` siempre estable y desplegable, ramas cortas
por tarea, integracion mediante Pull Request con revision del companero.

Justificacion para este equipo y esta duracion:

- **GitFlow** introduce `develop`, `release/*` y `hotfix/*`. Ese aparato existe
  para gestionar varias versiones en produccion en paralelo. Aqui hay una sola
  entrega, asi que solo agrega ceremonia y una rama de integracion que nadie
  necesita.
- **Trunk Based** con commits directos a `main` elimina el PR, y el PR es
  justamente donde queda registrada la evidencia de revision que el enunciado
  pide (tarea 7, pruebas cruzadas, y el criterio de entrega "Issues y Pull
  Requests del proyecto").
- **GitHub Flow** deja el PR como punto obligatorio de verificacion entre pares
  sin ramas de larga vida. Con 2 personas trabajando sobre los mismos modulos,
  ramas cortas significan menos conflictos.

Regla practica: una rama no deberia vivir mas de 2 o 3 dias. Si la tarea es mas
grande, se parte en varios issues.

## 2. Convencion de ramas

`<tipo>/<descripcion-en-kebab-case>`

| Prefijo | Uso |
| --- | --- |
| `feat/` | Nueva funcionalidad de la aplicacion |
| `test/` | Casos de prueba y pruebas cruzadas |
| `docs/` | Documentos de la entrega |
| `fix/` | Correccion de un defecto encontrado en pruebas cruzadas |
| `chore/` | CI, configuracion, tooling |

Cada rama corresponde a **un** issue. El nombre de la rama esta escrito al final
del issue correspondiente.

Las ramas se crean desde `main` actualizado:

```bash
git checkout main && git pull && git checkout -b feat/solicitudes
```

Las ramas de correccion de defectos se nombran con el numero del issue:
`fix/23-devolucion-sin-entrega`.

Una vez fusionada, la rama se borra en GitHub.

## 3. Convencion de commits

[Conventional Commits](https://www.conventionalcommits.org/):

```
<tipo>(<alcance>): <descripcion en imperativo, minuscula, sin punto final>

[cuerpo opcional]

Refs #<numero de issue>
```

Tipos: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`.

Ejemplos reales del proyecto:

```
feat(solicitudes): rechazar solapamiento de reservas sobre el mismo equipo
test(borde): agregar CP-08 devolucion en el ultimo dia del plazo
fix(prestamos): impedir devolucion de un prestamo nunca entregado
docs(estados): documentar transiciones prohibidas
```

El commit que cierra un issue usa `Closes #N` en el cuerpo.

## 4. Politica de Pull Requests

1. El PR usa la plantilla de `.github/pull_request_template.md` y **siempre**
   enlaza su issue con `Closes #N`.
2. El PR debe referenciar los IDs que toca: `RF-XX`, `RN-XX`, `CP-XX`, `DEF-XX`.
3. **Una aprobacion del otro integrante es obligatoria.** Nadie fusiona su
   propio PR sin revision, aunque el cambio parezca trivial. Esta revision es
   una de las actividades de verificacion documentadas en
   [verificacion-validacion.md](verificacion-validacion.md).
4. El workflow `Pruebas` (`.github/workflows/pruebas.yml`) debe estar en verde.
   Un `pytest` en rojo bloquea la fusion.
5. El revisor no aprueba solo leyendo el diff: descarga la rama y ejecuta las
   pruebas al menos una vez por PR de implementacion.
6. Estrategia de fusion: **squash merge**, para que `main` tenga un commit por
   issue y el historial sea legible para el revisor del ramo.
7. La rama se borra tras fusionar.

Lo que el revisor mira, en orden:

- La regla de negocio implementada coincide con lo escrito en
  [reglas-negocio.md](reglas-negocio.md) y [estados-transiciones.md](estados-transiciones.md).
- Hay al menos una prueba que falla si se revierte el cambio.
- Los errores se manejan con excepciones de dominio, no con tracebacks crudos.
- No entran contrasenas, tokens ni el DSN de Sentry al repositorio.

## 5. Herramienta de organizacion

**GitHub Projects (tablero) + Issues + Milestones**, en el mismo repositorio.

Justificacion frente a JIRA o Trello: el enunciado pide entregar "Issues y Pull
Requests del proyecto" como evidencia. Manteniendo el tablero dentro de GitHub,
cada tarjeta es un issue real, enlazado automaticamente a su rama, a su PR y a
los commits que la cierran. No hay que exportar capturas de una herramienta
externa ni mantener dos fuentes de verdad sincronizadas.

### Estructura del tablero

Columnas: `Backlog` -> `En progreso` -> `En revision` -> `Hecho`.

Una tarjeta pasa a `En revision` cuando su PR esta abierto, y a `Hecho` solo
cuando el PR fue fusionado. Nadie tiene mas de dos tarjetas en `En progreso`.

### Etiquetas

| Etiqueta | Significado |
| --- | --- |
| `area:analisis` | Requerimientos y reglas de negocio |
| `area:implementacion` | Codigo de la aplicacion |
| `area:pruebas` | Casos de prueba y ejecucion |
| `area:documentacion` | Documentos de la entrega |
| `area:infra` | CI, tooling, configuracion |
| `tipo:defecto` | Defecto encontrado en pruebas cruzadas |
| `prueba-cruzada` | Revision de la funcionalidad del companero |
| `prioridad:alta` / `media` / `baja` | Orden de atencion |

### Hitos

| Hito | Contenido |
| --- | --- |
| M1 - Analisis y diseno | Ambiguedades, reglas de negocio, maquina de estados, flujo de trabajo |
| M2 - Nucleo del sistema | Modelos, persistencia, autenticacion, errores/logs, motor de reglas |
| M3 - Casos de uso y CLI | Solicitud, aprobacion, entrega, devolucion, consultas, menu, datos demo |
| M4 - Pruebas y pruebas cruzadas | 15+ casos ejecutados, defectos registrados y corregidos |
| M5 - Entrega final | V&V, trazabilidad, documento principal, IA, reflexiones, README |

M1 es bloqueante: la maquina de estados y las reglas de negocio son el contrato
que despues se implementa en `src/prestamos/reglas.py` y se verifica en las
pruebas. No se empieza a codificar el motor de reglas antes de cerrar M1.

## 6. Reparto de trabajo

El criterio de reparto no es "mitad y mitad de los archivos", sino que **cada
integrante sea dueno de un conjunto de funcionalidades que el otro pueda probar
sin haberlas escrito**. Eso es lo que hace posible la tarea 7 (pruebas cruzadas)
del enunciado: si ambos escriben todo, no hay nada que revisar con mirada fresca.

| Integrante | Responsabilidades |
| --- | --- |
| _(Integrante 1)_ | Analisis de ambiguedades y requerimiento mejorado; modelos de dominio; persistencia JSON; solicitud, aprobacion y rechazo; consultas; casos funcionales y de borde; matriz de trazabilidad |
| _(Integrante 2)_ | Reglas de negocio y maquina de estados; autenticacion y roles; errores, logs y Sentry; motor de reglas; entrega, devolucion y cancelacion; CLI y datos demo; casos negativos, combinados y escenario completo; estrategia de pruebas |

Compartido: documento principal, declaracion de uso de IA, README final.
Individual e intransferible: la reflexion de cada uno.

**Pruebas cruzadas.** El integrante 1 prueba lo que implemento el 2 (issue de
pruebas cruzadas correspondiente) y viceversa. Los casos se disenan leyendo el
requerimiento y las reglas de negocio, **no** el codigo del companero: si el caso
se escribe mirando la implementacion, solo confirma lo que el codigo ya hace y
deja de ser una prueba util.

## 7. Evidencia de cambios originados por una revision

Enlaces a PRs donde un comentario de revision produjo un cambio real en el
codigo o en la documentacion. Se completa a medida que avanza el proyecto.

| PR | Comentario de la revision | Cambio que produjo |
| --- | --- | --- |
| _(pendiente)_ | | |
