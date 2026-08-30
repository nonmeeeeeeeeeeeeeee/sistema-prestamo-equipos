"""Configuración de logs de eventos relevantes.

Los logs son un entregable: deben registrar login, creación/aprobación/rechazo
de solicitudes, entregas, devoluciones, cancelaciones y errores.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER_NAME = "prestamos"
DEFAULT_LOG_PATH = Path("datos/logs/eventos.log")
SENSITIVE_KEYS = ("password", "contrasena", "contraseña", "token", "secret", "dsn")


def configurar_logging(
    ruta_log: str | Path | None = None,
    nivel: str | int | None = None,
) -> logging.Logger:
    """Configura el logger de la aplicación y devuelve `logging.Logger`.

    La función es idempotente: puede llamarse varias veces sin duplicar handlers.
    """

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(_resolver_nivel(nivel or os.getenv("NIVEL_LOG", "INFO")))
    logger.propagate = False

    log_path = Path(ruta_log or os.getenv("PRESTAMOS_LOG_PATH", DEFAULT_LOG_PATH))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    existente = _buscar_file_handler(logger, log_path)
    if existente is None:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._prestamos_log_path = log_path.resolve()  # type: ignore[attr-defined]
        logger.addHandler(handler)

    return logger


def registrar_evento(
    accion: str,
    *,
    usuario: str | None = None,
    resultado: str = "ok",
    logger: logging.Logger | None = None,
    **contexto: Any,
) -> dict[str, Any]:
    """Registra un evento de auditoría sin exponer secretos."""

    evento = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "usuario": usuario or "anonimo",
        "accion": accion,
        "resultado": resultado,
        "contexto": sanitizar(contexto),
    }
    (logger or configurar_logging()).info(
        json.dumps(evento, ensure_ascii=False, sort_keys=True)
    )
    return evento


def sanitizar(valor: Any) -> Any:
    """Elimina claves sensibles de estructuras usadas en logs."""

    if isinstance(valor, dict):
        limpio = {}
        for clave, contenido in valor.items():
            if _es_clave_sensible(str(clave)):
                limpio[clave] = "***"
            else:
                limpio[clave] = sanitizar(contenido)
        return limpio
    if isinstance(valor, list):
        return [sanitizar(item) for item in valor]
    if isinstance(valor, tuple):
        return tuple(sanitizar(item) for item in valor)
    return valor


def _buscar_file_handler(
    logger: logging.Logger,
    log_path: Path,
) -> logging.FileHandler | None:
    esperado = log_path.resolve()
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            actual = getattr(handler, "_prestamos_log_path", None)
            if actual == esperado:
                return handler
    return None


def _resolver_nivel(nivel: str | int) -> int:
    if isinstance(nivel, int):
        return nivel
    return getattr(logging, nivel.upper(), logging.INFO)


def _es_clave_sensible(clave: str) -> bool:
    clave_normalizada = clave.lower()
    return any(sensible in clave_normalizada for sensible in SENSITIVE_KEYS)
