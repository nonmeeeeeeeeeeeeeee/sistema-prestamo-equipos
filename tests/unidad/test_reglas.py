"""Pruebas unitarias del motor de reglas y transiciones (issue #9)."""

from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import date

import pytest

import prestamos.reglas as reglas
from prestamos.errores import ErrorAutorizacion, ErrorValidacion, TransicionNoPermitida
from prestamos.modelos import Equipo, EstadoEquipo, EstadoPrestamo, Prestamo, Rol, Usuario
from prestamos.reglas import (
    EventoTransicion,
    TRANSICIONES_PERMITIDAS,
    validar_transicion,
)


HOY = date(2026, 9, 7)


def usuario(
    id_usuario: str = "sol-1",
    rol: Rol = Rol.SOLICITANTE,
    *,
    activo: bool = True,
) -> Usuario:
    return Usuario(
        id=id_usuario,
        nombre="Usuario de prueba",
        correo=f"{id_usuario}@usm.cl",
        rol=rol,
        activo=activo,
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
    equipos: tuple[str, ...] = ("EQ-01",),
    estado: EstadoPrestamo = EstadoPrestamo.SOLICITADA,
    fecha_inicio: date = date(2026, 9, 8),
    fecha_termino: date = date(2026, 9, 10),
    fecha_aprobacion: date | None = None,
    fecha_entrega: date | None = None,
    fecha_devolucion: date | None = None,
    motivo_rechazo: str | None = None,
    motivo_cancelacion: str | None = None,
) -> Prestamo:
    return Prestamo(
        id=id_prestamo,
        id_solicitante=id_solicitante,
        equipos=equipos,
        motivo="Proyecto de electronica",
        estado=estado,
        fecha_solicitud=HOY,
        fecha_inicio=fecha_inicio,
        fecha_termino=fecha_termino,
        fecha_aprobacion=fecha_aprobacion,
        fecha_entrega=fecha_entrega,
        fecha_devolucion=fecha_devolucion,
        motivo_rechazo=motivo_rechazo,
        motivo_cancelacion=motivo_cancelacion,
    )


def test_tabla_contiene_las_nueve_transiciones_documentadas() -> None:
    assert {transicion.id for transicion in TRANSICIONES_PERMITIDAS.values()} == {
        "T-01",
        "T-02",
        "T-03",
        "T-04",
        "T-05",
        "T-06",
        "T-07",
        "T-08",
        "T-09",
    }
    assert (
        TRANSICIONES_PERMITIDAS[
            (EstadoPrestamo.SOLICITADA, EventoTransicion.APROBAR_SOLICITUD)
        ].destino
        is EstadoPrestamo.APROBADA
    )


def test_transiciones_t01_a_t09_tienen_casos_exitosos() -> None:
    casos = [
        (
            "T-01",
            prestamo(),
            EventoTransicion.CREAR_SOLICITUD,
            usuario(),
            {
                "fecha_actual": HOY,
                "equipos": [equipo()],
                "prestamos_existentes": [],
            },
        ),
        (
            "T-02",
            prestamo(),
            EventoTransicion.APROBAR_SOLICITUD,
            usuario("enc-1", Rol.ENCARGADO),
            {
                "fecha_actual": HOY,
                "equipos": [equipo()],
                "prestamos_existentes": [],
                "solicitante": usuario(),
            },
        ),
        (
            "T-03",
            prestamo(),
            EventoTransicion.RECHAZAR_SOLICITUD,
            usuario("enc-1", Rol.ENCARGADO),
            {"fecha_actual": HOY, "motivo_rechazo": "No cumple prioridad"},
        ),
        (
            "T-04",
            prestamo(),
            EventoTransicion.CANCELAR_SOLICITUD,
            usuario(),
            {"fecha_actual": HOY, "motivo_cancelacion": "Ya no se requiere"},
        ),
        (
            "T-05",
            prestamo(estado=EstadoPrestamo.APROBADA),
            EventoTransicion.CANCELAR_SOLICITUD,
            usuario(),
            {"fecha_actual": HOY, "motivo_cancelacion": "Cambio de plan"},
        ),
        (
            "T-06",
            prestamo(
                estado=EstadoPrestamo.APROBADA,
                fecha_aprobacion=date(2026, 9, 7),
            ),
            EventoTransicion.REGISTRAR_ENTREGA,
            usuario("enc-1", Rol.ENCARGADO),
            {
                "fecha_actual": HOY,
                "fecha_operacion": date(2026, 9, 8),
                "equipos": [equipo()],
            },
        ),
        (
            "T-07",
            prestamo(
                estado=EstadoPrestamo.ENTREGADA,
                fecha_termino=date(2026, 9, 8),
            ),
            EventoTransicion.MARCAR_ATRASO,
            None,
            {"fecha_actual": date(2026, 9, 9)},
        ),
        (
            "T-08",
            prestamo(
                estado=EstadoPrestamo.ENTREGADA,
                fecha_entrega=date(2026, 9, 8),
            ),
            EventoTransicion.REGISTRAR_DEVOLUCION,
            usuario("enc-1", Rol.ENCARGADO),
            {
                "fecha_actual": HOY,
                "fecha_operacion": date(2026, 9, 10),
                "equipos_devueltos": ["EQ-01"],
            },
        ),
        (
            "T-09",
            prestamo(
                estado=EstadoPrestamo.ATRASADA,
                fecha_entrega=date(2026, 9, 8),
            ),
            EventoTransicion.REGISTRAR_DEVOLUCION_ATRASADA,
            usuario("enc-1", Rol.ENCARGADO),
            {
                "fecha_actual": date(2026, 9, 12),
                "fecha_operacion": date(2026, 9, 12),
                "equipos_devueltos": ["EQ-01"],
            },
        ),
    ]

    for id_transicion, solicitud, evento, operador, contexto in casos:
        transicion = validar_transicion(solicitud, evento, operador, **contexto)

        assert transicion.id == id_transicion


def test_validar_transicion_no_depende_de_auth_py() -> None:
    assert "prestamos.auth" not in inspect.getsource(reglas)


def test_crear_solicitud_valida_estado_rol_fechas_equipos_y_limite() -> None:
    transicion = validar_transicion(
        prestamo(equipos=("EQ-01", "EQ-02")),
        "crear solicitud",
        usuario(),
        fecha_actual=HOY,
        equipos=[equipo("EQ-01"), equipo("EQ-02")],
        prestamos_existentes=[
            prestamo(
                id_prestamo="P-00",
                equipos=("EQ-03",),
                estado=EstadoPrestamo.DEVUELTA,
            )
        ],
    )

    assert transicion.id == "T-01"
    assert transicion.destino is EstadoPrestamo.SOLICITADA


def test_crear_solicitud_rechaza_equipo_no_disponible_con_rn05() -> None:
    with pytest.raises(ErrorValidacion) as exc_info:
        validar_transicion(
            prestamo(),
            EventoTransicion.CREAR_SOLICITUD,
            usuario(),
            fecha_actual=HOY,
            equipos=[equipo(estado=EstadoEquipo.MANTENCION)],
            prestamos_existentes=[],
        )

    assert exc_info.value.regla == "RN-05"
    assert "RN-05" in exc_info.value.mensaje


def test_crear_solicitud_rechaza_mas_de_tres_equipos_activos_con_rn07() -> None:
    with pytest.raises(ErrorValidacion) as exc_info:
        validar_transicion(
            prestamo(equipos=("EQ-01", "EQ-02")),
            EventoTransicion.CREAR_SOLICITUD,
            usuario(),
            fecha_actual=HOY,
            equipos=[equipo("EQ-01"), equipo("EQ-02")],
            prestamos_existentes=[
                prestamo(
                    id_prestamo="P-00",
                    equipos=("EQ-03", "EQ-04"),
                    estado=EstadoPrestamo.APROBADA,
                )
            ],
        )

    assert exc_info.value.regla == "RN-07"
    assert "RN-07" in exc_info.value.mensaje


def test_crear_solicitud_rechaza_duracion_mayor_a_cinco_habiles_con_rn08() -> None:
    with pytest.raises(ErrorValidacion) as exc_info:
        validar_transicion(
            prestamo(fecha_inicio=date(2026, 9, 7), fecha_termino=date(2026, 9, 15)),
            EventoTransicion.CREAR_SOLICITUD,
            usuario(),
            fecha_actual=HOY,
            prestamos_existentes=[],
        )

    assert exc_info.value.regla == "RN-08"
    assert "RN-08" in exc_info.value.mensaje


def test_crear_solicitud_rechaza_inicio_fuera_de_ventana_con_rn09() -> None:
    with pytest.raises(ErrorValidacion) as exc_info:
        validar_transicion(
            prestamo(fecha_inicio=date(2026, 10, 6), fecha_termino=date(2026, 10, 7)),
            EventoTransicion.CREAR_SOLICITUD,
            usuario(),
            fecha_actual=HOY,
            prestamos_existentes=[],
        )

    assert exc_info.value.regla == "RN-09"
    assert "RN-09" in exc_info.value.mensaje


def test_aprobar_revalida_disponibilidad_y_solapamiento_con_rn10() -> None:
    with pytest.raises(ErrorValidacion) as exc_info:
        validar_transicion(
            prestamo(),
            EventoTransicion.APROBAR_SOLICITUD,
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=HOY,
            equipos=[equipo()],
            prestamos_existentes=[
                prestamo(
                    id_prestamo="P-00",
                    estado=EstadoPrestamo.APROBADA,
                    fecha_inicio=date(2026, 9, 10),
                    fecha_termino=date(2026, 9, 11),
                )
            ],
            solicitante=usuario(),
        )

    assert exc_info.value.regla == "RN-10"
    assert "RN-10" in exc_info.value.mensaje


def test_aprobar_rechaza_usuario_sin_rol_encargado_con_rn11() -> None:
    with pytest.raises(ErrorAutorizacion) as exc_info:
        validar_transicion(
            prestamo(),
            EventoTransicion.APROBAR_SOLICITUD,
            usuario(rol=Rol.SOLICITANTE),
            fecha_actual=HOY,
        )

    assert exc_info.value.regla == "RN-11"
    assert "RN-11" in exc_info.value.mensaje


def test_aprobar_estado_no_solicitado_falla_con_rn12() -> None:
    with pytest.raises(TransicionNoPermitida) as exc_info:
        validar_transicion(
            prestamo(estado=EstadoPrestamo.APROBADA),
            EventoTransicion.APROBAR_SOLICITUD,
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=HOY,
        )

    assert exc_info.value.regla == "RN-12"
    assert "RN-12" in exc_info.value.mensaje


def test_rechazar_exige_motivo_con_rn17() -> None:
    with pytest.raises(ErrorValidacion) as exc_info:
        validar_transicion(
            prestamo(),
            EventoTransicion.RECHAZAR_SOLICITUD,
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=HOY,
        )

    assert exc_info.value.regla == "RN-17"
    assert "RN-17" in exc_info.value.mensaje


def test_cancelar_permite_solicitante_dueno_y_bloquea_terceros_con_rn15() -> None:
    valida = validar_transicion(
        prestamo(),
        EventoTransicion.CANCELAR_SOLICITUD,
        usuario(),
        fecha_actual=HOY,
        motivo_cancelacion="Ya no se usara",
    )
    assert valida.id == "T-04"

    with pytest.raises(ErrorAutorizacion) as exc_info:
        validar_transicion(
            prestamo(),
            EventoTransicion.CANCELAR_SOLICITUD,
            usuario("otro-sol", Rol.SOLICITANTE),
            fecha_actual=HOY,
        )

    assert exc_info.value.regla == "RN-15"
    assert "RN-15" in exc_info.value.mensaje


def test_cancelar_por_encargado_exige_motivo_con_rn15() -> None:
    with pytest.raises(ErrorValidacion) as exc_info:
        validar_transicion(
            prestamo(),
            EventoTransicion.CANCELAR_SOLICITUD,
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=HOY,
        )

    assert exc_info.value.regla == "RN-15"
    assert "RN-15" in exc_info.value.mensaje


def test_entrega_exige_aprobada_y_fecha_no_anterior_a_aprobacion_con_rn13() -> None:
    with pytest.raises(TransicionNoPermitida) as exc_estado:
        validar_transicion(
            prestamo(estado=EstadoPrestamo.SOLICITADA),
            EventoTransicion.REGISTRAR_ENTREGA,
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=HOY,
        )

    assert exc_estado.value.regla == "RN-13"

    with pytest.raises(ErrorValidacion) as exc_fecha:
        validar_transicion(
            prestamo(
                estado=EstadoPrestamo.APROBADA,
                fecha_aprobacion=date(2026, 9, 9),
            ),
            EventoTransicion.REGISTRAR_ENTREGA,
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=HOY,
            fecha_operacion=date(2026, 9, 8),
        )

    assert exc_fecha.value.regla == "RN-13"
    assert "RN-13" in exc_fecha.value.mensaje


def test_devolucion_exige_estado_y_todos_los_equipos_con_rn14() -> None:
    with pytest.raises(TransicionNoPermitida) as exc_estado:
        validar_transicion(
            prestamo(estado=EstadoPrestamo.APROBADA),
            EventoTransicion.REGISTRAR_DEVOLUCION,
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=HOY,
        )

    assert exc_estado.value.regla == "RN-14"

    with pytest.raises(ErrorValidacion) as exc_equipos:
        validar_transicion(
            prestamo(
                equipos=("EQ-01", "EQ-02"),
                estado=EstadoPrestamo.ENTREGADA,
                fecha_entrega=date(2026, 9, 8),
            ),
            EventoTransicion.REGISTRAR_DEVOLUCION,
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=HOY,
            fecha_operacion=date(2026, 9, 10),
            equipos_devueltos=["EQ-01"],
        )

    assert exc_equipos.value.regla == "RN-14"
    assert "RN-14" in exc_equipos.value.mensaje


def test_cancelar_entregada_no_esta_permitido_con_rn15() -> None:
    with pytest.raises(TransicionNoPermitida) as exc_info:
        validar_transicion(
            prestamo(estado=EstadoPrestamo.ENTREGADA),
            EventoTransicion.CANCELAR_SOLICITUD,
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=HOY,
        )

    assert exc_info.value.regla == "RN-15"
    assert "RN-15" in exc_info.value.mensaje


def test_marcar_atraso_solo_despues_del_dia_de_termino_con_rn16() -> None:
    dentro_de_plazo = prestamo(
        estado=EstadoPrestamo.ENTREGADA,
        fecha_termino=date(2026, 9, 10),
    )
    with pytest.raises(ErrorValidacion) as exc_info:
        validar_transicion(
            dentro_de_plazo,
            EventoTransicion.MARCAR_ATRASO,
            None,
            fecha_actual=date(2026, 9, 10),
        )

    assert exc_info.value.regla == "RN-16"
    assert "RN-16" in exc_info.value.mensaje

    transicion = validar_transicion(
        dentro_de_plazo,
        EventoTransicion.MARCAR_ATRASO,
        None,
        fecha_actual=date(2026, 9, 11),
    )
    assert transicion.id == "T-07"


def test_usuario_inactivo_no_puede_operar_con_rn02() -> None:
    with pytest.raises(ErrorAutorizacion) as exc_info:
        validar_transicion(
            prestamo(),
            EventoTransicion.CREAR_SOLICITUD,
            usuario(activo=False),
            fecha_actual=HOY,
        )

    assert exc_info.value.regla == "RN-02"
    assert "RN-02" in exc_info.value.mensaje


def test_equipo_atrasado_bloquea_disponibilidad_sin_importar_el_rango() -> None:
    disponible = reglas.equipo_disponible(
        equipo(),
        date(2026, 10, 1),
        date(2026, 10, 2),
        prestamos_existentes=[
            prestamo(
                id_prestamo="P-00",
                estado=EstadoPrestamo.ATRASADA,
                fecha_inicio=date(2026, 9, 1),
                fecha_termino=date(2026, 9, 3),
            )
        ],
    )

    assert disponible is False


def test_solapamiento_es_inclusivo() -> None:
    assert reglas.hay_solapamiento(
        date(2026, 9, 3),
        date(2026, 9, 4),
        date(2026, 9, 1),
        date(2026, 9, 3),
    )
    assert not reglas.hay_solapamiento(
        date(2026, 9, 4),
        date(2026, 9, 5),
        date(2026, 9, 1),
        date(2026, 9, 3),
    )


def test_validar_transicion_no_muta_el_prestamo() -> None:
    original = prestamo()
    copia = replace(original)

    validar_transicion(
        original,
        EventoTransicion.APROBAR_SOLICITUD,
        usuario("enc-1", Rol.ENCARGADO),
        fecha_actual=HOY,
        equipos=[equipo()],
        prestamos_existentes=[],
        solicitante=usuario(),
    )

    assert original == copia


def test_crear_y_aprobar_exigen_contexto_para_guardas_de_disponibilidad() -> None:
    with pytest.raises(ErrorValidacion) as exc_prestamos:
        validar_transicion(
            prestamo(),
            EventoTransicion.CREAR_SOLICITUD,
            usuario(),
            fecha_actual=HOY,
            equipos=[equipo()],
        )

    assert exc_prestamos.value.regla == "RN-17"
    assert exc_prestamos.value.detalles["contexto_requerido"] == "prestamos_existentes"

    with pytest.raises(ErrorValidacion) as exc_equipos:
        validar_transicion(
            prestamo(),
            EventoTransicion.CREAR_SOLICITUD,
            usuario(),
            fecha_actual=HOY,
            prestamos_existentes=[],
        )

    assert exc_equipos.value.regla == "RN-17"
    assert exc_equipos.value.detalles["contexto_requerido"] == "equipos"

    with pytest.raises(ErrorValidacion) as exc_solicitante:
        validar_transicion(
            prestamo(),
            EventoTransicion.APROBAR_SOLICITUD,
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=HOY,
            equipos=[equipo()],
            prestamos_existentes=[],
        )

    assert exc_solicitante.value.regla == "RN-17"
    assert exc_solicitante.value.detalles["contexto_requerido"] == "solicitante"


def test_entrega_y_devolucion_exigen_contexto_para_guardas_propias() -> None:
    with pytest.raises(ErrorValidacion) as exc_equipos:
        validar_transicion(
            prestamo(
                estado=EstadoPrestamo.APROBADA,
                fecha_aprobacion=date(2026, 9, 7),
            ),
            EventoTransicion.REGISTRAR_ENTREGA,
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=HOY,
            fecha_operacion=date(2026, 9, 8),
        )

    assert exc_equipos.value.regla == "RN-17"
    assert exc_equipos.value.detalles["contexto_requerido"] == "equipos"

    with pytest.raises(ErrorValidacion) as exc_devueltos:
        validar_transicion(
            prestamo(
                estado=EstadoPrestamo.ENTREGADA,
                fecha_entrega=date(2026, 9, 8),
            ),
            EventoTransicion.REGISTRAR_DEVOLUCION,
            usuario("enc-1", Rol.ENCARGADO),
            fecha_actual=HOY,
            fecha_operacion=date(2026, 9, 10),
        )

    assert exc_devueltos.value.regla == "RN-17"
    assert exc_devueltos.value.detalles["contexto_requerido"] == "equipos_devueltos"
