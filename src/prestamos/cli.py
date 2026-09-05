"""Capa de linea de comandos.

Esta capa solo traduce argumentos a llamadas de los servicios; no contiene
reglas de negocio (eso vive en prestamos.reglas y prestamos.servicios).
"""

import argparse

from prestamos import __version__
from prestamos.errores import ErrorDominio
from prestamos.logging_conf import configurar_logging, registrar_evento
from prestamos.observabilidad import (
    cargar_env,
    capturar_excepcion,
    capturar_mensaje,
    inicializar_sentry,
)


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prestamos",
        description="Sistema de prestamo de equipos de laboratorio",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="comando")
    subparsers.add_parser(
        "probar-sentry",
        help="envia un evento de prueba a Sentry si SENTRY_DSN esta configurado",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        cargar_env()
        configurar_logging()
        inicializar_sentry()

        args = construir_parser().parse_args(argv)
        if args.comando is None:
            registrar_evento("cli_inicio", resultado="ok")
            print("Proyecto inicializado. Aun no hay comandos implementados.")
            return 0
        if args.comando == "probar-sentry":
            enviado = capturar_mensaje(
                "Evento de prueba desde sistema-prestamo-equipos",
                usuario="revisor",
                contexto={"origen": "cli"},
            )
            if enviado:
                print("Evento de prueba enviado a Sentry.")
                return 0
            print("Sentry no esta configurado. Define SENTRY_DSN en .env.")
            return 1
        registrar_evento(
            "cli_comando_no_implementado",
            resultado="error",
            comando=args.comando,
        )
        print(f"Comando no implementado: {args.comando}")
        return 1
    except ErrorDominio as exc:
        _reportar_error(exc)
        print(f"Error: {exc.mensaje}")
        return 1
    except Exception as exc:
        _reportar_error(exc)
        print("Error: No se pudo completar la operacion.")
        return 1


def _reportar_error(error: Exception) -> None:
    """Intenta reportar el error sin depender de que observabilidad funcione."""
    try:
        contexto = error.para_log() if isinstance(error, ErrorDominio) else None
        capturar_excepcion(error, contexto=contexto)
    except Exception:
        # No volver a usar logging/Sentry: pueden ser la causa del fallo.
        pass
