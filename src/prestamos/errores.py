"""Excepciones del dominio.

Cada error puede mapearse a una regla de negocio (RN-XX) para que el mensaje
mostrado al usuario y el caso de prueba negativo coincidan.
"""

from __future__ import annotations

from typing import Any


class ErrorDominio(Exception):
    """Base de todos los errores de negocio.

    La CLI debe capturar estas excepciones y mostrar solo `mensaje`, sin
    traceback. `codigo`, `regla` y `detalles` quedan para logs, Sentry y pruebas.
    """

    codigo = "ERROR_DOMINIO"
    regla: str | None = None

    def __init__(
        self,
        mensaje: str,
        *,
        codigo: str | None = None,
        regla: str | None = None,
        detalles: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo or self.codigo
        self.regla = regla or self.regla
        self.detalles = detalles or {}

    def para_log(self) -> dict[str, Any]:
        datos: dict[str, Any] = {
            "codigo": self.codigo,
            "mensaje": self.mensaje,
        }
        if self.regla:
            datos["regla"] = self.regla
        if self.detalles:
            datos["detalles"] = self.detalles
        return datos


class ErrorAutenticacion(ErrorDominio):
    codigo = "ERROR_AUTENTICACION"


class ErrorAutorizacion(ErrorDominio):
    codigo = "ERROR_AUTORIZACION"


class ErrorValidacion(ErrorDominio):
    codigo = "ERROR_VALIDACION"


class TransicionNoPermitida(ErrorDominio):
    codigo = "TRANSICION_NO_PERMITIDA"


class RecursoNoEncontrado(ErrorDominio):
    codigo = "RECURSO_NO_ENCONTRADO"
