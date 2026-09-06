"""Pruebas de `prestamos.auth`: hashing, inicio de sesion y control de rol.

Nombres descriptivos y sin etiqueta CP-XX, igual que `test_json_repo.py`. El
catalogo de casos (`docs/casos-de-prueba.md`) define solo CP-01..CP-15 y lo
asignan los issues #16-#19; ver el defecto DEF-01 (issue #43).

Todas las derivaciones usan `iteraciones=1`: aqui interesa el contrato del
formato, no el costo de la KDF.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from pathlib import Path

import pytest

from prestamos.auth import (
    ALGORITMO,
    ServicioAuth,
    hash_contrasena,
    verificar_contrasena,
)
from prestamos.errores import (
    ErrorAutenticacion,
    ErrorAutorizacion,
    ErrorPersistencia,
    ErrorValidacion,
)
from prestamos.logging_conf import LOGGER_NAME, configurar_logging
from prestamos.modelos import Rol, Usuario
from prestamos.repositorios.json_repo import RepositorioJson

CONTRASENA = "clave-de-demostracion"


def _usuario(
    id_usuario: str = "u1",
    *,
    correo: str = "ana.perez@universidad.cl",
    rol: Rol = Rol.SOLICITANTE,
    activo: bool = True,
    contrasena: str = CONTRASENA,
) -> Usuario:
    return Usuario(
        id=id_usuario,
        nombre="Ana Perez",
        correo=correo,
        rol=rol,
        activo=activo,
        hash_contrasena=hash_contrasena(contrasena, iteraciones=1),
    )


@pytest.fixture
def repo_usuarios(tmp_path: Path) -> RepositorioJson[Usuario]:
    return RepositorioJson(tmp_path / "usuarios.json", Usuario, "id")


@pytest.fixture
def log_pruebas(tmp_path: Path):
    """Logger de archivo aislado por prueba.

    `configurar_logging` agrega handlers al logger singleton `"prestamos"`, asi
    que el handler se quita al terminar: sin esto los eventos de una prueba se
    irian tambien a los archivos de las siguientes.
    """
    ruta = tmp_path / "eventos.log"
    logger = configurar_logging(ruta)
    yield logger, ruta
    for handler in list(logging.getLogger(LOGGER_NAME).handlers):
        if getattr(handler, "_prestamos_log_path", None) == ruta.resolve():
            logger.removeHandler(handler)
            handler.close()


def _eventos(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    return [
        json.loads(linea)
        for linea in ruta.read_text(encoding="utf-8").splitlines()
        if linea.strip()
    ]


# ------------------------------------------------------------------- Hashing


def test_hash_tiene_los_cuatro_campos_del_formato() -> None:
    partes = hash_contrasena(CONTRASENA, iteraciones=1).split("$")

    assert len(partes) == 4
    assert partes[0] == ALGORITMO
    assert partes[1] == "1"
    assert bytes.fromhex(partes[2])
    assert bytes.fromhex(partes[3])


def test_dos_hashes_de_la_misma_contrasena_difieren_por_la_sal() -> None:
    primero = hash_contrasena(CONTRASENA, iteraciones=1)
    segundo = hash_contrasena(CONTRASENA, iteraciones=1)

    assert primero != segundo
    assert verificar_contrasena(CONTRASENA, primero)
    assert verificar_contrasena(CONTRASENA, segundo)


def test_el_hash_no_contiene_la_contrasena() -> None:
    assert CONTRASENA not in hash_contrasena(CONTRASENA, iteraciones=1)


def test_verificar_rechaza_la_contrasena_incorrecta() -> None:
    almacenado = hash_contrasena(CONTRASENA, iteraciones=1)

    assert verificar_contrasena("otra-cosa", almacenado) is False
    assert verificar_contrasena("", almacenado) is False


def test_verificar_usa_las_iteraciones_almacenadas_y_no_la_constante() -> None:
    # El hash se derivo con 1 iteracion; la constante del modulo son 200_000.
    # Si `verificar_contrasena` usara la constante, esto fallaria.
    almacenado = hash_contrasena(CONTRASENA, iteraciones=1)

    assert almacenado.split("$")[1] == "1"
    assert verificar_contrasena(CONTRASENA, almacenado)


def test_contrasena_vacia_o_en_blanco_es_error_de_validacion() -> None:
    for invalida in ("", "   ", "\t"):
        with pytest.raises(ErrorValidacion) as exc:
            hash_contrasena(invalida)
        assert exc.value.regla == "RN-03"


def test_iteraciones_invalidas_son_error_de_programacion() -> None:
    with pytest.raises(ValueError):
        hash_contrasena(CONTRASENA, iteraciones=0)


@pytest.mark.parametrize(
    "almacenado",
    [
        "no-es-un-hash",
        "pbkdf2_sha256$1$aabb",
        "sha256$1$aabb$ccdd",
        "pbkdf2_sha256$muchas$aabb$ccdd",
        "pbkdf2_sha256$0$aabb$ccdd",
        "pbkdf2_sha256$1$zzzz$ccdd",
        "pbkdf2_sha256$1$$ccdd",
    ],
)
def test_hash_corrupto_levanta_error_de_persistencia(almacenado: str) -> None:
    with pytest.raises(ErrorPersistencia):
        verificar_contrasena(CONTRASENA, almacenado)


def test_credencial_truncada_es_corrupcion_y_no_contrasena_equivocada() -> None:
    """Una sal o un digest recortados no pueden pasar por "clave incorrecta".

    Sin la comprobacion de largos, `hmac.compare_digest` simplemente devolveria
    False y un `usuarios.json` truncado se veria igual que un typo del usuario.
    """
    algoritmo, iteraciones, sal, digest = hash_contrasena(
        CONTRASENA, iteraciones=1
    ).split("$")

    with pytest.raises(ErrorPersistencia) as sal_corta:
        verificar_contrasena(CONTRASENA, f"{algoritmo}${iteraciones}${sal[:2]}${digest}")
    with pytest.raises(ErrorPersistencia) as digest_corto:
        verificar_contrasena(CONTRASENA, f"{algoritmo}${iteraciones}${sal}${digest[:2]}")
    with pytest.raises(ErrorPersistencia) as digest_largo:
        verificar_contrasena(
            CONTRASENA, f"{algoritmo}${iteraciones}${sal}${digest}00"
        )

    assert sal_corta.value.detalles["motivo"] == "sal_demasiado_corta"
    assert digest_corto.value.detalles["motivo"] == "largo_de_digest_invalido"
    assert digest_largo.value.detalles["motivo"] == "largo_de_digest_invalido"


def test_una_sal_mas_larga_que_la_actual_sigue_siendo_valida() -> None:
    """El minimo protege de truncamientos sin congelar `BYTES_DE_SAL`.

    Si algun dia la constante de generacion sube, las credenciales ya creadas
    con 16 bytes deben seguir sirviendo -y las nuevas, mas largas, tambien-.
    Por eso la sal se compara contra un minimo y no contra la constante.
    """
    sal = secrets.token_bytes(32)
    digest = hashlib.pbkdf2_hmac("sha256", CONTRASENA.encode("utf-8"), sal, 1)

    assert verificar_contrasena(CONTRASENA, f"{ALGORITMO}$1${sal.hex()}${digest.hex()}")


def test_error_de_hash_corrupto_no_filtra_la_credencial() -> None:
    almacenado = "pbkdf2_sha256$1$aabb"

    with pytest.raises(ErrorPersistencia) as exc:
        verificar_contrasena(CONTRASENA, almacenado)

    volcado = json.dumps(exc.value.para_log())
    assert "aabb" not in volcado
    assert CONTRASENA not in volcado


# --------------------------------------------------------------------- Login


def test_login_correcto_abre_la_sesion(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario())
    auth = ServicioAuth(repo_usuarios)

    sesion = auth.iniciar_sesion("u1", CONTRASENA)

    assert sesion.usuario.id == "u1"
    assert auth.usuario_actual is not None
    assert auth.usuario_actual.id == "u1"
    assert sesion.iniciada_en.tzinfo is not None


def test_login_por_correo(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario(correo="ana.perez@universidad.cl"))
    auth = ServicioAuth(repo_usuarios)

    sesion = auth.iniciar_sesion("ana.perez@universidad.cl", CONTRASENA)

    assert sesion.usuario.id == "u1"


@pytest.mark.parametrize(
    "tecleado", ["U1", "u1", "ANA.PEREZ@UNIVERSIDAD.CL", "Ana.Perez@Universidad.cl"]
)
def test_login_ignora_mayusculas_en_id_y_en_correo(repo_usuarios, tecleado) -> None:
    repo_usuarios.guardar(_usuario())
    auth = ServicioAuth(repo_usuarios)

    assert auth.iniciar_sesion(tecleado, CONTRASENA).usuario.id == "u1"


def test_la_sesion_guarda_el_id_almacenado_y_no_el_tecleado(repo_usuarios) -> None:
    """La canonicalizacion es lo que hace seguro el login sin mayusculas."""
    repo_usuarios.guardar(_usuario("u1"))
    auth = ServicioAuth(repo_usuarios)

    sesion = auth.iniciar_sesion("U1", CONTRASENA)

    assert sesion.usuario.id == "u1"
    # El id de la sesion sirve para releer del repositorio, que compara exacto.
    assert repo_usuarios.buscar(sesion.usuario.id) is not None
    assert auth.requiere_sesion().id == "u1"


def test_usuario_inexistente_y_contrasena_mala_dan_el_mismo_mensaje(
    repo_usuarios,
) -> None:
    repo_usuarios.guardar(_usuario())
    auth = ServicioAuth(repo_usuarios)

    with pytest.raises(ErrorAutenticacion) as inexistente:
        auth.iniciar_sesion("no-existe", CONTRASENA)
    with pytest.raises(ErrorAutenticacion) as contrasena_mala:
        auth.iniciar_sesion("u1", "equivocada")

    assert inexistente.value.mensaje == contrasena_mala.value.mensaje
    assert inexistente.value.detalles == contrasena_mala.value.detalles
    assert inexistente.value.detalles["motivo"] == "credenciales_invalidas"


def test_usuario_inactivo_tiene_mensaje_propio(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario(activo=False))
    auth = ServicioAuth(repo_usuarios)

    with pytest.raises(ErrorAutenticacion) as exc:
        auth.iniciar_sesion("u1", CONTRASENA)

    assert exc.value.regla == "RN-02"
    assert exc.value.detalles["motivo"] == "usuario_inactivo"
    assert auth.usuario_actual is None


def test_inactivo_con_contrasena_mala_no_revela_que_esta_inactivo(
    repo_usuarios,
) -> None:
    """La contrasena se verifica antes de mirar `activo`."""
    repo_usuarios.guardar(_usuario(activo=False))
    auth = ServicioAuth(repo_usuarios)

    with pytest.raises(ErrorAutenticacion) as exc:
        auth.iniciar_sesion("u1", "equivocada")

    assert exc.value.detalles["motivo"] == "credenciales_invalidas"


def test_correo_duplicado_es_error_de_persistencia(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario("u1", correo="repetido@universidad.cl"))
    repo_usuarios.guardar(_usuario("u2", correo="repetido@universidad.cl"))
    auth = ServicioAuth(repo_usuarios)

    with pytest.raises(ErrorPersistencia) as exc:
        auth.iniciar_sesion("repetido@universidad.cl", CONTRASENA)

    assert exc.value.detalles["campo"] == "correo"


def test_colision_de_mayusculas_en_el_id_es_error_de_persistencia(
    repo_usuarios,
) -> None:
    repo_usuarios.guardar(_usuario("u1", correo="a@universidad.cl"))
    repo_usuarios.guardar(_usuario("U1", correo="b@universidad.cl"))
    auth = ServicioAuth(repo_usuarios)

    with pytest.raises(ErrorPersistencia) as exc:
        auth.iniciar_sesion("u1", CONTRASENA)

    assert exc.value.detalles["campo"] == "id"


def test_el_id_tiene_precedencia_sobre_el_correo(repo_usuarios) -> None:
    # El id de "u2" es igual al correo de "u1".
    repo_usuarios.guardar(_usuario("u1", correo="compartido"))
    repo_usuarios.guardar(_usuario("compartido", correo="otro@universidad.cl"))
    auth = ServicioAuth(repo_usuarios)

    assert auth.iniciar_sesion("compartido", CONTRASENA).usuario.id == "compartido"


def test_login_con_sesion_abierta_se_rechaza(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario("u1", correo="a@universidad.cl"))
    repo_usuarios.guardar(_usuario("u2", correo="b@universidad.cl"))
    auth = ServicioAuth(repo_usuarios)
    auth.iniciar_sesion("u1", CONTRASENA)

    with pytest.raises(ErrorAutenticacion) as exc:
        auth.iniciar_sesion("u2", CONTRASENA)

    assert exc.value.detalles["motivo"] == "sesion_ya_iniciada"
    # La sesion original sigue intacta.
    assert auth.usuario_actual.id == "u1"


def test_login_fallido_no_cierra_una_sesion_abierta(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario("u1"))
    auth = ServicioAuth(repo_usuarios)
    auth.iniciar_sesion("u1", CONTRASENA)

    with pytest.raises(ErrorAutenticacion):
        auth.iniciar_sesion("u1", "equivocada")

    assert auth.usuario_actual.id == "u1"


# -------------------------------------------------------------------- Sesion


def test_cerrar_sesion_sin_sesion_no_falla(repo_usuarios) -> None:
    auth = ServicioAuth(repo_usuarios)

    auth.cerrar_sesion()
    auth.cerrar_sesion()

    assert auth.usuario_actual is None


def test_cerrar_sesion_permite_entrar_con_otro_usuario(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario("u1", correo="a@universidad.cl"))
    repo_usuarios.guardar(_usuario("u2", correo="b@universidad.cl"))
    auth = ServicioAuth(repo_usuarios)

    auth.iniciar_sesion("u1", CONTRASENA)
    auth.cerrar_sesion()

    assert auth.iniciar_sesion("u2", CONTRASENA).usuario.id == "u2"


# -------------------------------------------------------------- Autorizacion


def test_requiere_sesion_sin_sesion_levanta_autenticacion(repo_usuarios) -> None:
    auth = ServicioAuth(repo_usuarios)

    with pytest.raises(ErrorAutenticacion) as exc:
        auth.requiere_sesion()

    assert exc.value.detalles["motivo"] == "sin_sesion"


def test_requiere_rol_con_rol_correcto_devuelve_el_usuario(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario(rol=Rol.ENCARGADO))
    auth = ServicioAuth(repo_usuarios)
    auth.iniciar_sesion("u1", CONTRASENA)

    usuario = auth.requiere_rol(Rol.ENCARGADO)

    assert usuario.id == "u1"
    assert usuario.rol is Rol.ENCARGADO


def test_requiere_rol_con_rol_incorrecto_levanta_autorizacion(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario(rol=Rol.SOLICITANTE))
    auth = ServicioAuth(repo_usuarios)
    auth.iniciar_sesion("u1", CONTRASENA)

    with pytest.raises(ErrorAutorizacion) as exc:
        auth.requiere_rol(Rol.ENCARGADO)

    assert exc.value.regla == "RN-11"
    assert exc.value.detalles["rol_actual"] == Rol.SOLICITANTE.value
    assert exc.value.detalles["roles_requeridos"] == [Rol.ENCARGADO.value]


def test_requiere_rol_acepta_varios_roles(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario(rol=Rol.SOLICITANTE))
    auth = ServicioAuth(repo_usuarios)
    auth.iniciar_sesion("u1", CONTRASENA)

    assert auth.requiere_rol(Rol.ENCARGADO, Rol.SOLICITANTE).id == "u1"


def test_requiere_rol_sin_argumentos_es_error_de_programacion(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario())
    auth = ServicioAuth(repo_usuarios)
    auth.iniciar_sesion("u1", CONTRASENA)

    with pytest.raises(ValueError):
        auth.requiere_rol()


def test_usuario_desactivado_durante_la_sesion_pierde_el_acceso(
    repo_usuarios,
) -> None:
    """RN-02 exige usuario activo para iniciar sesion *y para operar*."""
    repo_usuarios.guardar(_usuario(rol=Rol.ENCARGADO))
    auth = ServicioAuth(repo_usuarios)
    auth.iniciar_sesion("u1", CONTRASENA)

    almacenado = repo_usuarios.obtener("u1")
    repo_usuarios.guardar(
        Usuario(
            id=almacenado.id,
            nombre=almacenado.nombre,
            correo=almacenado.correo,
            rol=almacenado.rol,
            activo=False,
            hash_contrasena=almacenado.hash_contrasena,
        )
    )

    with pytest.raises(ErrorAutenticacion) as exc:
        auth.requiere_rol(Rol.ENCARGADO)

    assert exc.value.regla == "RN-02"
    assert auth.usuario_actual is None


def test_usuario_borrado_durante_la_sesion_pierde_el_acceso(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario())
    auth = ServicioAuth(repo_usuarios)
    auth.iniciar_sesion("u1", CONTRASENA)

    repo_usuarios.eliminar("u1")

    with pytest.raises(ErrorAutenticacion) as exc:
        auth.requiere_sesion()

    assert exc.value.detalles["motivo"] == "usuario_inexistente"
    assert auth.usuario_actual is None


def test_cambio_de_rol_en_disco_se_respeta_de_inmediato(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario(rol=Rol.ENCARGADO))
    auth = ServicioAuth(repo_usuarios)
    auth.iniciar_sesion("u1", CONTRASENA)

    almacenado = repo_usuarios.obtener("u1")
    repo_usuarios.guardar(
        Usuario(
            id=almacenado.id,
            nombre=almacenado.nombre,
            correo=almacenado.correo,
            rol=Rol.SOLICITANTE,
            activo=True,
            hash_contrasena=almacenado.hash_contrasena,
        )
    )

    with pytest.raises(ErrorAutorizacion):
        auth.requiere_rol(Rol.ENCARGADO)
    # `usuario_actual` es solo presentacion: conserva la copia de la sesion.
    assert auth.usuario_actual.rol is Rol.ENCARGADO
    assert auth.requiere_sesion().rol is Rol.SOLICITANTE


# ----------------------------------------------------------------------- Logs


def test_login_exitoso_queda_registrado(repo_usuarios, log_pruebas) -> None:
    logger, ruta = log_pruebas
    repo_usuarios.guardar(_usuario(rol=Rol.ENCARGADO))
    auth = ServicioAuth(repo_usuarios, logger=logger)

    auth.iniciar_sesion("u1", CONTRASENA)

    evento = _eventos(ruta)[-1]
    assert evento["accion"] == "login"
    assert evento["resultado"] == "ok"
    assert evento["usuario"] == "u1"
    assert evento["contexto"]["rol"] == Rol.ENCARGADO.value


def test_intento_fallido_queda_registrado_con_el_identificador(
    repo_usuarios, log_pruebas
) -> None:
    logger, ruta = log_pruebas
    auth = ServicioAuth(repo_usuarios, logger=logger)

    with pytest.raises(ErrorAutenticacion):
        auth.iniciar_sesion("intruso", CONTRASENA)

    evento = _eventos(ruta)[-1]
    assert evento["accion"] == "login"
    assert evento["resultado"] == "error"
    assert evento["usuario"] == "intruso"
    assert evento["contexto"]["motivo"] == "credenciales_invalidas"


def test_la_contrasena_nunca_llega_al_log(repo_usuarios, log_pruebas) -> None:
    """RN-18 y RNF-04: ni en el intento correcto ni en el fallido."""
    logger, ruta = log_pruebas
    repo_usuarios.guardar(_usuario())
    auth = ServicioAuth(repo_usuarios, logger=logger)

    auth.iniciar_sesion("u1", CONTRASENA)
    auth.cerrar_sesion()
    with pytest.raises(ErrorAutenticacion):
        auth.iniciar_sesion("u1", "otra-clave-secreta")

    contenido = ruta.read_text(encoding="utf-8")
    assert CONTRASENA not in contenido
    assert "otra-clave-secreta" not in contenido
    assert repo_usuarios.obtener("u1").hash_contrasena not in contenido


def test_el_correo_no_llega_al_log_cuando_el_usuario_existe(
    repo_usuarios, log_pruebas
) -> None:
    """Mitigacion de privacidad: si se resuelve el usuario, se registra su id."""
    logger, ruta = log_pruebas
    correo = "ana.perez@universidad.cl"
    repo_usuarios.guardar(_usuario(correo=correo))
    auth = ServicioAuth(repo_usuarios, logger=logger)

    auth.iniciar_sesion(correo, CONTRASENA)
    auth.cerrar_sesion()
    with pytest.raises(ErrorAutenticacion):
        auth.iniciar_sesion(correo, "equivocada")

    contenido = ruta.read_text(encoding="utf-8")
    assert correo not in contenido
    assert "u1" in contenido


def test_logout_y_denegacion_quedan_registrados(repo_usuarios, log_pruebas) -> None:
    logger, ruta = log_pruebas
    repo_usuarios.guardar(_usuario(rol=Rol.SOLICITANTE))
    auth = ServicioAuth(repo_usuarios, logger=logger)
    auth.iniciar_sesion("u1", CONTRASENA)

    with pytest.raises(ErrorAutorizacion):
        auth.requiere_rol(Rol.ENCARGADO)
    auth.cerrar_sesion()

    acciones = [(e["accion"], e["resultado"]) for e in _eventos(ruta)]
    assert ("autorizacion", "error") in acciones
    assert ("logout", "ok") in acciones


def test_autorizacion_exitosa_no_genera_evento(repo_usuarios, log_pruebas) -> None:
    logger, ruta = log_pruebas
    repo_usuarios.guardar(_usuario(rol=Rol.ENCARGADO))
    auth = ServicioAuth(repo_usuarios, logger=logger)
    auth.iniciar_sesion("u1", CONTRASENA)

    antes = len(_eventos(ruta))
    auth.requiere_rol(Rol.ENCARGADO)

    assert len(_eventos(ruta)) == antes
