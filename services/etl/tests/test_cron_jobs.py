"""
Tests de cron_jobs.py (Issue #111) — bookkeeping del cron nocturno en
jobs_historial.

Integracion contra MySQL real con pytest.skip si no hay DB (CI no levanta
MySQL para services/etl/tests), mismo patron que test_backfill_jobs.py.
Cada test limpia sus propias filas antes y despues: jobs_historial es una
tabla compartida con datos reales en la DB local sincronizada de produccion,
no una tabla de scratch.
"""

import datetime as dt
import json
import os

import pytest

import cron_jobs

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


@pytest.fixture
def conn(monkeypatch):
    """
    Conexion de verificacion + limpieza. Las filas creadas por el test se
    borran por rango de id (todo lo insertado despues del MAX(id) inicial),
    sin necesidad de marcadores de test en el codigo de produccion.
    """
    c = _try_connect()
    # cron_jobs.db_connect() lee del env con los nombres que usa el contenedor
    monkeypatch.setenv("MYSQL_HOST", os.environ.get("MYSQL_HOST", "localhost"))
    monkeypatch.setenv("MYSQL_PORT", os.environ.get("MYSQL_PORT", "3307"))
    monkeypatch.setenv("MYSQL_USER", os.environ.get("MYSQL_USER", "evalutia"))
    monkeypatch.setenv("MYSQL_PASSWORD", os.environ.get("MYSQL_PASSWORD", "evalutia"))
    monkeypatch.setenv("MYSQL_DB", os.environ.get("MYSQL_DB", "evalutia"))

    with c.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM jobs_historial")
        id_inicial = cur.fetchone()[0]
    c.commit()

    yield c

    with c.cursor() as cur:
        cur.execute("DELETE FROM jobs_historial WHERE id > %s", (id_inicial,))
    c.commit()
    c.close()


def _fila(conn, job_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tipo_job, estado, fecha_inicio, fecha_fin, detalle "
            "FROM jobs_historial WHERE id = %s",
            (job_id,),
        )
        row = cur.fetchone()
    return None if row is None else {
        "tipo_job": row[0], "estado": row[1], "fecha_inicio": row[2],
        "fecha_fin": row[3], "detalle": json.loads(row[4]) if row[4] else {},
    }


def test_start_inserta_ejecutando_y_devuelve_id(conn, capsys):
    rc = cron_jobs.cmd_start()
    assert rc == 0
    job_id = int(capsys.readouterr().out.strip())

    fila = _fila(conn, job_id)
    assert fila["tipo_job"] == "etl"
    assert fila["estado"] == "ejecutando"
    assert fila["fecha_fin"] is None
    assert fila["detalle"]["subtipo"] == "cron_diario"


def test_end_exitoso_cierra_la_fila_con_duracion_y_exit_code(conn, capsys):
    cron_jobs.cmd_start()
    job_id = int(capsys.readouterr().out.strip())

    assert cron_jobs.cmd_end(str(job_id), "0", "123.5") == 0

    fila = _fila(conn, job_id)
    assert fila["estado"] == "exitoso"
    assert fila["fecha_fin"] is not None
    assert fila["detalle"]["exit_code"] == 0
    assert fila["detalle"]["duracion_seg"] == 123.5
    assert fila["detalle"]["subtipo"] == "cron_diario"


def test_end_con_exit_code_distinto_de_cero_marca_fallido(conn, capsys):
    """El caso que hoy no deja rastro: la extraccion muere y nadie se entera."""
    cron_jobs.cmd_start()
    job_id = int(capsys.readouterr().out.strip())

    cron_jobs.cmd_end(str(job_id), "1", "37.0")

    fila = _fila(conn, job_id)
    assert fila["estado"] == "fallido"
    assert fila["detalle"]["exit_code"] == 1


def test_end_con_exit_code_137_marca_posible_oom(conn, capsys):
    """
    Issue #136: 137 (SIGKILL) sin marcar es un numero pelado que solo alguien
    que sepa que 128+9=SIGKILL puede leer -- inferencia, no confirmacion
    contra dmesg del host, pero suficiente para que la fila sea reconocible.
    """
    cron_jobs.cmd_start()
    job_id = int(capsys.readouterr().out.strip())

    cron_jobs.cmd_end(str(job_id), "137", "5420.0")

    fila = _fila(conn, job_id)
    assert fila["estado"] == "fallido"
    assert fila["detalle"]["posible_oom"] is True


def test_end_con_exit_code_distinto_de_137_no_marca_oom(conn, capsys):
    cron_jobs.cmd_start()
    job_id = int(capsys.readouterr().out.strip())

    cron_jobs.cmd_end(str(job_id), "1", "37.0")

    fila = _fila(conn, job_id)
    assert "posible_oom" not in fila["detalle"]


def test_skip_deja_registro_terminal_no_ejecutando(conn, capsys):
    """
    Las noches salteadas por el lock del backfill (29-31/07) fueron invisibles
    en la DB. Se registran, pero marcadas como omitidas para que no cuenten
    como corrida real.
    """
    assert cron_jobs.cmd_skip("backfill en curso") == 0
    job_id = int(capsys.readouterr().out.strip())

    fila = _fila(conn, job_id)
    assert fila["estado"] == "omitido"
    assert fila["estado"] != "ejecutando"
    assert fila["fecha_fin"] is not None
    assert fila["detalle"]["resultado"] == "omitido"
    assert "backfill" in fila["detalle"]["motivo"]


def test_skip_ya_no_se_cuenta_como_exitoso(conn, capsys):
    """
    Issue #132: antes un skip por lock de backfill quedaba con
    estado='exitoso' -- indistinguible de una corrida real y buena
    (29-31/07/2026: tres noches salteadas, las tres contadas como buenas).
    """
    cron_jobs.cmd_skip("backfill en curso")
    job_id = int(capsys.readouterr().out.strip())

    assert _fila(conn, job_id)["estado"] != "exitoso"


def test_estado_usa_solo_valores_del_enum(conn, capsys):
    """
    jobs_historial.estado es ENUM('en_cola','ejecutando','exitoso','fallido',
    'omitido'). Un valor fuera del ENUM lo rechaza MySQL en runtime (o lo
    trunca a ''), asi que ningun camino puede inventar estados nuevos sin
    migracion (ver infra/sql/22-jobs-historial-estado-omitido.sql).
    """
    validos = {"en_cola", "ejecutando", "exitoso", "fallido", "omitido"}

    cron_jobs.cmd_start()
    jid_run = int(capsys.readouterr().out.strip())
    cron_jobs.cmd_end(str(jid_run), "0", "1.0")
    cron_jobs.cmd_skip("motivo cualquiera")
    jid_skip = int(capsys.readouterr().out.strip())

    for jid in (jid_run, jid_skip):
        assert _fila(conn, jid)["estado"] in validos


def test_start_cierra_corridas_zombi_de_noches_anteriores(conn, capsys):
    """
    Si el contenedor muere a mitad de corrida (paso el 01/08/2026: ofelia
    quedo abajo), la fila queda en 'ejecutando' para siempre y el registro
    miente. La corrida siguiente la cierra como fallida -- seguro porque
    ofelia corre este job con no-overlap=true: nunca hay dos en paralelo.
    """
    cron_jobs.cmd_start()
    zombi = int(capsys.readouterr().out.strip())
    assert _fila(conn, zombi)["estado"] == "ejecutando"

    cron_jobs.cmd_start()
    nuevo = int(capsys.readouterr().out.strip())

    conn.commit()  # refresca el snapshot de la transaccion de lectura
    cerrada = _fila(conn, zombi)
    assert cerrada["estado"] == "fallido"
    assert cerrada["fecha_fin"] is not None
    assert cerrada["detalle"]["resultado"] == "interrumpido"
    assert _fila(conn, nuevo)["estado"] == "ejecutando", "la corrida nueva sigue viva"


def test_start_no_toca_jobs_ejecutando_de_otro_subtipo(conn, capsys):
    """El auto-sanado es solo del cron: no puede pisar un backfill en curso."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs_historial (tipo_job, estado, fecha_inicio, detalle) "
            "VALUES ('backfill', 'ejecutando', NOW(6), %s)",
            (json.dumps({"subtipo": "backfill_ventas", "grupo_id": "999"}),),
        )
        backfill_id = cur.lastrowid
    conn.commit()

    cron_jobs.cmd_start()
    capsys.readouterr()

    conn.commit()
    assert _fila(conn, backfill_id)["estado"] == "ejecutando"


def test_stale_cuenta_dias_desde_el_ultimo_dato_de_ventas(conn, capsys):
    """
    La señal de atraso se mide sobre la frescura del DATO (MAX(fecha) de
    ventas_historicas), no sobre el bookkeeping del propio job: una noche
    salteada o un job que muere antes del merge dejan el dato viejo igual.
    """
    rc = cron_jobs.cmd_stale("-", "2")
    salida = capsys.readouterr().out.strip()

    with conn.cursor() as cur:
        cur.execute("SELECT MAX(fecha) FROM ventas_historicas")
        maxf = cur.fetchone()[0]
    atraso_real = (dt.date.today() - maxf).days

    assert str(atraso_real) in salida
    assert rc == (1 if atraso_real > 2 else 0)


def test_stale_con_job_id_guion_no_escribe_nada(conn):
    """job_id='-' es el modo sin persistencia (uso manual/legacy) -- read-only."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM jobs_historial")
        antes = cur.fetchone()[0]

    cron_jobs.cmd_stale("-", "2")

    conn.commit()  # refresca la vista de la transaccion
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM jobs_historial")
        assert cur.fetchone()[0] == antes


def test_stale_conexion_caida_no_propaga_excepcion(monkeypatch, capsys):
    """
    Hallazgo de /code-review: antes solo el UPDATE de guardado estaba
    protegido -- una caida de MySQL en la conexion o el SELECT principal
    tiraba un traceback sin manejar, pese a que el docstring ya prometia
    el mismo comportamiento no-bloqueante que `coherencia`.
    """
    def _explota_conexion():
        raise Exception("Can't connect to MySQL server")

    monkeypatch.setattr(cron_jobs, "db_connect", _explota_conexion)

    rc = cron_jobs.cmd_stale("-", "2")

    assert rc == 1
    assert "no se pudo conectar" in capsys.readouterr().err


def test_stale_con_job_id_guarda_atraso_en_detalle(conn, capsys):
    """
    Issue #132: antes el resultado de `stale` solo se imprimia a stdout,
    invisible fuera del log efimero de Docker, y no quedaba en
    jobs_historial. Con un job_id valido, el resultado queda en
    detalle.atraso (JSON_SET, mismo patron que `coherencia`).
    """
    cron_jobs.cmd_start()
    job_id = int(capsys.readouterr().out.strip())

    cron_jobs.cmd_stale(str(job_id), "2")

    fila = _fila(conn, job_id)
    assert "atraso_dias" in fila["detalle"]["atraso"]
    assert fila["detalle"]["atraso"]["umbral_dias"] == 2


def test_stale_sobrevive_al_end_posterior(conn, capsys):
    """
    Issue #132: `stale` corre ANTES de `end` a proposito (mide el atraso "al
    entrar a la noche"). Antes, `end` reemplazaba detalle entero y esto se
    hubiera perdido -- ahora `end` hace JSON_MERGE_PATCH, asi que sobrevive.
    """
    cron_jobs.cmd_start()
    job_id = int(capsys.readouterr().out.strip())

    cron_jobs.cmd_stale(str(job_id), "2")
    cron_jobs.cmd_end(str(job_id), "0", "12.0")

    fila = _fila(conn, job_id)
    assert "atraso" in fila["detalle"]
    assert fila["detalle"]["exit_code"] == 0
    assert fila["detalle"]["subtipo"] == "cron_diario"


# ---------------------------------------------------------------------------
# coherencia (Issue #115) -- ratio venta/caida-de-stock, la firma de #114.
#
# Fechas en 2030 y un SKU sintetico para no pisar datos reales de produccion
# (la DB local esta sincronizada de produccion, no es una tabla de scratch).
# ---------------------------------------------------------------------------

SKU_TEST = "TEST-COHERENCIA-115"


@pytest.fixture
def sku_articulo(conn):
    """Fila minima en articulos: ventas_historicas tiene FK a articulos(sku)."""
    with conn.cursor() as cur:
        # Idempotente por si una corrida anterior murio a mitad de camino
        # (mismo patron que test_run_calc_planilla.py).
        cur.execute("DELETE FROM ventas_historicas WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM stock_diario WHERE sku = %s", (SKU_TEST,))
        # Issue #121: articulo_grupo tiene FK RESTRICT a articulos(sku).
        cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM articulos WHERE sku = %s", (SKU_TEST,))
        cur.execute(
            "INSERT INTO articulos (sku, descripcion, grupo_id) VALUES (%s, %s, %s)",
            (SKU_TEST, "SKU de prueba -- issue #115, no es un articulo real", 201),
        )
    conn.commit()

    yield SKU_TEST

    with conn.cursor() as cur:
        cur.execute("DELETE FROM ventas_historicas WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM stock_diario WHERE sku = %s", (SKU_TEST,))
        # Issue #121: articulo_grupo tiene FK RESTRICT a articulos(sku).
        cur.execute("DELETE FROM articulo_grupo WHERE sku = %s", (SKU_TEST,))
        cur.execute("DELETE FROM articulos WHERE sku = %s", (SKU_TEST,))
    conn.commit()


def _cargar_stock(conn, sku, fecha, cantidad, deposito_id="D1"):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO stock_diario (sku, fecha, cantidad, deposito_id, fuente) "
            "VALUES (%s, %s, %s, %s, 'test')",
            (sku, fecha, cantidad, deposito_id),
        )
    conn.commit()


def _cargar_venta(conn, sku, fecha, cantidad):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ventas_historicas (sku, fecha, cantidad, fuente) VALUES (%s, %s, %s, 'test')",
            (sku, fecha, cantidad),
        )
    conn.commit()


def test_coherencia_caso_limpio_ratio_uno_no_marca_nada(conn, sku_articulo):
    """Stock cae 10, se vende 10: ratio 1.0, sano."""
    _cargar_stock(conn, sku_articulo, "2030-01-14", 100)
    _cargar_stock(conn, sku_articulo, "2030-01-15", 90)
    _cargar_venta(conn, sku_articulo, "2030-01-15", 10)

    resultado = cron_jobs._calcular_coherencia(conn, "2030-01-15", "2030-01-15")

    assert resultado["num_observaciones"] == 1
    assert resultado["num_anomalos"] == 0
    assert resultado["pct_anomalo"] == 0.0


def test_coherencia_caso_duplicado_ratio_dos_lo_marca(conn, sku_articulo):
    """La firma de #114: la venta registrada da el doble de la caida real de stock."""
    _cargar_stock(conn, sku_articulo, "2030-01-14", 100)
    _cargar_stock(conn, sku_articulo, "2030-01-15", 90)
    _cargar_venta(conn, sku_articulo, "2030-01-15", 20)  # 2x la caida (10)

    resultado = cron_jobs._calcular_coherencia(conn, "2030-01-15", "2030-01-15")

    assert resultado["num_observaciones"] == 1
    assert resultado["num_anomalos"] == 1
    assert resultado["pct_anomalo"] == 100.0


def test_coherencia_sin_caidas_de_stock_da_sin_observaciones(conn, sku_articulo):
    """
    Ningun dia con caida de stock en el rango (stock sube o se mantiene):
    no hay filas que comparar, no un ratio de 0 -- son cosas distintas.
    """
    _cargar_stock(conn, sku_articulo, "2030-02-14", 50)
    _cargar_stock(conn, sku_articulo, "2030-02-15", 60)  # sube, no baja
    _cargar_venta(conn, sku_articulo, "2030-02-15", 5)

    resultado = cron_jobs._calcular_coherencia(conn, "2030-02-15", "2030-02-15")

    assert resultado["num_observaciones"] == 0
    assert resultado["num_anomalos"] == 0
    assert resultado["pct_anomalo"] is None


def test_coherencia_rango_totalmente_vacio_da_sin_observaciones(conn):
    """Rango sin ninguna fila cargada -- caso trivial, no debe explotar."""
    resultado = cron_jobs._calcular_coherencia(conn, "2031-01-01", "2031-01-01")
    assert resultado["num_observaciones"] == 0
    assert resultado["pct_anomalo"] is None


def test_cmd_coherencia_guarda_bajo_detalle_coherencia_sin_pisar_lo_de_end(conn, sku_articulo, capsys):
    """
    coherencia corre despues de `end` en run_ofelia.sh -- tiene que fusionar
    (JSON_SET) en vez de reemplazar, o se perderia exit_code/duracion_seg.
    """
    cron_jobs.cmd_start()
    job_id = int(capsys.readouterr().out.strip())
    cron_jobs.cmd_end(str(job_id), "0", "42.0")
    capsys.readouterr()

    _cargar_stock(conn, sku_articulo, "2030-01-14", 100)
    _cargar_stock(conn, sku_articulo, "2030-01-15", 90)
    _cargar_venta(conn, sku_articulo, "2030-01-15", 20)

    rc = cron_jobs.cmd_coherencia(str(job_id), "2030-01-15", "2030-01-15")
    assert rc == 0

    fila = _fila(conn, job_id)
    assert fila["detalle"]["exit_code"] == 0  # lo que escribio `end` sigue ahi
    assert fila["detalle"]["duracion_seg"] == 42.0
    assert fila["detalle"]["coherencia"]["num_observaciones"] == 1
    assert fila["detalle"]["coherencia"]["pct_anomalo"] == 100.0


def test_cmd_coherencia_con_job_id_guion_no_escribe_nada(conn, sku_articulo, capsys):
    """job_id='-' es el modo manual (#115): correr sobre un rango arbitrario
    (ej. verificar la reparacion de #123) sin tocar jobs_historial."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM jobs_historial")
        antes = cur.fetchone()[0]

    _cargar_stock(conn, sku_articulo, "2030-01-14", 100)
    _cargar_stock(conn, sku_articulo, "2030-01-15", 90)
    _cargar_venta(conn, sku_articulo, "2030-01-15", 10)

    rc = cron_jobs.cmd_coherencia("-", "2030-01-15", "2030-01-15")
    assert rc == 0
    assert "0.0% anomalo" in capsys.readouterr().out

    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM jobs_historial")
        assert cur.fetchone()[0] == antes


def test_cmd_coherencia_default_sin_fechas_usa_ayer(conn, monkeypatch):
    """Sin fechas explicitas, mide el dia que el cron acaba de cargar (ayer)."""
    capturado = {}

    def _fake_calcular(conn_, desde, hasta):
        capturado["desde"] = desde
        capturado["hasta"] = hasta
        return {"fecha_desde": desde, "fecha_hasta": hasta,
                "num_observaciones": 0, "num_anomalos": 0, "pct_anomalo": None}

    monkeypatch.setattr(cron_jobs, "_calcular_coherencia", _fake_calcular)

    cron_jobs.cmd_coherencia("-")

    ayer = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    assert capturado["desde"] == ayer
    assert capturado["hasta"] == ayer


def test_cmd_coherencia_chequeo_roto_no_propaga_excepcion(conn, monkeypatch, capsys):
    """
    Criterio de aceptacion de #115: un chequeo caido (DB abajo, consulta
    rota) se loguea pero jamas debe interrumpir el ETL con una excepcion.
    """
    def _explota(conn_, desde, hasta):
        raise Exception("Table 'evalutia.stock_diario' doesn't exist")

    monkeypatch.setattr(cron_jobs, "_calcular_coherencia", _explota)

    rc = cron_jobs.cmd_coherencia("-", "2030-01-15", "2030-01-15")

    assert rc == 1
    assert "no bloquea el ETL" in capsys.readouterr().err


def test_cmd_coherencia_conexion_caida_no_propaga_excepcion(monkeypatch, capsys):
    """Mismo criterio, pero fallando un paso antes: ni siquiera conecta a MySQL."""
    def _explota_conexion():
        raise Exception("Can't connect to MySQL server")

    monkeypatch.setattr(cron_jobs, "db_connect", _explota_conexion)

    rc = cron_jobs.cmd_coherencia("-", "2030-01-15", "2030-01-15")

    assert rc == 1
    assert "no se pudo conectar" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# stock_gaps (Issue #133) -- huecos de stock que NO se pueden recuperar
# (a diferencia de ventas), deben quedar visibles.
# ---------------------------------------------------------------------------

def test_stock_gaps_sin_huecos_cuando_todos_los_dias_tienen_dato(conn, sku_articulo):
    _cargar_stock(conn, sku_articulo, "2030-03-10", 10)
    _cargar_stock(conn, sku_articulo, "2030-03-11", 9)
    _cargar_stock(conn, sku_articulo, "2030-03-12", 8)

    resultado = cron_jobs._calcular_stock_gaps(conn, "2030-03-10", "2030-03-12")

    assert resultado["num_dias_sin_datos"] == 0
    assert resultado["dias_sin_datos"] == []


def test_stock_gaps_detecta_el_dia_del_medio_faltante(conn, sku_articulo):
    """La firma real de #133: 2026-08-10 sin ninguna fila tras el cron caido del 11."""
    _cargar_stock(conn, sku_articulo, "2030-03-10", 10)
    # 2030-03-11 -- sin cargar, el hueco
    _cargar_stock(conn, sku_articulo, "2030-03-12", 8)

    resultado = cron_jobs._calcular_stock_gaps(conn, "2030-03-10", "2030-03-12")

    assert resultado["num_dias_sin_datos"] == 1
    assert resultado["dias_sin_datos"] == ["2030-03-11"]


def test_stock_gaps_varios_skus_un_solo_dia_no_cuenta_como_hueco(conn, sku_articulo):
    """Alcanza con que UN sku tenga dato ese dia -- la pregunta es sobre la
    tabla completa, no sobre un sku puntual."""
    _cargar_stock(conn, sku_articulo, "2030-03-15", 5)

    resultado = cron_jobs._calcular_stock_gaps(conn, "2030-03-15", "2030-03-15")

    assert resultado["num_dias_sin_datos"] == 0


def test_stock_gaps_rango_totalmente_vacio_marca_todos_los_dias(conn):
    resultado = cron_jobs._calcular_stock_gaps(conn, "2031-02-01", "2031-02-03")

    assert resultado["num_dias_sin_datos"] == 3
    assert resultado["dias_sin_datos"] == ["2031-02-01", "2031-02-02", "2031-02-03"]


def test_cmd_stock_gaps_guarda_bajo_detalle_stock_gaps_sin_pisar_lo_de_end(conn, sku_articulo, capsys):
    cron_jobs.cmd_start()
    job_id = int(capsys.readouterr().out.strip())
    cron_jobs.cmd_end(str(job_id), "0", "42.0")
    capsys.readouterr()

    _cargar_stock(conn, sku_articulo, "2030-03-10", 10)
    # 2030-03-11 sin cargar

    rc = cron_jobs.cmd_stock_gaps(str(job_id), "2030-03-10", "2030-03-11")
    assert rc == 0

    fila = _fila(conn, job_id)
    assert fila["detalle"]["exit_code"] == 0  # lo que escribio `end` sigue ahi
    assert fila["detalle"]["stock_gaps"]["num_dias_sin_datos"] == 1
    assert fila["detalle"]["stock_gaps"]["dias_sin_datos"] == ["2030-03-11"]


def test_cmd_stock_gaps_con_job_id_guion_no_escribe_nada(conn, sku_articulo, capsys):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM jobs_historial")
        antes = cur.fetchone()[0]

    rc = cron_jobs.cmd_stock_gaps("-", "2030-03-20", "2030-03-20")
    assert rc == 0
    assert "1 dia(s) sin ningun dato de stock" in capsys.readouterr().out

    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM jobs_historial")
        assert cur.fetchone()[0] == antes


def test_cmd_stock_gaps_default_sin_fechas_usa_ventana_de_7_dias(conn, monkeypatch):
    """Misma ventana que la recuperacion de ventas -- no solo ayer, como coherencia."""
    capturado = {}

    def _fake_calcular(conn_, desde, hasta):
        capturado["desde"] = desde
        capturado["hasta"] = hasta
        return {"fecha_desde": desde, "fecha_hasta": hasta,
                "dias_sin_datos": [], "num_dias_sin_datos": 0,
                "depositos_esperados": [], "dias_con_depositos_faltantes": [],
                "num_dias_con_depositos_faltantes": 0}

    monkeypatch.setattr(cron_jobs, "_calcular_stock_gaps", _fake_calcular)

    cron_jobs.cmd_stock_gaps("-")

    ayer = dt.date.today() - dt.timedelta(days=1)
    hace_7 = ayer - dt.timedelta(days=6)
    assert capturado["hasta"] == ayer.isoformat()
    assert capturado["desde"] == hace_7.isoformat()


def test_cmd_stock_gaps_con_solo_fecha_desde_se_acota_a_ese_unico_dia(conn, monkeypatch):
    """
    Code review de #133: la version original ignoraba fecha_desde en este
    caso (setState fecha_hasta="ayer" igual, corriendo sobre una ventana
    distinta a la pedida en silencio). Mismo criterio que cmd_coherencia:
    con un solo argumento de fecha, se acota a ese unico dia.
    """
    capturado = {}

    def _fake_calcular(conn_, desde, hasta):
        capturado["desde"] = desde
        capturado["hasta"] = hasta
        return {"fecha_desde": desde, "fecha_hasta": hasta,
                "dias_sin_datos": [], "num_dias_sin_datos": 0,
                "depositos_esperados": [], "dias_con_depositos_faltantes": [],
                "num_dias_con_depositos_faltantes": 0}

    monkeypatch.setattr(cron_jobs, "_calcular_stock_gaps", _fake_calcular)

    cron_jobs.cmd_stock_gaps("-", "2030-05-10")

    assert capturado["desde"] == "2030-05-10"
    assert capturado["hasta"] == "2030-05-10"


def test_cmd_stock_gaps_chequeo_roto_no_propaga_excepcion(conn, monkeypatch, capsys):
    def _explota(conn_, desde, hasta):
        raise Exception("Table 'evalutia.stock_diario' doesn't exist")

    monkeypatch.setattr(cron_jobs, "_calcular_stock_gaps", _explota)

    rc = cron_jobs.cmd_stock_gaps("-", "2030-01-15", "2030-01-15")

    assert rc == 1
    assert "no bloquea el ETL" in capsys.readouterr().err


def test_cmd_stock_gaps_conexion_caida_no_propaga_excepcion(monkeypatch, capsys):
    def _explota_conexion():
        raise Exception("Can't connect to MySQL server")

    monkeypatch.setattr(cron_jobs, "db_connect", _explota_conexion)

    rc = cron_jobs.cmd_stock_gaps("-", "2030-01-15", "2030-01-15")

    assert rc == 1
    assert "no se pudo conectar" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# stock_gaps por deposito (Issue #155) -- hueco PARCIAL: la fecha tiene
# filas (algun deposito escribio), pero no todos los depositos configurados
# lo hicieron. _calcular_stock_gaps (#133) es ciego a esto: solo mira
# presencia/ausencia de fecha, nunca agrupa por deposito_id.
# ---------------------------------------------------------------------------

def test_depositos_esperados_desde_env_lee_s_depositos_separado_por_coma(monkeypatch):
    monkeypatch.setenv("S_DEPOSITOS", "1,5,8,9,10,11")
    assert cron_jobs._depositos_esperados_desde_env() == ["1", "10", "11", "5", "8", "9"]


def test_depositos_esperados_desde_env_ignora_espacios_y_tokens_vacios(monkeypatch):
    """Mismo criterio de parseo que run_extract_stockxml.sh (coma, trim por token)."""
    monkeypatch.setenv("S_DEPOSITOS", " 1, 5,,8 ,9,10,11 ")
    assert cron_jobs._depositos_esperados_desde_env() == ["1", "10", "11", "5", "8", "9"]


def test_depositos_esperados_desde_env_no_seteada_devuelve_vacio(monkeypatch):
    monkeypatch.delenv("S_DEPOSITOS", raising=False)
    assert cron_jobs._depositos_esperados_desde_env() == []


def test_stock_gaps_detecta_deposito_faltante_con_parametro_explicito(conn, sku_articulo):
    """Firma real de #155: D2 no escribe el 2030-04-10, D1 si -- la fecha
    'tiene datos' pero esta incompleta."""
    _cargar_stock(conn, sku_articulo, "2030-04-10", 10, deposito_id="D1")
    # D2 -- sin cargar ese dia, el hueco parcial

    resultado = cron_jobs._calcular_stock_gaps(
        conn, "2030-04-10", "2030-04-10", depositos_esperados=["D1", "D2"]
    )

    assert resultado["num_dias_sin_datos"] == 0  # la fecha SI tiene filas
    assert resultado["num_dias_con_depositos_faltantes"] == 1
    assert resultado["dias_con_depositos_faltantes"] == [
        {"fecha": "2030-04-10", "depositos_faltantes": ["D2"]}
    ]


def test_stock_gaps_sin_faltantes_cuando_todos_los_depositos_escriben(conn, sku_articulo):
    _cargar_stock(conn, sku_articulo, "2030-04-11", 10, deposito_id="D1")
    _cargar_stock(conn, sku_articulo, "2030-04-11", 7, deposito_id="D2")

    resultado = cron_jobs._calcular_stock_gaps(
        conn, "2030-04-11", "2030-04-11", depositos_esperados=["D1", "D2"]
    )

    assert resultado["num_dias_con_depositos_faltantes"] == 0
    assert resultado["dias_con_depositos_faltantes"] == []


def test_stock_gaps_dia_totalmente_vacio_no_duplica_en_depositos_faltantes(conn, sku_articulo):
    """
    Issue #155 AC: el hueco parcial es ADEMAS del hueco total que ya cubre
    #133, no un duplicado -- un dia sin NINGUNA fila ya queda en
    dias_sin_datos y no debe reaparecer en dias_con_depositos_faltantes.
    """
    _cargar_stock(conn, sku_articulo, "2030-04-12", 10, deposito_id="D1")
    _cargar_stock(conn, sku_articulo, "2030-04-12", 7, deposito_id="D2")
    # 2030-04-13 -- ninguna fila, hueco TOTAL (no parcial)

    resultado = cron_jobs._calcular_stock_gaps(
        conn, "2030-04-12", "2030-04-13", depositos_esperados=["D1", "D2"]
    )

    assert resultado["dias_sin_datos"] == ["2030-04-13"]
    assert resultado["num_dias_con_depositos_faltantes"] == 0
    assert resultado["dias_con_depositos_faltantes"] == []


def test_stock_gaps_sin_depositos_esperados_no_rompe(conn, sku_articulo, monkeypatch):
    """
    S_DEPOSITOS sin configurar (dev/manual) no debe romper el chequeo de
    huecos totales que ya funcionaba -- el chequeo por deposito simplemente
    no corre (no hay contra que comparar).
    """
    monkeypatch.delenv("S_DEPOSITOS", raising=False)
    _cargar_stock(conn, sku_articulo, "2030-04-14", 10, deposito_id="D1")

    resultado = cron_jobs._calcular_stock_gaps(conn, "2030-04-14", "2030-04-14")

    assert resultado["depositos_esperados"] == []
    assert resultado["num_dias_con_depositos_faltantes"] == 0
    assert resultado["dias_con_depositos_faltantes"] == []


def test_stock_gaps_depositos_esperados_por_defecto_sale_de_env(conn, sku_articulo, monkeypatch):
    """AC #155: la cantidad esperada de depositos no queda hardcodeada --
    sale de S_DEPOSITOS (Issue #139)."""
    monkeypatch.setenv("S_DEPOSITOS", "D1,D2")
    _cargar_stock(conn, sku_articulo, "2030-04-15", 10, deposito_id="D1")
    # D2 -- sin cargar, el hueco parcial

    resultado = cron_jobs._calcular_stock_gaps(conn, "2030-04-15", "2030-04-15")

    assert resultado["depositos_esperados"] == ["D1", "D2"]
    assert resultado["dias_con_depositos_faltantes"] == [
        {"fecha": "2030-04-15", "depositos_faltantes": ["D2"]}
    ]


def test_cmd_stock_gaps_guarda_depositos_faltantes_bajo_detalle_stock_gaps(
    conn, sku_articulo, monkeypatch, capsys
):
    monkeypatch.setenv("S_DEPOSITOS", "D1,D2")
    cron_jobs.cmd_start()
    job_id = int(capsys.readouterr().out.strip())
    cron_jobs.cmd_end(str(job_id), "0", "12.0")
    capsys.readouterr()

    _cargar_stock(conn, sku_articulo, "2030-04-16", 10, deposito_id="D1")
    # D2 -- sin cargar, el hueco parcial

    rc = cron_jobs.cmd_stock_gaps(str(job_id), "2030-04-16", "2030-04-16")
    assert rc == 0

    fila = _fila(conn, job_id)
    assert fila["detalle"]["stock_gaps"]["num_dias_con_depositos_faltantes"] == 1
    assert fila["detalle"]["stock_gaps"]["dias_con_depositos_faltantes"] == [
        {"fecha": "2030-04-16", "depositos_faltantes": ["D2"]}
    ]

    salida = capsys.readouterr().out
    assert "PARCIAL" in salida
    assert "D2" in salida


def test_cmd_stock_gaps_sin_depositos_faltantes_no_menciona_parcial(
    conn, sku_articulo, monkeypatch, capsys
):
    monkeypatch.setenv("S_DEPOSITOS", "D1")
    _cargar_stock(conn, sku_articulo, "2030-04-17", 10, deposito_id="D1")

    rc = cron_jobs.cmd_stock_gaps("-", "2030-04-17", "2030-04-17")
    assert rc == 0

    salida = capsys.readouterr().out
    assert "PARCIAL" not in salida


# ---------------------------------------------------------------------------
# end (Issue #132) -- merge del detalle, no reemplazo.
# ---------------------------------------------------------------------------

def test_end_hace_merge_no_pisa_lo_que_ya_habia_en_detalle(conn, capsys):
    """
    Antes `end` reemplazaba detalle entero -- cualquier cosa escrita antes
    (ej. por `stale`) se perdia sin dejar rastro. Ahora usa JSON_MERGE_PATCH.
    """
    cron_jobs.cmd_start()
    job_id = int(capsys.readouterr().out.strip())

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs_historial SET detalle = JSON_SET(detalle, '$.marca_previa', 'seguia-aca') "
            "WHERE id = %s", (job_id,),
        )
    conn.commit()

    cron_jobs.cmd_end(str(job_id), "0", "5.0")

    fila = _fila(conn, job_id)
    assert fila["detalle"]["marca_previa"] == "seguia-aca"
    assert fila["detalle"]["exit_code"] == 0


# ---------------------------------------------------------------------------
# abort (Issue #132) -- fallo previo a `start`.
# ---------------------------------------------------------------------------

def test_abort_inserta_fila_terminal_fallido_con_motivo(conn, capsys):
    """
    El caso del 2026-08-11: run_ofelia.sh aborto antes de poder llamar a
    `start` (lock_backfill.sh faltante) y no quedo ninguna fila en
    jobs_historial -- la unica huella fue el log efimero de Docker.
    """
    rc = cron_jobs.cmd_abort("no encuentro /app/services/etl/lock_backfill.sh")
    assert rc == 0
    job_id = int(capsys.readouterr().out.strip())

    fila = _fila(conn, job_id)
    assert fila["tipo_job"] == "etl"
    assert fila["estado"] == "fallido"
    assert fila["fecha_fin"] is not None
    assert fila["detalle"]["resultado"] == "abortado_temprano"
    assert "lock_backfill.sh" in fila["detalle"]["motivo"]
    assert fila["detalle"]["subtipo"] == "cron_diario"


# ---------------------------------------------------------------------------
# mark_step_failed (Issue #131) -- auditoria de un paso "marca y sigue".
# ---------------------------------------------------------------------------

def test_mark_step_failed_inserta_fila_terminal_fallido_con_paso_y_motivo(conn, capsys):
    rc = cron_jobs.cmd_mark_step_failed("RUN CALC_PLANILLA", "codigo de salida 1")
    assert rc == 0
    job_id = int(capsys.readouterr().out.strip())

    fila = _fila(conn, job_id)
    assert fila["tipo_job"] == "etl"
    assert fila["estado"] == "fallido"
    assert fila["fecha_fin"] is not None
    assert fila["detalle"]["resultado"] == "paso_fallido"
    assert fila["detalle"]["paso"] == "RUN CALC_PLANILLA"
    assert fila["detalle"]["motivo"] == "codigo de salida 1"


# ---------------------------------------------------------------------------
# last_run (Issue #132) -- heartbeat del propio cron, no del dato.
# ---------------------------------------------------------------------------

def test_last_run_sin_corridas_previas_da_fallo(conn, monkeypatch):
    """Tabla vacia (de subtipo cron_diario): no se puede afirmar que el cron corrio."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM jobs_historial WHERE detalle->>'$.subtipo' = 'cron_diario'")
    conn.commit()

    assert cron_jobs.cmd_last_run() == 1


def test_last_run_corrida_reciente_da_ok(conn, capsys):
    cron_jobs.cmd_start()
    capsys.readouterr()

    assert cron_jobs.cmd_last_run("30") == 0


def test_last_run_no_se_desfasa_por_husos_horarios(conn, capsys):
    """
    Regresion: fecha_inicio es TIMESTAMP y MySQL lo devuelve en el time_zone
    de LA SESION (el contenedor de mysql corre en America/Montevideo,
    UTC-3) -- comparar eso contra dt.utcnow() sin convertir a UTC primero
    infla el resultado en ~3h. Un umbral ajustado (1h) sobre una fila recien
    insertada detecta el sesgo: con el bug, "horas" daba ~3 en vez de ~0.
    """
    cron_jobs.cmd_start()
    capsys.readouterr()

    assert cron_jobs.cmd_last_run("1") == 0


def test_last_run_corrida_vieja_supera_umbral(conn, capsys):
    """
    Cuenta cualquier estado -- un intento fallido/abortado todavia demuestra
    que el cron corrio; lo que importa es la fecha, no el resultado.
    """
    cron_jobs.cmd_start()
    job_id = int(capsys.readouterr().out.strip())
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs_historial SET fecha_inicio = NOW(6) - INTERVAL 3 DAY WHERE id = %s",
            (job_id,),
        )
    conn.commit()

    assert cron_jobs.cmd_last_run("30") == 1


def test_last_run_umbral_por_defecto_es_generoso(conn, capsys):
    """No debe dispararse por una corrida que arranco un poco mas tarde de lo usual."""
    cron_jobs.cmd_start()
    capsys.readouterr()
    assert cron_jobs.cmd_last_run() == 0
