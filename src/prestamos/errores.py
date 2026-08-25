"""Excepciones del dominio.

Cada error deberia poder mapearse a una regla de negocio (RN-XX) para que el
mensaje mostrado al usuario y el caso de prueba negativo coincidan.
"""


class ErrorDominio(Exception):
    """Base de todos los errores de negocio."""


class ErrorAutenticacion(ErrorDominio):
    pass


class ErrorAutorizacion(ErrorDominio):
    pass


class ErrorValidacion(ErrorDominio):
    pass


class TransicionNoPermitida(ErrorDominio):
    pass


class RecursoNoEncontrado(ErrorDominio):
    pass
