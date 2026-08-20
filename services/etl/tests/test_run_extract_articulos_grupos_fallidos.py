"""
Tests de integracion: run_extract_articulos.sh propaga un MensError real
del WS como fallo (Issue #167) -- antes, la rama de MensError hacia
`echo "Salida OK."; return 0`, y el `.kjb` nunca disparaba el hop
"RUN EXTRACT ARTICULOS" -> "MARK ARTICULOS FAILED" ya cableado (categoria
"marca y sigue"). Capa 1 de #124, cerrada para ventas
(test_run_extract_sales_chunk_grupos_fallidos.py) y nunca replicada aca.

Mismo motivo que esos tests para correr dentro del contenedor evalutia-etl
en vez del bash del host: rutas hardcodeadas a /app/services/etl/... y
bash 3.2 de macOS. Mismo stub de curl (PATH shadowing, sin red real),
adaptado al tag <Grupos> que usa este script (no <IdGrupo> como ventas).
"""

import subprocess
from pathlib import Path

import pytest

CONTAINER = "evalutia-etl"
SCRIPT_HOST = Path(__file__).resolve().parent.parent / "run_extract_articulos.sh"
SCRIPT_CONTAINER = "/app/services/etl/run_extract_articulos.sh"
STUB_DIR = "/tmp/test167_curl_stub"

CURL_STUB = """#!/usr/bin/env bash
# Stub de curl para test_run_extract_articulos_grupos_fallidos.py (#167) --
# nunca pega a la red. Responde distinto segun el grupo pedido (via
# FAKE_CURL_BODY_GRUPO_<n>), leyendo <Grupos>N</Grupos> del request (no
# <IdGrupo>, que es el tag que usa run_extract_sales_chunk.sh).
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
grupo="$(grep -o '<Grupos>[0-9]*</Grupos>' "$req" | grep -o '[0-9]*')"
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
    "FORCE_START": "01/08/2026",
}

GRUPO_OK = "93"
GRUPO_MAL = "94"

BODY_OK = (
    '<?xml version="1.0"?>'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
    "<soap:Body><ConsArticulosWebResponse>"
    "<ConsArticulosWebResult>[]</ConsArticulosWebResult>"
    "</ConsArticulosWebResponse></soap:Body></soap:Envelope>"
)
BODY_MENS_ERROR = (
    '<?xml version="1.0"?>'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
    "<soap:Body><ConsArticulosWebResponse>"
    "<MensError>Grupo inexistente</MensError>"
    "</ConsArticulosWebResponse></soap:Body></soap:Envelope>"
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
    """Mismo canario que #158/#157: valida contra la copia horneada en la
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
    import tempfile
    import os

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


def test_mens_error_hace_fallar_el_script(request):
    proc = _correr({
        "GRUPOS": GRUPO_MAL,
        "FAKE_CURL_BODY_GRUPO_94": BODY_MENS_ERROR,
    })

    assert proc.returncode != 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "MensError" in proc.stdout


def test_grupo_exitoso_sin_mens_error_termina_ok():
    proc = _correr({
        "GRUPOS": GRUPO_OK,
        "FAKE_CURL_BODY_GRUPO_93": BODY_OK,
    })

    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
