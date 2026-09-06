"""Pruebas de `prestamos.servicios.equipos`: catalogo, baja logica y guardas.

Nombres descriptivos y sin etiqueta CP-XX, igual que `test_auth.py` y
`test_servicio_usuarios.py`; ver DEF-01 (issue #43).

El grupo importante es el de las guardas: comprueban que la baja mira los
*prestamos* y no `Equipo.estado`, distincion que hoy tiene consecuencias reales
porque nadie escribe `RESERVADO` todavia (la aprobacion, #11, es un stub).
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from prestamos.auth import ServicioAuth
from prestamos.errores import (
    ErrorAutenticacion,
    ErrorAutorizacion,
    ErrorValidacion,
    RecursoNoEncontrado,
)
from prestamos.logging_conf import LOGGER_NAME, configurar_logging
from prestamos.modelos import Equipo, EstadoEquipo, EstadoPrestamo, Prestamo, Rol, Usuario
from prestamos.repositorios.json_repo import RepositorioJson
from prestamos.servicios.equipos import ServicioEquipos
from prestamos.servicios.usuarios import ServicioUsuarios, crear_encargado_inicial

CONTRASENA = "clave-de-demostracion"


# ---------------------------------------------------------------- Fixtures


@pytest.fixture
def repo_usuarios(tmp_path: Path) -> RepositorioJson[Usuario]:
    return RepositorioJson(tmp_path / "usuarios.json", Usuario, "id")


@pytest.fixture
def repo_equipos(tmp_path: Path) -> RepositorioJson[Equipo]:
    return RepositorioJson(tmp_path / "equipos.json", Equipo, "codigo")


@pytest.fixture
def repo_prestamos(tmp_path: Path) -> RepositorioJson[Prestamo]:
    return RepositorioJson(tmp_path / "solicitudes.json", Prestamo, "id")


@pytest.fixture
def log_pruebas(tmp_path: Path):
    ruta = tmp_path / "eventos.log"
    logger = configurar_logging(ruta)
    yield logger, ruta
    for handler in list(logging.getLogger(LOGGER_NAME).handlers):
        if getattr(handler, "_prestamos_log_path", None) == ruta.resolve():
            logger.removeHandler(handler)
            handler.close()


@pytest.fixture
def auth(repo_usuarios, log_pruebas) -> ServicioAuth:
    logger, _ = log_pruebas
    return ServicioAuth(repo_usuarios, logger=logger)


@pytest.fixture
def servicio(auth, repo_equipos, repo_prestamos, log_pruebas) -> ServicioEquipos:
    logger, _ = log_pruebas
    return ServicioEquipos(auth, repo_equipos, repo_prestamos, logger=logger)


@pytest.fixture
def servicio_usuarios(auth, repo_usuarios, log_pruebas) -> ServicioUsuarios:
    logger, _ = log_pruebas
    return ServicioUsuarios(auth, repo_usuarios, logger=logger, iteraciones_hash=1)


@pytest.fixture
def sesion_encargado(auth, repo_usuarios) -> Usuario:
    encargado = crear_encargado_inicial(
        "enc", "Encargada Principal", "encargada@universidad.cl", CONTRASENA,
        repositorio=repo_usuarios, iteraciones_hash=1,
    )
    auth.iniciar_sesion("enc", CONTRASENA)
    return encargado


def _eventos(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    return [
        json.loads(linea)
        for linea in ruta.read_text(encoding="utf-8").splitlines()
        if linea.strip()
    ]


def _alta(servicio: ServicioEquipos, **cambios) -> Equipo:
    datos = {
        "codigo": "M-01",
        "nombre": "Microscopio optico",
        "tipo": "Optica",
        "descripcion": "Microscopio binocular de laboratorio",
    }
    datos.update(cambios)
    return servicio.registrar_equipo(**datos)


def _prestamo(
    repo: RepositorioJson[Prestamo],
    estado: EstadoPrestamo,
    *,
    id_prestamo: str = "p1",
    codigo: str = "M-01",
) -> Prestamo:
    hoy = date.today()
    prestamo = Prestamo(
        id=id_prestamo,
        id_solicitante="u1",
        equipos=(codigo,),
        motivo="Practico de laboratorio",
        estado=estado,
        fecha_solicitud=hoy,
        fecha_inicio=hoy + timedelta(days=1),
        fecha_termino=hoy + timedelta(days=3),
    )
    repo.guardar(prestamo)
    return prestamo


# ------------------------------------------------------------------- Alta


def test_alta_deja_el_equipo_disponible(servicio, sesion_encargado) -> None:
    equipo = _alta(servicio)

    assert equipo.estado is EstadoEquipo.DISPONIBLE


def test_alta_sin_sesion_es_rechazada(servicio) -> None:
    with pytest.raises(ErrorAutenticacion):
        _alta(servicio)


def test_alta_por_solicitante_es_rechazada(
    servicio, servicio_usuarios, auth, sesion_encargado
) -> None:
    servicio_usuarios.registrar_usuario(
        "u1", "Ana Perez", "ana@universidad.cl", Rol.SOLICITANTE, CONTRASENA
    )
    auth.cerrar_sesion()
    auth.iniciar_sesion("u1", CONTRASENA)

    with pytest.raises(ErrorAutorizacion):
        _alta(servicio)


def test_alta_rechaza_codigo_repetido(servicio, sesion_encargado) -> None:
    _alta(servicio)

    with pytest.raises(ErrorValidacion) as exc:
        _alta(servicio, nombre="Otro microscopio")
    assert exc.value.detalles["motivo"] == "codigo_duplicado"


def test_alta_rechaza_codigo_que_solo_difiere_en_mayusculas(
    servicio, sesion_encargado
) -> None:
    _alta(servicio, codigo="M-01")

    with pytest.raises(ErrorValidacion) as exc:
        _alta(servicio, codigo="m-01")
    assert exc.value.detalles["motivo"] == "codigo_duplicado"


def test_no_se_reutiliza_el_codigo_de_un_equipo_dado_de_baja(
    servicio, sesion_encargado
) -> None:
    """El codigo es la etiqueta fisica: reutilizarlo reengancharia el historial
    de prestamos del equipo viejo a un objeto distinto."""
    _alta(servicio)
    servicio.dar_de_baja("M-01")

    with pytest.raises(ErrorValidacion) as exc:
        _alta(servicio, nombre="Microscopio nuevo")
    assert exc.value.detalles["motivo"] == "codigo_dado_de_baja"
    assert "reactivar" in exc.value.mensaje


def test_alta_rechaza_un_codigo_que_solo_difiere_en_espacios(
    servicio, sesion_encargado
) -> None:
    _alta(servicio, codigo="M-01")

    with pytest.raises(ErrorValidacion) as exc:
        _alta(servicio, codigo=" M-01 ")
    assert exc.value.detalles["motivo"] == "codigo_duplicado"


def test_alta_recorta_los_espacios_del_codigo(servicio, sesion_encargado) -> None:
    assert _alta(servicio, codigo="  M-01  ").codigo == "M-01"


# ---------------------------------------------------------------- Edicion


def test_edicion_actualiza_los_datos_descriptivos(servicio, sesion_encargado) -> None:
    _alta(servicio)

    editado = servicio.editar_equipo(
        "M-01", nombre="Microscopio trinocular", descripcion="Con camara"
    )

    assert editado.nombre == "Microscopio trinocular"
    assert editado.descripcion == "Con camara"
    assert editado.tipo == "Optica"


def test_edicion_no_puede_cambiar_el_estado(servicio, sesion_encargado) -> None:
    """`estado` no es parametro de `editar_equipo`: lo gestionan las operaciones
    administrativas y el ciclo de vida del prestamo."""
    _alta(servicio)
    servicio.dar_de_baja("M-01")

    editado = servicio.editar_equipo("M-01", nombre="Microscopio retirado")

    assert editado.estado is EstadoEquipo.BAJA
    with pytest.raises(TypeError):
        servicio.editar_equipo("M-01", estado=EstadoEquipo.DISPONIBLE)


def test_edicion_de_equipo_inexistente_levanta_no_encontrado(
    servicio, sesion_encargado
) -> None:
    with pytest.raises(RecursoNoEncontrado):
        servicio.editar_equipo("X-99", nombre="Nada")


# ------------------------------------------------- Baja y guardas (RN-05)


def test_baja_sin_prestamos_deja_el_equipo_en_baja(servicio, sesion_encargado) -> None:
    _alta(servicio)

    assert servicio.dar_de_baja("M-01").estado is EstadoEquipo.BAJA


def test_baja_rechazada_por_prestamo_aprobado_aunque_el_equipo_este_disponible(
    servicio, sesion_encargado, repo_prestamos, repo_equipos
) -> None:
    """La prueba clave del diseno.

    Hoy nadie escribe `RESERVADO` -la aprobacion (#11) es un stub-, asi que un
    prestamo APROBADA deja su equipo en DISPONIBLE. Una guarda que mirase
    `Equipo.estado` daria de baja un equipo ya comprometido; preguntar por los
    prestamos acierta.
    """
    _alta(servicio)
    _prestamo(repo_prestamos, EstadoPrestamo.APROBADA)
    assert repo_equipos.obtener("M-01").estado is EstadoEquipo.DISPONIBLE

    with pytest.raises(ErrorValidacion) as exc:
        servicio.dar_de_baja("M-01")
    assert exc.value.detalles["motivo"] == "prestamo_activo"
    assert exc.value.detalles["prestamos"] == ["p1"]
    assert exc.value.regla == "RN-21"


@pytest.mark.parametrize(
    "estado", [EstadoPrestamo.APROBADA, EstadoPrestamo.ENTREGADA, EstadoPrestamo.ATRASADA]
)
def test_baja_rechazada_por_prestamo_comprometido(
    servicio, sesion_encargado, repo_prestamos, estado
) -> None:
    _alta(servicio)
    _prestamo(repo_prestamos, estado)

    with pytest.raises(ErrorValidacion):
        servicio.dar_de_baja("M-01")


def test_una_solicitud_sin_aprobar_no_bloquea_la_baja(
    servicio, sesion_encargado, repo_prestamos
) -> None:
    """SOLICITADA es una peticion, no un compromiso: si el equipo se rompe el
    Encargado debe poder retirarlo. Esa solicitud muere luego en la aprobacion,
    que revalida RN-05."""
    _alta(servicio)
    _prestamo(repo_prestamos, EstadoPrestamo.SOLICITADA)

    assert servicio.dar_de_baja("M-01").estado is EstadoEquipo.BAJA


@pytest.mark.parametrize(
    "estado",
    [EstadoPrestamo.DEVUELTA, EstadoPrestamo.CANCELADA, EstadoPrestamo.RECHAZADA],
)
def test_un_prestamo_terminado_no_bloquea_la_baja(
    servicio, sesion_encargado, repo_prestamos, estado
) -> None:
    _alta(servicio)
    _prestamo(repo_prestamos, estado)

    assert servicio.dar_de_baja("M-01").estado is EstadoEquipo.BAJA


def test_un_prestamo_de_otro_equipo_no_bloquea_la_baja(
    servicio, sesion_encargado, repo_prestamos
) -> None:
    _alta(servicio)
    _alta(servicio, codigo="M-02", nombre="Otro microscopio")
    _prestamo(repo_prestamos, EstadoPrestamo.ENTREGADA, codigo="M-02")

    assert servicio.dar_de_baja("M-01").estado is EstadoEquipo.BAJA


def test_baja_rechazada_por_prestamo_con_el_codigo_en_otras_mayusculas(
    servicio, sesion_encargado, repo_prestamos
) -> None:
    """RN-04 considera "M-01" y "m-01" el mismo equipo, asi que el barrido de
    RN-21 tambien debe hacerlo.

    `Prestamo.equipos` guarda los codigos como texto suelto y nadie resuelve la
    referencia: con una comparacion exacta, un prestamo activo sobre "m-01" no
    bloqueaba la baja de "M-01".
    """
    _alta(servicio, codigo="M-01")
    _prestamo(repo_prestamos, EstadoPrestamo.APROBADA, codigo="m-01")

    with pytest.raises(ErrorValidacion) as exc:
        servicio.dar_de_baja("M-01")
    assert exc.value.detalles["motivo"] == "prestamo_activo"


# ----------------------------------------------------------- Mantencion


def test_mantencion_usa_la_misma_guarda_que_la_baja(
    servicio, sesion_encargado, repo_prestamos
) -> None:
    """Dejar en MANTENCION un equipo comprometido haria fallar la entrega mas
    tarde, en el mostrador (RN-13)."""
    _alta(servicio)
    _prestamo(repo_prestamos, EstadoPrestamo.ENTREGADA)

    with pytest.raises(ErrorValidacion) as exc:
        servicio.enviar_a_mantencion("M-01")
    assert exc.value.detalles["motivo"] == "prestamo_activo"


def test_mantencion_sin_prestamos_activos(servicio, sesion_encargado) -> None:
    _alta(servicio)

    assert servicio.enviar_a_mantencion("M-01").estado is EstadoEquipo.MANTENCION


# ----------------------------------------------------------- Reactivacion


def test_la_baja_es_reversible(servicio, sesion_encargado) -> None:
    _alta(servicio)
    servicio.dar_de_baja("M-01")

    assert servicio.reactivar("M-01").estado is EstadoEquipo.DISPONIBLE


def test_se_reactiva_desde_mantencion(servicio, sesion_encargado) -> None:
    _alta(servicio)
    servicio.enviar_a_mantencion("M-01")

    assert servicio.reactivar("M-01").estado is EstadoEquipo.DISPONIBLE


def test_no_se_reactiva_un_equipo_prestado(
    servicio, sesion_encargado, repo_equipos
) -> None:
    """PRESTADO lo gestiona el ciclo de vida del prestamo; forzarlo a DISPONIBLE
    desde el catalogo volveria reservable un equipo que esta fuera."""
    _alta(servicio)
    repo_equipos.guardar(
        replace(repo_equipos.obtener("M-01"), estado=EstadoEquipo.PRESTADO)
    )

    with pytest.raises(ErrorValidacion) as exc:
        servicio.reactivar("M-01")
    assert exc.value.detalles["motivo"] == "estado_no_administrativo"


def test_reactivar_un_equipo_disponible_es_idempotente(
    servicio, sesion_encargado
) -> None:
    _alta(servicio)

    assert servicio.reactivar("M-01").estado is EstadoEquipo.DISPONIBLE


def test_una_baja_repetida_deja_evidencia_en_el_log(
    servicio, sesion_encargado, log_pruebas
) -> None:
    """Idempotente en el estado, no en la auditoria (DoD de #10)."""
    _, ruta = log_pruebas
    _alta(servicio)
    servicio.dar_de_baja("M-01")
    servicio.dar_de_baja("M-01")

    bajas = [e for e in _eventos(ruta) if e["accion"] == "equipo_dado_de_baja"]
    assert [e["resultado"] for e in bajas] == ["ok", "sin_cambio"]
    assert bajas[-1]["contexto"]["estado_anterior"] == "BAJA"


def test_una_reactivacion_redundante_deja_evidencia_en_el_log(
    servicio, sesion_encargado, log_pruebas
) -> None:
    _, ruta = log_pruebas
    _alta(servicio)
    servicio.reactivar("M-01")

    eventos = [e for e in _eventos(ruta) if e["accion"] == "equipo_reactivado"]
    assert [e["resultado"] for e in eventos] == ["sin_cambio"]


# --------------------------------------------------------------- Listado


def test_listado_incluye_dados_de_baja_por_defecto(servicio, sesion_encargado) -> None:
    _alta(servicio)
    _alta(servicio, codigo="M-02", nombre="Otro")
    servicio.dar_de_baja("M-02")

    assert {e.codigo for e in servicio.listar()} == {"M-01", "M-02"}


def test_listado_puede_omitir_los_dados_de_baja(servicio, sesion_encargado) -> None:
    _alta(servicio)
    _alta(servicio, codigo="M-02", nombre="Otro")
    servicio.dar_de_baja("M-02")

    assert {e.codigo for e in servicio.listar(incluir_dados_de_baja=False)} == {"M-01"}


def test_un_solicitante_puede_ver_el_catalogo(
    servicio, servicio_usuarios, auth, sesion_encargado
) -> None:
    """Solo modificar el catalogo es exclusivo del Encargado: un solicitante
    necesita verlo para poder pedir algo (RF-04)."""
    _alta(servicio)
    servicio_usuarios.registrar_usuario(
        "u1", "Ana Perez", "ana@universidad.cl", Rol.SOLICITANTE, CONTRASENA
    )
    auth.cerrar_sesion()
    auth.iniciar_sesion("u1", CONTRASENA)

    assert [e.codigo for e in servicio.listar()] == ["M-01"]


def test_el_catalogo_exige_sesion(servicio) -> None:
    with pytest.raises(ErrorAutenticacion):
        servicio.listar()


# ------------------------------------------------------------------ Logs


def test_la_baja_registra_evento(servicio, sesion_encargado, log_pruebas) -> None:
    _, ruta = log_pruebas
    _alta(servicio)
    servicio.dar_de_baja("M-01")

    bajas = [e for e in _eventos(ruta) if e["accion"] == "equipo_dado_de_baja"]
    assert bajas[-1]["resultado"] == "ok"
    assert bajas[-1]["usuario"] == "enc"
    assert bajas[-1]["contexto"]["estado_anterior"] == "DISPONIBLE"


def test_el_rechazo_por_prestamo_activo_registra_evento(
    servicio, sesion_encargado, repo_prestamos, log_pruebas
) -> None:
    _, ruta = log_pruebas
    _alta(servicio)
    _prestamo(repo_prestamos, EstadoPrestamo.ENTREGADA)
    with pytest.raises(ErrorValidacion):
        servicio.dar_de_baja("M-01")

    errores = [
        e for e in _eventos(ruta)
        if e["accion"] == "equipo_dado_de_baja" and e["resultado"] == "error"
    ]
    assert errores[-1]["contexto"]["motivo"] == "prestamo_activo"
