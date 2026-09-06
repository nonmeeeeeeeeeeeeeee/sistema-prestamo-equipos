"""Caso de uso de entrega, devolucion, atraso, cancelacion y consultas.

Este servicio orquesta persistencia JSON y motor de reglas. No decide si una
transicion es valida por su cuenta: antes de guardar cualquier cambio llama a
``prestamos.reglas.validar_transicion`` con el contexto necesario.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

from prestamos.errores import ErrorAutorizacion, ErrorValidacion
from prestamos.modelos import Equipo, EstadoEquipo, EstadoPrestamo, Prestamo, Rol, Usuario
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

    def prestamos_futuros(
        self,
        usuario: Usuario | None,
        *,
        fecha_actual: date | None = None,
        id_usuario: str | None = None,
        codigo_equipo: str | None = None,
    ) -> list[Prestamo]:
        """Consulta futuros: APROBADA con inicio posterior a hoy (RN-16)."""

        hoy = fecha_actual or date.today()
        return self._consultar(
            usuario,
            id_usuario=id_usuario,
            codigo_equipo=codigo_equipo,
            clasificador=lambda prestamo: (
                prestamo.estado is EstadoPrestamo.APROBADA
                and prestamo.fecha_inicio > hoy
            ),
        )

    def prestamos_vigentes(
        self,
        usuario: Usuario | None,
        *,
        fecha_actual: date | None = None,
        id_usuario: str | None = None,
        codigo_equipo: str | None = None,
    ) -> list[Prestamo]:
        """Consulta vigentes: ENTREGADA sin devolucion y dentro del plazo (RN-16)."""

        hoy = fecha_actual or date.today()
        return self._consultar(
            usuario,
            id_usuario=id_usuario,
            codigo_equipo=codigo_equipo,
            clasificador=lambda prestamo: (
                prestamo.estado is EstadoPrestamo.ENTREGADA
                and prestamo.fecha_devolucion is None
                and prestamo.fecha_inicio <= hoy <= prestamo.fecha_termino
            ),
        )

    def prestamos_atrasados(
        self,
        usuario: Usuario | None,
        *,
        fecha_actual: date | None = None,
        id_usuario: str | None = None,
        codigo_equipo: str | None = None,
    ) -> list[Prestamo]:
        """Consulta atrasados sin modificar estados persistidos (RN-16)."""

        hoy = fecha_actual or date.today()
        return self._consultar(
            usuario,
            id_usuario=id_usuario,
            codigo_equipo=codigo_equipo,
            clasificador=lambda prestamo: (
                prestamo.fecha_devolucion is None
                and (
                    prestamo.estado is EstadoPrestamo.ATRASADA
                    or (
                        prestamo.estado is EstadoPrestamo.ENTREGADA
                        and prestamo.fecha_termino < hoy
                    )
                )
            ),
        )

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

    def _consultar(
        self,
        usuario: Usuario | None,
        *,
        id_usuario: str | None,
        codigo_equipo: str | None,
        clasificador: Callable[[Prestamo], bool],
    ) -> list[Prestamo]:
        id_filtrado = self._id_usuario_visible(usuario, id_usuario)
        equipo_filtrado = self._filtro_texto(codigo_equipo, "codigo_equipo")
        resultado: list[Prestamo] = []
        for prestamo in self.repo_prestamos.listar():
            if id_filtrado is not None and prestamo.id_solicitante != id_filtrado:
                continue
            if equipo_filtrado is not None and equipo_filtrado not in prestamo.equipos:
                continue
            if clasificador(prestamo):
                resultado.append(prestamo)
        return resultado

    def _id_usuario_visible(
        self,
        usuario: Usuario | None,
        id_usuario: str | None,
    ) -> str | None:
        if usuario is None:
            raise ErrorAutorizacion(
                "La consulta requiere un usuario autenticado (RN-02).",
                regla="RN-02",
            )
        if not usuario.activo:
            raise ErrorAutorizacion(
                "El usuario debe estar activo para consultar prestamos (RN-02).",
                regla="RN-02",
                detalles={"usuario": usuario.id},
            )

        id_filtrado = self._filtro_texto(id_usuario, "id_usuario")
        if usuario.rol is Rol.SOLICITANTE:
            if id_filtrado is not None and id_filtrado != usuario.id:
                raise ErrorAutorizacion(
                    "El solicitante solo puede consultar sus propios prestamos (RN-17).",
                    regla="RN-17",
                    detalles={"usuario": usuario.id, "id_usuario": id_filtrado},
                )
            return usuario.id
        if usuario.rol is Rol.ENCARGADO:
            return id_filtrado

        raise ErrorAutorizacion(
            "El rol del usuario no esta autorizado para consultar prestamos (RN-01).",
            regla="RN-01",
            detalles={"rol": getattr(usuario.rol, "value", usuario.rol)},
        )

    def _filtro_texto(self, valor: str | None, campo: str) -> str | None:
        if valor is None:
            return None
        if not isinstance(valor, str) or not valor.strip():
            raise ErrorValidacion(
                f"El filtro '{campo}' no puede estar vacio (RN-17).",
                regla="RN-17",
                detalles={"campo": campo},
            )
        return valor.strip()

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


def prestamos_futuros(
    usuario: Usuario | None,
    *,
    fecha_actual: date | None = None,
    id_usuario: str | None = None,
    codigo_equipo: str | None = None,
    datos_dir: str | Path | None = None,
) -> list[Prestamo]:
    return crear_servicio_prestamos(datos_dir=datos_dir).prestamos_futuros(
        usuario,
        fecha_actual=fecha_actual,
        id_usuario=id_usuario,
        codigo_equipo=codigo_equipo,
    )


def prestamos_vigentes(
    usuario: Usuario | None,
    *,
    fecha_actual: date | None = None,
    id_usuario: str | None = None,
    codigo_equipo: str | None = None,
    datos_dir: str | Path | None = None,
) -> list[Prestamo]:
    return crear_servicio_prestamos(datos_dir=datos_dir).prestamos_vigentes(
        usuario,
        fecha_actual=fecha_actual,
        id_usuario=id_usuario,
        codigo_equipo=codigo_equipo,
    )


def prestamos_atrasados(
    usuario: Usuario | None,
    *,
    fecha_actual: date | None = None,
    id_usuario: str | None = None,
    codigo_equipo: str | None = None,
    datos_dir: str | Path | None = None,
) -> list[Prestamo]:
    return crear_servicio_prestamos(datos_dir=datos_dir).prestamos_atrasados(
        usuario,
        fecha_actual=fecha_actual,
        id_usuario=id_usuario,
        codigo_equipo=codigo_equipo,
    )
