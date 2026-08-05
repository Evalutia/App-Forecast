"""
Tests de orquestacion de run_ofelia.sh (Issue #111).

No tocan MySQL ni Pentaho: se inyectan stubs por env (CRON_JOBS, KITCHEN) y
se verifica el contrato del wrapper -- que registre inicio/fin, que preserve
el exit code del ETL, y que el bookkeeping nunca voltee la corrida.

Se saltan si no hay bash disponible (el script es bash, no sh).
"""

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "run_ofelia.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash no disponible")


def _escribir(path: Path, contenido: str) -> Path:
    path.write_text(textwrap.dedent(contenido).lstrip(), encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def entorno(tmp_path):
    """
    Stubs de cron_jobs.py y kitchen.sh que registran sus llamadas en un
    archivo, para poder asertar la secuencia sin DB ni Pentaho.
    """
    llamadas = tmp_path / "llamadas.log"

    cron_stub = _escribir(tmp_path / "cron_stub.py", f"""
        import sys
        with open(r"{llamadas}", "a", encoding="utf-8") as fh:
            fh.write("cron:" + " ".join(sys.argv[1:]) + "\\n")
        sub = sys.argv[1]
        if sub == "start":
            print("4242")
        elif sub == "stale":
            print("[CRON][ATRASO] 9 dias")
            sys.exit(1)   # atraso detectado: NO es un fallo del chequeo
        sys.exit(0)
        """)

    kitchen_stub = _escribir(tmp_path / "kitchen_stub.sh", f"""
        #!/usr/bin/env bash
        echo "kitchen" >> "{llamadas}"
        exit ${{FAKE_ETL_RC:-0}}
        """)

    env = {
        **os.environ,
        "CRON_JOBS": str(cron_stub),
        "KITCHEN": str(kitchen_stub),
        "BACKFILL_LOCK_FILE": str(tmp_path / "no-existe.lock"),
    }
    return {"env": env, "llamadas": llamadas, "tmp": tmp_path}


def _correr(entorno, **extra_env):
    proc = subprocess.run(
        [BASH, str(SCRIPT)],
        env={**entorno["env"], **extra_env},
        capture_output=True, text=True,
    )
    registro = (entorno["llamadas"].read_text(encoding="utf-8").splitlines()
                if entorno["llamadas"].exists() else [])
    return proc, registro


def test_corrida_ok_registra_inicio_y_cierre_con_exito(entorno):
    proc, registro = _correr(entorno, FAKE_ETL_RC="0")

    assert proc.returncode == 0
    assert "cron:start" in registro
    assert "kitchen" in registro
    cierre = [ln for ln in registro if ln.startswith("cron:end")]
    assert len(cierre) == 1
    partes = cierre[0].split()
    assert partes[1] == "4242"   # job_id devuelto por start
    assert partes[2] == "0"      # exit code del ETL


def test_fallo_del_etl_queda_registrado_y_preserva_el_exit_code(entorno):
    """El caso de #111: la extraccion muere y hoy no deja rastro."""
    proc, registro = _correr(entorno, FAKE_ETL_RC="9")

    assert proc.returncode == 9, "ofelia debe seguir viendo la corrida como fallida"
    cierre = [ln for ln in registro if ln.startswith("cron:end")]
    assert cierre and cierre[0].split()[2] == "9"


def test_atraso_detectado_no_aborta_la_corrida(entorno):
    """`stale` sale con 1 cuando hay atraso; eso no debe frenar el ETL."""
    proc, registro = _correr(entorno, FAKE_ETL_RC="0")

    assert "cron:stale" in registro
    assert "kitchen" in registro, "el ETL tiene que correr igual"
    assert proc.returncode == 0


def test_lock_de_backfill_saltea_y_deja_registro(entorno):
    lock = entorno["tmp"] / "backfill.lock"
    lock.write_text("1", encoding="utf-8")

    proc, registro = _correr(entorno, BACKFILL_LOCK_FILE=str(lock))

    assert proc.returncode == 0
    assert any(ln.startswith("cron:skip") for ln in registro)
    assert "kitchen" not in registro, "no debe correr el ETL con backfill en curso"


def test_bookkeeping_caido_no_impide_la_corrida(entorno, tmp_path):
    """Si la DB no responde, el ETL tiene que correr igual."""
    roto = _escribir(tmp_path / "roto.py", """
        import sys
        sys.stderr.write("boom: no such table jobs_historial en la linea 77\\n")
        sys.exit(1)
        """)

    proc, registro = _correr(entorno, CRON_JOBS=str(roto), FAKE_ETL_RC="0")

    assert "kitchen" in registro, "el ETL corre aunque el bookkeeping falle"
    assert proc.returncode == 0


def test_coherencia_corre_despues_de_end_con_el_job_id(entorno):
    """
    Issue #115: el chequeo de coherencia venta-vs-stock corre despues de
    `end` (para no perder su escritura al JSON_SET) y con el mismo job_id
    que devolvio `start`.
    """
    proc, registro = _correr(entorno, FAKE_ETL_RC="0")

    assert proc.returncode == 0
    idx_end = next(i for i, ln in enumerate(registro) if ln.startswith("cron:end"))
    idx_coherencia = next(i for i, ln in enumerate(registro) if ln.startswith("cron:coherencia"))
    assert idx_coherencia > idx_end, "coherencia debe correr despues de end"
    partes = registro[idx_coherencia].split()
    assert partes[1] == "4242"  # job_id devuelto por start
    # fecha ISO explicita (mismo "ayer" que FORCE_START/FORCE_END), no una
    # recalculada por cron_jobs.py despues de que corrio KITCHEN.
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", partes[2])


def test_coherencia_caida_no_impide_que_ofelia_devuelva_el_rc_del_etl(entorno, tmp_path):
    """Igual que `stale`: si el chequeo de coherencia esta roto, no debe alterar el resultado."""
    cron_roto_coherencia = _escribir(tmp_path / "cron_stub2.py", f"""
        import sys
        with open(r"{entorno['llamadas']}", "a", encoding="utf-8") as fh:
            fh.write("cron:" + " ".join(sys.argv[1:]) + "\\n")
        sub = sys.argv[1]
        if sub == "start":
            print("4242")
            sys.exit(0)
        if sub == "coherencia":
            sys.stderr.write("boom: no se pudo conectar a MySQL\\n")
            sys.exit(1)
        sys.exit(0)
        """)

    proc, registro = _correr(entorno, CRON_JOBS=str(cron_roto_coherencia), FAKE_ETL_RC="0")

    assert proc.returncode == 0, "un chequeo de coherencia roto no debe voltear la corrida"
    assert any(ln.startswith("cron:coherencia") for ln in registro)


def test_start_que_falla_no_inventa_job_id_desde_el_stderr(entorno, tmp_path):
    """
    Regresion: extraer digitos del mensaje de error daria un job_id falso
    (ej. "linea 77" -> 77) y el cierre pisaria una fila ajena de
    jobs_historial. Sin id valido no se cierra nada.
    """
    llamadas = entorno["llamadas"]
    roto = _escribir(tmp_path / "start_roto.py", f"""
        import sys
        with open(r"{llamadas}", "a", encoding="utf-8") as fh:
            fh.write("cron:" + " ".join(sys.argv[1:]) + "\\n")
        if sys.argv[1] == "start":
            sys.stderr.write("Traceback ... linea 77, error 500\\n")
            sys.exit(1)
        sys.exit(0)
        """)

    proc, registro = _correr(entorno, CRON_JOBS=str(roto), FAKE_ETL_RC="0")

    assert "kitchen" in registro
    assert not [ln for ln in registro if ln.startswith("cron:end")], \
        "no debe cerrar ninguna fila si no hubo job_id valido"
    assert "no se pudo registrar el inicio" in proc.stderr
