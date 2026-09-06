"""Caso de uso: registro de usuarios autorizados (RF-01, RN-03).

Alta, edicion, baja logica y listado de las personas que pueden operar en el
sistema. Este modulo es el dueno de RN-03: campos obligatorios, id y correo
unicos, y formato del correo.

Reparto con los modulos vecinos:

- `modelos.Usuario` valida *estructura*: que los campos existan, no esten vacios
  y tengan el tipo correcto. No puede validar unicidad, porque solo ve un
  registro a la vez.
- `auth.py` valida *credenciales* y produce el hash. No valida RN-03: su
  docstring lo dice, y `hash_contrasena` esta expuesta como funcion de modulo
  justamente para que este servicio pueda crear usuarios sin abrir una sesion.
- Este servicio valida lo que solo se puede ver mirando *toda* la coleccion:
  duplicados y la existencia de al menos un Encargado activo.

Autorizacion: a diferencia de `ServicioPrestamos`, que recibe un `Usuario` por
parametro, aqui se inyecta un `ServicioAuth` y cada operacion llama
`requiere_rol(Rol.ENCARGADO)` por dentro. Eso relee `usuarios.json` en cada
llamada, de modo que un encargado desactivado a mitad de sesion deja de poder
operar de inmediato (RN-02). La convivencia de ambas convenciones esta anotada
en el issue #48; la tabla para la CLI, en el #14.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

from prestamos.auth import ITERACIONES_PBKDF2, ServicioAuth, hash_contrasena
from prestamos.errores import ErrorValidacion
from prestamos.logging_conf import registrar_evento
from prestamos.modelos import Rol, Usuario
from prestamos.repositorios.fabricas import repositorio_usuarios
from prestamos.repositorios.json_repo import RepositorioJson

# Forma minima de un correo: exactamente una arroba, ambos lados no vacios y sin
# espacios. No se exige un dominio institucional concreto a proposito: RN-03 y
# SUP-01 hablan de "correo institucional" pero ningun documento define cual es,
# y SUP-01 deja anotado que el modelo deberia ajustarse si el cliente lo define.
# Hardcodear aqui el dominio de los datos de prueba seria inventar la regla.
_CORREO_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+$")


class ServicioUsuarios:
    """Operaciones sobre el padron de usuarios, respaldadas por JSON."""

    def __init__(
        self,
        auth: ServicioAuth,
        repositorio: RepositorioJson[Usuario] | None = None,
        *,
        datos_dir: str | Path | None = None,
        logger: logging.Logger | None = None,
        iteraciones_hash: int = ITERACIONES_PBKDF2,
    ) -> None:
        """Servicio de usuarios.

        `repositorio` deberia ser *el mismo* que usa `auth`: ambos leen y
        escriben `usuarios.json`, y si apuntan a archivos distintos una baja
        logica no invalidaria la sesion correspondiente.

        `iteraciones_hash` existe por la misma razon que el parametro homonimo
        de `auth.hash_contrasena`: derivar con las 200.000 iteraciones de
        produccion cuesta ~100 ms por alta, lo que vuelve lentas las pruebas que
        crean usuarios. En produccion nadie deberia pasarlo.

        `logger` se inyecta para que las pruebas no escriban en el log real:
        `configurar_logging` acumula handlers sobre el logger singleton
        "prestamos", y `datos/logs/eventos.log` esta versionado.
        """
        self._auth = auth
        self._usuarios = repositorio or repositorio_usuarios(datos_dir)
        self._logger = logger
        self._iteraciones_hash = iteraciones_hash

    # ------------------------------------------------------------------ API

    def listar(self, *, incluir_inactivos: bool = True) -> list[Usuario]:
        """Padron completo (RF-01).

        Exige rol Encargado: el listado incluye correos, y RN-18 pide no
        derramar datos de contacto mas alla de quien los necesita.

        `incluir_inactivos` viene en `True` porque ocultar a los usuarios dados
        de baja haria que un id ocupado pareciera libre, y el alta lo rechazaria
        despues sin explicacion visible.
        """
        self._auth.requiere_rol(Rol.ENCARGADO)
        usuarios = self._usuarios.listar()
        if incluir_inactivos:
            return usuarios
        return [usuario for usuario in usuarios if usuario.activo]

    def obtener(self, id_usuario: str) -> Usuario:
        """Un usuario por id; `RecursoNoEncontrado` si no existe."""
        self._auth.requiere_rol(Rol.ENCARGADO)
        return self._usuarios.obtener(id_usuario)

    def registrar_usuario(
        self,
        id_usuario: str,
        nombre: str,
        correo: str,
        rol: Rol,
        contrasena: str,
    ) -> Usuario:
        """Alta de un usuario autorizado (RF-01, RN-03).

        El alta siempre deja al usuario activo: para crear a alguien ya dado de
        baja habria que registrarlo y desactivarlo, que es lo que realmente
        ocurre y queda en el log como dos eventos.
        """
        actor = self._auth.requiere_rol(Rol.ENCARGADO)

        self._validar_correo(correo, actor=actor, accion="usuario_registrado")
        self._exigir_id_libre(id_usuario, actor=actor, accion="usuario_registrado")
        self._exigir_correo_libre(correo, actor=actor, accion="usuario_registrado")

        usuario = Usuario(
            id=id_usuario,
            nombre=nombre,
            correo=correo,
            rol=rol,
            activo=True,
            hash_contrasena=hash_contrasena(
                contrasena, iteraciones=self._iteraciones_hash
            ),
        )
        self._usuarios.guardar(usuario)
        self._evento(
            "usuario_registrado",
            actor=actor,
            objetivo=usuario.id,
            rol=usuario.rol.value,
        )
        return usuario

    def editar_usuario(
        self,
        id_usuario: str,
        *,
        nombre: str | None = None,
        correo: str | None = None,
        rol: Rol | None = None,
    ) -> Usuario:
        """Edita los datos descriptivos y el rol (RN-03).

        No toca `activo` ni `hash_contrasena`: esos tienen sus propias
        operaciones, para que cada cambio quede como un evento distinto en el
        log en vez de esconderse dentro de un "usuario_editado" generico.

        Tampoco toca `id`. `Prestamo.id_solicitante` guarda ese id como texto
        suelto y nadie resuelve la referencia, asi que renombrarlo dejaria
        huerfanos, en silencio, todos los prestamos de esa persona.
        """
        actor = self._auth.requiere_rol(Rol.ENCARGADO)
        actual = self._usuarios.obtener(id_usuario)

        if correo is not None:
            self._validar_correo(correo, actor=actor, accion="usuario_editado")
            # Excluir el propio registro: sin esto, reenviar el correo que el
            # usuario ya tiene -o editar solo el nombre- chocaria consigo mismo.
            self._exigir_correo_libre(
                correo, actor=actor, accion="usuario_editado", excluir_id=actual.id
            )

        actualizado = replace(
            actual,
            nombre=actual.nombre if nombre is None else nombre,
            correo=actual.correo if correo is None else correo,
            rol=actual.rol if rol is None else rol,
        )
        self._proteger_ultimo_encargado(
            actual, actualizado, actor=actor, accion="usuario_editado"
        )

        self._usuarios.guardar(actualizado)
        self._evento(
            "usuario_editado",
            actor=actor,
            objetivo=actualizado.id,
            campos=sorted(
                campo
                for campo, valor in (
                    ("nombre", nombre),
                    ("correo", correo),
                    ("rol", rol),
                )
                if valor is not None
            ),
        )
        return actualizado

    def desactivar(self, id_usuario: str) -> Usuario:
        """Baja logica (RN-02).

        No se borra el registro: `Prestamo.id_solicitante` seguiria apuntando a
        el, y el historial deber quedar auditable. Un usuario inactivo no puede
        iniciar sesion ni operar, y `auth.requiere_sesion` corta su sesion en
        curso en la siguiente accion.
        """
        actor = self._auth.requiere_rol(Rol.ENCARGADO)
        actual = self._usuarios.obtener(id_usuario)
        if not actual.activo:
            return actual

        actualizado = replace(actual, activo=False)
        self._proteger_ultimo_encargado(
            actual, actualizado, actor=actor, accion="usuario_desactivado"
        )

        self._usuarios.guardar(actualizado)
        self._evento("usuario_desactivado", actor=actor, objetivo=actualizado.id)
        return actualizado

    def reactivar(self, id_usuario: str) -> Usuario:
        """Revierte la baja logica. Idempotente si ya estaba activo."""
        actor = self._auth.requiere_rol(Rol.ENCARGADO)
        actual = self._usuarios.obtener(id_usuario)
        if actual.activo:
            return actual

        actualizado = replace(actual, activo=True)
        self._usuarios.guardar(actualizado)
        self._evento("usuario_reactivado", actor=actor, objetivo=actualizado.id)
        return actualizado

    def cambiar_contrasena(self, id_usuario: str, nueva_contrasena: str) -> Usuario:
        """Reemplaza la credencial derivada (RN-03).

        Unica operacion del servicio que recibe una contrasena en claro. No se
        registra en el evento ni siquiera enmascarada: `sanitizar()` empareja por
        nombre de clave, asi que confiar en el seria confiar en como se llamo la
        variable (RN-18).
        """
        actor = self._auth.requiere_rol(Rol.ENCARGADO)
        actual = self._usuarios.obtener(id_usuario)

        actualizado = replace(
            actual,
            hash_contrasena=hash_contrasena(
                nueva_contrasena, iteraciones=self._iteraciones_hash
            ),
        )
        self._usuarios.guardar(actualizado)
        self._evento(
            "usuario_contrasena_cambiada", actor=actor, objetivo=actualizado.id
        )
        return actualizado

    # -------------------------------------------------------------- Interno

    def _validar_correo(
        self, correo: object, *, actor: Usuario | None, accion: str
    ) -> None:
        """Formato minimo del correo (RN-03).

        Se valida al escribir y no en `modelos.Usuario.__post_init__` a
        proposito: `__post_init__` corre en `desde_dict`, que corre en cada
        `listar()`. Una sola fila con un correo mal formado en `datos/` haria
        que `ErrorValidacion` saliera de `RepositorioJson.listar()` y ninguna
        operacion funcionara, ni siquiera listar usuarios para encontrar la fila
        culpable. Validando al escribir, un dato heredado sigue siendo legible y
        se puede corregir con `editar_usuario`.
        """
        if not isinstance(correo, str) or not _CORREO_VALIDO.fullmatch(correo.strip()):
            self._rechazar(
                "El correo debe tener la forma 'nombre@dominio'.",
                actor=actor,
                accion=accion,
                motivo="correo_invalido",
            )

    def _exigir_id_libre(
        self, id_usuario: object, *, actor: Usuario | None, accion: str
    ) -> None:
        """Unicidad del id sin distinguir mayusculas (RN-03).

        `RepositorioJson` solo compara `campo_id` de forma exacta, asi que sin
        esta comprobacion podrian convivir `u1` y `U1`. No es un detalle
        cosmetico: `auth._resolver` busca con `casefold()` y levanta
        `ErrorPersistencia` ante mas de una coincidencia, de modo que ambos
        usuarios quedarian sin poder iniciar sesion nunca.
        """
        if not isinstance(id_usuario, str) or not id_usuario.strip():
            # Deja que el modelo produzca el mensaje de campo obligatorio.
            return
        buscado = id_usuario.casefold()
        if any(u.id.casefold() == buscado for u in self._usuarios.listar()):
            self._rechazar(
                f"Ya existe un usuario con el id '{id_usuario}'.",
                actor=actor,
                accion=accion,
                motivo="id_duplicado",
                objetivo=id_usuario,
            )

    def _exigir_correo_libre(
        self,
        correo: str,
        *,
        actor: Usuario | None,
        accion: str,
        excluir_id: str | None = None,
    ) -> None:
        """Unicidad del correo sin distinguir mayusculas (RN-03).

        Se comprueba por separado del id, sin cruzarlos: un correo lleva arroba
        y un id no, asi que no pueden colisionar entre si en la practica, y
        cruzarlos rechazaria datos legitimos para cubrir un caso imposible.
        """
        buscado = correo.strip().casefold()
        for usuario in self._usuarios.listar():
            if excluir_id is not None and usuario.id == excluir_id:
                continue
            if usuario.correo.casefold() == buscado:
                self._rechazar(
                    "Ya existe un usuario registrado con ese correo.",
                    actor=actor,
                    accion=accion,
                    motivo="correo_duplicado",
                    # El correo no viaja a `detalles`: `para_log()` termina en el
                    # log y en Sentry (RN-18).
                    objetivo=excluir_id,
                )

    def _proteger_ultimo_encargado(
        self,
        actual: Usuario,
        resultante: Usuario,
        *,
        actor: Usuario | None,
        accion: str,
    ) -> None:
        """Impide que el sistema quede sin ningun Encargado activo.

        Cubre las dos formas de llegar ahi -bajar el rol y desactivar la cuenta-
        comparando el antes y el despues, en vez de repetir la comprobacion en
        cada operacion.

        Sin esto, el unico Encargado puede dejarse a si mismo sin permisos y el
        sistema queda inutilizable de forma permanente: nadie podria pasar
        `requiere_rol(ENCARGADO)`, y `crear_encargado_inicial` se niega a correr
        porque ya existen usuarios. La unica salida seria editar el JSON a mano.
        """
        era_encargado_activo = actual.activo and actual.rol is Rol.ENCARGADO
        sigue_siendolo = resultante.activo and resultante.rol is Rol.ENCARGADO
        if not era_encargado_activo or sigue_siendolo:
            return

        quedan_otros = any(
            u.id != actual.id and u.activo and u.rol is Rol.ENCARGADO
            for u in self._usuarios.listar()
        )
        if not quedan_otros:
            self._rechazar(
                "No se puede dejar el sistema sin ningun Encargado activo. "
                "Registre o reactive otro Encargado antes de este cambio.",
                actor=actor,
                accion=accion,
                motivo="ultimo_encargado",
                regla="RN-20",
                objetivo=actual.id,
            )

    def _rechazar(
        self,
        mensaje: str,
        *,
        actor: Usuario | None,
        accion: str,
        motivo: str,
        objetivo: str | None = None,
        regla: str = "RN-03",
    ) -> NoReturn:
        """Registra el rechazo y lo levanta (RN-17, RN-18).

        Los rechazos se registran igual que los exitos: son lo que necesitan las
        pruebas negativas (#18) y lo que hace auditable un intento fallido.
        """
        self._evento(
            accion,
            actor=actor,
            objetivo=objetivo,
            resultado="error",
            motivo=motivo,
        )
        raise ErrorValidacion(mensaje, regla=regla, detalles={"motivo": motivo})

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


def crear_encargado_inicial(
    id_usuario: str,
    nombre: str,
    correo: str,
    contrasena: str,
    *,
    repositorio: RepositorioJson[Usuario] | None = None,
    datos_dir: str | Path | None = None,
    logger: logging.Logger | None = None,
    iteraciones_hash: int = ITERACIONES_PBKDF2,
) -> Usuario:
    """Crea el primer Encargado de un sistema vacio (RF-01).

    Existe porque `ServicioUsuarios.registrar_usuario` exige una sesion de
    Encargado, y en un `usuarios.json` vacio no hay nadie con quien iniciarla:
    sin este seam, un sistema recien instalado no tiene forma de crear a su
    primer usuario.

    Se niega a correr si existe *cualquier* usuario. Esa condicion es lo que
    mantiene la excepcion cerrada: no es "si no hay Encargados activos", que
    volveria a abrirse cada vez que alguien desactivara al ultimo y convertiria
    esta funcion en un camino permanente para saltarse la autorizacion. Vaciar
    el padron a mano para reabrirla ya requiere acceso al disco, que es de por si
    mas privilegio que el que esta funcion concede.

    Es el camino soportado para #15 (`init-demo`): escribir `usuarios.json` a
    mano se salta las validaciones de RN-03 y puede producir usuarios que jamas
    logren iniciar sesion. No se expone en la CLI ni en el menu (#14).
    """
    usuarios = repositorio or repositorio_usuarios(datos_dir)

    existentes = usuarios.listar()
    if existentes:
        registrar_evento(
            "encargado_inicial_creado",
            resultado="error",
            logger=logger,
            motivo="padron_no_vacio",
            usuarios_existentes=len(existentes),
        )
        raise ErrorValidacion(
            "Ya existen usuarios registrados: el Encargado inicial solo puede "
            "crearse sobre un sistema vacio.",
            regla="RN-03",
            detalles={"motivo": "padron_no_vacio"},
        )

    if not isinstance(correo, str) or not _CORREO_VALIDO.fullmatch(correo.strip()):
        registrar_evento(
            "encargado_inicial_creado",
            resultado="error",
            logger=logger,
            motivo="correo_invalido",
        )
        raise ErrorValidacion(
            "El correo debe tener la forma 'nombre@dominio'.",
            regla="RN-03",
            detalles={"motivo": "correo_invalido"},
        )

    encargado = Usuario(
        id=id_usuario,
        nombre=nombre,
        correo=correo,
        rol=Rol.ENCARGADO,
        activo=True,
        hash_contrasena=hash_contrasena(contrasena, iteraciones=iteraciones_hash),
    )
    usuarios.guardar(encargado)
    registrar_evento(
        "encargado_inicial_creado",
        usuario=encargado.id,
        resultado="ok",
        logger=logger,
    )
    return encargado
