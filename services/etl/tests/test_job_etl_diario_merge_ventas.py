"""
Tests del paso "MERGE STAGING -> VENTAS (con snapshot)" de job_etl_diario.kjb
(Issue #157) -- ejecuta el SQL real, extraido del propio .kjb (no una copia
de mano, para que un cambio futuro en el XML no pueda desalinearse en
silencio con lo que este archivo prueba).

Antes de #157, un grupo fallido en la extraccion saltaba este INSERT
entero via el hop condicional de "RUN EXTRACT VENTAS" -- los ~66 grupos,
incluidos los que salieron bien, quedaban sin mergear esa noche. Ahora el
INSERT siempre corre, y es su propio WHERE (NOT EXISTS contra
ventas_grupos_fallidos_run) el que excluye solo los grupos fallidos.

Integracion contra MySQL real con pytest.skip si no hay DB, mismo patron
que el resto de los tests de este directorio.
"""

import datetime as dt
import os
import re
from pathlib import Path

import pytest

KJB = Path(__file__).resolve().parent.parent / "job_etl_diario.kjb"

SKU_GRUPO_OK = "__TEST_157_OK__"
SKU_GRUPO_FALLIDO = "__TEST_157_FALLIDO__"
SKU_SIN_GRUPO = "__TEST_157_SINGRUPO__"
FECHA = dt.date(2026, 8, 1)
GRUPO_OK = 90157
GRUPO_FALLIDO = 90158


def _extraer_merge_sql() -> str:
    texto = KJB.read_text(encoding="utf-8")
    m = re.search(
        r"<name>MERGE STAGING -&gt; VENTAS \(con snapshot\)</name>.*?"
        r"<sql><!\[CDATA\[(.*?)\]\]></sql>",
        texto,
        re.S,
    )
    if m is None:
        # El nombre del entry puede venir con '->' literal en vez de
        # escapado, segun como Spoon haya guardado el archivo la ultima vez.
        m = re.search(
            r"<name>MERGE STAGING -> VENTAS \(con snapshot\)</name>.*?"
            r"<sql><!\[CDATA\[(.*?)\]\]></sql>",
            texto,
            re.S,
        )
    assert m, "no se encontró el SQL del step MERGE STAGING -> VENTAS (con snapshot) en el .kjb"
    return m.group(1)


def _try_connect():
    import pymysql

    try:
        port = int(os.environ.get("MYSQL_PORT", "3307"))
    except ValueError as e:
        pytest.fail(f"MYSQL_PORT invalido: {e}")

    try:
        return pymysql.connect(
            host=os.environ.get("MYSQL_HOST", "localhost"),
            port=port,
            user=os.environ.get("MYSQL_USER", "evalutia"),
            password=os.environ.get("MYSQL_PASSWORD", "evalutia"),
            database=os.environ.get("MYSQL_DB", "evalutia"),
            autocommit=False,
            charset="utf8mb4",
        )
    except pymysql.err.OperationalError:
        pytest.skip("Sin conexion a MySQL disponible -- test de integracion se salta.")


SKUS_TEST = (SKU_GRUPO_OK, SKU_GRUPO_FALLIDO, SKU_SIN_GRUPO)


@pytest.fixture
def conn():
    c = _try_connect()

    def _limpiar(cur):
        cur.execute(
            "DELETE FROM ventas_historicas WHERE sku IN (%s, %s, %s)", SKUS_TEST
        )
        cur.execute(
            "DELETE FROM ventas_historicas_stage WHERE sku IN (%s, %s, %s)", SKUS_TEST
        )
        cur.execute("DELETE FROM articulos WHERE sku IN (%s, %s, %s)", SKUS_TEST)
        cur.execute(
            "DELETE FROM ventas_grupos_fallidos_run WHERE grupo_id IN (%s, %s)",
            (GRUPO_OK, GRUPO_FALLIDO),
        )
        cur.execute("DELETE FROM grupos WHERE id IN (%s, %s)", (GRUPO_OK, GRUPO_FALLIDO))

    with c.cursor() as cur:
        _limpiar(cur)
        # articulos.grupo_id es NOT NULL con FK a grupos.id -- el valor en
        # si no importa para este test (el filtro real es por
        # ventas_historicas_stage.grupo_id, no por el "principal" de
        # articulos), solo tiene que satisfacer la FK.
        cur.executemany(
            "INSERT INTO grupos (id, descripcion) VALUES (%s, %s)",
            [(GRUPO_OK, "TEST GRUPO 157 OK"), (GRUPO_FALLIDO, "TEST GRUPO 157 FALLIDO")],
        )
        cur.executemany(
            "INSERT INTO articulos (sku, grupo_id) VALUES (%s, %s)",
            [(s, GRUPO_OK) for s in SKUS_TEST],
        )
    c.commit()

    yield c

    with c.cursor() as cur:
        _limpiar(cur)
    c.commit()
    c.close()


def _stage(conn, sku, cantidad, grupo_id, deposito_id="5"):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ventas_historicas_stage "
            "(fecha, sku, cantidad, deposito_id, grupo_id, fuente) "
            "VALUES (%s, %s, %s, %s, %s, 'ws_consstockventa')",
            (FECHA, sku, cantidad, deposito_id, grupo_id),
        )
    conn.commit()


def _marcar_fallido(conn, grupo_id):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT IGNORE INTO ventas_grupos_fallidos_run (grupo_id) VALUES (%s)",
            (grupo_id,),
        )
    conn.commit()


def _correr_merge(conn):
    sql = _extraer_merge_sql()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def _cantidad_en_ventas_historicas(conn, sku):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cantidad FROM ventas_historicas WHERE sku = %s AND fecha = %s",
            (sku, FECHA),
        )
        row = cur.fetchone()
        return row[0] if row else None


def test_grupo_fallido_no_se_mergea_pero_el_grupo_bueno_si(conn):
    """El caso central del issue: un grupo fallo, otro no, en la misma
    corrida -- el bueno debe llegar a ventas_historicas, el fallido no."""
    _stage(conn, SKU_GRUPO_OK, cantidad=10, grupo_id=GRUPO_OK)
    _stage(conn, SKU_GRUPO_FALLIDO, cantidad=999, grupo_id=GRUPO_FALLIDO)
    _marcar_fallido(conn, GRUPO_FALLIDO)

    _correr_merge(conn)

    assert _cantidad_en_ventas_historicas(conn, SKU_GRUPO_OK) == 10
    assert _cantidad_en_ventas_historicas(conn, SKU_GRUPO_FALLIDO) is None


def test_sin_grupos_fallidos_se_mergea_todo_como_antes(conn):
    """Regresion: si ventas_grupos_fallidos_run esta vacia (corrida sin
    fallos), el comportamiento es identico al de antes de #157."""
    _stage(conn, SKU_GRUPO_OK, cantidad=7, grupo_id=GRUPO_OK)

    _correr_merge(conn)

    assert _cantidad_en_ventas_historicas(conn, SKU_GRUPO_OK) == 7


def test_grupo_id_null_no_se_excluye_nunca(conn):
    """Filas sin grupo_id (esquema viejo antes de #114, o una fila que
    nunca pudo asociarse a un grupo) no deben excluirse por falta de dato
    -- NOT EXISTS con NULL nunca matchea, es exactamente lo que se quiere:
    la exclusion es solo para fallos confirmados y registrados."""
    _stage(conn, SKU_SIN_GRUPO, cantidad=3, grupo_id=None)
    _marcar_fallido(conn, GRUPO_FALLIDO)  # cualquier fallo, no relacionado

    _correr_merge(conn)

    assert _cantidad_en_ventas_historicas(conn, SKU_SIN_GRUPO) == 3


def test_grupo_marcado_fallido_pero_sin_filas_en_stage_no_rompe_nada(conn):
    """Un grupo puede fallar por completo (cero filas en stage, ni siquiera
    parciales) -- el NOT EXISTS no debe romper el merge de los demas."""
    _stage(conn, SKU_GRUPO_OK, cantidad=5, grupo_id=GRUPO_OK)
    _marcar_fallido(conn, GRUPO_FALLIDO)  # nunca escribio nada en stage

    _correr_merge(conn)

    assert _cantidad_en_ventas_historicas(conn, SKU_GRUPO_OK) == 5
