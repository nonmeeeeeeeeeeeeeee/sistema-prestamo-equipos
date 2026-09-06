"""Fabricas de los repositorios concretos del sistema.

Un unico lugar donde vive la terna (archivo, entidad, campo_id) de cada
coleccion. Antes esa terna estaba repetida en cada servicio y en `auth`, de modo
que renombrar `solicitudes.json` obligaba a buscar el literal por todo el
codigo; ahora se cambia aqui.

Por que un modulo aparte y no `repositorios/__init__.py`:

`json_repo.py` evita a proposito depender de `modelos`, y se apoya en el
`Protocol EntidadPersistible` para lograrlo. Poner estas fabricas en el
`__init__` del paquete anularia esa decision *en tiempo de importacion*: bastaria
`import prestamos.repositorios.json_repo` para arrastrar `modelos` detras, aunque
el codigo solo quisiera el repositorio generico. Con un modulo propio, solo paga
esa dependencia quien pide entidades concretas.

Ojo con el nombre del archivo de prestamos: la entidad se llama `Prestamo` pero
el archivo es `solicitudes.json`, porque una misma entidad cubre todo el ciclo de
vida desde SOLICITADA hasta DEVUELTA (ver el docstring de `modelos.Prestamo`).
Esa asimetria es justamente la que conviene tener escrita en un solo sitio.
"""

from __future__ import annotations

from pathlib import Path

from prestamos.modelos import Equipo, Prestamo, Usuario
from prestamos.repositorios.json_repo import RepositorioJson, directorio_datos

ARCHIVO_USUARIOS = "usuarios.json"
ARCHIVO_EQUIPOS = "equipos.json"
ARCHIVO_PRESTAMOS = "solicitudes.json"

CAMPO_ID_USUARIO = "id"
CAMPO_ID_EQUIPO = "codigo"
CAMPO_ID_PRESTAMO = "id"


def raiz_de_datos(datos_dir: str | Path | None = None) -> Path:
    """Directorio de los JSON: el indicado, o el de la variable de entorno.

    `datos_dir` explicito gana sobre `PRESTAMOS_DATOS_DIR` para que las pruebas
    construyan repositorios sobre `tmp_path` sin tocar el entorno del proceso.
    """
    return Path(datos_dir) if datos_dir is not None else directorio_datos()


def repositorio_usuarios(
    datos_dir: str | Path | None = None,
) -> RepositorioJson[Usuario]:
    return RepositorioJson(
        raiz_de_datos(datos_dir) / ARCHIVO_USUARIOS, Usuario, CAMPO_ID_USUARIO
    )


def repositorio_equipos(
    datos_dir: str | Path | None = None,
) -> RepositorioJson[Equipo]:
    return RepositorioJson(
        raiz_de_datos(datos_dir) / ARCHIVO_EQUIPOS, Equipo, CAMPO_ID_EQUIPO
    )


def repositorio_prestamos(
    datos_dir: str | Path | None = None,
) -> RepositorioJson[Prestamo]:
    return RepositorioJson(
        raiz_de_datos(datos_dir) / ARCHIVO_PRESTAMOS, Prestamo, CAMPO_ID_PRESTAMO
    )
