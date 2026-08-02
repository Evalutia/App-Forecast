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
