"""
Tests de la ventana de fechas de run_extract_sales_chunk.sh (Issue #133).

Antes, run_ofelia.sh forzaba FORCE_START=FORCE_END=ayer en TODAS las noches
-- el default natural de este script (7 dias terminando ayer) nunca se
usaba, asi que una noche perdida (cron caido, WS caido) no se reponia sola:
la corrida siguiente solo volvia a pedir el dia de ayer, dejando el hueco
para siempre. SALES_FORCE_START/SALES_FORCE_END son parametros nuevos,
propios de este paso (no compartidos con RUN EXTRACT STOCKXML, que sigue
siendo de un solo dia a proposito -- ConsStockXml no respeta el rango
pedido, ver run_extract_stockxml.sh).

No llegan a la extraccion real: WS_URL apunta a un puerto cerrado
(connection refused rapido), mismo patron que test_run_extract_stockxml.py
-- alcanza con leer la ventana calculada de "[INFO] Sales window: ..." en
stdout antes de que el curl falle.
"""

import datetime as dt
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "run_extract_sales_chunk.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash no disponible")

REQUIRED_ENV = {
    "WS_URL": "http://127.0.0.1:1",  # puerto cerrado -- curl falla rapido
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
    for var in ("FORCE_START", "FORCE_END", "SALES_FORCE_START", "SALES_FORCE_END",
                "CHUNK_START", "CHUNK_END"):
        env.pop(var, None)
    env.update(extra_env)
    return subprocess.run(
        [BASH, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=15,
    )


def _ventana(proc) -> str:
    linea = next(ln for ln in proc.stdout.splitlines() if ln.startswith("[INFO] Sales window:"))
    return linea.split("[INFO] Sales window:")[1].strip()


def test_sales_force_start_end_tiene_prioridad_sobre_force_start_end():
    proc = _correr(
        SALES_FORCE_START="01/08/2026", SALES_FORCE_END="07/08/2026",
        FORCE_START="15/08/2026", FORCE_END="15/08/2026",
    )
    assert _ventana(proc) == "01/08/2026 -> 07/08/2026"


def test_sin_sales_force_cae_a_force_start_end():
    """Fallback para invocaciones manuales que no conocen las variables nuevas."""
    proc = _correr(FORCE_START="15/08/2026", FORCE_END="15/08/2026")
    assert _ventana(proc) == "15/08/2026 -> 15/08/2026"


def test_chunk_start_end_externo_tiene_prioridad_sobre_todo():
    """Regresion: el override externo (ya existente) no debe quedar pisado."""
    proc = _correr(
        CHUNK_START="01/01/2020", CHUNK_END="02/01/2020",
        SALES_FORCE_START="01/08/2026", SALES_FORCE_END="07/08/2026",
    )
    assert _ventana(proc) == "01/01/2020 -> 02/01/2020"


def test_sin_nada_usa_ventana_de_7_dias_default():
    """Sin ninguna variable de rango: el default natural del script (nunca
    activo hasta #133) sigue siendo 7 dias terminando ayer."""
    proc = _correr()

    hoy = dt.date.today()
    ayer = hoy - dt.timedelta(days=1)
    hace_7 = ayer - dt.timedelta(days=6)
    esperado = f"{hace_7:%d/%m/%Y} -> {ayer:%d/%m/%Y}"

    assert _ventana(proc) == esperado
