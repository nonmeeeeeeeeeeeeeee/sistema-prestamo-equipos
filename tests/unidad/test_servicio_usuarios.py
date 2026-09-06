"""Pruebas de `prestamos.servicios.usuarios`: alta, edicion, baja y unicidad.

Nombres descriptivos y sin etiqueta CP-XX, igual que `test_auth.py` y
`test_json_repo.py`. El catalogo (`docs/casos-de-prueba.md`) define CP-01..CP-15
y lo asignan los issues #16-#19; ver el defecto DEF-01 (issue #43).

Todos los servicios se construyen con `iteraciones_hash=1`: aqui interesa el
contrato del servicio, no el costo de la KDF, que con el valor de produccion
anadiria ~100 ms por cada alta.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from prestamos.auth import ServicioAuth, verificar_contrasena
from prestamos.errores import (
    ErrorAutenticacion,
    ErrorAutorizacion,
    ErrorValidacion,
    RecursoNoEncontrado,
)
from prestamos.logging_conf import LOGGER_NAME, configurar_logging
from prestamos.modelos import Rol, Usuario
from prestamos.repositorios.json_repo import RepositorioJson
from prestamos.servicios.usuarios import ServicioUsuarios, crear_encargado_inicial

CONTRASENA = "clave-de-demostracion"
CORREO_ENCARGADO = "encargada@universidad.cl"


# ---------------------------------------------------------------- Fixtures


@pytest.fixture
def repo_usuarios(tmp_path: Path) -> RepositorioJson[Usuario]:
    return RepositorioJson(tmp_path / "usuarios.json", Usuario, "id")


@pytest.fixture
def log_pruebas(tmp_path: Path):
    """Logger de archivo aislado por prueba.

    Mismo patron que `test_auth.py`: `configurar_logging` acumula handlers sobre
    el logger singleton "prestamos", asi que hay que quitarlo al terminar o los
    eventos de una prueba terminan en los archivos de las siguientes.
    """
    ruta = tmp_path / "eventos.log"
    logger = configurar_logging(ruta)
    yield logger, ruta
    for handler in list(logging.getLogger(LOGGER_NAME).handlers):
        if getattr(handler, "_prestamos_log_path", None) == ruta.resolve():
            logger.removeHandler(handler)
            handler.close()


@pytest.fixture
def auth(repo_usuarios, log_pruebas) -> ServicioAuth:
    logger, _ = log_pruebas
    return ServicioAuth(repo_usuarios, logger=logger)


@pytest.fixture
def servicio(auth, repo_usuarios, log_pruebas) -> ServicioUsuarios:
    logger, _ = log_pruebas
    return ServicioUsuarios(
        auth, repo_usuarios, logger=logger, iteraciones_hash=1
    )


@pytest.fixture
def sesion_encargado(auth, repo_usuarios) -> Usuario:
    """Padron con un Encargado inicial y su sesion ya abierta."""
    encargado = crear_encargado_inicial(
        "enc",
        "Encargada Principal",
        CORREO_ENCARGADO,
        CONTRASENA,
        repositorio=repo_usuarios,
        iteraciones_hash=1,
    )
    auth.iniciar_sesion("enc", CONTRASENA)
    return encargado


def _eventos(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    return [
        json.loads(linea)
        for linea in ruta.read_text(encoding="utf-8").splitlines()
        if linea.strip()
    ]


def _alta_solicitante(servicio: ServicioUsuarios, **cambios) -> Usuario:
    datos = {
        "id_usuario": "u1",
        "nombre": "Ana Perez",
        "correo": "ana.perez@universidad.cl",
        "rol": Rol.SOLICITANTE,
        "contrasena": CONTRASENA,
    }
    datos.update(cambios)
    return servicio.registrar_usuario(**datos)


# ------------------------------------------------------------------- Alta


def test_alta_crea_usuario_activo_con_credencial_verificable(
    servicio, sesion_encargado, repo_usuarios
) -> None:
    usuario = _alta_solicitante(servicio)

    assert usuario.activo is True
    assert usuario.rol is Rol.SOLICITANTE
    assert verificar_contrasena(CONTRASENA, usuario.hash_contrasena)
    assert repo_usuarios.obtener("u1").correo == "ana.perez@universidad.cl"


def test_alta_sin_sesion_es_rechazada(servicio) -> None:
    with pytest.raises(ErrorAutenticacion):
        _alta_solicitante(servicio)


def test_alta_por_solicitante_es_rechazada(
    servicio, auth, sesion_encargado
) -> None:
    _alta_solicitante(servicio)
    auth.cerrar_sesion()
    auth.iniciar_sesion("u1", CONTRASENA)

    with pytest.raises(ErrorAutorizacion):
        _alta_solicitante(servicio, id_usuario="u2", correo="otro@universidad.cl")


def test_alta_rechaza_id_repetido(servicio, sesion_encargado) -> None:
    _alta_solicitante(servicio)

    with pytest.raises(ErrorValidacion) as exc:
        _alta_solicitante(servicio, correo="distinto@universidad.cl")
    assert exc.value.detalles["motivo"] == "id_duplicado"


def test_alta_rechaza_id_que_solo_difiere_en_mayusculas(
    servicio, sesion_encargado
) -> None:
    """Sin esto `auth._resolver` encontraria dos coincidencias y ninguno de los
    dos usuarios podria iniciar sesion nunca (ver test_auth.py:311)."""
    _alta_solicitante(servicio, id_usuario="u1")

    with pytest.raises(ErrorValidacion) as exc:
        _alta_solicitante(servicio, id_usuario="U1", correo="otra@universidad.cl")
    assert exc.value.detalles["motivo"] == "id_duplicado"


def test_alta_rechaza_correo_repetido_ignorando_mayusculas(
    servicio, sesion_encargado
) -> None:
    _alta_solicitante(servicio, correo="ana.perez@universidad.cl")

    with pytest.raises(ErrorValidacion) as exc:
        _alta_solicitante(
            servicio, id_usuario="u2", correo="ANA.PEREZ@UNIVERSIDAD.CL"
        )
    assert exc.value.detalles["motivo"] == "correo_duplicado"


def test_alta_rechaza_el_correo_del_encargado_inicial(
    servicio, sesion_encargado
) -> None:
    with pytest.raises(ErrorValidacion) as exc:
        _alta_solicitante(servicio, correo=CORREO_ENCARGADO)
    assert exc.value.detalles["motivo"] == "correo_duplicado"


@pytest.mark.parametrize(
    "correo",
    ["sin-arroba", "dos@@arrobas", "con espacio@universidad.cl", "@universidad.cl", "ana@"],
)
def test_alta_rechaza_correos_mal_formados(
    servicio, sesion_encargado, correo
) -> None:
    with pytest.raises(ErrorValidacion) as exc:
        _alta_solicitante(servicio, correo=correo)
    assert exc.value.detalles["motivo"] == "correo_invalido"


def test_alta_rechaza_campos_obligatorios_vacios(servicio, sesion_encargado) -> None:
    """La obligatoriedad la impone `modelos.Usuario`, no el servicio (RN-03)."""
    with pytest.raises(ErrorValidacion):
        _alta_solicitante(servicio, nombre="   ")


def test_alta_recorta_los_espacios_del_id_y_del_correo(
    servicio, sesion_encargado, repo_usuarios
) -> None:
    """Los campos de identidad se guardan recortados.

    `modelos.Usuario` usa `strip()` solo para comprobar que el campo no este
    vacio, pero guarda el texto crudo; sin recortar al escribir, el correo
    almacenado no vuelve a coincidir con lo que su duena teclea.
    """
    usuario = _alta_solicitante(
        servicio, id_usuario="  u1  ", correo="  ana.perez@universidad.cl  "
    )

    assert usuario.id == "u1"
    assert usuario.correo == "ana.perez@universidad.cl"
    assert repo_usuarios.obtener("u1").id == "u1"


def test_un_correo_con_espacios_no_deja_al_usuario_fuera(
    servicio, auth, sesion_encargado
) -> None:
    _alta_solicitante(servicio, correo=" ana.perez@universidad.cl ")
    auth.cerrar_sesion()

    assert auth.iniciar_sesion("ana.perez@universidad.cl", CONTRASENA).usuario.id == "u1"


def test_alta_rechaza_un_id_que_solo_difiere_en_espacios(
    servicio, sesion_encargado
) -> None:
    _alta_solicitante(servicio, id_usuario="u1")

    with pytest.raises(ErrorValidacion) as exc:
        _alta_solicitante(servicio, id_usuario=" u1 ", correo="otra@universidad.cl")
    assert exc.value.detalles["motivo"] == "id_duplicado"


def test_alta_rechaza_un_correo_que_solo_difiere_en_espacios(
    servicio, sesion_encargado
) -> None:
    _alta_solicitante(servicio, correo="ana.perez@universidad.cl")

    with pytest.raises(ErrorValidacion) as exc:
        _alta_solicitante(
            servicio, id_usuario="u2", correo=" ana.perez@universidad.cl "
        )
    assert exc.value.detalles["motivo"] == "correo_duplicado"


def test_el_encargado_inicial_tambien_recorta_espacios(repo_usuarios) -> None:
    encargado = crear_encargado_inicial(
        "  enc  ", "Encargada", "  " + CORREO_ENCARGADO + "  ", CONTRASENA,
        repositorio=repo_usuarios, iteraciones_hash=1,
    )

    assert encargado.id == "enc"
    assert encargado.correo == CORREO_ENCARGADO


# ---------------------------------------------------------------- Edicion


def test_edicion_actualiza_nombre_y_correo(servicio, sesion_encargado) -> None:
    _alta_solicitante(servicio)

    editado = servicio.editar_usuario(
        "u1", nombre="Ana Maria Perez", correo="ana.m.perez@universidad.cl"
    )

    assert editado.nombre == "Ana Maria Perez"
    assert editado.correo == "ana.m.perez@universidad.cl"


def test_edicion_de_solo_el_nombre_no_choca_con_el_propio_correo(
    servicio, sesion_encargado
) -> None:
    """La unicidad debe excluir el registro editado, o editar el nombre fallaria
    contra el correo que ese mismo usuario ya tiene."""
    _alta_solicitante(servicio)

    editado = servicio.editar_usuario("u1", nombre="Ana M. Perez")

    assert editado.correo == "ana.perez@universidad.cl"


def test_edicion_acepta_reenviar_el_mismo_correo(servicio, sesion_encargado) -> None:
    _alta_solicitante(servicio)

    editado = servicio.editar_usuario("u1", correo="ana.perez@universidad.cl")

    assert editado.correo == "ana.perez@universidad.cl"


def test_edicion_rechaza_el_correo_de_otro_usuario(servicio, sesion_encargado) -> None:
    _alta_solicitante(servicio)
    _alta_solicitante(servicio, id_usuario="u2", correo="beto@universidad.cl")

    with pytest.raises(ErrorValidacion) as exc:
        servicio.editar_usuario("u2", correo="ana.perez@universidad.cl")
    assert exc.value.detalles["motivo"] == "correo_duplicado"


def test_tras_editar_el_correo_se_inicia_sesion_con_el_nuevo(
    servicio, auth, sesion_encargado
) -> None:
    """Requisito explicito: cambiar el correo no debe dejar al usuario fuera.

    `auth._resolver` relee `usuarios.json` en cada login, asi que el correo nuevo
    sirve de inmediato y el viejo deja de servir.
    """
    _alta_solicitante(servicio)
    servicio.editar_usuario("u1", correo="ana.nueva@universidad.cl")
    auth.cerrar_sesion()

    sesion = auth.iniciar_sesion("ana.nueva@universidad.cl", CONTRASENA)

    assert sesion.usuario.id == "u1"


def test_tras_editar_el_correo_el_anterior_deja_de_servir(
    servicio, auth, sesion_encargado
) -> None:
    _alta_solicitante(servicio)
    servicio.editar_usuario("u1", correo="ana.nueva@universidad.cl")
    auth.cerrar_sesion()

    with pytest.raises(ErrorAutenticacion):
        auth.iniciar_sesion("ana.perez@universidad.cl", CONTRASENA)


def test_edicion_de_usuario_inexistente_levanta_no_encontrado(
    servicio, sesion_encargado
) -> None:
    with pytest.raises(RecursoNoEncontrado):
        servicio.editar_usuario("fantasma", nombre="Nadie")


# ------------------------------------------------------------ Baja logica


def test_desactivar_impide_iniciar_sesion(servicio, auth, sesion_encargado) -> None:
    _alta_solicitante(servicio)
    servicio.desactivar("u1")
    auth.cerrar_sesion()

    with pytest.raises(ErrorAutenticacion):
        auth.iniciar_sesion("u1", CONTRASENA)


def test_desactivar_conserva_el_registro(servicio, sesion_encargado, repo_usuarios) -> None:
    """Baja logica, no borrado: `Prestamo.id_solicitante` sigue apuntando aqui."""
    _alta_solicitante(servicio)
    servicio.desactivar("u1")

    assert repo_usuarios.obtener("u1").activo is False


def test_reactivar_devuelve_el_acceso(servicio, auth, sesion_encargado) -> None:
    _alta_solicitante(servicio)
    servicio.desactivar("u1")
    servicio.reactivar("u1")
    auth.cerrar_sesion()

    assert auth.iniciar_sesion("u1", CONTRASENA).usuario.id == "u1"


def test_desactivar_es_idempotente(servicio, sesion_encargado) -> None:
    _alta_solicitante(servicio)
    servicio.desactivar("u1")

    assert servicio.desactivar("u1").activo is False


def test_una_baja_repetida_deja_evidencia_en_el_log(
    servicio, sesion_encargado, log_pruebas
) -> None:
    """Idempotente en el estado, no en la auditoria: el DoD de #10 pide que
    toda operacion escriba en el log, tambien la que no cambia nada."""
    _, ruta = log_pruebas
    _alta_solicitante(servicio)
    servicio.desactivar("u1")
    servicio.desactivar("u1")

    bajas = [e for e in _eventos(ruta) if e["accion"] == "usuario_desactivado"]
    assert [e["resultado"] for e in bajas] == ["ok", "sin_cambio"]
    assert bajas[-1]["contexto"]["objetivo"] == "u1"


def test_una_reactivacion_redundante_deja_evidencia_en_el_log(
    servicio, sesion_encargado, log_pruebas
) -> None:
    _, ruta = log_pruebas
    _alta_solicitante(servicio)
    servicio.reactivar("u1")

    eventos = [e for e in _eventos(ruta) if e["accion"] == "usuario_reactivado"]
    assert [e["resultado"] for e in eventos] == ["sin_cambio"]


# ------------------------------------------- Proteccion del ultimo Encargado


def test_no_se_puede_desactivar_al_unico_encargado(servicio, sesion_encargado) -> None:
    """Sin esta guarda el sistema queda inutilizable de forma permanente."""
    with pytest.raises(ErrorValidacion) as exc:
        servicio.desactivar("enc")
    assert exc.value.detalles["motivo"] == "ultimo_encargado"
    # La regla queda trazada como RN-20, no como el RN-03 por defecto del servicio.
    assert exc.value.regla == "RN-20"


def test_no_se_puede_degradar_al_unico_encargado(servicio, sesion_encargado) -> None:
    with pytest.raises(ErrorValidacion) as exc:
        servicio.editar_usuario("enc", rol=Rol.SOLICITANTE)
    assert exc.value.detalles["motivo"] == "ultimo_encargado"
    assert exc.value.regla == "RN-20"


def test_se_puede_desactivar_un_encargado_si_queda_otro_activo(
    servicio, sesion_encargado
) -> None:
    _alta_solicitante(
        servicio, id_usuario="enc2", correo="enc2@universidad.cl", rol=Rol.ENCARGADO
    )

    assert servicio.desactivar("enc").activo is False


def test_un_encargado_inactivo_no_cuenta_como_relevo(servicio, sesion_encargado) -> None:
    """El relevo debe estar activo: un Encargado dado de baja no puede operar."""
    _alta_solicitante(
        servicio, id_usuario="enc2", correo="enc2@universidad.cl", rol=Rol.ENCARGADO
    )
    servicio.desactivar("enc2")

    with pytest.raises(ErrorValidacion) as exc:
        servicio.desactivar("enc")
    assert exc.value.detalles["motivo"] == "ultimo_encargado"


# ------------------------------------------------------------ Contrasena


def test_cambiar_contrasena_permite_entrar_con_la_nueva(
    servicio, auth, sesion_encargado
) -> None:
    _alta_solicitante(servicio)
    servicio.cambiar_contrasena("u1", "otra-clave-distinta")
    auth.cerrar_sesion()

    assert auth.iniciar_sesion("u1", "otra-clave-distinta").usuario.id == "u1"


def test_cambiar_contrasena_rechaza_la_vieja(servicio, auth, sesion_encargado) -> None:
    _alta_solicitante(servicio)
    servicio.cambiar_contrasena("u1", "otra-clave-distinta")
    auth.cerrar_sesion()

    with pytest.raises(ErrorAutenticacion):
        auth.iniciar_sesion("u1", CONTRASENA)


# --------------------------------------------------------------- Listado


def test_listado_incluye_inactivos_por_defecto(servicio, sesion_encargado) -> None:
    _alta_solicitante(servicio)
    servicio.desactivar("u1")

    assert {u.id for u in servicio.listar()} == {"enc", "u1"}


def test_listado_puede_omitir_inactivos(servicio, sesion_encargado) -> None:
    _alta_solicitante(servicio)
    servicio.desactivar("u1")

    assert {u.id for u in servicio.listar(incluir_inactivos=False)} == {"enc"}


def test_listado_exige_rol_encargado(servicio, auth, sesion_encargado) -> None:
    """El padron expone correos: RN-18 pide no derramarlos."""
    _alta_solicitante(servicio)
    auth.cerrar_sesion()
    auth.iniciar_sesion("u1", CONTRASENA)

    with pytest.raises(ErrorAutorizacion):
        servicio.listar()


# ------------------------------------------------- Encargado inicial (#15)


def test_encargado_inicial_se_crea_sobre_padron_vacio(repo_usuarios) -> None:
    encargado = crear_encargado_inicial(
        "enc", "Encargada", CORREO_ENCARGADO, CONTRASENA,
        repositorio=repo_usuarios, iteraciones_hash=1,
    )

    assert encargado.rol is Rol.ENCARGADO
    assert encargado.activo is True
    assert verificar_contrasena(CONTRASENA, repo_usuarios.obtener("enc").hash_contrasena)


def test_encargado_inicial_se_niega_si_ya_hay_usuarios(
    servicio, sesion_encargado, repo_usuarios
) -> None:
    """La condicion es "padron vacio", no "sin Encargados activos": eso mantiene
    el seam cerrado para siempre tras el primer uso."""
    with pytest.raises(ErrorValidacion) as exc:
        crear_encargado_inicial(
            "enc2", "Otra", "otra@universidad.cl", CONTRASENA,
            repositorio=repo_usuarios, iteraciones_hash=1,
        )
    assert exc.value.detalles["motivo"] == "padron_no_vacio"


def test_encargado_inicial_valida_el_correo(repo_usuarios) -> None:
    with pytest.raises(ErrorValidacion) as exc:
        crear_encargado_inicial(
            "enc", "Encargada", "sin-arroba", CONTRASENA,
            repositorio=repo_usuarios, iteraciones_hash=1,
        )
    assert exc.value.detalles["motivo"] == "correo_invalido"


# ------------------------------------------------------------------ Logs


def test_el_alta_registra_evento(servicio, sesion_encargado, log_pruebas) -> None:
    _, ruta = log_pruebas
    _alta_solicitante(servicio)

    altas = [e for e in _eventos(ruta) if e["accion"] == "usuario_registrado"]
    assert altas[-1]["resultado"] == "ok"
    assert altas[-1]["usuario"] == "enc"
    assert altas[-1]["contexto"]["objetivo"] == "u1"


def test_el_rechazo_por_duplicado_tambien_registra_evento(
    servicio, sesion_encargado, log_pruebas
) -> None:
    """Los rechazos son lo que necesitan las pruebas negativas (#18)."""
    _, ruta = log_pruebas
    _alta_solicitante(servicio)
    with pytest.raises(ErrorValidacion):
        _alta_solicitante(servicio, correo="distinto@universidad.cl")

    errores = [
        e for e in _eventos(ruta)
        if e["accion"] == "usuario_registrado" and e["resultado"] == "error"
    ]
    assert errores[-1]["contexto"]["motivo"] == "id_duplicado"


def test_los_eventos_nunca_contienen_la_contrasena(
    servicio, sesion_encargado, log_pruebas
) -> None:
    _, ruta = log_pruebas
    _alta_solicitante(servicio)
    servicio.cambiar_contrasena("u1", "otra-clave-distinta")

    crudo = ruta.read_text(encoding="utf-8")
    assert CONTRASENA not in crudo
    assert "otra-clave-distinta" not in crudo
    assert "pbkdf2_sha256" not in crudo
