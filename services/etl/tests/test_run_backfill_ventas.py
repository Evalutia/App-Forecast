"""
Tests del lock de run_backfill_ventas.sh (Issue #119).

Antes la exclusion con run_ofelia.sh era unidireccional: run_ofelia.sh solo
LEIA BACKFILL_LOCK_FILE para saltearse, nunca lo creaba -- si el backfill
arrancaba mientras el cron ya estaba corriendo, no habia nada que lo
detuviera. Ahora los dos usan flock (atomico) sobre el mismo archivo, asi que
alcanza con probar que run_backfill_ventas.sh respeta el lock cuando OTRO
proceso lo tiene tomado de verdad (no solo "el archivo existe", que es lo que
probaba el mecanismo viejo y ya no aplica).

No tocan MySQL ni el WS real: se corta en el lock (caso "tomado") o en un
stub de get_grupos_backfill.py (caso "libre"), antes de llegar a nada de eso.
"""

import fcntl
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REAL_SCRIPT = Path(__file__).resolve().parent.parent / "run_backfill_ventas.sh"
KJB = Path(__file__).resolve().parent.parent / "job_etl_diario.kjb"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash no disponible")

REQUIRED_ENV = {
    "WS_URL": "https://fake.invalid:81",
    "MYSQL_HOST": "fake-host",
    "MYSQL_DB": "fake-db",
    "MYSQL_USER": "fake-user",
    "MYSQL_PASSWORD": "fake-pass",
    "CERT_PATH": "/dev/null",
    "CACERT_PATH": "/dev/null",
    "CERT_PASSWORD": "x",
}


def _escribir(path: Path, contenido: str) -> Path:
    path.write_text(textwrap.dedent(contenido).lstrip(), encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def script_dir(tmp_path):
    """
    Copia run_backfill_ventas.sh a un directorio propio (SELF_DIR se deriva
    de la ubicacion del script, no es overridable por env) junto a un stub
    de get_grupos_backfill.py -- el primer script hermano que se invoca,
    bastante despues del lock, asi que no hace falta para el caso "tomado".
    """
    dest = tmp_path / "run_backfill_ventas.sh"
    shutil.copy(REAL_SCRIPT, dest)
    dest.chmod(0o755)
    # SELF_DIR (de donde sourcea lock_backfill.sh) tambien se deriva de la
    # ubicacion del script copiado.
    shutil.copy(REAL_SCRIPT.parent / "lock_backfill.sh", tmp_path / "lock_backfill.sh")

    marker = tmp_path / "get_grupos_llamado.marker"
    _escribir(tmp_path / "get_grupos_backfill.py", f"""
        # Si esto corre, el lock NO freno la ejecucion -- se deja constancia
        # y se devuelve vacio para que el script termine limpio despues.
        open(r"{marker}", "w").close()
        print("")
        """)
    return {"script": dest, "marker": marker, "tmp": tmp_path}


def _correr(script_dir, lock_path, **extra_env):
    env = {**os.environ, **REQUIRED_ENV, "BACKFILL_LOCK_FILE": str(lock_path)}
    env.update(extra_env)
    return subprocess.run(
        [BASH, str(script_dir["script"])],
        env=env, capture_output=True, text=True, timeout=15,
    )


def test_lock_tomado_por_otro_proceso_aborta_sin_tocar_nada(script_dir):
    lock = script_dir["tmp"] / "backfill.lock"
    lock.touch()

    # flock real, sostenido por este mismo proceso de test -- simula al
    # cron (run_ofelia.sh) corriendo de verdad, no solo "el archivo existe"
    # (eso era el mecanismo viejo, ya no representa el lock real).
    fd = os.open(lock, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        proc = _correr(script_dir, lock)

        assert proc.returncode == 1
        assert "en curso" in proc.stderr.lower()
        assert not script_dir["marker"].exists(), (
            "no debe llegar a get_grupos_backfill.py con el lock tomado"
        )
    finally:
        os.close(fd)


def test_lock_libre_sigue_de_largo(script_dir):
    lock = script_dir["tmp"] / "backfill.lock"

    proc = _correr(script_dir, lock)

    assert script_dir["marker"].exists(), (
        "con el lock libre, el script debe llegar a get_grupos_backfill.py"
    )
    # Sale con error despues (el stub devuelve lista vacia de grupos) -- lo
    # que importa acá es que pasó el lock, no el resultado final del backfill.
    assert proc.returncode == 2
    assert "no se obtuvo lista de grupos" in proc.stderr.lower()


# ── Nombres de tabla configurables (Issue #186) -- validados antes del ────────
# lock, para no tomar el flock (ni pegarle al WS) con una corrida condenada.

def test_tabla_ventas_stage_invalida_aborta_antes_del_lock(script_dir):
    lock = script_dir["tmp"] / "backfill.lock"

    proc = _correr(script_dir, lock, TABLA_VENTAS_STAGE="ventas; DROP TABLE articulos")

    assert proc.returncode == 2
    assert "no es un nombre de tabla valido" in proc.stderr.lower()
    assert not script_dir["marker"].exists(), (
        "invalido antes del lock -- no debe llegar a get_grupos_backfill.py"
    )
    assert not lock.exists(), "no debe tomar/crear el lock con un nombre de tabla invalido"


def test_tabla_ventas_invalida_aborta_antes_del_lock(script_dir):
    lock = script_dir["tmp"] / "backfill.lock"

    proc = _correr(script_dir, lock, TABLA_VENTAS="ventas_historicas; DROP TABLE articulos")

    assert proc.returncode == 2
    assert "no es un nombre de tabla valido" in proc.stderr.lower()
    assert not script_dir["marker"].exists()


def test_tabla_stock_diario_invalida_aborta_antes_del_lock(script_dir):
    """TABLA_STOCK_DIARIO no se usa dentro de este script (lo consume
    run_extract_sales_chunk.py via env) pero tiene que validarse en el mismo
    punto que las otras dos -- sin esto, un valor invalido recien fallaba
    despues de tomar el lock y de al menos una llamada SOAP real por chunk."""
    lock = script_dir["tmp"] / "backfill.lock"

    proc = _correr(script_dir, lock, TABLA_STOCK_DIARIO="stock_diario; DROP TABLE articulos")

    assert proc.returncode == 2
    assert "no es un nombre de tabla valido" in proc.stderr.lower()
    assert not script_dir["marker"].exists()


def test_nombres_de_tabla_por_defecto_pasan_la_validacion(script_dir):
    """Caso negativo del anterior: sin overrides, los defaults de produccion
    tienen que seguir pasando la validacion -- #186 no puede romper la
    corrida real de backfill_ventas."""
    lock = script_dir["tmp"] / "backfill.lock"

    proc = _correr(script_dir, lock)

    assert "no es un nombre de tabla valido" not in proc.stderr.lower()
    assert script_dir["marker"].exists()


def _extraer_join_where(texto: str) -> str:
    """Normaliza espacios para comparar el mismo bloque SQL entre un heredoc
    de bash indentado y un CDATA de XML indentado distinto."""
    # Issue #186: el nombre de la tabla stage en run_backfill_ventas.sh
    # dejo de ser el literal "ventas_historicas_stage" (ahora es la
    # variable Python tabla_stage, para poder redirigir al almacen de
    # comparacion) -- el FROM matchea cualquier identificador/variable, el
    # invariante real que este test protege es el JOIN+WHERE de abajo, que
    # sigue siendo texto fijo en los dos lados.
    m = re.search(
        r"FROM \S+ s\s*"
        r"INNER JOIN articulos a ON a\.sku = TRIM\(s\.sku\)\s*"
        r"WHERE s\.sku IS NOT NULL",
        texto,
    )
    assert m, "no se encontró el bloque FROM/JOIN/WHERE esperado"
    normalizado = re.sub(r"\s+", " ", m.group(0)).strip()
    return re.sub(r"^FROM \S+ s ", "FROM <TABLA> s ", normalizado)


def test_filtro_del_merge_identico_al_del_cron_diario():
    """
    Issue #119 (code-review post-implement): el hallazgo central de este
    issue -- los dos merges filtraban distinto -- no tenía ningún test que
    lo protegiera. Si en el futuro se edita uno de los dos lados (este
    script o el paso "MERGE STAGING -> VENTAS" de job_etl_diario.kjb) sin
    actualizar el otro, este test tiene que fallar en vez de dejar pasar en
    silencio la misma divergencia que #119 cerró.
    """
    backfill_sql = REAL_SCRIPT.read_text(encoding="utf-8")
    kjb_sql = KJB.read_text(encoding="utf-8")

    assert _extraer_join_where(backfill_sql) == _extraer_join_where(kjb_sql)
