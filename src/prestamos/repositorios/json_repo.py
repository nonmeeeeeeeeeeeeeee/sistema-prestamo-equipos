"""Lectura/escritura de los archivos JSON en datos/.

Escritura atomica (archivo temporal + reemplazo) para no corromper los datos
si la aplicacion se interrumpe.

Este modulo es la frontera con el disco. Expone un unico repositorio generico,
`RepositorioJson`, que se parametriza con la entidad que guarda: no conoce
usuarios, equipos ni prestamos, solo pide que la entidad sepa convertirse
hacia/desde diccionario (`a_dict` / `desde_dict`, definidos en
``prestamos.modelos``) y cual de sus campos actua como identificador.

Reparto de responsabilidades:

- Aqui vive la *integridad del archivo*: que exista, que sea una lista JSON
  valida y que nunca quede a medio escribir.
- La *validez de cada registro* la decide el modelo, en ``desde_dict``; su
  ``ErrorValidacion`` se propaga tal cual, ya trae ``regla`` y ``detalles``.
- Las *reglas de negocio* (correos duplicados, transiciones permitidas, limites
  por persona) viven en ``prestamos.reglas`` y en los servicios. El repositorio
  guarda lo que le den.

Limitacion conocida: no hay bloqueo de archivos. Es una CLI monousuario y
``os.replace`` garantiza que nadie lea un archivo a medio escribir, pero si dos
procesos guardan la misma coleccion a la vez, el ultimo gana.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Generic, Protocol, TypeVar

from prestamos.errores import ErrorPersistencia, RecursoNoEncontrado

DIRECTORIO_DATOS_DEFAULT = Path("datos")


def directorio_datos() -> Path:
    """Directorio raiz de los archivos JSON de ejecucion.

    Mismo patron que ``prestamos.logging_conf``: variable de entorno con un
    default por constante. Las pruebas no la necesitan, construyen el
    repositorio con una ruta de ``tmp_path``.
    """
    return Path(os.getenv("PRESTAMOS_DATOS_DIR", DIRECTORIO_DATOS_DEFAULT))


class EntidadPersistible(Protocol):
    """Contrato minimo que el repositorio le exige a una entidad.

    Lo cumplen ``Usuario``, ``Equipo`` y ``Prestamo`` sin heredar de nada: el
    Protocol mantiene ``repositorios`` desacoplado de ``modelos``, y permite
    probar el repositorio con una entidad falsa.
    """

    def a_dict(self) -> dict[str, Any]: ...

    @classmethod
    def desde_dict(cls, datos: Any) -> Any: ...


T = TypeVar("T", bound=EntidadPersistible)


class RepositorioJson(Generic[T]):
    """Coleccion de entidades respaldada por un unico archivo JSON.

    Una instancia por archivo::

        repo = RepositorioJson(directorio_datos() / "usuarios.json", Usuario, "id")
        repo = RepositorioJson(directorio_datos() / "equipos.json", Equipo, "codigo")

    El archivo guarda siempre una lista de objetos en la raiz.
    """

    def __init__(self, ruta: str | Path, tipo: type[T], campo_id: str = "id") -> None:
        self.ruta = Path(ruta)
        self.tipo = tipo
        self.campo_id = campo_id

    # ------------------------------------------------------------------ API

    def listar(self) -> list[T]:
        """Todas las entidades, en el orden en que estan en el archivo.

        Un archivo inexistente es una coleccion vacia, no un error: asi el
        primer arranque del sistema funciona sin haber corrido ``init-demo``.
        """
        return [self._construir(registro) for registro in self._leer_crudo()]

    def buscar(self, identificador: str) -> T | None:
        """La entidad con ese id, o ``None`` si no esta.

        Es la version no excepcional de `obtener`, pensada para los chequeos de
        existencia de los servicios (por ejemplo, rechazar un alta duplicada)
        sin usar excepciones como control de flujo.
        """
        for entidad in self.listar():
            if self._id_de(entidad) == identificador:
                return entidad
        return None

    def obtener(self, identificador: str) -> T:
        """La entidad con ese id; levanta `RecursoNoEncontrado` si no existe."""
        entidad = self.buscar(identificador)
        if entidad is None:
            raise self._no_encontrado(identificador)
        return entidad

    def guardar(self, entidad: T) -> T:
        """Inserta la entidad, o reemplaza la que tenga el mismo id.

        El reemplazo ocurre *en la posicion actual*, no borrando y agregando al
        final: asi el orden del archivo se mantiene estable entre ejecuciones y
        los diffs de los datos versionados siguen siendo legibles.
        """
        identificador = self._id_de(entidad)
        entidades = self.listar()
        for indice, existente in enumerate(entidades):
            if self._id_de(existente) == identificador:
                entidades[indice] = entidad
                break
        else:
            entidades.append(entidad)
        self._escribir_atomico(entidades)
        return entidad

    def eliminar(self, identificador: str) -> None:
        """Borra la entidad con ese id; levanta `RecursoNoEncontrado` si no esta.

        Borrar algo inexistente es un error del llamador, no una operacion
        exitosa sin efecto.
        """
        entidades = self.listar()
        restantes = [e for e in entidades if self._id_de(e) != identificador]
        if len(restantes) == len(entidades):
            raise self._no_encontrado(identificador)
        self._escribir_atomico(restantes)

    # -------------------------------------------------------------- Interno

    def _id_de(self, entidad: T) -> Any:
        return getattr(entidad, self.campo_id)

    def _no_encontrado(self, identificador: str) -> RecursoNoEncontrado:
        return RecursoNoEncontrado(
            f"No existe un registro con {self.campo_id} '{identificador}'.",
            detalles={
                "coleccion": self.ruta.name,
                self.campo_id: identificador,
            },
        )

    def _construir(self, registro: Any) -> T:
        """Delega la validacion del registro en el modelo.

        `desde_dict` levanta `ErrorValidacion` con su `regla` correspondiente;
        no se envuelve para no perder esa trazabilidad.
        """
        return self.tipo.desde_dict(registro)

    def _leer_crudo(self) -> list[Any]:
        """Contenido del archivo como lista de registros sin validar."""
        if not self.ruta.exists():
            return []
        try:
            contenido = self.ruta.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise self._error_archivo("No se pudo decodificar", exc) from exc
        except OSError as exc:
            raise self._error_archivo("No se pudo leer", exc) from exc

        try:
            datos = json.loads(contenido)
        except json.JSONDecodeError as exc:
            raise ErrorPersistencia(
                f"El archivo de datos '{self.ruta.name}' no contiene JSON valido.",
                detalles={
                    "archivo": str(self.ruta),
                    "linea": exc.lineno,
                    "columna": exc.colno,
                },
            ) from exc

        if not isinstance(datos, list):
            raise ErrorPersistencia(
                f"El archivo de datos '{self.ruta.name}' deberia contener una lista.",
                detalles={
                    "archivo": str(self.ruta),
                    "tipo_encontrado": type(datos).__name__,
                },
            )
        return datos

    def _escribir_atomico(self, entidades: list[T]) -> None:
        r"""Reescribe el archivo completo sin dejarlo nunca a medio escribir.

        No existe el append atomico: el archivo se regenera entero en un
        temporal del *mismo directorio* (un rename entre volumenes no es
        atomico, y en Windows falla) y recien entonces se reemplaza el destino.

        `os.replace` y no `os.rename`: en Windows `rename` falla si el destino
        ya existe, que es el caso a partir del segundo guardado.

        `newline="\n"` explicito para que Python en Windows no traduzca a CRLF
        y los JSON versionados de `datos/demo/` no cambien enteros segun quien
        los guarde.
        """
        registros = [entidad.a_dict() for entidad in entidades]
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporal = tempfile.mkstemp(
                dir=self.ruta.parent,
                prefix=f".{self.ruta.name}.",
                suffix=".tmp",
            )
        except OSError as exc:
            raise self._error_archivo("No se pudo preparar", exc) from exc

        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                json.dump(registros, archivo, ensure_ascii=False, indent=2)
                archivo.write("\n")
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, self.ruta)
        except OSError as exc:
            raise self._error_archivo("No se pudo escribir", exc) from exc
        finally:
            # Tras un `replace` exitoso el temporal ya no existe; si algo fallo
            # antes, esto evita dejar basura en el directorio de datos.
            Path(temporal).unlink(missing_ok=True)

    def _error_archivo(self, accion: str, exc: Exception) -> ErrorPersistencia:
        """Error de E/S sin volcar el contenido del archivo (RN-18)."""
        return ErrorPersistencia(
            f"{accion} el archivo de datos '{self.ruta.name}'.",
            detalles={"archivo": str(self.ruta), "causa": type(exc).__name__},
        )
