"""
Tests del mecanismo de deteccion de fallos del wrapper bash
run_extract_sales_chunk.sh (Issue #124), que hasta ahora no tenia ningun
test propio (Issue #158). `call_for_grupo_deposito()` decide que un
grupo/deposito fallo mirando la respuesta REAL del WS -- un <MensError> en
el cuerpo, una respuesta vacia, o un cuerpo sin JSON reconocible -- y
acumula esos fallos en FAILED_GRUPO_DEPOSITO para que el wrapper salga con
exit != 0. Antes de #124 cualquiera de estos casos quedaba en un
"[WARN] ... continuando" sin marcar nada, y el merge corria igual con
datos parciales -- el fallo silencioso real en produccion que motivo el
ticket. El unico test cercano que existia (test_run_extract_sales_chunk_window.py)
cubre el calculo de la ventana de fechas, nunca este manejo de errores.

Por que Docker y no el bash del host (mismo antecedente que
test_run_ofelia.py y el cierre de #131-#139 en .claude/CONTEXTO.md sobre
bash 3.2 de macOS, pero ademas un motivo mas duro aca): dentro de
call_for_grupo_deposito(), run_extract_sales_chunk.sh invoca python3 con
rutas HARDCODEADAS a /app/services/etl/... -- asi corre en produccion, el
Dockerfile de etl hace `COPY . /app` sin volumen montado (ver
docker-compose.override.yml). Esas rutas no existen en el host de
desarrollo, asi que en bash del host el script se cae en la linea de
`get_grupos.py` antes de llegar siquiera a la logica que este archivo
prueba -- test_run_extract_sales_chunk_window.py nunca pasa de ahi porque
solo necesita la linea "[INFO] Sales window: ..." impresa ANTES de esa
llamada. Estos tests si necesitan pasar de ahi, asi que corren dentro del
contenedor evalutia-etl (bash 5 real, mismas rutas que produccion).

Sin red real: curl se reemplaza por un stub (PATH shadowing solo dentro
del `bash -c` que invoca el script) que escribe FAKE_CURL_BODY en el
archivo que el script pasa con `-o`, sin pegarle a ningun WS real. Cada
test controla el cuerpo que "responde" el WS.

Se saltan enteros si el contenedor no esta corriendo, y el unico test que
necesita escritura real (el camino de EXITO, de control) se salta aparte
si no hay MySQL -- mismo criterio de skip que el resto de la suite (CI no
levanta ninguno de los dos para services/etl/tests).
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

CONTAINER = "evalutia-etl"
SCRIPT_HOST = Path(__file__).resolve().parent.parent / "run_extract_sales_chunk.sh"
SCRIPT_CONTAINER = "/app/services/etl/run_extract_sales_chunk.sh"
STUB_DIR = "/tmp/test158_curl_stub"

CURL_STUB = """#!/usr/bin/env bash
# Stub de curl para test_run_extract_sales_chunk_wrapper_failures.py (#158)
# -- nunca pega a la red, solo escribe el cuerpo indicado por FAKE_CURL_BODY
# en el destino que el script real pasa con -o (y unas cabeceras dummy en
# -D, que el script nunca llega a parsear).
hdr=""
out=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -D) hdr="$2"; shift 2 ;;
    -o) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
[[ -n "$hdr" ]] && printf 'HTTP/1.1 200 OK\\r\\n\\r\\n' > "$hdr"
[[ -n "$out" ]] && printf '%s' "${FAKE_CURL_BODY-}" > "$out"
exit "${FAKE_CURL_EXIT:-0}"
"""

BASE_ENV = {
    "WS_URL": "http://fake-ws.invalid",
    "MYSQL_HOST": "fake-host",
    "MYSQL_DB": "fake-db",
    "MYSQL_USER": "fake-user",
    "MYSQL_PASSWORD": "fake-pass",
    "CERT_PATH": "/dev/null",
    "CACERT_PATH": "/dev/null",
    "CERT_PASSWORD": "x",
    "GROUPS": "99",  # override de get_grupos.py (Issue #42) -- sin esto pega a la tabla real
    "S_DEPOSITOS": "5",
    "FORCE_START": "01/08/2026",
    "FORCE_END": "01/08/2026",
}


def _docker_disponible():
    try:
        r = subprocess.run(["docker", "exec", CONTAINER, "true"], capture_output=True, timeout=5)
        return r.returncode == 0
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _docker_disponible(), reason=f"contenedor {CONTAINER} no disponible")


@pytest.fixture(scope="module", autouse=True)
def _imagen_sincronizada():
    """
    Canario: el Dockerfile de etl hornea el codigo (`COPY . /app`, sin
    volumen montado) -- estos tests validan la copia que quedo en la
    imagen, no el archivo que se esta editando en el host. Si difieren, es
    mejor saltar con un mensaje claro que validar en silencio una version
    vieja del script.
    """
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


def _correr(env_extra, timeout=20):
    env_flags = []
    for k, v in env_extra.items():
        env_flags += ["-e", f"{k}={v}"]
    cmd = [
        "docker", "exec", *env_flags, CONTAINER,
        "bash", "-c",
        f'export PATH="{STUB_DIR}:$PATH"; exec bash {SCRIPT_CONTAINER}',
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _falla_count(proc):
    m = re.search(r"^\[ERROR\] (\d+) grupo\(s\)/deposito\(s\) fallaron esta corrida:$", proc.stdout, re.M)
    return int(m.group(1)) if m else 0


def _mysql_disponible():
    r = subprocess.run(
        [
            "docker", "exec", CONTAINER, "python3", "-c",
            "import pymysql; pymysql.connect(host='mysql', port=3306, user='evalutia', "
            "password='evalutia', database='evalutia').close()",
        ],
        capture_output=True, timeout=10,
    )
    return r.returncode == 0


def test_mens_error_en_cuerpo_marca_grupo_deposito_como_fallido():
    """Issue #124: el WS puede responder 200 con un <MensError> en el
    cuerpo (deposito inexistente, credenciales, etc.) -- no es una falla de
    red ni HTTP, hay que leer el cuerpo para saber que fallo."""
    body = (
        '<?xml version="1.0"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body><ConsStockVentaResponse>"
        "<MensError>Deposito inexistente</MensError>"
        "</ConsStockVentaResponse></soap:Body></soap:Envelope>"
    )
    proc = _correr({**BASE_ENV, "FAKE_CURL_BODY": body})

    assert proc.returncode == 1, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "MensError en ConsStockVenta (grupo 99, deposito 5)" in proc.stdout
    assert "grupo=99 dep=5" in proc.stdout
    assert _falla_count(proc) == 1


def test_respuesta_vacia_marca_grupo_deposito_como_fallido():
    """Una caida a mitad de respuesta puede dejar el archivo de salida de
    curl vacio pese a exit 0 de curl -- el script lo trata como fallo
    explicito, no como 'sin ventas para este grupo/deposito'."""
    proc = _correr({**BASE_ENV, "FAKE_CURL_BODY": ""})

    assert proc.returncode == 1, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "Respuesta vacía de ConsStockVenta (grupo 99, deposito 5)" in proc.stdout
    assert "grupo=99 dep=5" in proc.stdout
    assert _falla_count(proc) == 1


def test_json_no_encontrado_marca_grupo_deposito_como_fallido():
    """Tercer modo del mismo mecanismo: cuerpo bien formado (200, XML
    valido) pero sin ningun patron de JSON reconocible -- ni
    <...Result>...</...Result>, ni <string>, ni CDATA."""
    body = (
        '<?xml version="1.0"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body><algo>sin resultado reconocible</algo></soap:Body></soap:Envelope>"
    )
    proc = _correr({**BASE_ENV, "FAKE_CURL_BODY": body})

    assert proc.returncode == 1, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "No se detectó JSON en ConsStockVenta (grupo 99, deposito 5)" in proc.stdout
    assert "grupo=99 dep=5" in proc.stdout
    assert _falla_count(proc) == 1


def test_varios_fallos_se_acumulan_y_el_exit_code_los_refleja():
    """Dos depositos del mismo grupo, los dos fallan -- FAILED_GRUPO_DEPOSITO
    debe listar los DOS (no solo el ultimo en pisar la variable) y el exit
    code final debe seguir siendo != 0."""
    proc = _correr({**BASE_ENV, "S_DEPOSITOS": "5,8", "FAKE_CURL_BODY": ""})

    assert proc.returncode == 1, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert _falla_count(proc) == 2
    assert "grupo=99 dep=5" in proc.stdout
    assert "grupo=99 dep=8" in proc.stdout


def test_sin_fallos_no_marca_nada_y_sale_con_exit_0():
    """
    Control del mecanismo: una respuesta VALIDA con JSON real no debe
    activar nada de lo de arriba -- FAILED_GRUPO_DEPOSITO queda vacio y el
    wrapper sale con exit 0. A diferencia de los otros cuatro tests, esto
    si llega a invocar run_extract_sales_chunk.py con una conexion MySQL
    real (aunque el lote venga vacio) -- se salta si no hay MySQL
    disponible en el compose local.
    """
    if not _mysql_disponible():
        pytest.skip("Sin MySQL real disponible (compose local) para ejercitar el camino de exito.")

    body = (
        '<?xml version="1.0"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body><ConsStockVentaResponse>"
        "<ConsStockVentaResult>[]</ConsStockVentaResult>"
        "</ConsStockVentaResponse></soap:Body></soap:Envelope>"
    )
    proc = _correr({
        **BASE_ENV,
        "FAKE_CURL_BODY": body,
        "MYSQL_HOST": "mysql",
        "MYSQL_DB": "evalutia",
        "MYSQL_USER": "evalutia",
        "MYSQL_PASSWORD": "evalutia",
    })

    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "fallaron esta corrida" not in proc.stdout
