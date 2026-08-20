"""
Tests de finalize_articulo_grupos.py (Issue #121) -- vuelca articulo_grupo_stage
a articulo_grupo y recalcula grupo_id "principal".

Integracion contra MySQL real con pytest.skip si no hay DB (mismo patron que
test_run_extract_sales_chunk.py / test_cron_jobs.py).

finalize() SOLO reemplaza por completo la membresia de los grupos que el
caller marca como `full_pull_grupos` (los que hicieron pull sin filtro de
fecha esta corrida, ver run_extract_articulos.sh) -- para el resto es
aditivo (INSERT IGNORE, nunca DELETE). Motivo: la llamada SOAP de un grupo ya
conocido es incremental (7 dias); tratar cualquier corrida como "la foto
completa" borraria a diario la membresia real de todo articulo que no
hubiera cambiado esa semana -- el bug que encontro el /code-review antes de
commitear esto. El fixture respalda articulo_grupo antes de correr y lo
restaura al terminar, para no pisar datos reales si el test corre contra una
DB que ya tiene el ETL en uso.
"""

import os

import pytest

import finalize_articulo_grupos as fg


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


SKU_A = "__TEST_121_A__"
SKU_B = "__TEST_121_B__"
# 9101/9102 visibles (como la mayoria del catalogo real), 9103 catch-all --
# mismo patron que 199/200 en produccion (visible_planilla=FALSE).
GRUPO_VISIBLE_BAJO = 9101
GRUPO_VISIBLE_ALTO = 9102
GRUPO_CATCHALL = 9103
GRUPOS_TEST = [GRUPO_VISIBLE_BAJO, GRUPO_VISIBLE_ALTO, GRUPO_CATCHALL]


@pytest.fixture
def conn():
    c = _try_connect()

    def _limpiar(cur):
        cur.execute("DELETE FROM articulo_grupo_stage")
        cur.execute("DELETE FROM articulo_grupo WHERE sku IN (%s, %s)", (SKU_A, SKU_B))
        cur.execute("DELETE FROM articulos WHERE sku IN (%s, %s)", (SKU_A, SKU_B))
        cur.execute(
            f"DELETE FROM grupos WHERE id IN ({','.join(['%s'] * len(GRUPOS_TEST))})",
            GRUPOS_TEST,
        )

    with c.cursor() as cur:
        _limpiar(cur)
        cur.executemany(
            "INSERT INTO grupos (id, descripcion, visible_planilla) VALUES (%s, %s, %s)",
            [
                (GRUPO_VISIBLE_BAJO, "TEST GRUPO VISIBLE BAJO", True),
                (GRUPO_VISIBLE_ALTO, "TEST GRUPO VISIBLE ALTO", True),
                (GRUPO_CATCHALL, "TEST GRUPO CATCH-ALL", False),
            ],
        )
        # grupo_id inicial = el catch-all, simulando el bug de #121 (el
        # articulo ya quedo mal etiquetado por una corrida anterior).
        cur.executemany(
            "INSERT INTO articulos (sku, grupo_id) VALUES (%s, %s)",
            [(SKU_A, GRUPO_CATCHALL), (SKU_B, GRUPO_CATCHALL)],
        )
    c.commit()

    # Respaldo de lo que hubiera en articulo_grupo antes del test -- un
    # full_pull_grupos que incluya GRUPOS_TEST reemplaza esas filas por completo.
    with c.cursor() as cur:
        cur.execute("SELECT sku, grupo_id FROM articulo_grupo")
        snapshot = cur.fetchall()

    yield c

    with c.cursor() as cur:
        cur.execute("DELETE FROM articulo_grupo_stage")
        cur.execute("DELETE FROM articulo_grupo")
        if snapshot:
            cur.executemany(
                "INSERT INTO articulo_grupo (sku, grupo_id) VALUES (%s, %s)", snapshot
            )
        _limpiar(cur)
    c.commit()
    c.close()


def _membresias(conn, sku):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT grupo_id FROM articulo_grupo WHERE sku = %s ORDER BY grupo_id", (sku,)
        )
        return [row[0] for row in cur.fetchall()]


def _grupo_principal(conn, sku):
    with conn.cursor() as cur:
        cur.execute("SELECT grupo_id FROM articulos WHERE sku = %s", (sku,))
        return cur.fetchone()[0]


def _stage(conn, sku, grupos):
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO articulo_grupo_stage (sku, grupo_id) VALUES (%s, %s)",
            [(sku, g) for g in grupos],
        )
    conn.commit()


def test_grupo_principal_es_el_menor_id_entre_los_visibles(conn):
    """
    Caso central del issue: un articulo que el catch-all (mayor id, invisible
    en el filtro) se habia quedado con TODA la membresia. finalize() tiene
    que elegir el menor id entre los visibles, no el catch-all. Los tres
    grupos de prueba hicieron pull completo esta corrida (simula la primera
    corrida del ETL con el codigo nuevo).
    """
    _stage(conn, SKU_A, [GRUPO_CATCHALL, GRUPO_VISIBLE_ALTO, GRUPO_VISIBLE_BAJO])

    fg.finalize(conn, full_pull_grupos=GRUPOS_TEST)
    conn.commit()

    assert _membresias(conn, SKU_A) == [
        GRUPO_VISIBLE_BAJO,
        GRUPO_VISIBLE_ALTO,
        GRUPO_CATCHALL,
    ], "todas las membresias reales tienen que quedar guardadas, no solo la principal"
    assert _grupo_principal(conn, SKU_A) == GRUPO_VISIBLE_BAJO


def test_sin_ningun_grupo_visible_cae_al_menor_id_general(conn):
    """
    Si un articulo SOLO pertenece a grupos no visibles (ej. 199 y 200), no
    puede quedar sin grupo_id (columna NOT NULL con FK) -- usa el menor id
    entre los que tiene, aunque ninguno sea visible.
    """
    _stage(conn, SKU_B, [GRUPO_CATCHALL])

    fg.finalize(conn, full_pull_grupos=[GRUPO_CATCHALL])
    conn.commit()

    assert _grupo_principal(conn, SKU_B) == GRUPO_CATCHALL


def test_grupo_con_pull_completo_reemplaza_su_membresia_entera(conn):
    """
    Reasignacion real del cliente: un articulo que pertenecia a dos grupos
    pasa a pertenecer a uno solo, y AMBOS grupos hicieron pull completo esta
    corrida (es_grupo_nuevo=1 para los dos, o un re-seed manual). Ahi si debe
    detectarse la baja -- el stage de esta corrida es la foto completa real.

    SKU_B en GRUPO_VISIBLE_BAJO es relleno (issue #168): sin al menos una
    fila real en stage para ese grupo, un pull completo que genuinamente
    perdio su unico articulo es indistinguible de un pull que fallo del
    todo -- la guard nueva de #168 no borraria un grupo con el stage
    totalmente vacio para el. Este test verifica el reemplazo real, no esa
    guard (ver test_full_pull_grupo_sin_ninguna_fila_en_stage_no_borra_su_membresia).
    """
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO articulo_grupo (sku, grupo_id) VALUES (%s, %s)",
            [(SKU_A, GRUPO_VISIBLE_BAJO), (SKU_A, GRUPO_VISIBLE_ALTO)],
        )
    conn.commit()

    # Esta corrida solo vio al articulo A en el grupo alto -- B se queda en
    # el bajo, prueba de que el pull de GRUPO_VISIBLE_BAJO si trajo datos.
    _stage(conn, SKU_A, [GRUPO_VISIBLE_ALTO])
    _stage(conn, SKU_B, [GRUPO_VISIBLE_BAJO])

    fg.finalize(conn, full_pull_grupos=[GRUPO_VISIBLE_BAJO, GRUPO_VISIBLE_ALTO])
    conn.commit()

    assert _membresias(conn, SKU_A) == [GRUPO_VISIBLE_ALTO]
    assert _grupo_principal(conn, SKU_A) == GRUPO_VISIBLE_ALTO


def test_grupo_incremental_sin_full_pull_no_borra_membresia_vieja(conn):
    """
    Regresion del bug encontrado en code-review: la llamada SOAP de un grupo
    YA conocido es incremental (7 dias), no la foto completa. Una corrida
    normal (full_pull_grupos vacio, el caso de casi todas las noches) NO
    puede borrar una membresia real solo porque no aparecio en el delta de
    esta semana -- si lo hiciera, el catalogo entero se vaciaria en unos
    dias. Verifica el fix: sin full_pull_grupos, todo lo que ya estaba en
    articulo_grupo sobrevive, se hayan visto o no en el stage de esta noche.
    """
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO articulo_grupo (sku, grupo_id) VALUES (%s, %s)",
            [(SKU_A, GRUPO_VISIBLE_BAJO), (SKU_A, GRUPO_VISIBLE_ALTO)],
        )
    conn.commit()

    # Noche tranquila: ningun grupo tuvo cambios para SKU_A (stage vacio para
    # el, o MensError -- da igual), y ningun grupo es "nuevo" esta corrida.
    fg.finalize(conn, full_pull_grupos=[])
    conn.commit()

    assert _membresias(conn, SKU_A) == [GRUPO_VISIBLE_BAJO, GRUPO_VISIBLE_ALTO], (
        "una corrida incremental sin novedades no debe tocar membresias existentes"
    )


def test_grupo_incremental_agrega_membresia_nueva_sin_tocar_las_demas(conn):
    """Un grupo no-nuevo que SI devuelve al articulo esta semana (porque
    cambio algo) agrega la membresia -- aditivo, no reemplaza el resto."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO articulo_grupo (sku, grupo_id) VALUES (%s, %s)",
            (SKU_A, GRUPO_VISIBLE_BAJO),
        )
    conn.commit()

    _stage(conn, SKU_A, [GRUPO_VISIBLE_ALTO])  # grupo alto, incremental, no "nuevo"

    fg.finalize(conn, full_pull_grupos=[])
    conn.commit()

    assert _membresias(conn, SKU_A) == [GRUPO_VISIBLE_BAJO, GRUPO_VISIBLE_ALTO]


def test_stage_queda_vacio_despues_de_finalizar(conn):
    _stage(conn, SKU_A, [GRUPO_VISIBLE_BAJO])

    fg.finalize(conn, full_pull_grupos=[GRUPO_VISIBLE_BAJO])
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM articulo_grupo_stage")
        assert cur.fetchone()[0] == 0


def test_articulo_sin_cambio_de_principal_no_se_toca(conn):
    """
    Si el grupo principal recalculado coincide con el que ya tenia, el
    UPDATE no debe tocar esa fila (evita golpear actualizado_en sin motivo
    en el 99% de los articulos que no cambian de mes a mes).
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE articulos SET grupo_id = %s WHERE sku = %s",
            (GRUPO_VISIBLE_BAJO, SKU_A),
        )
    conn.commit()

    _stage(conn, SKU_A, [GRUPO_VISIBLE_BAJO, GRUPO_VISIBLE_ALTO])

    _, n_articulos, _ = fg.finalize(conn, full_pull_grupos=GRUPOS_TEST)
    conn.commit()

    assert n_articulos == 0


# ── Issue #168: guard contra vaciado silencioso de grupo ────────────────────
# Root cause verificado: si un grupo entra a full_pull_grupos pero el WS
# fallo para el (#167 lo hace fallar de verdad ahora, pero esta guard es
# defensa en profundidad -- "sea por fallo o por otra causa" dice el propio
# issue), articulo_grupo_stage nunca tuvo ninguna fila de ese grupo. El
# DELETE de mas arriba lo vaciaria igual si confiara ciegamente en
# full_pull_grupos, y el INSERT IGNORE de la reconstruccion no repone nada
# porque el stage esta vacio para ese grupo -- el grupo queda sin ningun
# articulo, en silencio.

def test_full_pull_grupo_sin_ninguna_fila_en_stage_no_borra_su_membresia(conn):
    """Root cause de #168: un grupo en full_pull_grupos sin NINGUNA fila en
    el stage (WS fallo, o cualquier otra causa) no debe perder su membresia
    existente -- guard explicito, no basta con que el caller haya excluido
    el grupo de full_pull_grupos correctamente (defensa en profundidad)."""
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO articulo_grupo (sku, grupo_id) VALUES (%s, %s)",
            [(SKU_A, GRUPO_VISIBLE_BAJO), (SKU_B, GRUPO_VISIBLE_ALTO)],
        )
    conn.commit()

    # GRUPO_VISIBLE_BAJO entra como full_pull pero el stage no tiene NINGUNA
    # fila suya (simulacro del bug: el WS fallo para este grupo puntual).
    # GRUPO_VISIBLE_ALTO ni siquiera esta en full_pull_grupos, no deberia
    # tocarse tampoco.
    fg.finalize(conn, full_pull_grupos=[GRUPO_VISIBLE_BAJO])
    conn.commit()

    assert _membresias(conn, SKU_A) == [GRUPO_VISIBLE_BAJO], (
        "un grupo full_pull sin ninguna fila en stage no debe perder su membresia existente"
    )
    assert _membresias(conn, SKU_B) == [GRUPO_VISIBLE_ALTO]


def test_violacion_de_fk_se_cuenta_y_loguea_sin_perder_las_filas_buenas(conn, capsys):
    """El INSERT ya no puede tragarse una violacion de FK en silencio (antes:
    INSERT IGNORE se tragaba duplicados Y violaciones de FK por igual). Un
    SKU en stage que nunca llego a existir en `articulos` (ej. fallo su
    propia insercion en run_extract_articulos.py) debe contarse aparte y
    loguearse -- sin abortar el resto de las membresias validas del mismo
    lote."""
    sku_sin_articulo = "__TEST_168_SIN_ARTICULO__"
    with conn.cursor() as cur:
        cur.execute("DELETE FROM articulo_grupo_stage WHERE sku = %s", (sku_sin_articulo,))
        cur.execute(
            "INSERT INTO articulo_grupo_stage (sku, grupo_id) VALUES (%s, %s)",
            (sku_sin_articulo, GRUPO_VISIBLE_BAJO),
        )
    conn.commit()
    _stage(conn, SKU_A, [GRUPO_VISIBLE_ALTO])  # fila valida, en el mismo lote

    try:
        n_membresias, _, n_fk_violations = fg.finalize(conn, full_pull_grupos=[])
        conn.commit()

        assert n_fk_violations == 1
        assert n_membresias == 1  # SKU_A/GRUPO_VISIBLE_ALTO si se inserto
        assert _membresias(conn, SKU_A) == [GRUPO_VISIBLE_ALTO]

        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM articulo_grupo WHERE sku = %s", (sku_sin_articulo,)
            )
            assert cur.fetchone() is None

        salida = capsys.readouterr().out
        assert sku_sin_articulo in salida
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM articulo_grupo_stage WHERE sku = %s", (sku_sin_articulo,))
        conn.commit()
