"""Errores de la CLI comprobados mediante su punto de entrada real."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture
def ejecutar_cli(tmp_path):
    entorno = os.environ.copy()
    entorno.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"),
        PYTHONDONTWRITEBYTECODE="1",
        SENTRY_DSN="",
        NIVEL_LOG="INFO",
        PRESTAMOS_LOG_PATH=str(tmp_path / "eventos.log"),
    )

    def ejecutar(*argumentos, codigo=None):
        comando = [sys.executable, "-B"]
        comando += ["-c", codigo] if codigo else ["-m", "prestamos", *argumentos]
        return subprocess.run(
            comando, cwd=tmp_path, env=entorno, capture_output=True,
            text=True, timeout=15,
        )

    return ejecutar


@pytest.mark.parametrize("fallo_reporte", [False, True])
@pytest.mark.parametrize(
    "punto,error,mensaje",
    [
        ("construir_parser", "ErrorValidacion('Fecha invalida')", "Error: Fecha invalida"),
        ("construir_parser", "RuntimeError('detalle interno')", "Error: No se pudo completar la operacion."),
        ("cargar_env", "OSError('detalle interno')", "Error: No se pudo completar la operacion."),
        ("configurar_logging", "OSError('detalle interno')", "Error: No se pudo completar la operacion."),
        ("inicializar_sentry", "RuntimeError('detalle interno')", "Error: No se pudo completar la operacion."),
    ],
)
def test_cli_errores_sin_traceback(ejecutar_cli, punto, error, mensaje, fallo_reporte):
    resultado = ejecutar_cli(codigo=f"""
import runpy
from unittest.mock import patch
from prestamos import cli
from prestamos.errores import ErrorValidacion

with patch.object(cli, {punto!r}, side_effect={error}), \
     patch.object(cli, 'capturar_excepcion', side_effect={"RuntimeError('fallo al reportar')" if fallo_reporte else "None"}) as reportar:
    try:
        runpy.run_module('prestamos', run_name='__main__')
    except SystemExit:
        reportar.assert_called_once()
        raise
""")
    assert resultado.returncode == 1
    assert resultado.stdout.strip() == mensaje
    assert resultado.stderr == ""
    assert "Traceback" not in resultado.stdout + resultado.stderr
    assert "detalle interno" not in resultado.stdout + resultado.stderr


def test_cli_fallo_real_logging_al_iniciar_y_reportar(ejecutar_cli, tmp_path):
    # FileHandler falla al abrir un directorio como archivo, también al reportar.
    (tmp_path / "eventos.log").mkdir()
    resultado = ejecutar_cli()
    assert resultado.returncode == 1
    assert resultado.stdout.strip() == "Error: No se pudo completar la operacion."
    assert resultado.stderr == ""
    assert "Traceback" not in resultado.stdout + resultado.stderr


@pytest.mark.parametrize("argumentos,codigo", [((), 0), (("--help",), 0), (("--version",), 0), (("inexistente",), 2)])
def test_cli_conserva_salidas_normales(ejecutar_cli, argumentos, codigo):
    resultado = ejecutar_cli(*argumentos)
    assert resultado.returncode == codigo
    assert "Traceback" not in resultado.stdout + resultado.stderr
