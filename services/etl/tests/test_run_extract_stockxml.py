"""
Tests de las guardas de rango de run_extract_stockxml.sh (Issue #119) y del
timeout del curl (Issue #141).

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

Issue #141 agrega el caso "el WS acepta la conexion TCP y nunca responde" --
antes de ese fix el curl no tenia --connect-timeout/--max-time, asi que ese
escenario colgaba el script para siempre. Ver
test_ws_acepta_conexion_pero_nunca_responde_no_cuelga_para_siempre.
"""

import os
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "run_extract_stockxml.sh"
KJB = Path(__file__).resolve().parent.parent / "job_etl_diario.kjb"
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


class _WsQueAceptaYNuncaResponde:
    """Servidor TCP que acepta la conexion y nunca manda nada -- simula un
    web service que acepta pero jamas responde, para el AC de Issue #141
    ("verificado simulando un web service que acepta la conexion y no
    responde"). Nunca lee ni escribe en el socket aceptado: el request que
    curl mande queda sentado en el buffer del kernel sin que nada lo drene,
    y la conexion se mantiene abierta hasta stop()."""

    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        self._conns = []
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        self._sock.settimeout(0.2)
        while not self._stop:
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self._conns.append(conn)

    def stop(self):
        self._stop = True
        self._thread.join(timeout=2)
        for conn in self._conns:
            try:
                conn.close()
            except OSError:
                pass
        try:
            self._sock.close()
        except OSError:
            pass


def test_ws_acepta_conexion_pero_nunca_responde_no_cuelga_para_siempre():
    """
    Issue #141: antes de este fix el curl no tenia --connect-timeout ni
    --max-time -- un WS que acepta la conexion TCP y jamas manda la
    respuesta HTTP dejaba el script colgado para siempre. Ahora
    CURL_CONNECT_TIMEOUT/CURL_MAX_TIME lo acotan.
    """
    srv = _WsQueAceptaYNuncaResponde()
    try:
        inicio = time.monotonic()
        proc = _correr(
            WS_URL=f"http://127.0.0.1:{srv.port}",
            FORCE_START="01/08/2026",
            FORCE_END="01/08/2026",
            CURL_CONNECT_TIMEOUT="1",
            CURL_MAX_TIME="2",
        )
        elapsed = time.monotonic() - inicio
    finally:
        srv.stop()

    # _correr ya tiene timeout=15 como red de seguridad del propio test --
    # lo que este assert verifica es que el script terminó MUCHO antes de
    # eso, acotado por CURL_MAX_TIME, no que eventualmente lo mataria pytest.
    assert elapsed < 8, f"el script tardó {elapsed:.1f}s -- debería cortar por CURL_MAX_TIME=2s"
    assert proc.returncode != 0
    # El propio script loguea a stdout (mismo criterio que
    # run_extract_articulos.sh); el mensaje crudo de curl va a stderr.
    assert "curl fall" in proc.stdout.lower()
    assert "timed out" in proc.stderr.lower()


def test_kjb_envuelve_el_paso_de_stock_con_timeout():
    """
    Issue #141: el curl interno ya tiene su propio --max-time, pero eso solo
    lo cubre a el -- cualquier otro hijo que se cuelgue (la escritura a
    MySQL, por ejemplo) seguia sin techo y podia retener para siempre el fd
    200 del lock de backfill (ver lock_backfill.sh). job_etl_diario.kjb
    envuelve el paso completo con `timeout` como red de seguridad adicional.
    Este test es un guardrail: que una edicion futura del .kjb no vuelva a
    sacar el wrapper sin que un test lo note.
    """
    kjb = KJB.read_text(encoding="utf-8")

    m = re.search(
        r"<name>RUN EXTRACT STOCKXML</name>.*?<script><!\[CDATA\[(.*?)\]\]></script>",
        kjb,
        re.DOTALL,
    )
    assert m, "no se encontró la entrada RUN EXTRACT STOCKXML en el .kjb"

    comando = m.group(1)
    assert re.search(r"\btimeout\s+--kill-after=\S+\s+\S+\s+/bin/bash\b.*run_extract_stockxml\.sh", comando), (
        f"el paso RUN EXTRACT STOCKXML deberia invocar el script con un timeout que garantice "
        f"un techo duro, comando actual:\n{comando}"
    )
