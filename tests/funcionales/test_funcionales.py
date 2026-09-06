"""Casos funcionales canonicos CP-01 a CP-05."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from prestamos.auth import ServicioAuth, hash_contrasena
from prestamos.modelos import Equipo, EstadoEquipo, EstadoPrestamo, Prestamo, Rol, Usuario
from prestamos.repositorios.json_repo import RepositorioJson
from prestamos.servicios.prestamos import ServicioPrestamos

CONTRASENA_DEMO = "Clave-Funcional-2026"
FECHA_HOY = date(2026, 9, 10)


def _usuario(
    id_usuario: str,
    *,
    rol: Rol,
    activo: bool = True,
    contrasena: str = CONTRASENA_DEMO,
) -> Usuario:
    return Usuario(
        id=id_usuario,
        nombre=f"Usuario funcional {id_usuario}",
        correo=f"{id_usuario}@usm.cl",
        rol=rol,
        activo=activo,
        hash_contrasena=hash_contrasena(contrasena, iteraciones=1),
    )


def _encargado(id_usuario: str = "enc-funcional") -> Usuario:
    return _usuario(id_usuario, rol=Rol.ENCARGADO)


def _solicitante(id_usuario: str = "sol-funcional") -> Usuario:
    return _usuario(id_usuario, rol=Rol.SOLICITANTE)


def _equipo(
    codigo: str = "EQ-FUNC-01",
    *,
    estado: EstadoEquipo = EstadoEquipo.DISPONIBLE,
) -> Equipo:
    return Equipo(
        codigo=codigo,
        nombre=f"Notebook {codigo}",
        tipo="Notebook",
        descripcion="Equipo funcional de laboratorio",
        estado=estado,
    )


def _prestamo(
    id_prestamo: str,
    *,
    id_solicitante: str = "sol-funcional",
    equipos: tuple[str, ...] = ("EQ-FUNC-01",),
    estado: EstadoPrestamo = EstadoPrestamo.APROBADA,
    fecha_inicio: date = date(2026, 9, 10),
    fecha_termino: date = date(2026, 9, 12),
    fecha_solicitud: date = date(2026, 9, 8),
    fecha_aprobacion: date | None = date(2026, 9, 9),
    fecha_entrega: date | None = None,
    fecha_devolucion: date | None = None,
) -> Prestamo:
    return Prestamo(
        id=id_prestamo,
        id_solicitante=id_solicitante,
        equipos=equipos,
        motivo="Uso en laboratorio de software",
        estado=estado,
        fecha_solicitud=fecha_solicitud,
        fecha_inicio=fecha_inicio,
        fecha_termino=fecha_termino,
        fecha_aprobacion=fecha_aprobacion,
        fecha_entrega=fecha_entrega,
        fecha_devolucion=fecha_devolucion,
    )


def _repos_prestamos(tmp_path: Path) -> tuple[
    RepositorioJson[Prestamo],
    RepositorioJson[Equipo],
    ServicioPrestamos,
]:
    repo_prestamos = RepositorioJson(tmp_path / "solicitudes.json", Prestamo, "id")
    repo_equipos = RepositorioJson(tmp_path / "equipos.json", Equipo, "codigo")
    return repo_prestamos, repo_equipos, ServicioPrestamos(repo_prestamos, repo_equipos)


@pytest.mark.funcional
def test_CP01_RF02_login_valido_abre_sesion_sin_exponer_contrasena(
    tmp_path: Path,
) -> None:
    repo_usuarios = RepositorioJson(tmp_path / "usuarios.json", Usuario, "id")
    usuario = _solicitante("sol-login")
    repo_usuarios.guardar(usuario)
    auth = ServicioAuth(repo_usuarios)

    sesion = auth.iniciar_sesion("sol-login", CONTRASENA_DEMO)

    assert sesion.usuario.id == "sol-login"
    assert auth.usuario_actual == usuario
    assert auth.sesion == sesion
    assert sesion.iniciada_en.tzinfo is not None
    assert CONTRASENA_DEMO not in repr(sesion)
    assert CONTRASENA_DEMO not in repr(sesion.usuario)
    assert CONTRASENA_DEMO not in sesion.usuario.a_dict()["hash_contrasena"]
    assert sesion.usuario.a_dict()["hash_contrasena"] != CONTRASENA_DEMO


@pytest.mark.funcional
def test_CP02_RF09_registrar_entrega_aprobada_persiste_prestamo_y_equipo(
    tmp_path: Path,
) -> None:
    repo_prestamos, repo_equipos, servicio = _repos_prestamos(tmp_path)
    repo_prestamos.guardar(
        _prestamo(
            "PREST-ENTREGA",
            estado=EstadoPrestamo.APROBADA,
            fecha_inicio=date(2026, 9, 10),
            fecha_termino=date(2026, 9, 12),
            fecha_aprobacion=date(2026, 9, 9),
        )
    )
    repo_equipos.guardar(_equipo("EQ-FUNC-01", estado=EstadoEquipo.RESERVADO))

    entregado = servicio.registrar_entrega(
        "PREST-ENTREGA",
        _encargado(),
        fecha_entrega=date(2026, 9, 10),
    )

    persistido = repo_prestamos.obtener("PREST-ENTREGA")
    equipo_persistido = repo_equipos.obtener("EQ-FUNC-01")
    assert entregado.estado is EstadoPrestamo.ENTREGADA
    assert entregado.fecha_entrega == date(2026, 9, 10)
    assert entregado.fecha_devolucion is None
    assert persistido == entregado
    assert equipo_persistido.estado is EstadoEquipo.PRESTADO


@pytest.mark.funcional
def test_CP03_RF10_registrar_devolucion_en_plazo_persiste_prestamo_y_equipo(
    tmp_path: Path,
) -> None:
    repo_prestamos, repo_equipos, servicio = _repos_prestamos(tmp_path)
    repo_prestamos.guardar(
        _prestamo(
            "PREST-DEVOLUCION",
            estado=EstadoPrestamo.ENTREGADA,
            fecha_inicio=date(2026, 9, 10),
            fecha_termino=date(2026, 9, 12),
            fecha_aprobacion=date(2026, 9, 9),
            fecha_entrega=date(2026, 9, 10),
        )
    )
    repo_equipos.guardar(_equipo("EQ-FUNC-01", estado=EstadoEquipo.PRESTADO))

    devuelto = servicio.registrar_devolucion(
        "PREST-DEVOLUCION",
        _encargado(),
        fecha_devolucion=date(2026, 9, 12),
    )

    persistido = repo_prestamos.obtener("PREST-DEVOLUCION")
    equipo_persistido = repo_equipos.obtener("EQ-FUNC-01")
    assert devuelto.estado is EstadoPrestamo.DEVUELTA
    assert devuelto.fecha_entrega == date(2026, 9, 10)
    assert devuelto.fecha_devolucion == date(2026, 9, 12)
    assert persistido == devuelto
    assert equipo_persistido.estado is EstadoEquipo.DISPONIBLE


@pytest.mark.funcional
def test_CP04_RF11_cancelar_aprobada_antes_de_entrega_persiste_y_libera_equipo(
    tmp_path: Path,
) -> None:
    repo_prestamos, repo_equipos, servicio = _repos_prestamos(tmp_path)
    repo_prestamos.guardar(
        _prestamo(
            "PREST-CANCELACION",
            estado=EstadoPrestamo.APROBADA,
            fecha_inicio=date(2026, 9, 11),
            fecha_termino=date(2026, 9, 13),
            fecha_aprobacion=date(2026, 9, 9),
            fecha_entrega=None,
        )
    )
    repo_equipos.guardar(_equipo("EQ-FUNC-01", estado=EstadoEquipo.RESERVADO))

    cancelado = servicio.cancelar(
        "PREST-CANCELACION",
        _encargado(),
        "Solicitud cancelada antes de entrega",
    )

    persistido = repo_prestamos.obtener("PREST-CANCELACION")
    equipo_persistido = repo_equipos.obtener("EQ-FUNC-01")
    assert cancelado.estado is EstadoPrestamo.CANCELADA
    assert cancelado.fecha_entrega is None
    assert cancelado.motivo_cancelacion == "Solicitud cancelada antes de entrega"
    assert persistido == cancelado
    assert equipo_persistido.estado is EstadoEquipo.DISPONIBLE


@pytest.mark.funcional
def test_CP05_RF12_consultar_prestamos_clasifica_respeta_encargado_y_no_muta(
    tmp_path: Path,
) -> None:
    repo_prestamos, repo_equipos, servicio = _repos_prestamos(tmp_path)
    prestamos = [
        _prestamo(
            "PREST-FUTURO",
            id_solicitante="sol-uno",
            equipos=("EQ-FUTURO",),
            estado=EstadoPrestamo.APROBADA,
            fecha_inicio=date(2026, 9, 11),
            fecha_termino=date(2026, 9, 14),
            fecha_aprobacion=date(2026, 9, 9),
        ),
        _prestamo(
            "PREST-VIGENTE",
            id_solicitante="sol-dos",
            equipos=("EQ-VIGENTE",),
            estado=EstadoPrestamo.ENTREGADA,
            fecha_inicio=date(2026, 9, 9),
            fecha_termino=date(2026, 9, 10),
            fecha_aprobacion=date(2026, 9, 8),
            fecha_entrega=date(2026, 9, 9),
        ),
        _prestamo(
            "PREST-ATRASADO",
            id_solicitante="sol-tres",
            equipos=("EQ-ATRASADO",),
            estado=EstadoPrestamo.ATRASADA,
            fecha_inicio=date(2026, 9, 7),
            fecha_termino=date(2026, 9, 9),
            fecha_aprobacion=date(2026, 9, 6),
            fecha_entrega=date(2026, 9, 7),
        ),
        _prestamo(
            "PREST-ATRASADO-CALCULADO",
            id_solicitante="sol-cuatro",
            equipos=("EQ-ATRASADO-CALC",),
            estado=EstadoPrestamo.ENTREGADA,
            fecha_inicio=date(2026, 9, 7),
            fecha_termino=date(2026, 9, 9),
            fecha_aprobacion=date(2026, 9, 6),
            fecha_entrega=date(2026, 9, 7),
        ),
        _prestamo(
            "PREST-DEVUELTO",
            id_solicitante="sol-cinco",
            equipos=("EQ-DEVUELTO",),
            estado=EstadoPrestamo.DEVUELTA,
            fecha_inicio=date(2026, 9, 7),
            fecha_termino=date(2026, 9, 9),
            fecha_aprobacion=date(2026, 9, 6),
            fecha_entrega=date(2026, 9, 7),
            fecha_devolucion=date(2026, 9, 9),
        ),
    ]
    for prestamo in prestamos:
        repo_prestamos.guardar(prestamo)
    for codigo, estado in [
        ("EQ-FUTURO", EstadoEquipo.RESERVADO),
        ("EQ-VIGENTE", EstadoEquipo.PRESTADO),
        ("EQ-ATRASADO", EstadoEquipo.PRESTADO),
        ("EQ-ATRASADO-CALC", EstadoEquipo.PRESTADO),
        ("EQ-DEVUELTO", EstadoEquipo.DISPONIBLE),
    ]:
        repo_equipos.guardar(_equipo(codigo, estado=estado))
    prestamos_antes = [prestamo.a_dict() for prestamo in repo_prestamos.listar()]
    equipos_antes = [equipo.a_dict() for equipo in repo_equipos.listar()]
    encargado = _encargado()

    futuros = servicio.prestamos_futuros(encargado, fecha_actual=FECHA_HOY)
    vigentes = servicio.prestamos_vigentes(encargado, fecha_actual=FECHA_HOY)
    atrasados = servicio.prestamos_atrasados(encargado, fecha_actual=FECHA_HOY)

    assert [prestamo.id for prestamo in futuros] == ["PREST-FUTURO"]
    assert [prestamo.id for prestamo in vigentes] == ["PREST-VIGENTE"]
    assert [prestamo.id for prestamo in atrasados] == [
        "PREST-ATRASADO",
        "PREST-ATRASADO-CALCULADO",
    ]
    assert repo_prestamos.obtener("PREST-ATRASADO-CALCULADO").estado is EstadoPrestamo.ENTREGADA
    assert [prestamo.a_dict() for prestamo in repo_prestamos.listar()] == prestamos_antes
    assert [equipo.a_dict() for equipo in repo_equipos.listar()] == equipos_antes
