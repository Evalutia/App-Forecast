"""
Tests de run_backfill_comparacion.sh (Issue #186).

No corre el backfill real ni toca MySQL/WS -- reemplaza run_backfill_ventas.sh
por un stub que vuelca las variables de entorno recibidas a un archivo, y
verifica que el wrapper exporta exactamente lo que #186 pide: las tablas de
comparacion (nunca las de produccion), el subtipo aislado para
jobs_historial, y get_grupos.py en vez de get_grupos_backfill.py (para
incluir el grupo 201, ver el comentario de cabecera del propio script).
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REAL_SCRIPT = Path(__file__).resolve().parent.parent / "run_backfill_comparacion.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash no disponible")


@pytest.fixture
def script_dir(tmp_path):
    dest = tmp_path / "run_backfill_comparacion.sh"
    shutil.copy(REAL_SCRIPT, dest)
    dest.chmod(0o755)

    marker = tmp_path / "env_recibido.txt"
    # Stub de run_backfill_ventas.sh -- mismo nombre, mismo directorio (asi
    # lo encuentra el `exec "${SELF_DIR}/run_backfill_ventas.sh"` real), pero
    # solo vuelca las variables que #186 necesita ver propagadas.
    stub = dest.parent / "run_backfill_ventas.sh"
    stub.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        {{
          echo "TABLA_VENTAS_STAGE=${{TABLA_VENTAS_STAGE:-}}"
          echo "TABLA_VENTAS=${{TABLA_VENTAS:-}}"
          echo "TABLA_STOCK_DIARIO=${{TABLA_STOCK_DIARIO:-}}"
          echo "BACKFILL_SUBTIPO=${{BACKFILL_SUBTIPO:-}}"
          echo "GRUPOS_SCRIPT=${{GRUPOS_SCRIPT:-}}"
        }} > "{marker}"
        """), encoding="utf-8")
    stub.chmod(0o755)

    return {"script": dest, "marker": marker}


def _correr(script_dir):
    return subprocess.run(
        [BASH, str(script_dir["script"])],
        env=os.environ.copy(), capture_output=True, text=True, timeout=15,
    )


def _leer_env(marker: Path) -> dict:
    out = {}
    for line in marker.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def test_exporta_las_tablas_de_comparacion_no_las_de_produccion(script_dir):
    proc = _correr(script_dir)
    assert proc.returncode == 0, proc.stderr

    env = _leer_env(script_dir["marker"])
    assert env["TABLA_VENTAS_STAGE"] == "ventas_historicas_stage_comparacion"
    assert env["TABLA_VENTAS"] == "ventas_historicas_comparacion"
    assert env["TABLA_STOCK_DIARIO"] == "stock_diario_comparacion"
    # Ninguna apunta al nombre de produccion (sin sufijo _comparacion).
    for k in ("TABLA_VENTAS_STAGE", "TABLA_VENTAS", "TABLA_STOCK_DIARIO"):
        assert env[k].endswith("_comparacion")


def test_subtipo_aislado_del_backfill_real(script_dir):
    proc = _correr(script_dir)
    assert proc.returncode == 0, proc.stderr

    env = _leer_env(script_dir["marker"])
    assert env["BACKFILL_SUBTIPO"] == "backfill_comparacion"
    assert env["BACKFILL_SUBTIPO"] != "backfill_ventas"


def test_usa_get_grupos_completo_no_el_que_excluye_201(script_dir):
    """get_grupos_backfill.py excluye el grupo 201 a proposito (#44, ya
    tiene 10 anios cargados aparte) -- la comparacion contra produccion lo
    quiere incluido, asi que el wrapper tiene que apuntar a get_grupos.py."""
    proc = _correr(script_dir)
    assert proc.returncode == 0, proc.stderr

    env = _leer_env(script_dir["marker"])
    assert env["GRUPOS_SCRIPT"] == "get_grupos.py"
