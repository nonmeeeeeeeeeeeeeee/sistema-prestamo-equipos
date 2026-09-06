"""Pruebas de unidad del repositorio JSON generico (issue #6).

No usan identificadores CP-XX a proposito: esos slots son la evidencia de
aceptacion trazable a RF/RN de los issues #16-#19. Estas pruebas cubren un
componente interno que ningun requerimiento nombra.

Cada prueba corresponde a una linea del Definition of Done del issue, mas las
trampas de portabilidad entre Windows (desarrollo) y Linux (CI).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from prestamos.errores import (
    ErrorPersistencia,
    ErrorValidacion,
    RecursoNoEncontrado,
)
from prestamos.modelos import (
    Equipo,
    EstadoEquipo,
    EstadoPrestamo,
    Prestamo,
    Rol,
    Usuario,
)
from prestamos.repositorios.json_repo import (
    DIRECTORIO_DATOS_DEFAULT,
    RepositorioJson,
    directorio_datos,
)


# ------------------------------------------------------------------ Fixtures


def _usuario(id_usuario: str = "u1", nombre: str = "Isaías Carte") -> Usuario:
    return Usuario(
        id=id_usuario,
        nombre=nombre,
        correo=f"{id_usuario}@ejemplo.cl",
        rol=Rol.SOLICITANTE,
        activo=True,
        hash_contrasena="pbkdf2$1$sal$digest",
    )


def _equipo(codigo: str = "EQ-01") -> Equipo:
    return Equipo(
        codigo=codigo,
        nombre="Osciloscopio",
        tipo="instrumento",
        descripcion="Osciloscopio de 100 MHz",
        estado=EstadoEquipo.DISPONIBLE,
    )


def _prestamo(id_prestamo: str = "p1") -> Prestamo:
    return Prestamo(
        id=id_prestamo,
        id_solicitante="u1",
        equipos=("EQ-01", "EQ-02"),
        motivo="Laboratorio de electronica",
        estado=EstadoPrestamo.SOLICITADA,
        fecha_solicitud=date(2026, 9, 1),
        fecha_inicio=date(2026, 9, 10),
        fecha_termino=date(2026, 9, 15),
    )


@pytest.fixture
def repo_usuarios(tmp_path: Path) -> RepositorioJson[Usuario]:
    """Ruta de datos configurable: la prueba pasa su propio tmp_path."""
    return RepositorioJson(tmp_path / "usuarios.json", Usuario, "id")


# ------------------------------------------------------------- Configuracion


def test_directorio_datos_usa_default_sin_variable(monkeypatch) -> None:
    monkeypatch.delenv("PRESTAMOS_DATOS_DIR", raising=False)
    assert directorio_datos() == DIRECTORIO_DATOS_DEFAULT


def test_directorio_datos_respeta_variable_de_entorno(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PRESTAMOS_DATOS_DIR", str(tmp_path))
    assert directorio_datos() == tmp_path


# ------------------------------------------------------------------- Listar


def test_listar_archivo_inexistente_devuelve_vacio(repo_usuarios) -> None:
    """Primer arranque sin init-demo: coleccion vacia, no error."""
    assert repo_usuarios.listar() == []


def test_listar_no_crea_el_archivo(repo_usuarios) -> None:
    """Leer no debe tener efectos de escritura."""
    repo_usuarios.listar()
    assert not repo_usuarios.ruta.exists()


# ------------------------------------------------------- Round-trip completo


def test_guardar_crea_directorio_y_archivo(tmp_path: Path) -> None:
    ruta = tmp_path / "sub" / "directorio" / "usuarios.json"
    repo: RepositorioJson[Usuario] = RepositorioJson(ruta, Usuario, "id")

    repo.guardar(_usuario())

    assert ruta.exists()


def test_round_trip_usuario(repo_usuarios) -> None:
    usuario = _usuario()
    repo_usuarios.guardar(usuario)
    assert repo_usuarios.obtener("u1") == usuario


def test_round_trip_equipo_usa_codigo_como_id(tmp_path: Path) -> None:
    """El campo identificador es configurable: Equipo se indexa por codigo."""
    repo: RepositorioJson[Equipo] = RepositorioJson(
        tmp_path / "equipos.json", Equipo, "codigo"
    )
    equipo = _equipo()

    repo.guardar(equipo)

    assert repo.obtener("EQ-01") == equipo


def test_round_trip_prestamo_conserva_fechas_enums_y_tupla(tmp_path: Path) -> None:
    """El tipo mas complejo: fechas ISO, enum y tupla de equipos."""
    repo: RepositorioJson[Prestamo] = RepositorioJson(
        tmp_path / "solicitudes.json", Prestamo, "id"
    )
    prestamo = _prestamo()

    repo.guardar(prestamo)
    recuperado = repo.obtener("p1")

    assert recuperado == prestamo
    assert recuperado.fecha_inicio == date(2026, 9, 10)
    assert recuperado.estado is EstadoPrestamo.SOLICITADA
    assert recuperado.equipos == ("EQ-01", "EQ-02")


def test_guardar_devuelve_la_entidad(repo_usuarios) -> None:
    usuario = _usuario()
    assert repo_usuarios.guardar(usuario) is usuario


# ------------------------------------------------------------------ Guardar


def test_guardar_agrega_al_final_preservando_orden(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario("u1"))
    repo_usuarios.guardar(_usuario("u2"))
    repo_usuarios.guardar(_usuario("u3"))

    assert [u.id for u in repo_usuarios.listar()] == ["u1", "u2", "u3"]


def test_guardar_id_existente_reemplaza_en_su_posicion(repo_usuarios) -> None:
    """Upsert: no duplica y no manda el registro modificado al final."""
    repo_usuarios.guardar(_usuario("u1"))
    repo_usuarios.guardar(_usuario("u2", nombre="Nombre original"))
    repo_usuarios.guardar(_usuario("u3"))

    repo_usuarios.guardar(_usuario("u2", nombre="Nombre corregido"))

    usuarios = repo_usuarios.listar()
    assert [u.id for u in usuarios] == ["u1", "u2", "u3"]
    assert usuarios[1].nombre == "Nombre corregido"


# ------------------------------------------------- Buscar / obtener / eliminar


def test_buscar_inexistente_devuelve_none(repo_usuarios) -> None:
    """Version no excepcional, para los chequeos de existencia de #10."""
    repo_usuarios.guardar(_usuario("u1"))
    assert repo_usuarios.buscar("u404") is None


def test_obtener_inexistente_levanta_recurso_no_encontrado(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario("u1"))

    with pytest.raises(RecursoNoEncontrado) as exc_info:
        repo_usuarios.obtener("u404")

    assert exc_info.value.detalles["id"] == "u404"


def test_eliminar_quita_solo_ese_registro(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario("u1"))
    repo_usuarios.guardar(_usuario("u2"))

    repo_usuarios.eliminar("u1")

    assert [u.id for u in repo_usuarios.listar()] == ["u2"]


def test_eliminar_inexistente_levanta_recurso_no_encontrado(repo_usuarios) -> None:
    """Borrar algo que no esta es un error del llamador, no un no-op."""
    repo_usuarios.guardar(_usuario("u1"))

    with pytest.raises(RecursoNoEncontrado):
        repo_usuarios.eliminar("u404")

    assert len(repo_usuarios.listar()) == 1


# ----------------------------------------------------- Integridad del archivo


def test_json_malformado_levanta_error_de_dominio(repo_usuarios) -> None:
    """DoD: un JSON invalido no puede llegar al usuario como traceback."""
    repo_usuarios.ruta.write_text('[{"id": "u1",', encoding="utf-8")

    with pytest.raises(ErrorPersistencia) as exc_info:
        repo_usuarios.listar()

    assert exc_info.value.codigo == "ERROR_PERSISTENCIA"


def test_error_de_persistencia_no_filtra_el_contenido_del_archivo(
    repo_usuarios,
) -> None:
    """RN-18: `para_log()` viaja a logs y a Sentry; el hash no puede ir ahi."""
    repo_usuarios.ruta.write_text(
        '[{"hash_contrasena": "pbkdf2$secreto"', encoding="utf-8"
    )

    with pytest.raises(ErrorPersistencia) as exc_info:
        repo_usuarios.listar()

    volcado = json.dumps(exc_info.value.para_log(), ensure_ascii=False)
    assert "secreto" not in volcado


def test_raiz_que_no_es_lista_levanta_error_de_persistencia(repo_usuarios) -> None:
    repo_usuarios.ruta.write_text('{"u1": {"id": "u1"}}', encoding="utf-8")

    with pytest.raises(ErrorPersistencia) as exc_info:
        repo_usuarios.listar()

    assert exc_info.value.detalles["tipo_encontrado"] == "dict"


def test_registro_invalido_para_el_modelo_levanta_error_de_validacion(
    repo_usuarios,
) -> None:
    """JSON valido pero rol inexistente: el error del modelo se propaga tal cual."""
    registro = _usuario().a_dict() | {"rol": "ADMIN"}
    repo_usuarios.ruta.write_text(json.dumps([registro]), encoding="utf-8")

    with pytest.raises(ErrorValidacion) as exc_info:
        repo_usuarios.listar()

    assert exc_info.value.regla == "RN-01"


# ------------------------------------------------------- Escritura atomica


def test_no_deja_archivos_temporales(repo_usuarios) -> None:
    repo_usuarios.guardar(_usuario("u1"))
    repo_usuarios.guardar(_usuario("u2"))
    repo_usuarios.eliminar("u1")

    restantes = list(repo_usuarios.ruta.parent.iterdir())
    assert restantes == [repo_usuarios.ruta]


def test_archivo_no_contiene_crlf(repo_usuarios) -> None:
    """Windows no debe reescribir entero un JSON versionado por los saltos."""
    repo_usuarios.guardar(_usuario("u1"))

    assert b"\r\n" not in repo_usuarios.ruta.read_bytes()


def test_archivo_es_legible_con_tildes(repo_usuarios) -> None:
    """ensure_ascii=False: los datos demo versionados deben poder revisarse."""
    repo_usuarios.guardar(_usuario("u1", nombre="Isaías Carte"))

    assert "Isaías" in repo_usuarios.ruta.read_text(encoding="utf-8")


def test_guardar_sobre_archivo_existente_lo_reemplaza(repo_usuarios) -> None:
    """En Windows `os.rename` fallaria aqui; `os.replace` no."""
    repo_usuarios.guardar(_usuario("u1"))
    repo_usuarios.guardar(_usuario("u2"))

    assert len(repo_usuarios.listar()) == 2
