"""Pruebas de observabilidad y errores de dominio."""

from __future__ import annotations

import json

from prestamos.errores import ErrorValidacion
from prestamos.logging_conf import configurar_logging, registrar_evento, sanitizar
from prestamos.observabilidad import (
    capturar_mensaje,
    cargar_env,
    inicializar_sentry,
    sentry_activo,
)


def test_CP33_RF13_registra_evento_sin_exponer_secretos(tmp_path):
    log_path = tmp_path / "eventos.log"
    logger = configurar_logging(log_path)

    evento = registrar_evento(
        "login",
        usuario="solicitante1",
        resultado="error",
        logger=logger,
        password="secreto",
        token="abc",
    )

    contenido = log_path.read_text(encoding="utf-8").strip()
    registro = json.loads(contenido)

    assert evento["accion"] == "login"
    assert registro["usuario"] == "solicitante1"
    assert registro["resultado"] == "error"
    assert registro["contexto"]["password"] == "***"
    assert registro["contexto"]["token"] == "***"
    assert "secreto" not in contenido
    assert "abc" not in contenido


def test_CP34_RF13_sentry_sin_dsn_no_interrumpe_aplicacion(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("SENTRY_DSN=\nENTORNO=pruebas\n", encoding="utf-8")
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("ENTORNO", raising=False)

    cargadas = cargar_env(env_path)
    activo = inicializar_sentry(ruta_env=env_path)

    assert cargadas["SENTRY_DSN"] == ""
    assert cargadas["ENTORNO"] == "pruebas"
    assert activo is False
    assert sentry_activo() is False
    assert capturar_mensaje("evento de prueba", usuario="tester") is False


def test_CP32_RF13_error_dominio_expone_datos_para_log_sin_traceback():
    error = ErrorValidacion(
        "Fecha inválida",
        regla="RN-17",
        detalles={"campo": "fecha_inicio"},
    )

    assert str(error) == "Fecha inválida"
    assert error.para_log() == {
        "codigo": "ERROR_VALIDACION",
        "mensaje": "Fecha inválida",
        "regla": "RN-17",
        "detalles": {"campo": "fecha_inicio"},
    }
    assert sanitizar({"contrasena": "1234"}) == {"contrasena": "***"}
