"""Capa de linea de comandos.

Esta capa solo traduce argumentos a llamadas de los servicios; no contiene
reglas de negocio (eso vive en prestamos.reglas y prestamos.servicios).
"""

import argparse

from prestamos import __version__


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prestamos",
        description="Sistema de prestamo de equipos de laboratorio",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_subparsers(dest="comando")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.comando is None:
        print("Proyecto inicializado. Aun no hay comandos implementados.")
        return 0
    print(f"Comando no implementado: {args.comando}")
    return 1
