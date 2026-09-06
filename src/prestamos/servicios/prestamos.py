"""Caso de uso de entrega, devolucion, atraso y cancelacion.

Este servicio orquesta persistencia JSON y motor de reglas. No decide si una
transicion es valida por su cuenta: antes de guardar cualquier cambio llama a
``prestamos.reglas.validar_transicion`` con el contexto necesario.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Iterable

from prestamos.modelos import Equipo, EstadoEquipo, EstadoPrestamo, Prestamo, Usuario
from prestamos.reglas import EventoTransicion, validar_transicion
from prestamos.repositorios.json_repo import RepositorioJson, directorio_datos


class ServicioPrestamos:
    """Operaciones sobre prestamos existentes respaldadas por JSON."""

    def __init__(
        self,
        repo_prestamos: RepositorioJson[Prestamo] | None = None,
        repo_equipos: RepositorioJson[Equipo] | None = None,
        *,
        datos_dir: str | Path | None = None,
    ) -> None:
        raiz = Path(datos_dir) if datos_dir is not None else directorio_datos()
        self.repo_prestamos = repo_prestamos or RepositorioJson(
            raiz / "solicitudes.json", Prestamo, "id"
        )
        self.repo_equipos = repo_equipos or RepositorioJson(
            raiz / "equipos.json", Equipo, "codigo"
        )

    def registrar_entrega(
        self,
        id_prestamo: str,
        encargado: Usuario,
        *,
        fecha_entrega: date | None = None,
    ) -> Prestamo:
        """Registra T-06: APROBADA -> ENTREGADA (RN-13)."""

        prestamo = self.repo_prestamos.obtener(id_prestamo)
        fecha = fecha_entrega or date.today()
        equipos = self._equipos_de(prestamo)

        validar_transicion(
            prestamo,
            EventoTransicion.REGISTRAR_ENTREGA,
            encargado,
            fecha_actual=fecha,
            fecha_operacion=fecha,
            equipos=equipos,
        )

        actualizado = replace(
            prestamo,
            estado=EstadoPrestamo.ENTREGADA,
            fecha_entrega=fecha,
        )
        self.repo_prestamos.guardar(actualizado)
        self._marcar_equipos(equipos.values(), EstadoEquipo.PRESTADO)
        return actualizado

    def registrar_devolucion(
        self,
        id_prestamo: str,
        encargado: Usuario,
        *,
        fecha_devolucion: date | None = None,
        equipos_devueltos: Iterable[str] | None = None,
    ) -> Prestamo:
        """Registra T-08 o T-09 y libera equipos al devolver (RN-14/RN-16)."""

        prestamo = self.repo_prestamos.obtener(id_prestamo)
        fecha = fecha_devolucion or date.today()
        devueltos = tuple(prestamo.equipos if equipos_devueltos is None else equipos_devueltos)

        prestamo_a_devolver, requiere_marcar_atraso = self._preparar_atraso_si_corresponde(
            prestamo, fecha
        )
        evento = (
            EventoTransicion.REGISTRAR_DEVOLUCION_ATRASADA
            if prestamo_a_devolver.estado is EstadoPrestamo.ATRASADA
            else EventoTransicion.REGISTRAR_DEVOLUCION
        )

        validar_transicion(
            prestamo_a_devolver,
            evento,
            encargado,
            fecha_actual=fecha,
            fecha_operacion=fecha,
            equipos_devueltos=devueltos,
        )
        equipos = self._equipos_de(prestamo_a_devolver)

        actualizado = replace(
            prestamo_a_devolver,
            estado=EstadoPrestamo.DEVUELTA,
            fecha_devolucion=fecha,
        )
        if requiere_marcar_atraso:
            self.repo_prestamos.guardar(prestamo_a_devolver)
        self.repo_prestamos.guardar(actualizado)
        self._marcar_equipos(equipos.values(), EstadoEquipo.DISPONIBLE)
        return actualizado

    def cancelar(
        self,
        id_prestamo: str,
        usuario: Usuario,
        motivo: str | None,
    ) -> Prestamo:
        """Registra T-04 o T-05 antes de la entrega, con motivo (RN-15)."""

        prestamo = self.repo_prestamos.obtener(id_prestamo)
        validar_transicion(
            prestamo,
            EventoTransicion.CANCELAR_SOLICITUD,
            usuario,
            motivo_cancelacion=motivo,
        )
        equipos = (
            self._equipos_de(prestamo)
            if prestamo.estado is EstadoPrestamo.APROBADA
            else {}
        )

        actualizado = replace(
            prestamo,
            estado=EstadoPrestamo.CANCELADA,
            motivo_cancelacion=motivo,
        )
        self.repo_prestamos.guardar(actualizado)
        if prestamo.estado is EstadoPrestamo.APROBADA:
            self._liberar_reservas(equipos.values())
        return actualizado

    def marcar_atraso(
        self,
        id_prestamo: str,
        *,
        usuario: Usuario | None = None,
        fecha_actual: date | None = None,
    ) -> Prestamo:
        """Registra T-07: ENTREGADA -> ATRASADA (RN-16)."""

        prestamo = self.repo_prestamos.obtener(id_prestamo)
        fecha = fecha_actual or date.today()
        validar_transicion(
            prestamo,
            EventoTransicion.MARCAR_ATRASO,
            usuario,
            fecha_actual=fecha,
        )
        actualizado = replace(prestamo, estado=EstadoPrestamo.ATRASADA)
        self.repo_prestamos.guardar(actualizado)
        return actualizado

    def _preparar_atraso_si_corresponde(
        self,
        prestamo: Prestamo,
        fecha: date,
    ) -> tuple[Prestamo, bool]:
        if (
            prestamo.estado is EstadoPrestamo.ENTREGADA
            and prestamo.fecha_devolucion is None
            and fecha > prestamo.fecha_termino
        ):
            validar_transicion(
                prestamo,
                EventoTransicion.MARCAR_ATRASO,
                None,
                fecha_actual=fecha,
            )
            return replace(prestamo, estado=EstadoPrestamo.ATRASADA), True
        return prestamo, False

    def _equipos_de(self, prestamo: Prestamo) -> dict[str, Equipo]:
        return {codigo: self.repo_equipos.obtener(codigo) for codigo in prestamo.equipos}

    def _marcar_equipos(
        self,
        equipos: Iterable[Equipo],
        estado: EstadoEquipo,
    ) -> None:
        for equipo in equipos:
            self.repo_equipos.guardar(replace(equipo, estado=estado))

    def _liberar_reservas(self, equipos: Iterable[Equipo]) -> None:
        for equipo in equipos:
            if equipo.estado is EstadoEquipo.RESERVADO:
                self.repo_equipos.guardar(replace(equipo, estado=EstadoEquipo.DISPONIBLE))


def crear_servicio_prestamos(
    *,
    datos_dir: str | Path | None = None,
) -> ServicioPrestamos:
    return ServicioPrestamos(datos_dir=datos_dir)


def registrar_entrega(
    id_prestamo: str,
    encargado: Usuario,
    *,
    fecha_entrega: date | None = None,
    datos_dir: str | Path | None = None,
) -> Prestamo:
    return crear_servicio_prestamos(datos_dir=datos_dir).registrar_entrega(
        id_prestamo,
        encargado,
        fecha_entrega=fecha_entrega,
    )


def registrar_devolucion(
    id_prestamo: str,
    encargado: Usuario,
    *,
    fecha_devolucion: date | None = None,
    equipos_devueltos: Iterable[str] | None = None,
    datos_dir: str | Path | None = None,
) -> Prestamo:
    return crear_servicio_prestamos(datos_dir=datos_dir).registrar_devolucion(
        id_prestamo,
        encargado,
        fecha_devolucion=fecha_devolucion,
        equipos_devueltos=equipos_devueltos,
    )


def cancelar(
    id_prestamo: str,
    usuario: Usuario,
    motivo: str | None,
    *,
    datos_dir: str | Path | None = None,
) -> Prestamo:
    return crear_servicio_prestamos(datos_dir=datos_dir).cancelar(
        id_prestamo,
        usuario,
        motivo,
    )


def marcar_atraso(
    id_prestamo: str,
    *,
    usuario: Usuario | None = None,
    fecha_actual: date | None = None,
    datos_dir: str | Path | None = None,
) -> Prestamo:
    return crear_servicio_prestamos(datos_dir=datos_dir).marcar_atraso(
        id_prestamo,
        usuario=usuario,
        fecha_actual=fecha_actual,
    )
