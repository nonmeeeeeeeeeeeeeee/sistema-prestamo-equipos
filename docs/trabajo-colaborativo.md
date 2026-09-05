# Trabajo colaborativo

Equipo de 2 personas. Repositorio público:
https://github.com/nonmeeeeeeeeeeeeeee/sistema-prestamo-equipos

## 1. Flujo de trabajo Git elegido y justificación

**GitHub Flow simplificado**: `main` siempre estable y desplegable, ramas cortas
por tarea, integración mediante Pull Request con revisión del compañero.

Justificación para este equipo y esta duración:

- **GitFlow** introduce `develop`, `release/*` y `hotfix/*`. Ese aparato existe
  para gestionar varias versiones en producción en paralelo. Aquí hay una sola
  entrega, así que solo agrega ceremonia y una rama de integración que nadie
  necesita.
- **Trunk Based** con commits directos a `main` elimina el PR, y el PR es
  justamente donde queda registrada la evidencia de revisión que el enunciado
  pide (tarea 7, pruebas cruzadas, y el criterio de entrega "Issues y Pull
  Requests del proyecto").
- **GitHub Flow** deja el PR como punto obligatorio de verificación entre pares
  sin ramas de larga vida. Con 2 personas trabajando sobre los mismos módulos,
  ramas cortas significan menos conflictos.

Regla práctica: una rama no debería vivir más de 2 o 3 días. Si la tarea es más
grande, se parte en varios issues.

## 2. Convención de ramas

`<tipo>/<descripcion-en-kebab-case>`

| Prefijo | Uso |
| --- | --- |
| `feat/` | Nueva funcionalidad de la aplicación |
| `test/` | Casos de prueba y pruebas cruzadas |
| `docs/` | Documentos de la entrega |
| `fix/` | Corrección de un defecto encontrado en pruebas cruzadas |
| `chore/` | CI, configuración, tooling |

Cada rama corresponde a **un** issue. El nombre de la rama está escrito al final
del issue correspondiente.

Las ramas se crean desde `main` actualizado:

```bash
git checkout main && git pull && git checkout -b feat/solicitudes
```

Las ramas de corrección de defectos se nombran con el número del issue:
`fix/23-devolucion-sin-entrega`.

Una vez fusionada, la rama se borra en GitHub.

## 3. Convención de commits

[Conventional Commits](https://www.conventionalcommits.org/):

```
<tipo>(<alcance>): <descripción en imperativo, minúscula, sin punto final>

[cuerpo opcional]

Refs #<número de issue>
```

Tipos: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`.

Ejemplos reales del proyecto:

```
feat(solicitudes): rechazar solapamiento de reservas sobre el mismo equipo
test(borde): agregar CP-08 devolución en el último día del plazo
fix(prestamos): impedir devolución de un préstamo nunca entregado
docs(estados): documentar transiciones prohibidas
```

Los commits intermedios pueden usar `Refs #N` en el cuerpo cuando sea útil para
mantener trazabilidad, pero el cierre formal del issue se realiza en el Pull
Request. La descripción del PR debe incluir `Closes #N`. Si se usa squash merge,
el commit final que queda en `main` debe conservar esa referencia.

## 4. Política de Pull Requests

1. El PR usa la plantilla de `.github/pull_request_template.md` y **siempre**
   enlaza su issue con `Closes #N` en la descripción.
2. El PR debe referenciar los IDs que toca: `RF-XX`, `RN-XX`, `CP-XX`, `DEF-XX`.
3. **Una aprobación del otro integrante es obligatoria.** Nadie fusiona su
   propio PR sin revisión, aunque el cambio parezca trivial. Esta revisión es
   una de las actividades de verificación documentadas en
   [verificacion-validacion.md](verificacion-validacion.md).
4. El workflow `Pruebas` (`.github/workflows/pruebas.yml`) debe estar en verde.
   Un `pytest` en rojo bloquea la fusión.
5. El revisor no aprueba solo leyendo el diff: descarga la rama y ejecuta las
   pruebas al menos una vez por PR de implementación.
6. Estrategia de fusión: **squash merge**, para que `main` tenga un commit por
   issue y el historial sea legible para el revisor del ramo.
7. La rama se borra tras fusionar.

Lo que el revisor mira, en orden:

- La regla de negocio implementada coincide con lo escrito en
  [reglas-negocio.md](reglas-negocio.md) y [estados-transiciones.md](estados-transiciones.md).
- Hay al menos una prueba que falla si se revierte el cambio.
- Los errores se manejan con excepciones de dominio, no con tracebacks crudos.
- No entran contraseñas, tokens ni el DSN de Sentry al repositorio.

## 5. Herramienta de organización

**GitHub Projects (tablero) + Issues + Milestones**, en el mismo repositorio.

Tablero utilizado:
[Workflow sistema-prestamo-equipos](https://github.com/users/nonmeeeeeeeeeeeeeee/projects/5).

Justificación frente a JIRA o Trello: el enunciado pide entregar "Issues y Pull
Requests del proyecto" como evidencia. Manteniendo el tablero dentro de GitHub,
cada tarjeta es un issue real, enlazado automáticamente a su rama, a su PR y a
los commits que la cierran. No hay que exportar capturas de una herramienta
externa ni mantener dos fuentes de verdad sincronizadas.

### Estructura del tablero

Columnas: `Backlog` -> `En progreso` -> `En revisión` -> `Hecho`.

Una tarjeta pasa a `En revisión` cuando su PR está abierto, y a `Hecho` solo
cuando el PR fue fusionado. Nadie tiene más de dos tarjetas en `En progreso`.

### Etiquetas

| Etiqueta | Significado |
| --- | --- |
| `area:analisis` | Requerimientos y reglas de negocio |
| `area:implementacion` | Código de la aplicación |
| `area:pruebas` | Casos de prueba y ejecución |
| `area:documentacion` | Documentos de la entrega |
| `area:infra` | CI, tooling, configuración |
| `tipo:defecto` | Defecto encontrado en pruebas cruzadas |
| `prueba-cruzada` | Revisión de la funcionalidad del compañero |
| `prioridad:alta` / `media` / `baja` | Orden de atención |

### Hitos

| Hito | Contenido |
| --- | --- |
| M1 - Análisis y diseño | Ambigüedades, reglas de negocio, máquina de estados, flujo de trabajo |
| M2 - Núcleo del sistema | Modelos, persistencia, autenticación, errores/logs, motor de reglas |
| M3 - Casos de uso y CLI | Solicitud, aprobación, entrega, devolución, consultas, menú, datos demo |
| M4 - Pruebas y pruebas cruzadas | 15+ casos ejecutados, defectos registrados y corregidos |
| M5 - Entrega final | V&V, trazabilidad, documento principal, IA, reflexiones, README |

M1 es bloqueante: la máquina de estados y las reglas de negocio son el contrato
que después se implementa en `src/prestamos/reglas.py` y se verifica en las
pruebas. No se empieza a codificar el motor de reglas antes de cerrar M1.

## 6. Reparto de trabajo

El criterio de reparto no es "mitad y mitad de los archivos", sino que **cada
integrante sea dueño de un conjunto de funcionalidades que el otro pueda probar
sin haberlas escrito**. Eso es lo que hace posible la tarea 7 (pruebas cruzadas)
del enunciado: si ambos escriben todo, no hay nada que revisar con mirada fresca.

### Por rebanada vertical, no por capa

El primer reparto que consideramos dividía por capa (uno los modelos y la
persistencia, otro las reglas y la observabilidad). Al dibujar el grafo de
dependencias en [dag-dependencias.md](dag-dependencias.md) quedó a la vista que
ese reparto produce **ocho traspasos sobre la cadena crítica**: cada uno es una
espera donde una persona termina y la otra recién ahí empieza.

El reparto por rebanada vertical baja esos traspasos a cuatro. Cada integrante es
dueño de una pregunta completa del dominio, con sus cimientos, su servicio y su
persistencia:

| | **Benjamin Olguín (@nonmeeeeeeeeeeeeeee)** - Identidad y solicitud | **Isaías Carte (@IsaiasACF)** - Ciclo de vida y visibilidad |
| --- | --- | --- |
| Pregunta que responde | quién existe, qué equipos hay, quién pide qué | qué le pasa al préstamo y cómo se consulta |
| Cimientos | #5 modelos, #6 persistencia, #7 auth | #8 errores/logs/Sentry, #9 motor de reglas |
| Funcionalidad | #10 usuarios y equipos, #11 solicitud/aprobación/rechazo | #12 entrega/devolución, #13 consultas, #14 CLI, #15 datos demo |
| Pruebas | #18 negativos, #19 combinados + escenario, #20 cruzadas | #16 funcionales, #17 borde, #21 cruzadas |
| Documentos | #23 trazabilidad, #28 README final | #24 estrategia de pruebas |

Diez issues cada uno. Los cimientos de cada rebanada son cadenas internas con un
solo dueño de punta a punta, así que no hay esperas dentro del bloque.

**Juntos:** #1 ambigüedades, #2 reglas de negocio, #3 máquina de estados, #4 este
documento, #22 actividades de V&V, #25 documento principal, #26 declaración de IA.
**Individual e intransferible:** #27, la reflexión de cada uno.

`#3` se hace en una sesión de a dos y no se asigna. Es el issue con mayor costo de
estar mal (todo el código de dominio y todas las pruebas lo leen) y el más barato
de discutir en voz alta frente a una tabla.

### Cómo se trabaja en paralelo sin esperarse

`#12` (entrega y devolución) no necesita el *código* de `#11` (solicitudes):
necesita el *contrato*. Una vez cerrada la máquina de estados, cualquiera de los
dos puede fabricar un `Prestamo` en estado `APROBADO` como fixture y construir
sobre él, sin esperar a que el compañero termine.

Eso es exactamente lo que compra el issue `#3`, y la razón por la que bloquea a
todo lo demás.

### Pruebas cruzadas

**Regla: cada caso de prueba lo escribe quien NO implementó lo que ese caso
ejercita.**

De ahí sale el reparto de la tabla: Isaías escribe los funcionales y los de
borde, porque esos casos caen sobre la rebanada de Benjamin (límite de préstamos
simultáneos, solapamiento de reservas, plazo máximo); Benjamin escribe los
negativos y el escenario completo, porque caen sobre la rebanada de Isaías
(devolver un préstamo nunca entregado, cancelar después de la entrega).

Con esa regla los 15 casos **son** pruebas cruzadas por construcción y no hay que
escribir dos baterías separadas.

Los casos se diseñan leyendo el requerimiento y las reglas de negocio, **no** el
código del compañero: si el caso se escribe mirando la implementación, solo
confirma lo que el código ya hace y deja de ser una prueba útil.

`#28` (README final) lo escribe Benjamin precisamente porque no hizo los datos demo:
seguir el README sin conocer el sistema por dentro es la prueba de que el README
sirve. Esa verificación en limpio se documenta como actividad de validación en
`#22`.

## 7. Evidencia de cambios originados por una revisión

Enlaces a PRs donde un comentario de revisión produjo un cambio real en el
código o en la documentación. Se completa a medida que avanza el proyecto.

| PR | Comentario de la revisión | Cambio que produjo |
| --- | --- | --- |
| _(pendiente)_ | | |
