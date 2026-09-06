"""Pruebas unitarias del servicio de prestamos (issues #12 y #13)"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import prestamos.servicios.prestamos as servicio_mod
from prestamos.errores import (
    ErrorAutorizacion,
    ErrorValidacion,
    RecursoNoEncontrado,
    TransicionNoPermitida,
)
from prestamos.modelos import Equipo, EstadoEquipo, EstadoPrestamo, Prestamo, Rol, Usuario
from prestamos.reglas import EventoTransicion
from prestamos.repositorios.json_repo import RepositorioJson
from prestamos.servicios.prestamos import ServicioPrestamos


def usuario(
    id_usuario: str = "sol-1",
    rol: Rol = Rol.SOLICITANTE,
) -> Usuario:
    return Usuario(
        id=id_usuario,
        nombre="Usuario de prueba",
        correo=f"{id_usuario}@usm.cl",
        rol=rol,
        activo=True,
        hash_contrasena="pbkdf2$1$sal$digest",
    )


def equipo(
    codigo: str = "EQ-01",
    estado: EstadoEquipo = EstadoEquipo.DISPONIBLE,
) -> Equipo:
    return Equipo(
        codigo=codigo,
        nombre="Notebook",
        tipo="computador",
        descripcion="Notebook de laboratorio",
        estado=estado,
    )


def prestamo(
    *,
    id_prestamo: str = "P-01",
    id_solicitante: str = "sol-1",
    estado: EstadoPrestamo = EstadoPrestamo.APROBADA,
    equipos: tuple[str, ...] = ("EQ-01",),
    fecha_inicio: date = date(2026, 9, 8),
    fecha_termino: date = date(2026, 9, 10),
    fecha_aprobacion: date | None = date(2026, 9, 7),
    fecha_entrega: date | None = None,
    fecha_devolucion: date | None = None,
) -> Prestamo:
    return Prestamo(
        id=id_prestamo,
        id_solicitante=id_solicitante,
        equipos=equipos,
        motivo="Proyecto de electronica",
        estado=estado,
        fecha_solicitud=date(2026, 9, 7),
        fecha_inicio=fecha_inicio,
        fecha_termino=fecha_termino,
        fecha_aprobacion=fecha_aprobacion,
        fecha_entrega=fecha_entrega,
        fecha_devolucion=fecha_devolucion,
    )


@pytest.fixture
def repo_prestamos(tmp_path: Path) -> RepositorioJson[Prestamo]:
    return RepositorioJson(tmp_path / "solicitudes.json", Prestamo, "id")


@pytest.fixture
def repo_equipos(tmp_path: Path) -> RepositorioJson[Equipo]:
    return RepositorioJson(tmp_path / "equipos.json", Equipo, "codigo")


@pytest.fixture
def servicio(
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> ServicioPrestamos:
    return ServicioPrestamos(repo_prestamos, repo_equipos)


def test_registrar_entrega_actualiza_estado_fecha_y_equipo(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    repo_prestamos.guardar(prestamo())
    repo_equipos.guardar(equipo())

    actualizado = servicio.registrar_entrega(
        "P-01",
        usuario("enc-1", Rol.ENCARGADO),
        fecha_entrega=date(2026, 9, 8),
    )

    assert actualizado.estado is EstadoPrestamo.ENTREGADA
    assert actualizado.fecha_entrega == date(2026, 9, 8)
    assert repo_prestamos.obtener("P-01") == actualizado
    assert repo_equipos.obtener("EQ-01").estado is EstadoEquipo.PRESTADO


def test_entrega_solo_desde_aprobada_y_por_encargado(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    repo_prestamos.guardar(prestamo(estado=EstadoPrestamo.SOLICITADA))
    repo_equipos.guardar(equipo())

    with pytest.raises(TransicionNoPermitida) as exc_estado:
        servicio.registrar_entrega(
            "P-01",
            usuario("enc-1", Rol.ENCARGADO),
            fecha_entrega=date(2026, 9, 8),
        )

    assert exc_estado.value.regla == "RN-13"
    assert repo_prestamos.obtener("P-01").estado is EstadoPrestamo.SOLICITADA
    assert repo_equipos.obtener("EQ-01").estado is EstadoEquipo.DISPONIBLE

    repo_prestamos.guardar(prestamo())

    with pytest.raises(ErrorAutorizacion) as exc_rol:
        servicio.registrar_entrega(
            "P-01",
            usuario("sol-1", Rol.SOLICITANTE),
            fecha_entrega=date(2026, 9, 8),
        )

    assert exc_rol.value.regla == "RN-13"
    assert repo_prestamos.obtener("P-01").estado is EstadoPrestamo.APROBADA


def test_entrega_rechaza_equipo_prestado_fisicamente(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    repo_prestamos.guardar(prestamo())
    repo_equipos.guardar(equipo(estado=EstadoEquipo.PRESTADO))

    with pytest.raises(ErrorValidacion) as exc_info:
        servicio.registrar_entrega(
            "P-01",
            usuario("enc-1", Rol.ENCARGADO),
            fecha_entrega=date(2026, 9, 8),
        )

    assert exc_info.value.regla == "RN-13"
    assert repo_prestamos.obtener("P-01").estado is EstadoPrestamo.APROBADA
    assert repo_equipos.obtener("EQ-01").estado is EstadoEquipo.PRESTADO


def test_devolucion_en_plazo_registra_fecha_y_libera_equipo(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    repo_prestamos.guardar(
        prestamo(estado=EstadoPrestamo.ENTREGADA, fecha_entrega=date(2026, 9, 8))
    )
    repo_equipos.guardar(equipo(estado=EstadoEquipo.PRESTADO))

    actualizado = servicio.registrar_devolucion(
        "P-01",
        usuario("enc-1", Rol.ENCARGADO),
        fecha_devolucion=date(2026, 9, 10),
    )

    assert actualizado.estado is EstadoPrestamo.DEVUELTA
    assert actualizado.fecha_devolucion == date(2026, 9, 10)
    assert repo_prestamos.obtener("P-01") == actualizado
    assert repo_equipos.obtener("EQ-01").estado is EstadoEquipo.DISPONIBLE


def test_devolucion_atrasada_marca_atraso_y_luego_cierra(
    monkeypatch: pytest.MonkeyPatch,
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    repo_prestamos.guardar(
        prestamo(estado=EstadoPrestamo.ENTREGADA, fecha_entrega=date(2026, 9, 8))
    )
    repo_equipos.guardar(equipo(estado=EstadoEquipo.PRESTADO))
    eventos: list[EventoTransicion] = []
    validar_original = servicio_mod.validar_transicion

    def validar_spy(*args, **kwargs):
        eventos.append(args[1])
        return validar_original(*args, **kwargs)

    monkeypatch.setattr(servicio_mod, "validar_transicion", validar_spy)

    actualizado = servicio.registrar_devolucion(
        "P-01",
        usuario("enc-1", Rol.ENCARGADO),
        fecha_devolucion=date(2026, 9, 11),
    )

    assert eventos == [
        EventoTransicion.MARCAR_ATRASO,
        EventoTransicion.REGISTRAR_DEVOLUCION_ATRASADA,
    ]
    assert actualizado.estado is EstadoPrestamo.DEVUELTA
    assert actualizado.fecha_devolucion == date(2026, 9, 11)
    assert repo_prestamos.obtener("P-01") == actualizado
    assert repo_equipos.obtener("EQ-01").estado is EstadoEquipo.DISPONIBLE


def test_devolucion_invalida_no_persiste_atraso_intermedio(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    original = prestamo(
        estado=EstadoPrestamo.ENTREGADA,
        equipos=("EQ-01", "EQ-02"),
        fecha_entrega=date(2026, 9, 8),
    )
    repo_prestamos.guardar(original)
    repo_equipos.guardar(equipo("EQ-01", EstadoEquipo.PRESTADO))
    repo_equipos.guardar(equipo("EQ-02", EstadoEquipo.PRESTADO))

    with pytest.raises(ErrorValidacion) as exc_info:
        servicio.registrar_devolucion(
            "P-01",
            usuario("enc-1", Rol.ENCARGADO),
            fecha_devolucion=date(2026, 9, 11),
            equipos_devueltos=["EQ-01"],
        )

    assert exc_info.value.regla == "RN-14"
    assert repo_prestamos.obtener("P-01") == original
    assert repo_equipos.obtener("EQ-01").estado is EstadoEquipo.PRESTADO
    assert repo_equipos.obtener("EQ-02").estado is EstadoEquipo.PRESTADO


def test_devolucion_desde_atrasada_usa_t09(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    repo_prestamos.guardar(
        prestamo(estado=EstadoPrestamo.ATRASADA, fecha_entrega=date(2026, 9, 8))
    )
    repo_equipos.guardar(equipo(estado=EstadoEquipo.PRESTADO))

    actualizado = servicio.registrar_devolucion(
        "P-01",
        usuario("enc-1", Rol.ENCARGADO),
        fecha_devolucion=date(2026, 9, 12),
    )

    assert actualizado.estado is EstadoPrestamo.DEVUELTA
    assert actualizado.fecha_devolucion == date(2026, 9, 12)
    assert repo_equipos.obtener("EQ-01").estado is EstadoEquipo.DISPONIBLE


def test_devolucion_no_cierra_si_no_puede_liberar_equipo(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
) -> None:
    original = prestamo(
        estado=EstadoPrestamo.ENTREGADA,
        fecha_entrega=date(2026, 9, 8),
    )
    repo_prestamos.guardar(original)

    with pytest.raises(RecursoNoEncontrado):
        servicio.registrar_devolucion(
            "P-01",
            usuario("enc-1", Rol.ENCARGADO),
            fecha_devolucion=date(2026, 9, 10),
        )

    assert repo_prestamos.obtener("P-01") == original


def test_cancelacion_solicitada_registra_motivo(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    repo_prestamos.guardar(
        prestamo(estado=EstadoPrestamo.SOLICITADA, fecha_aprobacion=None)
    )
    repo_equipos.guardar(equipo())

    actualizado = servicio.cancelar("P-01", usuario(), "Ya no se usara")

    assert actualizado.estado is EstadoPrestamo.CANCELADA
    assert actualizado.motivo_cancelacion == "Ya no se usara"
    assert repo_prestamos.obtener("P-01") == actualizado
    assert repo_equipos.obtener("EQ-01").estado is EstadoEquipo.DISPONIBLE


def test_cancelacion_aprobada_no_persiste_si_no_puede_liberar_equipo(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
) -> None:
    original = prestamo()
    repo_prestamos.guardar(original)

    with pytest.raises(RecursoNoEncontrado):
        servicio.cancelar(
            "P-01",
            usuario("enc-1", Rol.ENCARGADO),
            "Equipo no disponible",
        )

    assert repo_prestamos.obtener("P-01") == original


def test_cancelacion_aprobada_por_encargado_libera_reserva(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    repo_prestamos.guardar(prestamo())
    repo_equipos.guardar(equipo(estado=EstadoEquipo.RESERVADO))

    actualizado = servicio.cancelar(
        "P-01",
        usuario("enc-1", Rol.ENCARGADO),
        "Equipo requerido para mantencion",
    )

    assert actualizado.estado is EstadoPrestamo.CANCELADA
    assert actualizado.motivo_cancelacion == "Equipo requerido para mantencion"
    assert repo_equipos.obtener("EQ-01").estado is EstadoEquipo.DISPONIBLE


def test_cancelacion_exige_motivo_desde_el_motor_y_solo_antes_de_entrega(
    monkeypatch: pytest.MonkeyPatch,
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    repo_prestamos.guardar(prestamo())
    repo_equipos.guardar(equipo(estado=EstadoEquipo.RESERVADO))
    llamadas = 0
    validar_original = servicio_mod.validar_transicion

    def validar_spy(*args, **kwargs):
        nonlocal llamadas
        llamadas += 1
        return validar_original(*args, **kwargs)

    monkeypatch.setattr(servicio_mod, "validar_transicion", validar_spy)

    with pytest.raises(ErrorValidacion) as exc_motivo:
        servicio.cancelar("P-01", usuario(), " ")

    assert llamadas == 1
    assert exc_motivo.value.regla == "RN-15"
    assert repo_prestamos.obtener("P-01").estado is EstadoPrestamo.APROBADA

    entregado = prestamo(
        estado=EstadoPrestamo.ENTREGADA,
        fecha_entrega=date(2026, 9, 8),
    )
    repo_prestamos.guardar(entregado)

    with pytest.raises(TransicionNoPermitida) as exc_estado:
        servicio.cancelar("P-01", usuario("enc-1", Rol.ENCARGADO), "Fuera de plazo")

    assert exc_estado.value.regla == "RN-15"
    assert repo_prestamos.obtener("P-01") == entregado


def test_marcar_atraso_persistente(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    repo_prestamos.guardar(
        prestamo(
            estado=EstadoPrestamo.ENTREGADA,
            fecha_entrega=date(2026, 9, 8),
            fecha_termino=date(2026, 9, 10),
        )
    )
    repo_equipos.guardar(equipo(estado=EstadoEquipo.PRESTADO))

    actualizado = servicio.marcar_atraso(
        "P-01",
        fecha_actual=date(2026, 9, 11),
    )

    assert actualizado.estado is EstadoPrestamo.ATRASADA
    assert repo_prestamos.obtener("P-01").estado is EstadoPrestamo.ATRASADA
    assert repo_equipos.obtener("EQ-01").estado is EstadoEquipo.PRESTADO


def test_toda_operacion_pasa_por_motor_de_reglas(
    monkeypatch: pytest.MonkeyPatch,
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    eventos: list[EventoTransicion] = []
    validar_original = servicio_mod.validar_transicion

    def validar_spy(*args, **kwargs):
        eventos.append(args[1])
        return validar_original(*args, **kwargs)

    monkeypatch.setattr(servicio_mod, "validar_transicion", validar_spy)

    repo_equipos.guardar(equipo())
    repo_prestamos.guardar(prestamo())
    servicio.registrar_entrega(
        "P-01",
        usuario("enc-1", Rol.ENCARGADO),
        fecha_entrega=date(2026, 9, 8),
    )

    repo_prestamos.guardar(
        prestamo(estado=EstadoPrestamo.ENTREGADA, fecha_entrega=date(2026, 9, 8))
    )
    repo_equipos.guardar(equipo(estado=EstadoEquipo.PRESTADO))
    servicio.registrar_devolucion(
        "P-01",
        usuario("enc-1", Rol.ENCARGADO),
        fecha_devolucion=date(2026, 9, 10),
    )

    repo_prestamos.guardar(prestamo())
    repo_equipos.guardar(equipo(estado=EstadoEquipo.RESERVADO))
    servicio.cancelar("P-01", usuario(), "Cambio de plan")

    assert eventos == [
        EventoTransicion.REGISTRAR_ENTREGA,
        EventoTransicion.REGISTRAR_DEVOLUCION,
        EventoTransicion.CANCELAR_SOLICITUD,
    ]


def test_consultas_clasifican_futuros_vigentes_y_atrasados_con_limites_de_fecha(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
) -> None:
    hoy = date(2026, 9, 10)
    for solicitud in [
        prestamo(
            id_prestamo="FUTURO",
            estado=EstadoPrestamo.APROBADA,
            fecha_inicio=date(2026, 9, 11),
            fecha_termino=date(2026, 9, 14),
        ),
        prestamo(
            id_prestamo="APROBADA_HOY",
            estado=EstadoPrestamo.APROBADA,
            fecha_inicio=hoy,
            fecha_termino=date(2026, 9, 11),
        ),
        prestamo(
            id_prestamo="VIGENTE_INICIO",
            estado=EstadoPrestamo.ENTREGADA,
            fecha_inicio=hoy,
            fecha_termino=date(2026, 9, 12),
            fecha_entrega=hoy,
        ),
        prestamo(
            id_prestamo="VIGENTE_TERMINO",
            estado=EstadoPrestamo.ENTREGADA,
            fecha_inicio=date(2026, 9, 8),
            fecha_termino=hoy,
            fecha_entrega=date(2026, 9, 8),
        ),
        prestamo(
            id_prestamo="ATRASADO_ESTADO",
            estado=EstadoPrestamo.ATRASADA,
            fecha_inicio=date(2026, 9, 8),
            fecha_termino=date(2026, 9, 9),
            fecha_entrega=date(2026, 9, 8),
        ),
        prestamo(
            id_prestamo="ATRASADO_CALCULADO",
            estado=EstadoPrestamo.ENTREGADA,
            fecha_inicio=date(2026, 9, 7),
            fecha_termino=date(2026, 9, 9),
            fecha_entrega=date(2026, 9, 7),
        ),
        prestamo(
            id_prestamo="DEVUELTA_NO_APARECE",
            estado=EstadoPrestamo.DEVUELTA,
            fecha_inicio=date(2026, 9, 7),
            fecha_termino=date(2026, 9, 9),
            fecha_entrega=date(2026, 9, 7),
            fecha_devolucion=hoy,
        ),
    ]:
        repo_prestamos.guardar(solicitud)

    encargado = usuario("enc-1", Rol.ENCARGADO)

    assert [p.id for p in servicio.prestamos_futuros(encargado, fecha_actual=hoy)] == [
        "FUTURO"
    ]
    assert [p.id for p in servicio.prestamos_vigentes(encargado, fecha_actual=hoy)] == [
        "VIGENTE_INICIO",
        "VIGENTE_TERMINO",
    ]
    assert [p.id for p in servicio.prestamos_atrasados(encargado, fecha_actual=hoy)] == [
        "ATRASADO_ESTADO",
        "ATRASADO_CALCULADO",
    ]


def test_encargado_ve_todos_los_prestamos_en_consultas(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
) -> None:
    hoy = date(2026, 9, 10)
    repo_prestamos.guardar(
        prestamo(
            id_prestamo="SOL1",
            id_solicitante="sol-1",
            estado=EstadoPrestamo.APROBADA,
            fecha_inicio=date(2026, 9, 11),
            fecha_termino=date(2026, 9, 14),
        )
    )
    repo_prestamos.guardar(
        prestamo(
            id_prestamo="SOL2",
            id_solicitante="sol-2",
            estado=EstadoPrestamo.APROBADA,
            fecha_inicio=date(2026, 9, 11),
            fecha_termino=date(2026, 9, 14),
        )
    )

    resultado = servicio.prestamos_futuros(
        usuario("enc-1", Rol.ENCARGADO),
        fecha_actual=hoy,
    )

    assert [p.id for p in resultado] == ["SOL1", "SOL2"]


def test_consultas_aplican_filtros_por_usuario_y_equipo_para_encargado(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
) -> None:
    hoy = date(2026, 9, 10)
    repo_prestamos.guardar(
        prestamo(
            id_prestamo="SOL1_EQ1",
            id_solicitante="sol-1",
            estado=EstadoPrestamo.APROBADA,
            equipos=("EQ-01",),
            fecha_inicio=date(2026, 9, 11),
            fecha_termino=date(2026, 9, 14),
        )
    )
    repo_prestamos.guardar(
        prestamo(
            id_prestamo="SOL2_EQ1_EQ2",
            id_solicitante="sol-2",
            estado=EstadoPrestamo.APROBADA,
            equipos=("EQ-01", "EQ-02"),
            fecha_inicio=date(2026, 9, 11),
            fecha_termino=date(2026, 9, 14),
        )
    )
    repo_prestamos.guardar(
        prestamo(
            id_prestamo="SOL2_EQ3",
            id_solicitante="sol-2",
            estado=EstadoPrestamo.APROBADA,
            equipos=("EQ-03",),
            fecha_inicio=date(2026, 9, 11),
            fecha_termino=date(2026, 9, 14),
        )
    )

    resultado = servicio.prestamos_futuros(
        usuario("enc-1", Rol.ENCARGADO),
        fecha_actual=hoy,
        id_usuario="sol-2",
        codigo_equipo="EQ-02",
    )

    assert [p.id for p in resultado] == ["SOL2_EQ1_EQ2"]


def test_solicitante_solo_consulta_prestamos_propios(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
) -> None:
    hoy = date(2026, 9, 10)
    repo_prestamos.guardar(
        prestamo(
            id_prestamo="PROPIO",
            id_solicitante="sol-1",
            estado=EstadoPrestamo.APROBADA,
            fecha_inicio=date(2026, 9, 11),
            fecha_termino=date(2026, 9, 14),
        )
    )
    repo_prestamos.guardar(
        prestamo(
            id_prestamo="AJENO",
            id_solicitante="sol-2",
            estado=EstadoPrestamo.APROBADA,
            fecha_inicio=date(2026, 9, 11),
            fecha_termino=date(2026, 9, 14),
        )
    )

    assert [
        p.id for p in servicio.prestamos_futuros(usuario(), fecha_actual=hoy)
    ] == ["PROPIO"]

    with pytest.raises(ErrorAutorizacion) as exc_info:
        servicio.prestamos_futuros(
            usuario(),
            fecha_actual=hoy,
            id_usuario="sol-2",
        )

    assert exc_info.value.regla == "RN-19"
    assert "RN-19" in exc_info.value.mensaje


def test_consultas_validan_usuario_inactivo_o_ausente_y_filtros_vacios(
    servicio: ServicioPrestamos,
) -> None:
    with pytest.raises(ErrorAutorizacion) as exc_inactivo:
        servicio.prestamos_vigentes(
            Usuario(
                id="enc-1",
                nombre="Encargado",
                correo="enc-1@usm.cl",
                rol=Rol.ENCARGADO,
                activo=False,
                hash_contrasena="pbkdf2$1$sal$digest",
            ),
            fecha_actual=date(2026, 9, 10),
        )

    assert exc_inactivo.value.regla == "RN-02"

    with pytest.raises(ErrorAutorizacion) as exc_ausente:
        servicio.prestamos_futuros(
            None,
            fecha_actual=date(2026, 9, 10),
        )

    assert exc_ausente.value.regla == "RN-02"

    with pytest.raises(ErrorValidacion) as exc_equipo:
        servicio.prestamos_atrasados(
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=date(2026, 9, 10),
            codigo_equipo=" ",
        )

    assert exc_equipo.value.regla == "RN-17"

    with pytest.raises(ErrorValidacion) as exc_usuario:
        servicio.prestamos_futuros(
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=date(2026, 9, 10),
            id_usuario=" ",
        )

    assert exc_usuario.value.regla == "RN-17"


def test_consultas_no_modifican_ni_persisten_estados(
    servicio: ServicioPrestamos,
    repo_prestamos: RepositorioJson[Prestamo],
    repo_equipos: RepositorioJson[Equipo],
) -> None:
    vencido_sin_marcar = prestamo(
        id_prestamo="VENCIDO_SIN_MARCAR",
        estado=EstadoPrestamo.ENTREGADA,
        fecha_inicio=date(2026, 9, 7),
        fecha_termino=date(2026, 9, 9),
        fecha_entrega=date(2026, 9, 7),
    )
    repo_prestamos.guardar(vencido_sin_marcar)
    repo_equipos.guardar(equipo(estado=EstadoEquipo.PRESTADO))
    prestamos_antes = [p.a_dict() for p in repo_prestamos.listar()]
    equipos_antes = [e.a_dict() for e in repo_equipos.listar()]

    resultado = servicio.prestamos_atrasados(
        usuario("enc-1", Rol.ENCARGADO),
        fecha_actual=date(2026, 9, 10),
    )

    assert [p.id for p in resultado] == ["VENCIDO_SIN_MARCAR"]
    assert repo_prestamos.obtener("VENCIDO_SIN_MARCAR").estado is EstadoPrestamo.ENTREGADA
    assert [p.a_dict() for p in repo_prestamos.listar()] == prestamos_antes
    assert [e.a_dict() for e in repo_equipos.listar()] == equipos_antes
