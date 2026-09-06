"""Entidades del dominio: Usuario, Equipo y Prestamo.

Contrato de referencia:

- ``docs/analisis-requerimiento.md`` (AMB-XX, RF-XX)
- ``docs/reglas-negocio.md`` (RN-XX)
- ``docs/estados-transiciones.md`` (estados, transiciones y disponibilidad)

Este modulo define unicamente estructura, validacion de tipos y serializacion
hacia/desde la capa JSON. No implementa logica de negocio: las transiciones, el
calculo de disponibilidad y los limites por persona viven en ``prestamos.reglas``
y en los servicios.

Las tres entidades son inmutables (``frozen=True``). Una transicion produce una
instancia nueva mediante ``dataclasses.replace``; asi una guarda incumplida no
puede dejar un objeto a medio modificar, tal como exige la seccion 2 de
``docs/estados-transiciones.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Self

from prestamos.errores import ErrorValidacion

MIN_EQUIPOS_POR_SOLICITUD = 1
MAX_EQUIPOS_POR_SOLICITUD = 3


class Rol(str, Enum):
    """Roles operativos del sistema (RN-01, AMB-02).

    No existen mas roles: el rol "Sistema" que aparece en la transicion T-07 del
    contrato representa una evaluacion temporal, no un usuario.
    """

    SOLICITANTE = "SOLICITANTE"
    ENCARGADO = "ENCARGADO"


class EstadoEquipo(str, Enum):
    """Estado operativo del equipo (RN-04, AMB-04)."""

    DISPONIBLE = "DISPONIBLE"
    RESERVADO = "RESERVADO"
    PRESTADO = "PRESTADO"
    MANTENCION = "MANTENCION"
    BAJA = "BAJA"


class EstadoPrestamo(str, Enum):
    """Estados de la solicitud/prestamo (docs/estados-transiciones.md, seccion 1).

    Se conservan los nombres femeninos del contrato para que una busqueda por
    ``APROBADA`` lleve directamente de la tabla de transiciones al codigo.
    """

    SOLICITADA = "SOLICITADA"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    CANCELADA = "CANCELADA"
    ENTREGADA = "ENTREGADA"
    ATRASADA = "ATRASADA"
    DEVUELTA = "DEVUELTA"


def _texto_obligatorio(valor: Any, campo: str, regla: str) -> None:
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorValidacion(
            f"El campo '{campo}' es obligatorio y no puede estar vacio.",
            regla=regla,
            detalles={"campo": campo},
        )


def _texto_opcional(valor: Any, campo: str, regla: str) -> None:
    if valor is None:
        return
    _texto_obligatorio(valor, campo, regla)


def _valor_de_enum(valor: Any, tipo: type[Enum], campo: str, regla: str) -> None:
    if not isinstance(valor, tipo):
        raise ErrorValidacion(
            f"El campo '{campo}' debe ser un {tipo.__name__} valido.",
            regla=regla,
            detalles={"campo": campo, "valores_validos": [m.value for m in tipo]},
        )


def _fecha_obligatoria(valor: Any, campo: str, regla: str) -> None:
    # datetime hereda de date: se rechaza explicitamente porque todo el contrato
    # razona por dias completos (rangos inclusivos, T-07).
    if not isinstance(valor, date) or isinstance(valor, datetime):
        raise ErrorValidacion(
            f"El campo '{campo}' debe ser una fecha (date) valida.",
            regla=regla,
            detalles={"campo": campo},
        )


def _fecha_opcional(valor: Any, campo: str, regla: str) -> None:
    if valor is None:
        return
    _fecha_obligatoria(valor, campo, regla)


def _enum_desde_texto(valor: Any, tipo: type[Enum], campo: str, regla: str) -> Any:
    try:
        return tipo(valor)
    except ValueError as exc:
        raise ErrorValidacion(
            f"El valor de '{campo}' no corresponde a un {tipo.__name__} valido.",
            regla=regla,
            detalles={
                "campo": campo,
                "recibido": valor,
                "valores_validos": [m.value for m in tipo],
            },
        ) from exc


def _fecha_desde_texto(valor: Any, campo: str, regla: str) -> date | None:
    if valor is None:
        return None
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError) as exc:
        raise ErrorValidacion(
            f"El campo '{campo}' debe venir como fecha ISO 'AAAA-MM-DD'.",
            regla=regla,
            detalles={"campo": campo, "recibido": valor},
        ) from exc


def _fecha_a_texto(valor: date | None) -> str | None:
    return valor.isoformat() if valor is not None else None


def _validar_claves(datos: Any, esperadas: frozenset[str], entidad: str) -> None:
    """Valida el diccionario crudo antes de construir la entidad (RN-17).

    ``desde_dict`` es la frontera de confianza con los archivos JSON, por eso
    tambien se rechazan claves desconocidas: una clave mal escrita en los datos
    de demostracion se cargaria como ``None`` sin aviso.
    """
    if not isinstance(datos, dict):
        raise ErrorValidacion(
            f"Los datos de {entidad} deben ser un objeto JSON.",
            regla="RN-17",
            detalles={"entidad": entidad, "tipo_recibido": type(datos).__name__},
        )
    recibidas = set(datos)
    faltantes = sorted(esperadas - recibidas)
    desconocidas = sorted(recibidas - esperadas)
    if faltantes or desconocidas:
        raise ErrorValidacion(
            f"Los datos de {entidad} no coinciden con el formato esperado.",
            regla="RN-17",
            detalles={
                "entidad": entidad,
                "claves_faltantes": faltantes,
                "claves_desconocidas": desconocidas,
            },
        )


@dataclass(frozen=True)
class Usuario:
    """Persona autorizada para operar en el sistema (RN-02, RN-03, AMB-01).

    ``hash_contrasena`` guarda la credencial ya derivada como una sola cadena
    opaca (algoritmo, iteraciones, sal y digest). El dominio no conoce el
    algoritmo: eso pertenece a ``prestamos.auth``. Se excluye del ``repr`` para
    que no llegue a logs ni a trazas (RN-18, RNF-04).
    """

    id: str
    nombre: str
    correo: str
    rol: Rol
    activo: bool
    hash_contrasena: str = field(repr=False)

    _CLAVES = frozenset({"id", "nombre", "correo", "rol", "activo", "hash_contrasena"})

    def __post_init__(self) -> None:
        _texto_obligatorio(self.id, "id", "RN-03")
        _texto_obligatorio(self.nombre, "nombre", "RN-03")
        _texto_obligatorio(self.correo, "correo", "RN-03")
        _valor_de_enum(self.rol, Rol, "rol", "RN-01")
        if not isinstance(self.activo, bool):
            raise ErrorValidacion(
                "El campo 'activo' debe ser booleano.",
                regla="RN-02",
                detalles={"campo": "activo"},
            )
        _texto_obligatorio(self.hash_contrasena, "hash_contrasena", "RN-03")

    def a_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "nombre": self.nombre,
            "correo": self.correo,
            "rol": self.rol.value,
            "activo": self.activo,
            "hash_contrasena": self.hash_contrasena,
        }

    @classmethod
    def desde_dict(cls, datos: Any) -> Self:
        _validar_claves(datos, cls._CLAVES, "usuario")
        return cls(
            id=datos["id"],
            nombre=datos["nombre"],
            correo=datos["correo"],
            rol=_enum_desde_texto(datos["rol"], Rol, "rol", "RN-01"),
            activo=datos["activo"],
            hash_contrasena=datos["hash_contrasena"],
        )


@dataclass(frozen=True)
class Equipo:
    """Equipo de laboratorio susceptible de reserva o prestamo (RN-04, AMB-03).

    El estado operativo es independiente de las reservas: la disponibilidad para
    un periodo concreto se calcula en ``prestamos.reglas`` cruzando este estado
    con los prestamos solapados (docs/estados-transiciones.md, seccion 5).
    """

    codigo: str
    nombre: str
    tipo: str
    descripcion: str
    estado: EstadoEquipo

    _CLAVES = frozenset({"codigo", "nombre", "tipo", "descripcion", "estado"})

    def __post_init__(self) -> None:
        _texto_obligatorio(self.codigo, "codigo", "RN-04")
        _texto_obligatorio(self.nombre, "nombre", "RN-04")
        _texto_obligatorio(self.tipo, "tipo", "RN-04")
        _texto_obligatorio(self.descripcion, "descripcion", "RN-04")
        _valor_de_enum(self.estado, EstadoEquipo, "estado", "RN-04")

    def a_dict(self) -> dict[str, Any]:
        return {
            "codigo": self.codigo,
            "nombre": self.nombre,
            "tipo": self.tipo,
            "descripcion": self.descripcion,
            "estado": self.estado.value,
        }

    @classmethod
    def desde_dict(cls, datos: Any) -> Self:
        _validar_claves(datos, cls._CLAVES, "equipo")
        return cls(
            codigo=datos["codigo"],
            nombre=datos["nombre"],
            tipo=datos["tipo"],
            descripcion=datos["descripcion"],
            estado=_enum_desde_texto(datos["estado"], EstadoEquipo, "estado", "RN-04"),
        )


@dataclass(frozen=True)
class Prestamo:
    """Solicitud de reserva o prestamo a lo largo de todo su ciclo de vida.

    Una unica entidad cubre los siete estados del contrato, desde SOLICITADA
    hasta DEVUELTA (RF-05, RN-06). ``equipos`` guarda codigos de ``Equipo`` y
    ``id_solicitante`` el id de un ``Usuario``; el modelo no resuelve esas
    referencias, eso corresponde a los servicios.

    Las fechas y motivos opcionales quedan en ``None`` hasta que la transicion
    correspondiente los registra (T-02, T-03, T-04/T-05, T-06, T-08/T-09).
    """

    id: str
    id_solicitante: str
    equipos: tuple[str, ...]
    motivo: str
    estado: EstadoPrestamo
    fecha_solicitud: date
    fecha_inicio: date
    fecha_termino: date
    fecha_aprobacion: date | None = None
    fecha_entrega: date | None = None
    fecha_devolucion: date | None = None
    motivo_rechazo: str | None = None
    motivo_cancelacion: str | None = None

    _CLAVES = frozenset(
        {
            "id",
            "id_solicitante",
            "equipos",
            "motivo",
            "estado",
            "fecha_solicitud",
            "fecha_inicio",
            "fecha_termino",
            "fecha_aprobacion",
            "fecha_entrega",
            "fecha_devolucion",
            "motivo_rechazo",
            "motivo_cancelacion",
        }
    )

    def __post_init__(self) -> None:
        _texto_obligatorio(self.id, "id", "RN-17")
        _texto_obligatorio(self.id_solicitante, "id_solicitante", "RN-17")
        self._validar_equipos()
        _texto_obligatorio(self.motivo, "motivo", "RN-17")
        _valor_de_enum(self.estado, EstadoPrestamo, "estado", "RN-12")

        _fecha_obligatoria(self.fecha_solicitud, "fecha_solicitud", "RN-17")
        _fecha_obligatoria(self.fecha_inicio, "fecha_inicio", "RN-17")
        _fecha_obligatoria(self.fecha_termino, "fecha_termino", "RN-17")
        _fecha_opcional(self.fecha_aprobacion, "fecha_aprobacion", "RN-17")
        _fecha_opcional(self.fecha_entrega, "fecha_entrega", "RN-17")
        _fecha_opcional(self.fecha_devolucion, "fecha_devolucion", "RN-17")

        _texto_opcional(self.motivo_rechazo, "motivo_rechazo", "RN-17")
        _texto_opcional(self.motivo_cancelacion, "motivo_cancelacion", "RN-17")

        if self.fecha_inicio > self.fecha_termino:
            raise ErrorValidacion(
                "La fecha de inicio no puede ser posterior a la fecha de termino.",
                regla="RN-17",
                detalles={
                    "fecha_inicio": self.fecha_inicio.isoformat(),
                    "fecha_termino": self.fecha_termino.isoformat(),
                },
            )

    def _validar_equipos(self) -> None:
        """Cardinalidad y unicidad de la lista de equipos (RN-06)."""
        if not isinstance(self.equipos, tuple):
            raise ErrorValidacion(
                "El campo 'equipos' debe ser una tupla de codigos de equipo.",
                regla="RN-06",
                detalles={"campo": "equipos"},
            )
        for indice, codigo in enumerate(self.equipos):
            _texto_obligatorio(codigo, f"equipos[{indice}]", "RN-06")
        if not (
            MIN_EQUIPOS_POR_SOLICITUD
            <= len(self.equipos)
            <= MAX_EQUIPOS_POR_SOLICITUD
        ):
            raise ErrorValidacion(
                "Una solicitud debe incluir entre "
                f"{MIN_EQUIPOS_POR_SOLICITUD} y {MAX_EQUIPOS_POR_SOLICITUD} equipos.",
                regla="RN-06",
                detalles={"cantidad": len(self.equipos)},
            )
        if len(set(self.equipos)) != len(self.equipos):
            raise ErrorValidacion(
                "Una solicitud no puede repetir el mismo equipo.",
                regla="RN-06",
                detalles={"equipos": list(self.equipos)},
            )

    def a_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "id_solicitante": self.id_solicitante,
            "equipos": list(self.equipos),
            "motivo": self.motivo,
            "estado": self.estado.value,
            "fecha_solicitud": _fecha_a_texto(self.fecha_solicitud),
            "fecha_inicio": _fecha_a_texto(self.fecha_inicio),
            "fecha_termino": _fecha_a_texto(self.fecha_termino),
            "fecha_aprobacion": _fecha_a_texto(self.fecha_aprobacion),
            "fecha_entrega": _fecha_a_texto(self.fecha_entrega),
            "fecha_devolucion": _fecha_a_texto(self.fecha_devolucion),
            "motivo_rechazo": self.motivo_rechazo,
            "motivo_cancelacion": self.motivo_cancelacion,
        }

    @classmethod
    def desde_dict(cls, datos: Any) -> Self:
        _validar_claves(datos, cls._CLAVES, "prestamo")
        equipos = datos["equipos"]
        if not isinstance(equipos, list):
            raise ErrorValidacion(
                "El campo 'equipos' debe ser una lista de codigos de equipo.",
                regla="RN-06",
                detalles={"campo": "equipos"},
            )
        return cls(
            id=datos["id"],
            id_solicitante=datos["id_solicitante"],
            equipos=tuple(equipos),
            motivo=datos["motivo"],
            estado=_enum_desde_texto(datos["estado"], EstadoPrestamo, "estado", "RN-12"),
            fecha_solicitud=_fecha_desde_texto(
                datos["fecha_solicitud"], "fecha_solicitud", "RN-17"
            ),
            fecha_inicio=_fecha_desde_texto(
                datos["fecha_inicio"], "fecha_inicio", "RN-17"
            ),
            fecha_termino=_fecha_desde_texto(
                datos["fecha_termino"], "fecha_termino", "RN-17"
            ),
            fecha_aprobacion=_fecha_desde_texto(
                datos["fecha_aprobacion"], "fecha_aprobacion", "RN-17"
            ),
            fecha_entrega=_fecha_desde_texto(
                datos["fecha_entrega"], "fecha_entrega", "RN-17"
            ),
            fecha_devolucion=_fecha_desde_texto(
                datos["fecha_devolucion"], "fecha_devolucion", "RN-17"
            ),
            motivo_rechazo=datos["motivo_rechazo"],
            motivo_cancelacion=datos["motivo_cancelacion"],
        )
