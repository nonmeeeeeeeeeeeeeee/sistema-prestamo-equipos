"""Reglas de negocio y maquina de estados.

Contrato trazable:

- RN-01/RN-02: roles operativos y usuario activo.
- RN-05/RN-10: disponibilidad del equipo y solapamiento inclusivo.
- RN-06/RN-07: cantidad solicitada y limite de equipos activos.
- RN-08/RN-09: duracion maxima y ventana de reserva futura.
- RN-11/RN-12: aprobacion/rechazo por encargado y estado solicitada.
- RN-13/RN-14/RN-15/RN-16: entrega, devolucion, cancelacion y atraso.
- RN-17: rechazar operaciones invalidas antes de persistir.

No corresponden completamente a este modulo:

- RN-02: el inicio de sesion vive en ``auth.py``; aqui solo se valida que el
  usuario recibido este activo antes de operar.
- RN-03: estructura, obligatoriedad y unicidad de usuarios viven en
  ``modelos.py`` y en ``servicios/usuarios.py``.
- RN-04: estructura, obligatoriedad y unicidad de equipos viven en
  ``modelos.py`` y en ``servicios/equipos.py``.
- RN-06: la cardinalidad de equipos es una invariante de ``Prestamo``; aqui se
  revalida antes de crear la solicitud.
- RN-18: logs y sanitizacion de secretos viven en ``logging_conf.py`` y
  ``observabilidad.py``.

No depende de ``auth.py``: recibe usuarios ya construidos y valida aqui rol,
estado activo y propiedad de la solicitud.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Iterable, Mapping

from prestamos.errores import ErrorAutorizacion, ErrorValidacion, TransicionNoPermitida
from prestamos.modelos import (
    Equipo,
    EstadoEquipo,
    EstadoPrestamo,
    MAX_EQUIPOS_POR_SOLICITUD,
    MIN_EQUIPOS_POR_SOLICITUD,
    Prestamo,
    Rol,
    Usuario,
)

MAX_DIAS_HABILES_PRESTAMO = 5
MAX_DIAS_LABORALES_ANTICIPACION = 20
ESTADOS_DISPONIBILIDAD_BLOQUEADA = frozenset(
    {
        EstadoPrestamo.APROBADA,
        EstadoPrestamo.ENTREGADA,
        EstadoPrestamo.ATRASADA,
    }
)


class EventoTransicion(str, Enum):
    """Eventos soportados por la tabla de transiciones del contrato."""

    CREAR_SOLICITUD = "CREAR_SOLICITUD"
    APROBAR_SOLICITUD = "APROBAR_SOLICITUD"
    RECHAZAR_SOLICITUD = "RECHAZAR_SOLICITUD"
    CANCELAR_SOLICITUD = "CANCELAR_SOLICITUD"
    REGISTRAR_ENTREGA = "REGISTRAR_ENTREGA"
    MARCAR_ATRASO = "MARCAR_ATRASO"
    REGISTRAR_DEVOLUCION = "REGISTRAR_DEVOLUCION"
    REGISTRAR_DEVOLUCION_ATRASADA = "REGISTRAR_DEVOLUCION_ATRASADA"


@dataclass(frozen=True)
class Transicion:
    """Fila de docs/estados-transiciones.md traducida a codigo."""

    id: str
    origen: EstadoPrestamo | None
    evento: EventoTransicion
    destino: EstadoPrestamo
    roles: frozenset[Rol] | None
    regla_estado: str


TRANSICIONES_PERMITIDAS: dict[
    tuple[EstadoPrestamo | None, EventoTransicion], Transicion
] = {
    (
        None,
        EventoTransicion.CREAR_SOLICITUD,
    ): Transicion(
        "T-01",
        None,
        EventoTransicion.CREAR_SOLICITUD,
        EstadoPrestamo.SOLICITADA,
        frozenset({Rol.SOLICITANTE}),
        "RN-17",
    ),
    (
        EstadoPrestamo.SOLICITADA,
        EventoTransicion.APROBAR_SOLICITUD,
    ): Transicion(
        "T-02",
        EstadoPrestamo.SOLICITADA,
        EventoTransicion.APROBAR_SOLICITUD,
        EstadoPrestamo.APROBADA,
        frozenset({Rol.ENCARGADO}),
        "RN-12",
    ),
    (
        EstadoPrestamo.SOLICITADA,
        EventoTransicion.RECHAZAR_SOLICITUD,
    ): Transicion(
        "T-03",
        EstadoPrestamo.SOLICITADA,
        EventoTransicion.RECHAZAR_SOLICITUD,
        EstadoPrestamo.RECHAZADA,
        frozenset({Rol.ENCARGADO}),
        "RN-12",
    ),
    (
        EstadoPrestamo.SOLICITADA,
        EventoTransicion.CANCELAR_SOLICITUD,
    ): Transicion(
        "T-04",
        EstadoPrestamo.SOLICITADA,
        EventoTransicion.CANCELAR_SOLICITUD,
        EstadoPrestamo.CANCELADA,
        frozenset({Rol.SOLICITANTE, Rol.ENCARGADO}),
        "RN-15",
    ),
    (
        EstadoPrestamo.APROBADA,
        EventoTransicion.CANCELAR_SOLICITUD,
    ): Transicion(
        "T-05",
        EstadoPrestamo.APROBADA,
        EventoTransicion.CANCELAR_SOLICITUD,
        EstadoPrestamo.CANCELADA,
        frozenset({Rol.SOLICITANTE, Rol.ENCARGADO}),
        "RN-15",
    ),
    (
        EstadoPrestamo.APROBADA,
        EventoTransicion.REGISTRAR_ENTREGA,
    ): Transicion(
        "T-06",
        EstadoPrestamo.APROBADA,
        EventoTransicion.REGISTRAR_ENTREGA,
        EstadoPrestamo.ENTREGADA,
        frozenset({Rol.ENCARGADO}),
        "RN-13",
    ),
    (
        EstadoPrestamo.ENTREGADA,
        EventoTransicion.MARCAR_ATRASO,
    ): Transicion(
        "T-07",
        EstadoPrestamo.ENTREGADA,
        EventoTransicion.MARCAR_ATRASO,
        EstadoPrestamo.ATRASADA,
        frozenset({Rol.ENCARGADO}),
        "RN-16",
    ),
    (
        EstadoPrestamo.ENTREGADA,
        EventoTransicion.REGISTRAR_DEVOLUCION,
    ): Transicion(
        "T-08",
        EstadoPrestamo.ENTREGADA,
        EventoTransicion.REGISTRAR_DEVOLUCION,
        EstadoPrestamo.DEVUELTA,
        frozenset({Rol.ENCARGADO}),
        "RN-14",
    ),
    (
        EstadoPrestamo.ATRASADA,
        EventoTransicion.REGISTRAR_DEVOLUCION_ATRASADA,
    ): Transicion(
        "T-09",
        EstadoPrestamo.ATRASADA,
        EventoTransicion.REGISTRAR_DEVOLUCION_ATRASADA,
        EstadoPrestamo.DEVUELTA,
        frozenset({Rol.ENCARGADO}),
        "RN-14",
    ),
}

_ALIAS_EVENTOS = {
    "crear": EventoTransicion.CREAR_SOLICITUD,
    "crear solicitud": EventoTransicion.CREAR_SOLICITUD,
    "aprobar": EventoTransicion.APROBAR_SOLICITUD,
    "aprobar solicitud": EventoTransicion.APROBAR_SOLICITUD,
    "rechazar": EventoTransicion.RECHAZAR_SOLICITUD,
    "rechazar solicitud": EventoTransicion.RECHAZAR_SOLICITUD,
    "cancelar": EventoTransicion.CANCELAR_SOLICITUD,
    "cancelar solicitud": EventoTransicion.CANCELAR_SOLICITUD,
    "registrar entrega": EventoTransicion.REGISTRAR_ENTREGA,
    "entregar": EventoTransicion.REGISTRAR_ENTREGA,
    "marcar atraso": EventoTransicion.MARCAR_ATRASO,
    "vencer plazo": EventoTransicion.MARCAR_ATRASO,
    "registrar devolucion": EventoTransicion.REGISTRAR_DEVOLUCION,
    "devolver": EventoTransicion.REGISTRAR_DEVOLUCION,
    "registrar devolucion atrasada": EventoTransicion.REGISTRAR_DEVOLUCION_ATRASADA,
}


def validar_transicion(
    prestamo: Prestamo,
    evento: EventoTransicion | str,
    usuario: Usuario | None,
    *,
    fecha_actual: date | None = None,
    equipos: Mapping[str, Equipo] | Iterable[Equipo] | None = None,
    prestamos_existentes: Iterable[Prestamo] | None = None,
    solicitante: Usuario | None = None,
    motivo_rechazo: str | None = None,
    motivo_cancelacion: str | None = None,
    fecha_operacion: date | None = None,
    equipos_devueltos: Iterable[str] | None = None,
) -> Transicion:
    """Valida estado, rol y guardas antes de persistir una transicion (RN-17).

    ``prestamo``, ``evento`` y ``usuario`` son la firma base usada por los
    servicios. Los parametros opcionales permiten validar guardas que necesitan
    contexto externo, como disponibilidad, solicitante activo o devolucion
    parcial, sin acoplar este modulo a repositorios ni a ``auth.py``.
    """

    evento_normalizado = normalizar_evento(evento)
    hoy = fecha_actual or date.today()
    transicion = _obtener_transicion(prestamo, evento_normalizado)

    _validar_usuario_operador(usuario, transicion)

    if evento_normalizado is EventoTransicion.CREAR_SOLICITUD:
        existentes = _exigir_prestamos_existentes(prestamos_existentes)
        _validar_creacion(prestamo, usuario, hoy, equipos, existentes)
    elif evento_normalizado is EventoTransicion.APROBAR_SOLICITUD:
        existentes = _exigir_prestamos_existentes(prestamos_existentes)
        _validar_aprobacion(
            prestamo, usuario, hoy, equipos, existentes, solicitante
        )
    elif evento_normalizado is EventoTransicion.RECHAZAR_SOLICITUD:
        _validar_motivo(motivo_rechazo or prestamo.motivo_rechazo, "rechazo", "RN-17")
    elif evento_normalizado is EventoTransicion.CANCELAR_SOLICITUD:
        _validar_cancelacion(prestamo, usuario, motivo_cancelacion)
    elif evento_normalizado is EventoTransicion.REGISTRAR_ENTREGA:
        _validar_entrega(prestamo, equipos, fecha_operacion or hoy)
    elif evento_normalizado is EventoTransicion.MARCAR_ATRASO:
        _validar_atraso(prestamo, hoy)
    elif evento_normalizado in {
        EventoTransicion.REGISTRAR_DEVOLUCION,
        EventoTransicion.REGISTRAR_DEVOLUCION_ATRASADA,
    }:
        _validar_devolucion(prestamo, fecha_operacion or hoy, equipos_devueltos)

    return transicion


def normalizar_evento(evento: EventoTransicion | str) -> EventoTransicion:
    """Normaliza nombres de evento documentados o usados por CLI/servicios (RN-17)."""

    if isinstance(evento, EventoTransicion):
        return evento
    if not isinstance(evento, str) or not evento.strip():
        raise ErrorValidacion(
            "El evento de transicion es obligatorio.",
            regla="RN-17",
            detalles={"evento": evento},
        )

    texto = evento.strip()
    try:
        return EventoTransicion(texto)
    except ValueError:
        alias = _ALIAS_EVENTOS.get(texto.casefold().replace("_", " "))
        if alias is not None:
            return alias
        raise ErrorValidacion(
            f"El evento '{evento}' no existe en la tabla de transiciones.",
            regla="RN-17",
            detalles={
                "evento": evento,
                "eventos_validos": [miembro.value for miembro in EventoTransicion],
            },
        )


def dias_habiles(inicio: date, termino: date) -> int:
    """Cuenta dias habiles inclusivos para RN-08."""

    if inicio > termino:
        raise ErrorValidacion(
            "La fecha de inicio no puede ser posterior a la fecha de termino.",
            regla="RN-17",
            detalles={
                "fecha_inicio": inicio.isoformat(),
                "fecha_termino": termino.isoformat(),
            },
        )

    total = 0
    actual = inicio
    while actual <= termino:
        if actual.weekday() < 5:
            total += 1
        actual += timedelta(days=1)
    return total


def sumar_dias_laborales(origen: date, cantidad: int) -> date:
    """Suma dias laborales lunes-viernes para la ventana futura de RN-09."""

    if cantidad < 0:
        raise ErrorValidacion(
            "La cantidad de dias laborales no puede ser negativa.",
            regla="RN-17",
            detalles={"cantidad": cantidad},
        )
    actual = origen
    sumados = 0
    while sumados < cantidad:
        actual += timedelta(days=1)
        if actual.weekday() < 5:
            sumados += 1
    return actual


def hay_solapamiento(a_inicio: date, a_termino: date, b_inicio: date, b_termino: date) -> bool:
    """Evalua solapamiento inclusivo de rangos para RN-10."""

    return a_inicio <= b_termino and a_termino >= b_inicio


def equipo_disponible(
    equipo: Equipo,
    inicio: date,
    termino: date,
    prestamos_existentes: Iterable[Prestamo] = (),
    *,
    prestamo_actual_id: str | None = None,
    fecha_actual: date | None = None,
) -> bool:
    """Determina disponibilidad para un periodo segun RN-05 y RN-10."""

    if equipo.estado is not EstadoEquipo.DISPONIBLE:
        return False
    hoy = fecha_actual or date.today()
    try:
        if inicio > termino:
            return False
        if dias_habiles(inicio, termino) > MAX_DIAS_HABILES_PRESTAMO:
            return False
        if inicio < hoy:
            return False
        if inicio > sumar_dias_laborales(hoy, MAX_DIAS_LABORALES_ANTICIPACION):
            return False
    except ErrorValidacion:
        return False
    for existente in prestamos_existentes:
        if existente.id == prestamo_actual_id:
            continue
        if equipo.codigo not in existente.equipos:
            continue
        if existente.estado is EstadoPrestamo.ATRASADA:
            return False
        if existente.estado not in ESTADOS_DISPONIBILIDAD_BLOQUEADA:
            continue
        if hay_solapamiento(inicio, termino, existente.fecha_inicio, existente.fecha_termino):
            return False
    return True


def _obtener_transicion(prestamo: Prestamo, evento: EventoTransicion) -> Transicion:
    if evento is EventoTransicion.CREAR_SOLICITUD:
        transicion = TRANSICIONES_PERMITIDAS[(None, evento)]
        if prestamo.estado is not transicion.destino:
            _rechazar_estado(prestamo, evento, transicion.regla_estado)
        return transicion

    transicion = TRANSICIONES_PERMITIDAS.get((prestamo.estado, evento))
    if transicion is None:
        _rechazar_estado(prestamo, evento, _regla_estado_para_evento(evento))
    return transicion


def _rechazar_estado(prestamo: Prestamo, evento: EventoTransicion, regla: str) -> None:
    raise TransicionNoPermitida(
        f"La transicion {evento.value} no esta permitida desde {prestamo.estado.value} ({regla}).",
        regla=regla,
        detalles={"estado": prestamo.estado.value, "evento": evento.value},
    )


def _regla_estado_para_evento(evento: EventoTransicion) -> str:
    if evento in {
        EventoTransicion.APROBAR_SOLICITUD,
        EventoTransicion.RECHAZAR_SOLICITUD,
    }:
        return "RN-12"
    if evento is EventoTransicion.REGISTRAR_ENTREGA:
        return "RN-13"
    if evento in {
        EventoTransicion.REGISTRAR_DEVOLUCION,
        EventoTransicion.REGISTRAR_DEVOLUCION_ATRASADA,
    }:
        return "RN-14"
    if evento is EventoTransicion.CANCELAR_SOLICITUD:
        return "RN-15"
    if evento is EventoTransicion.MARCAR_ATRASO:
        return "RN-16"
    return "RN-17"


def _validar_usuario_operador(usuario: Usuario | None, transicion: Transicion) -> None:
    if usuario is None:
        if transicion.evento is EventoTransicion.MARCAR_ATRASO:
            return
        raise ErrorAutorizacion(
            "La operacion requiere un usuario autenticado (RN-02).",
            regla="RN-02",
            detalles={"transicion": transicion.id},
        )
    if not usuario.activo:
        raise ErrorAutorizacion(
            "El usuario debe estar activo para operar (RN-02).",
            regla="RN-02",
            detalles={"usuario": usuario.id, "transicion": transicion.id},
        )
    if transicion.roles is not None and usuario.rol not in transicion.roles:
        regla = "RN-11" if transicion.evento in {
            EventoTransicion.APROBAR_SOLICITUD,
            EventoTransicion.RECHAZAR_SOLICITUD,
        } else transicion.regla_estado
        raise ErrorAutorizacion(
            f"El rol {usuario.rol.value} no esta autorizado para {transicion.evento.value} ({regla}).",
            regla=regla,
            detalles={
                "usuario": usuario.id,
                "rol": usuario.rol.value,
                "roles_autorizados": [rol.value for rol in transicion.roles],
                "transicion": transicion.id,
            },
        )


def _validar_creacion(
    prestamo: Prestamo,
    usuario: Usuario | None,
    hoy: date,
    equipos: Mapping[str, Equipo] | Iterable[Equipo] | None,
    prestamos_existentes: Iterable[Prestamo],
) -> None:
    if usuario is not None and usuario.id != prestamo.id_solicitante:
        raise ErrorAutorizacion(
            "El solicitante solo puede crear solicitudes propias (RN-17).",
            regla="RN-17",
            detalles={"usuario": usuario.id, "id_solicitante": prestamo.id_solicitante},
        )
    _validar_motivo(prestamo.motivo, "solicitud", "RN-17")
    _validar_cantidad_equipos(prestamo)
    _validar_fechas_reserva(prestamo, hoy)
    _validar_equipos_y_disponibilidad(
        prestamo, equipos, prestamos_existentes, "RN-05", hoy
    )
    _validar_limite_equipos_activos(prestamo, prestamos_existentes)


def _validar_aprobacion(
    prestamo: Prestamo,
    usuario: Usuario | None,
    hoy: date,
    equipos: Mapping[str, Equipo] | Iterable[Equipo] | None,
    prestamos_existentes: Iterable[Prestamo],
    solicitante: Usuario | None,
) -> None:
    del usuario
    if solicitante is None:
        raise ErrorValidacion(
            "Falta el solicitante para validar usuario activo antes de aprobar (RN-17/RN-02).",
            regla="RN-17",
            detalles={"contexto_requerido": "solicitante", "regla_validada": "RN-02"},
        )
    if not solicitante.activo:
        raise ErrorValidacion(
            "El solicitante debe estar activo para aprobar la solicitud (RN-02).",
            regla="RN-02",
            detalles={"id_solicitante": solicitante.id},
        )
    _validar_fechas_reserva(prestamo, hoy, validar_inicio_pasado=False)
    _validar_equipos_y_disponibilidad(
        prestamo, equipos, prestamos_existentes, "RN-10", hoy
    )
    _validar_limite_equipos_activos(prestamo, prestamos_existentes)


def _validar_cancelacion(
    prestamo: Prestamo,
    usuario: Usuario | None,
    motivo_cancelacion: str | None,
) -> None:
    if prestamo.fecha_entrega is not None:
        raise ErrorValidacion(
            "No se puede cancelar una solicitud con entrega registrada (RN-15).",
            regla="RN-15",
            detalles={"prestamo": prestamo.id, "fecha_entrega": prestamo.fecha_entrega.isoformat()},
        )
    if usuario is None:
        raise ErrorAutorizacion(
            "La cancelacion requiere un usuario autenticado (RN-02).",
            regla="RN-02",
            detalles={"prestamo": prestamo.id},
        )
    if usuario.rol is Rol.SOLICITANTE and usuario.id != prestamo.id_solicitante:
        raise ErrorAutorizacion(
            "El solicitante solo puede cancelar sus propias solicitudes (RN-15).",
            regla="RN-15",
            detalles={"usuario": usuario.id, "id_solicitante": prestamo.id_solicitante},
        )
    _validar_motivo(
        motivo_cancelacion or prestamo.motivo_cancelacion, "cancelacion", "RN-15"
    )


def _validar_entrega(
    prestamo: Prestamo,
    equipos: Mapping[str, Equipo] | Iterable[Equipo] | None,
    fecha_entrega: date,
) -> None:
    if prestamo.fecha_aprobacion is not None and fecha_entrega < prestamo.fecha_aprobacion:
        raise ErrorValidacion(
            "La fecha de entrega no puede ser anterior a la aprobacion (RN-13).",
            regla="RN-13",
            detalles={
                "prestamo": prestamo.id,
                "fecha_aprobacion": prestamo.fecha_aprobacion.isoformat(),
                "fecha_entrega": fecha_entrega.isoformat(),
            },
        )
    catalogo = _normalizar_catalogo(equipos)
    for codigo in prestamo.equipos:
        equipo = catalogo.get(codigo)
        if equipo is None:
            raise ErrorValidacion(
                f"El equipo {codigo} no existe (RN-17).",
                regla="RN-17",
                detalles={"equipo": codigo},
            )
        if equipo.estado in {
            EstadoEquipo.PRESTADO,
            EstadoEquipo.MANTENCION,
            EstadoEquipo.BAJA,
        }:
            raise ErrorValidacion(
                f"El equipo {codigo} no esta disponible fisicamente (RN-13).",
                regla="RN-13",
                detalles={"equipo": codigo, "estado": equipo.estado.value},
            )


def _validar_atraso(prestamo: Prestamo, hoy: date) -> None:
    if prestamo.fecha_devolucion is not None:
        raise ErrorValidacion(
            "No se puede marcar atraso si ya existe devolucion registrada (RN-16).",
            regla="RN-16",
            detalles={"prestamo": prestamo.id},
        )
    if hoy <= prestamo.fecha_termino:
        raise ErrorValidacion(
            "El prestamo solo queda atrasado desde el dia posterior al termino (RN-16).",
            regla="RN-16",
            detalles={
                "prestamo": prestamo.id,
                "fecha_actual": hoy.isoformat(),
                "fecha_termino": prestamo.fecha_termino.isoformat(),
            },
        )


def _validar_devolucion(
    prestamo: Prestamo,
    fecha_devolucion: date,
    equipos_devueltos: Iterable[str] | None,
) -> None:
    if prestamo.fecha_entrega is not None and fecha_devolucion < prestamo.fecha_entrega:
        raise ErrorValidacion(
            "La fecha de devolucion no puede ser anterior a la entrega (RN-14).",
            regla="RN-14",
            detalles={
                "prestamo": prestamo.id,
                "fecha_entrega": prestamo.fecha_entrega.isoformat(),
                "fecha_devolucion": fecha_devolucion.isoformat(),
            },
        )
    if equipos_devueltos is None:
        raise ErrorValidacion(
            "Falta la lista de equipos devueltos para validar devolucion completa (RN-17/RN-14).",
            regla="RN-17",
            detalles={
                "contexto_requerido": "equipos_devueltos",
                "regla_validada": "RN-14",
            },
        )
    devueltos = set(equipos_devueltos)
    esperados = set(prestamo.equipos)
    if devueltos != esperados:
        raise ErrorValidacion(
            "Deben devolverse todos los equipos del prestamo (RN-14).",
            regla="RN-14",
            detalles={
                "faltantes": sorted(esperados - devueltos),
                "no_esperados": sorted(devueltos - esperados),
            },
        )


def _validar_cantidad_equipos(prestamo: Prestamo) -> None:
    cantidad = len(prestamo.equipos)
    if not MIN_EQUIPOS_POR_SOLICITUD <= cantidad <= MAX_EQUIPOS_POR_SOLICITUD:
        raise ErrorValidacion(
            "Una solicitud debe incluir entre 1 y 3 equipos (RN-06).",
            regla="RN-06",
            detalles={"cantidad": cantidad},
        )
    if len(set(prestamo.equipos)) != cantidad:
        raise ErrorValidacion(
            "Una solicitud no puede repetir equipos (RN-06).",
            regla="RN-06",
            detalles={"equipos": list(prestamo.equipos)},
        )


def _validar_fechas_reserva(
    prestamo: Prestamo,
    hoy: date,
    *,
    validar_inicio_pasado: bool = True,
) -> None:
    if prestamo.fecha_inicio > prestamo.fecha_termino:
        raise ErrorValidacion(
            "La fecha de inicio no puede ser posterior a la fecha de termino (RN-17).",
            regla="RN-17",
            detalles={
                "fecha_inicio": prestamo.fecha_inicio.isoformat(),
                "fecha_termino": prestamo.fecha_termino.isoformat(),
            },
        )
    if dias_habiles(prestamo.fecha_inicio, prestamo.fecha_termino) > MAX_DIAS_HABILES_PRESTAMO:
        raise ErrorValidacion(
            "La duracion del prestamo no puede superar 5 dias habiles (RN-08).",
            regla="RN-08",
            detalles={
                "fecha_inicio": prestamo.fecha_inicio.isoformat(),
                "fecha_termino": prestamo.fecha_termino.isoformat(),
            },
        )
    if validar_inicio_pasado and prestamo.fecha_inicio < hoy:
        raise ErrorValidacion(
            "La fecha de inicio no puede estar en el pasado (RN-09).",
            regla="RN-09",
            detalles={"fecha_inicio": prestamo.fecha_inicio.isoformat(), "fecha_actual": hoy.isoformat()},
        )
    limite = sumar_dias_laborales(hoy, MAX_DIAS_LABORALES_ANTICIPACION)
    if prestamo.fecha_inicio > limite:
        raise ErrorValidacion(
            "La fecha de inicio no puede superar 20 dias laborales de anticipacion (RN-09).",
            regla="RN-09",
            detalles={"fecha_inicio": prestamo.fecha_inicio.isoformat(), "limite": limite.isoformat()},
        )


def _validar_equipos_y_disponibilidad(
    prestamo: Prestamo,
    equipos: Mapping[str, Equipo] | Iterable[Equipo] | None,
    prestamos_existentes: Iterable[Prestamo],
    regla_solapamiento: str,
    hoy: date,
) -> None:
    catalogo = _normalizar_catalogo(equipos)
    for codigo in prestamo.equipos:
        equipo = catalogo.get(codigo)
        if equipo is None:
            raise ErrorValidacion(
                f"El equipo {codigo} no existe (RN-17).",
                regla="RN-17",
                detalles={"equipo": codigo},
            )
        if equipo.estado is not EstadoEquipo.DISPONIBLE:
            raise ErrorValidacion(
                f"El equipo {codigo} no esta disponible (RN-05).",
                regla="RN-05",
                detalles={"equipo": codigo, "estado": equipo.estado.value},
            )
        if not equipo_disponible(
            equipo,
            prestamo.fecha_inicio,
            prestamo.fecha_termino,
            prestamos_existentes,
            prestamo_actual_id=prestamo.id,
            fecha_actual=hoy,
        ):
            raise ErrorValidacion(
                f"El equipo {codigo} no esta disponible para el periodo solicitado ({regla_solapamiento}).",
                regla=regla_solapamiento,
                detalles={
                    "equipo": codigo,
                    "fecha_inicio": prestamo.fecha_inicio.isoformat(),
                    "fecha_termino": prestamo.fecha_termino.isoformat(),
                },
            )


def _validar_limite_equipos_activos(
    prestamo: Prestamo,
    prestamos_existentes: Iterable[Prestamo],
) -> None:
    activos = 0
    for existente in prestamos_existentes:
        if existente.id == prestamo.id:
            continue
        if existente.id_solicitante != prestamo.id_solicitante:
            continue
        if existente.estado in ESTADOS_DISPONIBILIDAD_BLOQUEADA:
            activos += len(existente.equipos)
    total = activos + len(prestamo.equipos)
    if total > MAX_EQUIPOS_POR_SOLICITUD:
        raise ErrorValidacion(
            "El solicitante no puede superar 3 equipos activos (RN-07).",
            regla="RN-07",
            detalles={
                "id_solicitante": prestamo.id_solicitante,
                "equipos_activos": activos,
                "equipos_solicitados": len(prestamo.equipos),
                "total": total,
            },
        )


def _validar_motivo(motivo: str | None, nombre: str, regla: str) -> None:
    if not isinstance(motivo, str) or not motivo.strip():
        raise ErrorValidacion(
            f"El motivo de {nombre} es obligatorio ({regla}).",
            regla=regla,
            detalles={"campo": f"motivo_{nombre}"},
        )


def _exigir_prestamos_existentes(
    prestamos_existentes: Iterable[Prestamo] | None,
) -> tuple[Prestamo, ...]:
    if prestamos_existentes is None:
        raise ErrorValidacion(
            "Falta el contexto de prestamos existentes para validar disponibilidad y limite activo (RN-17/RN-07/RN-10).",
            regla="RN-17",
            detalles={
                "contexto_requerido": "prestamos_existentes",
                "reglas_validadas": ["RN-07", "RN-10"],
            },
        )
    return tuple(prestamos_existentes)


def _normalizar_catalogo(
    equipos: Mapping[str, Equipo] | Iterable[Equipo] | None,
) -> dict[str, Equipo] | None:
    if equipos is None:
        raise ErrorValidacion(
            "Falta el catalogo de equipos para validar existencia y disponibilidad (RN-17/RN-05).",
            regla="RN-17",
            detalles={
                "contexto_requerido": "equipos",
                "reglas_validadas": ["RN-05", "RN-10"],
            },
        )
    if isinstance(equipos, Mapping):
        return dict(equipos)
    return {equipo.codigo: equipo for equipo in equipos}
