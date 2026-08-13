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
    assert fila["estado"] in ("exitoso", "fallido")
    assert fila["estado"] != "ejecutando"
    assert fila["fecha_fin"] is not None
    assert fila["detalle"]["resultado"] == "omitido"
    assert "backfill" in fila["detalle"]["motivo"]


def test_estado_usa_solo_valores_del_enum(conn, capsys):
    """
    jobs_historial.estado es ENUM('en_cola','ejecutando','exitoso','fallido').
    Un valor fuera del ENUM lo rechaza MySQL en runtime (o lo trunca a ''),
    asi que ningun camino puede inventar estados nuevos sin migracion.
    """
    validos = {"en_cola", "ejecutando", "exitoso", "fallido"}

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
    rc = cron_jobs.cmd_stale("2")
    salida = capsys.readouterr().out.strip()

    with conn.cursor() as cur:
        cur.execute("SELECT MAX(fecha) FROM ventas_historicas")
        maxf = cur.fetchone()[0]
    atraso_real = (dt.date.today() - maxf).days

    assert str(atraso_real) in salida
    assert rc == (1 if atraso_real > 2 else 0)


def test_stale_no_escribe_nada(conn):
    """El chequeo de atraso es read-only: no puede ensuciar jobs_historial."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM jobs_historial")
        antes = cur.fetchone()[0]

    cron_jobs.cmd_stale("2")

    conn.commit()  # refresca la vista de la transaccion
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM jobs_historial")
        assert cur.fetchone()[0] == antes


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


def _cargar_stock(conn, sku, fecha, cantidad):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO stock_diario (sku, fecha, cantidad, deposito_id, fuente) "
            "VALUES (%s, %s, %s, 'D1', 'test')",
            (sku, fecha, cantidad),
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
