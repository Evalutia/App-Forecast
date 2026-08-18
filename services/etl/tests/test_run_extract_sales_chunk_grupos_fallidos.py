"""
Tests de integracion: run_extract_sales_chunk.sh registra los grupos
fallidos en ventas_grupos_fallidos_run (Issue #157), para que el paso
"MERGE STAGING -> VENTAS" del .kjb pueda excluirlos sin saltear el merge
entero (ver test_job_etl_diario_merge_ventas.py para ese lado, y
test_grupos_fallidos_run.py para el helper en aislamiento).

Mismo motivo que test_run_extract_sales_chunk_wrapper_failures.py (#158)
para correr dentro del contenedor evalutia-etl en vez del bash del host:
las rutas hardcodeadas a /app/services/etl/... no existen fuera de la
imagen, y el bash de macOS (3.2) ya dio diagnosticos equivocados antes
(#131-#139). Mismo stub de curl (PATH shadowing, sin red real).
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

CONTAINER = "evalutia-etl"
SCRIPT_HOST = Path(__file__).resolve().parent.parent / "run_extract_sales_chunk.sh"
SCRIPT_CONTAINER = "/app/services/etl/run_extract_sales_chunk.sh"
STUB_DIR = "/tmp/test157_curl_stub"

CURL_STUB = """#!/usr/bin/env bash
# Stub de curl para test_run_extract_sales_chunk_grupos_fallidos.py (#157)
# -- nunca pega a la red. Responde distinto segun el grupo pedido (via
# FAKE_CURL_BODY_GRUPO_<n>), para poder hacer que UN grupo falle y otro no
# en la misma corrida sin depender del WS real.
hdr=""
out=""
req=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -D) hdr="$2"; shift 2 ;;
    -o) out="$2"; shift 2 ;;
    --data-binary) req="${2#@}"; shift 2 ;;
    *) shift ;;
  esac
done
[[ -n "$hdr" ]] && printf 'HTTP/1.1 200 OK\\r\\n\\r\\n' > "$hdr"
grupo="$(grep -o '<IdGrupo>[0-9]*</IdGrupo>' "$req" | grep -o '[0-9]*')"
body_var="FAKE_CURL_BODY_GRUPO_${grupo}"
[[ -n "$out" ]] && printf '%s' "${!body_var-}" > "$out"
exit 0
"""

BASE_ENV = {
    "WS_URL": "http://fake-ws.invalid",
    "MYSQL_HOST": "mysql",
    "MYSQL_DB": "evalutia",
    "MYSQL_USER": "evalutia",
    "MYSQL_PASSWORD": "evalutia",
    "CERT_PATH": "/dev/null",
    "CACERT_PATH": "/dev/null",
    "CERT_PASSWORD": "x",
    "S_DEPOSITOS": "5",
    "FORCE_START": "01/08/2026",
    "FORCE_END": "01/08/2026",
}

GRUPO_OK = "91"
GRUPO_MAL = "92"

BODY_OK = (
    '<?xml version="1.0"?>'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
    "<soap:Body><ConsStockVentaResponse>"
    "<ConsStockVentaResult>[]</ConsStockVentaResult>"
    "</ConsStockVentaResponse></soap:Body></soap:Envelope>"
)
BODY_MENS_ERROR = (
    '<?xml version="1.0"?>'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
    "<soap:Body><ConsStockVentaResponse>"
    "<MensError>Deposito inexistente</MensError>"
    "</ConsStockVentaResponse></soap:Body></soap:Envelope>"
)


def _docker_disponible():
    try:
        r = subprocess.run(["docker", "exec", CONTAINER, "true"], capture_output=True, timeout=5)
        return r.returncode == 0
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


def _mysql_disponible():
    if not _docker_disponible():
        return False
    r = subprocess.run(
        [
            "docker", "exec", CONTAINER, "python3", "-c",
            "import pymysql; pymysql.connect(host='mysql', port=3306, user='evalutia', "
            "password='evalutia', database='evalutia').close()",
        ],
        capture_output=True, timeout=10,
    )
    return r.returncode == 0


pytestmark = pytest.mark.skipif(
    not _mysql_disponible(),
    reason=f"contenedor {CONTAINER} o MySQL no disponibles",
)


@pytest.fixture(scope="module", autouse=True)
def _imagen_sincronizada():
    """Mismo canario que #158: valida contra la copia horneada en la
    imagen, no el archivo que se esta editando en el host."""
    r = subprocess.run(
        ["docker", "exec", CONTAINER, "cat", SCRIPT_CONTAINER],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode != 0 or r.stdout != SCRIPT_HOST.read_text(encoding="utf-8"):
        pytest.skip(
            f"{SCRIPT_CONTAINER} en el contenedor difiere de {SCRIPT_HOST.name} en el host "
            "-- correr `docker compose build etl` antes de confiar en estos tests."
        )


@pytest.fixture(scope="module", autouse=True)
def _stub_curl_instalado():
    with tempfile.NamedTemporaryFile("w", suffix="_curl", delete=False) as f:
        f.write(CURL_STUB)
        tmp_path = f.name
    try:
        subprocess.run(["docker", "exec", CONTAINER, "mkdir", "-p", STUB_DIR], check=True, timeout=10)
        subprocess.run(["docker", "cp", tmp_path, f"{CONTAINER}:{STUB_DIR}/curl"], check=True, timeout=10)
        subprocess.run(["docker", "exec", CONTAINER, "chmod", "+x", f"{STUB_DIR}/curl"], check=True, timeout=10)
    finally:
        os.unlink(tmp_path)
    yield
    subprocess.run(["docker", "exec", CONTAINER, "rm", "-rf", STUB_DIR], timeout=10)


@pytest.fixture
def limpiar_tabla():
    """Vacia ventas_grupos_fallidos_run antes y despues de cada test --
    esta suite corre contra MySQL real, compartido con otros tests."""
    def _delete():
        subprocess.run(
            ["docker", "exec", CONTAINER, "python3", "-c",
             "import os, pymysql; c = pymysql.connect(host='mysql', port=3306, user='evalutia', "
             "password='evalutia', database='evalutia'); cur = c.cursor(); "
             "cur.execute('DELETE FROM ventas_grupos_fallidos_run'); c.commit()"],
            capture_output=True, timeout=10,
        )
    _delete()
    yield
    _delete()


def _listar_fallidos():
    r = subprocess.run(
        ["docker", "exec",
         "-e", "MYSQL_HOST=mysql", "-e", "MYSQL_DB=evalutia",
         "-e", "MYSQL_USER=evalutia", "-e", "MYSQL_PASSWORD=evalutia",
         CONTAINER, "python3", "/app/services/etl/grupos_fallidos_run.py", "listar"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    texto = r.stdout.strip()
    return [g for g in texto.split(",") if g]


def _correr(env_extra, timeout=30):
    env_flags = []
    for k, v in {**BASE_ENV, **env_extra}.items():
        env_flags += ["-e", f"{k}={v}"]
    cmd = [
        "docker", "exec", *env_flags, CONTAINER,
        "bash", "-c",
        f'export PATH="{STUB_DIR}:$PATH"; exec bash {SCRIPT_CONTAINER}',
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def test_grupo_fallido_queda_registrado_en_la_tabla(limpiar_tabla):
    proc = _correr({
        "GRUPOS": GRUPO_MAL,
        "FAKE_CURL_BODY_GRUPO_92": BODY_MENS_ERROR,
    })

    assert proc.returncode == 1, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert _listar_fallidos() == ["92"]


def test_grupo_exitoso_no_queda_registrado(limpiar_tabla):
    proc = _correr({
        "GRUPOS": GRUPO_OK,
        "FAKE_CURL_BODY_GRUPO_91": BODY_OK,
    })

    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert _listar_fallidos() == []


def test_reset_al_arrancar_no_arrastra_un_fallo_de_la_corrida_anterior(limpiar_tabla):
    """Simulacro de dos corridas seguidas: la primera deja un grupo
    fallido registrado; la segunda (una corrida normal, sin ese grupo en
    la lista) debe arrancar con la tabla vacia -- el reset del inicio no
    debe depender de que el grupo de anoche vuelva a aparecer hoy."""
    primera = _correr({
        "GRUPOS": GRUPO_MAL,
        "FAKE_CURL_BODY_GRUPO_92": BODY_MENS_ERROR,
    })
    assert primera.returncode == 1
    assert _listar_fallidos() == ["92"]

    segunda = _correr({
        "GRUPOS": GRUPO_OK,
        "FAKE_CURL_BODY_GRUPO_91": BODY_OK,
    })
    assert segunda.returncode == 0
    assert _listar_fallidos() == [], (
        "el grupo fallido de la corrida anterior no deberia sobrevivir al reset de esta"
    )
