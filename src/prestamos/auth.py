"""Autenticacion basica y control de acceso por rol (RF-02, RN-01, RN-02, RN-11).

El modulo tiene dos mitades deliberadamente separadas:

- Funciones puras (`hash_contrasena`, `verificar_contrasena`) que no dependen de
  ninguna sesion ni de ningun repositorio. Son las que usan el servicio de
  usuarios (RF-01) y la carga de datos de demostracion para *crear* credenciales.
- `ServicioAuth`, que si tiene estado (la sesion en memoria) y recibe por
  inyeccion el repositorio de usuarios y, opcionalmente, el logger.

`modelos.Usuario` guarda la credencial como una cadena opaca y declara que "el
dominio no conoce el algoritmo: eso pertenece a ``prestamos.auth``". Este modulo
es el unico lugar del sistema que sabe como esta construida esa cadena.

Nota para la CLI y el menu (issue #14): `iniciar_sesion` rechaza el intento si ya
hay una sesion abierta, asi que "cambiar de usuario" es siempre `cerrar_sesion()`
seguido de `iniciar_sesion(...)`, nunca un login directo encima de otro.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from prestamos.errores import (
    ErrorAutenticacion,
    ErrorAutorizacion,
    ErrorPersistencia,
    ErrorValidacion,
)
from prestamos.logging_conf import registrar_evento
from prestamos.modelos import Rol, Usuario
from prestamos.repositorios.json_repo import RepositorioJson

ALGORITMO = "pbkdf2_sha256"
ITERACIONES_PBKDF2 = 200_000
BYTES_DE_SAL = 16

# Un unico mensaje para "no existe" y para "contrasena incorrecta": distinguirlos
# solo sirve para averiguar que cuentas existen. El usuario inactivo si tiene
# mensaje propio, porque RN-02 es una regla verificable por separado.
MENSAJE_CREDENCIALES = "Credenciales invalidas."
MENSAJE_INACTIVO = "El usuario esta inactivo y no puede iniciar sesion."


# --------------------------------------------------------------------- Hashing


def hash_contrasena(
    contrasena: str,
    *,
    iteraciones: int = ITERACIONES_PBKDF2,
) -> str:
    """Deriva la contrasena a la cadena opaca que guarda `Usuario` (RN-03).

    Formato, cuatro campos separados por ``$``::

        pbkdf2_sha256$200000$<sal_hex>$<digest_hex>

    La cadena es autodescriptiva a proposito: `verificar_contrasena` lee de ahi
    el numero de iteraciones en vez de asumir la constante del modulo, de modo
    que subir `ITERACIONES_PBKDF2` no invalida las credenciales ya creadas.

    `iteraciones` es un parametro y no solo una constante para que las pruebas
    puedan derivar con 1 iteracion; en produccion nadie deberia pasarlo.
    """
    if not isinstance(contrasena, str) or not contrasena.strip():
        raise ErrorValidacion(
            "La contrasena es obligatoria y no puede estar vacia.",
            regla="RN-03",
            detalles={"campo": "contrasena"},
        )
    if iteraciones < 1:
        # Error de programacion, no del usuario: no es un ErrorDominio.
        raise ValueError("El numero de iteraciones debe ser mayor o igual a 1.")

    sal = secrets.token_bytes(BYTES_DE_SAL)
    digest = _derivar(contrasena, sal, iteraciones)
    return f"{ALGORITMO}${iteraciones}${sal.hex()}${digest.hex()}"


def verificar_contrasena(contrasena: str, hash_almacenado: str) -> bool:
    """Compara una contrasena contra la cadena almacenada.

    Una cadena corrupta o de otro formato levanta `ErrorPersistencia` en lugar
    de devolver ``False``: tratar la corrupcion como "contrasena equivocada"
    esconderia un problema real de los datos detras de un login fallido, que es
    justo la distincion que `errores.py` documenta para esa excepcion.
    """
    iteraciones, sal, digest_esperado = _descomponer(hash_almacenado)
    if not isinstance(contrasena, str):
        return False
    digest = _derivar(contrasena, sal, iteraciones)
    return hmac.compare_digest(digest, digest_esperado)


def _derivar(contrasena: str, sal: bytes, iteraciones: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), sal, iteraciones)


def _descomponer(hash_almacenado: object) -> tuple[int, bytes, bytes]:
    """Parte la cadena almacenada en (iteraciones, sal, digest).

    `detalles` describe *que* esta mal, nunca el contenido del hash: `para_log()`
    viaja a los logs y a Sentry (RN-18).
    """
    if not isinstance(hash_almacenado, str):
        raise _hash_corrupto("tipo_invalido")

    partes = hash_almacenado.split("$")
    if len(partes) != 4:
        raise _hash_corrupto("numero_de_campos")

    algoritmo, iteraciones_texto, sal_hex, digest_hex = partes
    if algoritmo != ALGORITMO:
        raise _hash_corrupto("algoritmo_desconocido")

    try:
        iteraciones = int(iteraciones_texto)
    except ValueError as exc:
        raise _hash_corrupto("iteraciones_no_numericas") from exc
    if iteraciones < 1:
        raise _hash_corrupto("iteraciones_fuera_de_rango")

    try:
        sal = bytes.fromhex(sal_hex)
        digest = bytes.fromhex(digest_hex)
    except ValueError as exc:
        raise _hash_corrupto("hex_invalido") from exc
    if not sal or not digest:
        raise _hash_corrupto("campos_vacios")

    return iteraciones, sal, digest


def _hash_corrupto(motivo: str) -> ErrorPersistencia:
    return ErrorPersistencia(
        "La credencial almacenada del usuario no tiene un formato valido.",
        detalles={"motivo": motivo},
    )


# --------------------------------------------------------------------- Sesion


@dataclass(frozen=True)
class Sesion:
    """Usuario autenticado durante la ejecucion actual.

    `usuario` es siempre la instancia *almacenada*, no una reconstruida a partir
    de lo que se tecleo en el prompt: ver `ServicioAuth._resolver`.

    No hay expiracion por tiempo. Nada en el contrato la pide y anadirla meteria
    una dependencia del reloj en cada comprobacion de permisos.
    """

    usuario: Usuario
    iniciada_en: datetime


class ServicioAuth:
    """Inicio de sesion y guardas de autorizacion.

    El repositorio y el logger se inyectan; no hay estado global de modulo. Eso
    mantiene las pruebas hermeticas (cada una construye su propio servicio sobre
    ``tmp_path``, sin nada que resetear) y evita el problema del logger: como
    `configurar_logging` acumula handlers sobre el logger singleton
    ``"prestamos"``, un servicio que siempre usara el logger por defecto
    escribiria los eventos de las pruebas en el log real del proyecto.
    """

    def __init__(
        self,
        repositorio_usuarios: RepositorioJson[Usuario],
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._usuarios = repositorio_usuarios
        self._logger = logger
        self._sesion: Sesion | None = None

    # ------------------------------------------------------------------ API

    @property
    def sesion(self) -> Sesion | None:
        return self._sesion

    @property
    def usuario_actual(self) -> Usuario | None:
        """Usuario de la sesion, para *mostrar* en pantalla.

        No relee el repositorio, asi que puede estar desactualizado. Nunca debe
        usarse para decidir un permiso: para eso estan `requiere_sesion` y
        `requiere_rol`, que si consultan el disco.
        """
        return self._sesion.usuario if self._sesion is not None else None

    def iniciar_sesion(self, identificador: str, contrasena: str) -> Sesion:
        """Autentica por id o por correo y abre la sesion (RF-02, RN-02).

        El orden de los pasos importa:

        1. Si ya hay sesion se rechaza antes de mirar las credenciales, para no
           correr la KDF ni tocar la contrasena.
        2. Se resuelve el identificador (ver `_resolver`).
        3. Se verifica la contrasena *antes* de mirar `activo`, de modo que "esta
           cuenta esta inactiva" solo se le revela a quien ya demostro la
           credencial.
        4. La sesion se asigna al final. Nunca se limpia antes de verificar: un
           intento fallido no puede cerrar la sesion que ya estaba abierta.
        """
        if self._sesion is not None:
            self._evento(
                "login",
                usuario=self._sesion.usuario.id,
                resultado="error",
                motivo="sesion_ya_iniciada",
            )
            raise ErrorAutenticacion(
                "Ya hay una sesion iniciada. Cierre la sesion actual antes de "
                "iniciar otra.",
                detalles={"motivo": "sesion_ya_iniciada"},
            )

        usuario = self._resolver(identificador)

        if usuario is None:
            # Unico caso en que se registra el texto tecleado: no coincide con
            # ninguna cuenta, y sin el la auditoria de intentos fallidos no
            # sirve de nada. Si el usuario existe se registra su id canonico,
            # de modo que los correos no se acumulan en el log (RN-18).
            self._evento(
                "login",
                usuario=identificador,
                resultado="error",
                motivo="credenciales_invalidas",
            )
            raise self._credenciales_invalidas()

        if not verificar_contrasena(contrasena, usuario.hash_contrasena):
            self._evento(
                "login",
                usuario=usuario.id,
                resultado="error",
                motivo="credenciales_invalidas",
            )
            raise self._credenciales_invalidas()

        if not usuario.activo:
            self._evento(
                "login",
                usuario=usuario.id,
                resultado="error",
                motivo="usuario_inactivo",
            )
            raise ErrorAutenticacion(
                MENSAJE_INACTIVO,
                regla="RN-02",
                detalles={"motivo": "usuario_inactivo"},
            )

        self._sesion = Sesion(usuario=usuario, iniciada_en=datetime.now(timezone.utc))
        self._evento("login", usuario=usuario.id, resultado="ok", rol=usuario.rol.value)
        return self._sesion

    def cerrar_sesion(self) -> None:
        """Cierra la sesion. Es idempotente: sin sesion abierta no hace nada.

        Decision opuesta a `RepositorioJson.eliminar`, que si levanta cuando el
        registro no existe. Borrar algo inexistente significa que el llamador se
        equivoco sobre los datos; cerrar una sesion vacia ya consigue lo pedido.
        """
        if self._sesion is None:
            return
        usuario_id = self._sesion.usuario.id
        self._sesion = None
        self._evento("logout", usuario=usuario_id, resultado="ok")

    def requiere_sesion(self) -> Usuario:
        """Exige una sesion valida y devuelve el usuario *fresco* (RN-02).

        Relee el repositorio en cada llamada en vez de confiar en la copia de la
        sesion. RN-02 dice "iniciar sesion **y operar**", y esa segunda mitad
        solo se cumple releyendo: `menu.py` es un bucle interactivo, asi que un
        encargado puede desactivar a alguien -o a si mismo- con la sesion
        abierta. La alternativa seria un hook de invalidacion desde el servicio
        de usuarios hacia este modulo, peor acoplamiento que una lectura.

        Si la sesion dejo de ser valida se cierra antes de levantar: mantenerla
        dejaria a `usuario_actual` mostrando a alguien que ya no puede operar.
        """
        if self._sesion is None:
            raise ErrorAutenticacion(
                "No hay sesion iniciada.",
                detalles={"motivo": "sin_sesion"},
            )

        # Siempre por el id canonico almacenado, nunca por lo que se tecleo.
        usuario = self._usuarios.buscar(self._sesion.usuario.id)

        if usuario is None:
            self._invalidar("usuario_inexistente")
            raise ErrorAutenticacion(
                "La sesion ya no es valida: el usuario no existe.",
                detalles={"motivo": "usuario_inexistente"},
            )

        if not usuario.activo:
            self._invalidar("usuario_inactivo")
            raise ErrorAutenticacion(
                MENSAJE_INACTIVO,
                regla="RN-02",
                detalles={"motivo": "usuario_inactivo"},
            )

        return usuario

    def requiere_rol(self, *roles: Rol) -> Usuario:
        """Exige sesion valida y uno de los roles indicados (RN-01, RN-11).

        Devuelve el usuario porque la relectura ya lo tiene en la mano y todo
        llamador lo necesita igual::

            usuario = auth.requiere_rol(Rol.ENCARGADO)

        Asi el permiso y la identidad son visiblemente la misma operacion, y no
        hay forma de obtener una sin comprobar el otro.
        """
        if not roles:
            # "Cualquier rol autenticado" es `requiere_sesion()`, que lo dice en
            # su nombre. Llegar aqui sin roles es un bug nuestro.
            raise ValueError(
                "requiere_rol necesita al menos un rol; use requiere_sesion() "
                "si basta con estar autenticado."
            )

        usuario = self.requiere_sesion()
        if usuario.rol not in roles:
            requeridos = [rol.value for rol in roles]
            self._evento(
                "autorizacion",
                usuario=usuario.id,
                resultado="error",
                rol_actual=usuario.rol.value,
                roles_requeridos=requeridos,
            )
            raise ErrorAutorizacion(
                "No tiene permisos para realizar esta operacion.",
                regla="RN-11",
                detalles={
                    "rol_actual": usuario.rol.value,
                    "roles_requeridos": requeridos,
                },
            )
        # La autorizacion exitosa no genera evento: se dispararia en cada accion y
        # el evento propio de la accion ya la implica.
        return usuario

    # -------------------------------------------------------------- Interno

    def _resolver(self, identificador: str) -> Usuario | None:
        """Busca por id y, si no hay, por correo. Ambos sin distinguir mayusculas.

        Se devuelve la instancia *almacenada*, de modo que lo que la persona
        tecleo no viaja mas alla de esta funcion. Eso es lo que permite que el
        login ignore mayusculas sin tocar el repositorio: `RepositorioJson`
        sigue comparando exacto, `requiere_sesion` relee con el id canonico y
        `Prestamo.id_solicitante` recibe el id real.

        Mas de una coincidencia es un problema de integridad de los datos, no un
        login fallido: RN-03 exige que id y correo sean unicos, pero el
        repositorio solo lo impone sobre `campo_id`, asi que nada estructural
        impide dos correos iguales -o un ``u1`` y un ``U1``-.
        """
        if not isinstance(identificador, str) or not identificador:
            return None

        buscado = identificador.casefold()
        usuarios = self._usuarios.listar()

        campo = "id"
        coincidencias = [u for u in usuarios if u.id.casefold() == buscado]
        if not coincidencias:
            campo = "correo"
            coincidencias = [u for u in usuarios if u.correo.casefold() == buscado]

        if len(coincidencias) > 1:
            # No se incluye el identificador en `detalles`: puede ser un correo
            # y `para_log()` termina en el log y en Sentry (RN-18).
            raise ErrorPersistencia(
                "Hay mas de un usuario registrado con ese identificador.",
                regla="RN-03",
                detalles={"campo": campo, "coincidencias": len(coincidencias)},
            )
        return coincidencias[0] if coincidencias else None

    def _invalidar(self, motivo: str) -> None:
        usuario_id = self._sesion.usuario.id if self._sesion else None
        self._sesion = None
        self._evento(
            "autorizacion",
            usuario=usuario_id,
            resultado="error",
            motivo=motivo,
        )

    def _credenciales_invalidas(self) -> ErrorAutenticacion:
        return ErrorAutenticacion(
            MENSAJE_CREDENCIALES,
            detalles={"motivo": "credenciales_invalidas"},
        )

    def _evento(self, accion: str, **campos: Any) -> None:
        """Registra un evento de auditoria (RN-18).

        La contrasena no se pasa nunca por aqui. `sanitizar()` la enmascararia
        si viniera bajo una clave que contenga "contrasena" o "password", pero
        empareja por *nombre de clave*: pasarla como `credencial` la burlaria en
        silencio. Es una red de seguridad, no la politica.
        """
        registrar_evento(accion, logger=self._logger, **campos)
