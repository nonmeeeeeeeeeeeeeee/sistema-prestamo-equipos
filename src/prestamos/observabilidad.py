"""Integración con Sentry.

El DSN se lee de la variable de entorno SENTRY_DSN o de un archivo `.env` local.
Nunca se debe versionar el DSN real.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from prestamos.logging_conf import registrar_evento, sanitizar

_sentry_activo = False


def cargar_env(ruta_env: str | Path = ".env") -> dict[str, str]:
    """Carga variables simples KEY=VALUE desde `.env` si existe.

    No sobreescribe variables que ya estén definidas en el entorno.
    """

    path = Path(ruta_env)
    cargadas: dict[str, str] = {}
    if not path.exists():
        return cargadas

    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        if clave and clave not in os.environ:
            os.environ[clave] = valor
            cargadas[clave] = valor
    return cargadas


def inicializar_sentry(
    *,
    dsn: str | None = None,
    entorno: str | None = None,
    ruta_env: str | Path = ".env",
) -> bool:
    """Inicializa Sentry si hay DSN; sin DSN la app sigue funcionando."""

    global _sentry_activo

    cargar_env(ruta_env)
    dsn_resuelto = dsn if dsn is not None else os.getenv("SENTRY_DSN", "")
    if not dsn_resuelto:
        _sentry_activo = False
        return False

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn_resuelto,
            environment=entorno or os.getenv("ENTORNO", "desarrollo"),
            traces_sample_rate=0.0,
        )
    except Exception as exc:  # pragma: no cover - depende de librería externa.
        _sentry_activo = False
        registrar_evento(
            "sentry_init",
            resultado="error",
            error=type(exc).__name__,
            detalle=str(exc),
        )
        return False

    _sentry_activo = True
    registrar_evento("sentry_init", resultado="ok")
    return True


def sentry_activo() -> bool:
    return _sentry_activo


def capturar_mensaje(
    mensaje: str,
    *,
    usuario: str | None = None,
    contexto: dict[str, Any] | None = None,
) -> bool:
    """Registra un mensaje de prueba y lo envía a Sentry si está activo."""

    contexto_limpio = sanitizar(contexto or {})
    registrar_evento(
        "sentry_mensaje",
        usuario=usuario,
        resultado="ok" if _sentry_activo else "omitido",
        mensaje=mensaje,
        contexto=contexto_limpio,
    )

    if not _sentry_activo:
        return False

    try:
        import sentry_sdk

        if usuario:
            sentry_sdk.set_user({"username": usuario})
        if contexto_limpio:
            sentry_sdk.set_context("prestamos", contexto_limpio)
        sentry_sdk.capture_message(mensaje)
    except Exception:
        return False
    return True


def capturar_excepcion(
    error: BaseException,
    *,
    usuario: str | None = None,
    contexto: dict[str, Any] | None = None,
) -> None:
    """Registra una excepción en logs y, si está activo, la envía a Sentry."""

    contexto_limpio = sanitizar(contexto or {})
    registrar_evento(
        "error",
        usuario=usuario,
        resultado="error",
        tipo=type(error).__name__,
        mensaje=str(error),
        contexto=contexto_limpio,
    )

    if not _sentry_activo:
        return

    try:
        import sentry_sdk

        if usuario:
            sentry_sdk.set_user({"username": usuario})
        if contexto_limpio:
            sentry_sdk.set_context("prestamos", contexto_limpio)
        sentry_sdk.capture_exception(error)
    except Exception:
        return
