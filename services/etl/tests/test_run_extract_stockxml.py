"""
Tests de las guardas de rango de run_extract_stockxml.sh (Issue #119).

ConsStockXml devuelve siempre la foto de HOY sin importar el rango pedido.
Pedir una ventana de mas de un dia significa escribir el mismo contenido
bajo fechas distintas -- pisando stock_diario real que si habia cargado
ConsStockVenta (que si respeta fechas). Estos tests verifican que el script
ahora rechaza esas ventanas en vez de ejecutarlas en silencio, y que un
FORCE_START sin FORCE_END falla claro en vez de defaultear a HOY.

No llegan a la extraccion real: los casos "debe abortar" cortan en la
guarda, antes de cualquier curl/DB. Los casos "debe seguir" usan un WS_URL
que falla rapido (puerto cerrado en localhost) -- alcanza con confirmar que
el script paso la guarda e intento la ventana, no que la extraccion en si
funcione (eso ya lo cubre el resto del script, sin tests, fuera de alcance
de este issue).
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "run_extract_stockxml.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash no disponible")

REQUIRED_ENV = {
    "WS_URL": "http://127.0.0.1:1",  # puerto cerrado -- curl falla rapido (connection refused)
    "MYSQL_HOST": "fake-host",
    "MYSQL_DB": "fake-db",
    "MYSQL_USER": "fake-user",
    "MYSQL_PASSWORD": "fake-pass",
    "CERT_PATH": "/dev/null",
    "CACERT_PATH": "/dev/null",
    "CERT_PASSWORD": "x",
}


def _correr(**extra_env):
    env = {**os.environ, **REQUIRED_ENV}
    # Limpio: ninguna variable de rango hereda del entorno del test runner.
    for var in ("FORCE_START", "FORCE_END", "CHUNK_START", "CHUNK_END"):
        env.pop(var, None)
    env.update(extra_env)
    return subprocess.run(
        [BASH, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=15,
    )


def test_force_start_sin_force_end_falla_claro():
    proc = _correr(FORCE_START="01/08/2026")

    assert proc.returncode == 2
    assert "rango incompleto" in proc.stderr.lower()


def test_default_sin_force_start_aborta_por_ventana_multidia():
    """
    Issue #119: antes esto corria una ventana de 7 dias en silencio. Ahora
    la guarda de "mas de un dia" la agarra -- ConsStockXml no soporta rango
    historico, este default nunca fue seguro para invocacion manual.
    """
    proc = _correr()

    assert proc.returncode == 3
    assert "foto de hoy" in proc.stderr.lower()


def test_force_start_y_end_multidia_explicito_aborta():
    proc = _correr(FORCE_START="01/08/2026", FORCE_END="03/08/2026")

    assert proc.returncode == 3
    assert "foto de hoy" in proc.stderr.lower()


def test_chunk_externo_multidia_aborta():
    """Modo 1 (CHUNK_START/CHUNK_END externos) tiene la misma guarda."""
    proc = _correr(CHUNK_START="01/08/2026", CHUNK_END="02/08/2026")

    assert proc.returncode == 3
    assert "foto de hoy" in proc.stderr.lower()


def test_force_start_igual_a_force_end_un_solo_dia_sigue_de_largo():
    proc = _correr(FORCE_START="01/08/2026", FORCE_END="01/08/2026")

    assert "Stock window:" in proc.stdout, "un solo dia forzado no debe abortar en la guarda"


def test_chunk_externo_un_solo_dia_sigue_de_largo():
    proc = _correr(CHUNK_START="01/08/2026", CHUNK_END="01/08/2026")

    assert "Stock window (externo):" in proc.stdout


def test_chunk_externo_dos_fechas_invalidas_no_bypasea_la_guarda():
    """
    Issue #119 (code-review post-implement): to_iso() de una fecha invalida
    imprime "" -- dos fechas invalidas DISTINTAS resolvian a la misma cadena
    vacia, y assert_ventana_no_peligrosa("", "") las veia "iguales" y dejaba
    pasar la ventana en vez de abortar. Confirmado que ocurria antes del fix.
    """
    proc = _correr(CHUNK_START="no-es-una-fecha", CHUNK_END="tampoco-esta")

    assert proc.returncode == 2
    assert "inválidas" in proc.stderr.lower() or "invalidas" in proc.stderr.lower()
    assert "Stock window" not in proc.stdout
