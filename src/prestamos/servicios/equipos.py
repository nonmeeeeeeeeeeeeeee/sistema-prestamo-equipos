"""Caso de uso: registro del catalogo de equipos (RF-03, RN-04).

Alta, edicion, baja logica y listado de los equipos de laboratorio. Este modulo
es el dueno de RN-04: campos obligatorios y codigo unico.

`Equipo.estado` tiene dos duenos distintos y este servicio solo es uno de ellos:

- `DISPONIBLE`, `RESERVADO` y `PRESTADO` pertenecen al ciclo de vida del
  prestamo. Hoy `ServicioPrestamos` solo escribe `PRESTADO` al entregar y
  `DISPONIBLE` al devolver o liberar; `RESERVADO` todavia no lo escribe nadie,
  porque la aprobacion (#11) es un stub. Ese hueco es justamente el motivo de
  que la guarda de RN-21 consulte los prestamos y no este campo.
- `MANTENCION` y `BAJA` son decisiones administrativas del Encargado, y son las
  que viven aqui.

Por eso `editar_equipo` no acepta `estado`: si lo aceptara, poner "DISPONIBLE"
sobre un equipo que esta fisicamente prestado lo volveria reservable por otra
persona (`reglas.equipo_disponible` solo mira este campo), y `registrar_devolucion`
sobreescribiria el cambio despues. Cada transicion administrativa tiene su propia
operacion, con su guarda y su evento.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

from prestamos.auth import ServicioAuth
from prestamos.errores import ErrorValidacion
from prestamos.logging_conf import registrar_evento
from prestamos.modelos import (
    Equipo,
    EstadoEquipo,
    Prestamo,
    Rol,
    Usuario,
    normalizar_identificador,
)
from prestamos.reglas import ESTADOS_DISPONIBILIDAD_BLOQUEADA
from prestamos.repositorios.fabricas import repositorio_equipos, repositorio_prestamos
from prestamos.repositorios.json_repo import RepositorioJson

# Estados administrativos desde los que `reactivar` puede devolver un equipo al
# catalogo. `RESERVADO` y `PRESTADO` quedan fuera a proposito: son del ciclo de
# vida del prestamo, y forzarlos a `DISPONIBLE` desde aqui es exactamente la
# corrupcion que se evita dejando `estado` fuera de `editar_equipo`.
ESTADOS_REACTIVABLES = frozenset({EstadoEquipo.BAJA, EstadoEquipo.MANTENCION})


class ServicioEquipos:
    """Operaciones sobre el catalogo de equipos, respaldadas por JSON."""

    def __init__(
        self,
        auth: ServicioAuth,
        repositorio: RepositorioJson[Equipo] | None = None,
        repo_prestamos: RepositorioJson[Prestamo] | None = None,
        *,
        datos_dir: str | Path | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Servicio de equipos.

        `repo_prestamos` no es opcional por comodidad: la baja y la mantencion
        necesitan saber si el equipo esta comprometido, y esa respuesta esta en
        `solicitudes.json`, no en el propio equipo (ver
        `_exigir_sin_prestamo_activo`).
        """
        self._auth = auth
        self._equipos = repositorio or repositorio_equipos(datos_dir)
        self._prestamos = repo_prestamos or repositorio_prestamos(datos_dir)
        self._logger = logger

    # ------------------------------------------------------------------ API

    def listar(self, *, incluir_dados_de_baja: bool = True) -> list[Equipo]:
        """Catalogo completo (RF-03).

        Basta con estar autenticado, sin exigir rol: un solicitante necesita ver
        el catalogo para poder pedir algo (RF-04). Solo *modificarlo* es
        exclusivo del Encargado.

        `incluir_dados_de_baja` viene en `True` porque un codigo dado de baja
        sigue ocupado: ocultarlo haria que pareciera libre y el alta lo
        rechazaria despues sin que se vea por que.
        """
        self._auth.requiere_sesion()
        equipos = self._equipos.listar()
        if incluir_dados_de_baja:
            return equipos
        return [e for e in equipos if e.estado is not EstadoEquipo.BAJA]

    def obtener(self, codigo: str) -> Equipo:
        """Un equipo por codigo; `RecursoNoEncontrado` si no existe."""
        self._auth.requiere_sesion()
        return self._equipos.obtener(normalizar_identificador(codigo))

    def registrar_equipo(
        self,
        codigo: str,
        nombre: str,
        tipo: str,
        descripcion: str,
    ) -> Equipo:
        """Alta de un equipo en el catalogo (RF-03, RN-04).

        Nace `DISPONIBLE`: un equipo recien registrado que no estuviera
        disponible seria invisible para `reglas.equipo_disponible` sin que nada
        lo explique. Para dar de alta algo que ya esta en el taller, registrar y
        luego `enviar_a_mantencion`, que deja los dos hechos en el log.
        """
        actor = self._auth.requiere_rol(Rol.ENCARGADO)
        codigo = normalizar_identificador(codigo)
        self._exigir_codigo_libre(codigo, actor=actor)

        equipo = Equipo(
            codigo=codigo,
            nombre=nombre,
            tipo=tipo,
            descripcion=descripcion,
            estado=EstadoEquipo.DISPONIBLE,
        )
        self._equipos.guardar(equipo)
        self._evento("equipo_registrado", actor=actor, objetivo=equipo.codigo)
        return equipo

    def editar_equipo(
        self,
        codigo: str,
        *,
        nombre: str | None = None,
        tipo: str | None = None,
        descripcion: str | None = None,
    ) -> Equipo:
        """Edita los datos descriptivos del equipo (RN-04).

        No acepta `estado` ni `codigo`. Lo primero, por el reparto de duenos que
        explica el docstring del modulo. Lo segundo, porque `Prestamo.equipos`
        guarda codigos como texto suelto: renombrar uno desligaria en silencio
        todo el historial de prestamos de ese equipo.
        """
        actor = self._auth.requiere_rol(Rol.ENCARGADO)
        actual = self._equipos.obtener(normalizar_identificador(codigo))

        actualizado = replace(
            actual,
            nombre=actual.nombre if nombre is None else nombre,
            tipo=actual.tipo if tipo is None else tipo,
            descripcion=actual.descripcion if descripcion is None else descripcion,
        )
        self._equipos.guardar(actualizado)
        self._evento(
            "equipo_editado",
            actor=actor,
            objetivo=actualizado.codigo,
            campos=sorted(
                campo
                for campo, valor in (
                    ("nombre", nombre),
                    ("tipo", tipo),
                    ("descripcion", descripcion),
                )
                if valor is not None
            ),
        )
        return actualizado

    def dar_de_baja(self, codigo: str) -> Equipo:
        """Retira el equipo del catalogo (baja logica, RN-04, RN-05).

        No se borra el registro: `Prestamo.equipos` seguiria nombrandolo y el
        historial dejaria de poder leerse. Un equipo en `BAJA` no vuelve a estar
        disponible (`reglas.equipo_disponible` corta con cualquier estado que no
        sea `DISPONIBLE`), pero su codigo sigue ocupado.

        Es reversible con `reactivar`.
        """
        return self._transicion_administrativa(
            codigo,
            EstadoEquipo.BAJA,
            accion="equipo_dado_de_baja",
        )

    def enviar_a_mantencion(self, codigo: str) -> Equipo:
        """Marca el equipo como no apto temporalmente (RN-04, RN-05).

        Misma guarda que la baja, y por la misma razon: dejar en `MANTENCION` un
        equipo con un prestamo aprobado haria fallar la entrega mas tarde, en el
        mostrador, con "no esta disponible fisicamente" (RN-13).

        Consecuencia conocida: un equipo que se rompe *mientras esta prestado* no
        puede marcarse hasta registrar su devolucion. `estado` es un solo campo y
        no puede decir "prestado y ademas roto"; escribir `MANTENCION` encima de
        `PRESTADO` perderia el dato, porque `registrar_devolucion` reescribe a
        `DISPONIBLE` sin mirar. Representarlo de verdad pide un campo aparte en
        `Equipo`, que excede a este caso de uso.
        """
        return self._transicion_administrativa(
            codigo,
            EstadoEquipo.MANTENCION,
            accion="equipo_enviado_a_mantencion",
        )

    def reactivar(self, codigo: str) -> Equipo:
        """Devuelve al catalogo un equipo en `BAJA` o `MANTENCION`.

        La baja es reversible: un equipo retirado por error, o reparado, vuelve
        con su historial intacto, que es justamente lo que la baja logica
        preserva frente a un borrado.

        Sobre un equipo que ya esta `DISPONIBLE` no cambia nada, pero registra
        el intento con `resultado="sin_cambio"`: idempotente en el estado, no en
        la auditoria (RN-18).
        """
        actor = self._auth.requiere_rol(Rol.ENCARGADO)
        actual = self._equipos.obtener(normalizar_identificador(codigo))

        if actual.estado is EstadoEquipo.DISPONIBLE:
            self._evento(
                "equipo_reactivado",
                actor=actor,
                objetivo=actual.codigo,
                resultado="sin_cambio",
                estado_anterior=actual.estado.value,
            )
            return actual
        if actual.estado not in ESTADOS_REACTIVABLES:
            self._rechazar(
                f"El equipo {codigo} esta {actual.estado.value} y su estado lo "
                "gestiona el ciclo de vida del prestamo, no el catalogo.",
                actor=actor,
                accion="equipo_reactivado",
                motivo="estado_no_administrativo",
                objetivo=codigo,
            )

        actualizado = replace(actual, estado=EstadoEquipo.DISPONIBLE)
        self._equipos.guardar(actualizado)
        self._evento(
            "equipo_reactivado",
            actor=actor,
            objetivo=actualizado.codigo,
            estado_anterior=actual.estado.value,
        )
        return actualizado

    # -------------------------------------------------------------- Interno

    def _transicion_administrativa(
        self,
        codigo: str,
        destino: EstadoEquipo,
        *,
        accion: str,
    ) -> Equipo:
        """Tronco comun de `dar_de_baja` y `enviar_a_mantencion`."""
        actor = self._auth.requiere_rol(Rol.ENCARGADO)
        codigo = normalizar_identificador(codigo)
        actual = self._equipos.obtener(codigo)
        if actual.estado is destino:
            self._evento(
                accion,
                actor=actor,
                objetivo=actual.codigo,
                resultado="sin_cambio",
                estado_anterior=actual.estado.value,
            )
            return actual

        self._exigir_sin_prestamo_activo(codigo, actor=actor, accion=accion)

        actualizado = replace(actual, estado=destino)
        self._equipos.guardar(actualizado)
        self._evento(
            accion,
            actor=actor,
            objetivo=actualizado.codigo,
            estado_anterior=actual.estado.value,
        )
        return actualizado

    def _exigir_codigo_libre(self, codigo: object, *, actor: Usuario | None) -> None:
        """Unicidad del codigo sin distinguir mayusculas (RN-04).

        Incluye los equipos dados de baja: el codigo es la etiqueta fisica del
        activo, y reutilizarlo reengancharia el historial de prestamos del
        equipo viejo a un objeto distinto, porque `Prestamo.equipos` guarda solo
        el texto del codigo. Para volver a usarlo esta `reactivar`.

        Se compara con `casefold()` aunque `RepositorioJson` compare exacto: un
        `M-01` junto a un `m-01` son dos equipos distintos para el motor de
        reglas y el mismo para cualquier persona.
        """
        if not isinstance(codigo, str) or not codigo.strip():
            # Deja que el modelo produzca el mensaje de campo obligatorio.
            return
        buscado = codigo.strip().casefold()
        for equipo in self._equipos.listar():
            if equipo.codigo.strip().casefold() != buscado:
                continue
            motivo = (
                "codigo_dado_de_baja"
                if equipo.estado is EstadoEquipo.BAJA
                else "codigo_duplicado"
            )
            mensaje = f"Ya existe un equipo con el codigo '{equipo.codigo}'."
            if equipo.estado is EstadoEquipo.BAJA:
                mensaje += " Esta dado de baja: use reactivar en lugar de registrarlo."
            self._rechazar(
                mensaje,
                actor=actor,
                accion="equipo_registrado",
                motivo=motivo,
                objetivo=codigo,
            )

    def _exigir_sin_prestamo_activo(
        self,
        codigo: str,
        *,
        actor: Usuario | None,
        accion: str,
    ) -> None:
        """Rechaza si algun prestamo comprometido nombra al equipo (RN-05).

        Se pregunta a `solicitudes.json` y no a `Equipo.estado`, aunque lo
        segundo seria O(1). El motivo es concreto: hoy nadie escribe
        `RESERVADO`. La aprobacion, que es quien deberia hacerlo, vive en
        `servicios/solicitudes.py` y todavia no existe (#11). Es decir, un
        prestamo `APROBADA` deja su equipo en `DISPONIBLE`, y una guarda basada
        en el estado daria de baja equipos ya comprometidos. Preguntar por los
        prestamos es correcto ahora y sigue siendolo despues de #11.

        `SOLICITADA` no bloquea: se reusa `ESTADOS_DISPONIBILIDAD_BLOQUEADA`, la
        misma definicion de "comprometido" que usa `reglas.equipo_disponible`,
        para no tener dos que puedan divergir. Una solicitud sin aprobar es una
        peticion, no un compromiso: si un equipo se rompe, el Encargado tiene que
        poder retirarlo aunque alguien lo haya pedido, o cualquiera podria
        bloquear el mantenimiento dejando solicitudes abiertas. Esa solicitud
        muere despues en la aprobacion, que revalida RN-05.
        """
        # Comparacion sin distinguir mayusculas ni espacios, igual que la
        # unicidad de RN-04. `Prestamo.equipos` guarda los codigos como texto
        # suelto y nadie resuelve la referencia, asi que un `in` exacto dejaria
        # que un prestamo sobre "m-01" no bloqueara la baja de "M-01" -dos
        # codigos que RN-04 considera el mismo equipo-.
        buscado = codigo.strip().casefold()
        bloqueantes = [
            prestamo
            for prestamo in self._prestamos.listar()
            if any(c.strip().casefold() == buscado for c in prestamo.equipos)
            and prestamo.estado in ESTADOS_DISPONIBILIDAD_BLOQUEADA
        ]
        if bloqueantes:
            self._rechazar(
                f"El equipo {codigo} tiene prestamos activos y no puede retirarse "
                "del catalogo. Registre la devolucion o cancele el prestamo primero.",
                actor=actor,
                accion=accion,
                motivo="prestamo_activo",
                objetivo=codigo,
                regla="RN-21",
                prestamos=[p.id for p in bloqueantes],
            )

    def _rechazar(
        self,
        mensaje: str,
        *,
        actor: Usuario | None,
        accion: str,
        motivo: str,
        objetivo: str | None = None,
        regla: str = "RN-04",
        **contexto: object,
    ) -> NoReturn:
        """Registra el rechazo y lo levanta (RN-17, RN-18)."""
        self._evento(
            accion,
            actor=actor,
            objetivo=objetivo,
            resultado="error",
            motivo=motivo,
            **contexto,
        )
        detalles: dict[str, object] = {"motivo": motivo}
        if objetivo is not None:
            detalles["equipo"] = objetivo
        detalles.update(contexto)
        raise ErrorValidacion(mensaje, regla=regla, detalles=detalles)

    def _evento(
        self,
        accion: str,
        *,
        actor: Usuario | None,
        resultado: str = "ok",
        **contexto: object,
    ) -> None:
        registrar_evento(
            accion,
            usuario=actor.id if actor is not None else None,
            resultado=resultado,
            logger=self._logger,
            **{k: v for k, v in contexto.items() if v is not None},
        )
