# Evidencia issue #16 - CP-01 a CP-05 funcionales

Ejecutado por: IsaiasACF  
Fecha: 2026-09-06  
Rama: test/casos-funcionales

## Comando literal solicitado: `pytest tests/funcionales/test_funcionales.py -v`

Resultado en este shell:

```text
/bin/bash: line 1: pytest: command not found
```

El ejecutable `pytest` no estaba en `PATH`, por lo que se ejecutó con el pytest del entorno virtual del proyecto.

## Comando ejecutado: `.venv/bin/pytest tests/funcionales/test_funcionales.py -v`

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0 -- .../.venv/bin/python3
collecting ... collected 5 items

tests/funcionales/test_funcionales.py::test_CP01_RF02_login_valido_abre_sesion_sin_exponer_contrasena PASSED [ 20%]
tests/funcionales/test_funcionales.py::test_CP02_RF09_registrar_entrega_aprobada_persiste_prestamo_y_equipo PASSED [ 40%]
tests/funcionales/test_funcionales.py::test_CP03_RF10_registrar_devolucion_en_plazo_persiste_prestamo_y_equipo PASSED [ 60%]
tests/funcionales/test_funcionales.py::test_CP04_RF11_cancelar_aprobada_antes_de_entrega_persiste_y_libera_equipo PASSED [ 80%]
tests/funcionales/test_funcionales.py::test_CP05_RF12_consultar_prestamos_clasifica_respeta_encargado_y_no_muta PASSED [100%]

============================== 5 passed in 0.49s ===============================
```

## Comando ejecutado: `PATH=.venv/bin:$PATH pytest -m funcional -v`

```text
collecting ... collected 138 items / 133 deselected / 5 selected

tests/funcionales/test_funcionales.py::test_CP01_RF02_login_valido_abre_sesion_sin_exponer_contrasena PASSED [ 20%]
tests/funcionales/test_funcionales.py::test_CP02_RF09_registrar_entrega_aprobada_persiste_prestamo_y_equipo PASSED [ 40%]
tests/funcionales/test_funcionales.py::test_CP03_RF10_registrar_devolucion_en_plazo_persiste_prestamo_y_equipo PASSED [ 60%]
tests/funcionales/test_funcionales.py::test_CP04_RF11_cancelar_aprobada_antes_de_entrega_persiste_y_libera_equipo PASSED [ 80%]
tests/funcionales/test_funcionales.py::test_CP05_RF12_consultar_prestamos_clasifica_respeta_encargado_y_no_muta PASSED [100%]

====================== 5 passed, 133 deselected in 0.90s =======================
```

## Comando ejecutado: `PATH=.venv/bin:$PATH pytest`

```text
collected 138 items

============================= 138 passed in 6.15s ==============================
```
