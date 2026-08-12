"""
Tests de lib_articulo_grupo_decision.sh (Issue #121).

La regla ("solo reconstruir articulo_grupo si la corrida barrio TODOS los
grupos y ninguno fallo") vive aislada en su propia funcion pura -- sin curl
ni MySQL de por medio -- para poder testearla sin levantar el resto de
run_extract_articulos.sh (mismo motivo que lock_backfill.sh vive aparte,
Issue #119).

Se salta si no hay bash disponible.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parent.parent / "lib_articulo_grupo_decision.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash no disponible")


def _decide(crawl_completo: str, grupos_fallidos: str) -> bool:
    proc = subprocess.run(
        [BASH, "-c", f'source "{LIB}"; debe_reconstruir_articulo_grupo "$1" "$2"',
         "--", crawl_completo, grupos_fallidos],
    )
    return proc.returncode == 0


def test_crawl_completo_sin_fallos_reconstruye():
    assert _decide("1", "0") is True


def test_crawl_completo_con_un_fallo_no_reconstruye():
    """El caso que #121 pide explicitamente: un grupo que fallo no puede
    hacer que se borren membresias reales de grupos que si funcionaron."""
    assert _decide("1", "1") is False


def test_crawl_completo_con_varios_fallos_no_reconstruye():
    assert _decide("1", "5") is False


def test_crawl_parcial_sin_fallos_no_reconstruye():
    """Override puntual de grupos (debug/reproceso) -- barrio menos grupos
    que el catalogo completo, asi que reconstruir borraria membresias reales
    de los grupos que quedaron afuera de este run."""
    assert _decide("0", "0") is False


def test_crawl_parcial_con_fallos_no_reconstruye():
    assert _decide("0", "1") is False
