import io
import json
import os
import sys

import pytest

import backfill_jobs
from backfill_jobs import cmd_check, cmd_end, cmd_start


def _try_connect():
    """
    Conexion real a MySQL para los tests de cmd_check -- se salta con
    pytest.skip si no hay DB disponible (CI no levanta MySQL para
    services/etl/tests, ver .github/workflows/ci.yml). Mismo patron que
    test_run_calc_planilla.py.
    """
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


def _insertar_corrida_exitosa(conn, grupo_id, fecha_desde, fecha_hasta):
    detalle = {
        "subtipo": "backfill_ventas",
        "grupo_id": str(grupo_id),
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
    }
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs_historial (tipo_job, estado, fecha_inicio, fecha_fin, detalle) "
            "VALUES ('backfill', 'exitoso', NOW(6), NOW(6), %s)",
            (json.dumps(detalle, ensure_ascii=False),),
        )
    conn.commit()


def _limpiar(conn, grupo_id):
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM jobs_historial WHERE tipo_job = 'backfill' "
            "  AND detalle->>'$.grupo_id' = %s",
            (str(grupo_id),),
        )
    conn.commit()


def _insertar_job_con_detalle(conn, estado, detalle):
    """Fila 'ejecutando' (o el estado que sea) con un detalle ya escrito,
    simulando un chequeo hipotetico que corrio antes del `end` -- el mismo
    escenario que #132 cubrio para cron_jobs.py con `stale`."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs_historial (tipo_job, estado, fecha_inicio, detalle) "
            "VALUES ('backfill', %s, NOW(6), %s)",
            (estado, json.dumps(detalle, ensure_ascii=False)),
        )
        job_id = cur.lastrowid
    conn.commit()
    return job_id


def _leer_fila(conn, job_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT estado, fecha_fin, detalle FROM jobs_historial WHERE id = %s",
            (job_id,),
        )
        row = cur.fetchone()
    return None if row is None else {
        "estado": row[0], "fecha_fin": row[1],
        "detalle": json.loads(row[2]) if row[2] else {},
    }


# ── cmd_check(): Issue #104 -- ahora compara tambien fecha_desde/fecha_hasta ──
# Bug original: solo comparaba grupo_id, asi que una corrida nueva con un
# rango de fechas distinto (ej. el backfill de 10 anios vs. el de 2 anios de
# #44) se salteaba en silencio por encontrar la corrida vieja del grupo.

def test_mismo_grupo_y_mismo_rango_ya_completo(capsys):
    conn = _try_connect()
    grupo = "TEST104A"
    try:
        _limpiar(conn, grupo)
        _insertar_corrida_exitosa(conn, grupo, "2016-10-03", "2024-06-30")

        cmd_check(grupo, "2016-10-03", "2024-06-30")

        assert capsys.readouterr().out.strip() == "1"
    finally:
        _limpiar(conn, grupo)
        conn.close()


def test_mismo_grupo_pero_rango_distinto_no_esta_completo(capsys):
    """Caso central del bug de #104: la corrida vieja de #44 (2 anios) no
    debe contar como 'ya hecho' para el backfill nuevo de 10 anios."""
    conn = _try_connect()
    grupo = "TEST104B"
    try:
        _limpiar(conn, grupo)
        _insertar_corrida_exitosa(conn, grupo, "2024-06-25", "2026-06-25")

        cmd_check(grupo, "2016-10-03", "2024-06-30")

        assert capsys.readouterr().out.strip() == "0"
    finally:
        _limpiar(conn, grupo)
        conn.close()


def test_grupo_sin_ninguna_corrida_no_esta_completo(capsys):
    conn = _try_connect()
    grupo = "TEST104C"
    try:
        _limpiar(conn, grupo)

        cmd_check(grupo, "2016-10-03", "2024-06-30")

        assert capsys.readouterr().out.strip() == "0"
    finally:
        _limpiar(conn, grupo)
        conn.close()


def test_solo_fecha_hasta_distinta_no_esta_completo(capsys):
    conn = _try_connect()
    grupo = "TEST104D"
    try:
        _limpiar(conn, grupo)
        _insertar_corrida_exitosa(conn, grupo, "2016-10-03", "2024-06-25")

        cmd_check(grupo, "2016-10-03", "2024-06-30")

        assert capsys.readouterr().out.strip() == "0"
    finally:
        _limpiar(conn, grupo)
        conn.close()


def test_main_dispatch_check_exige_tres_argumentos():
    """El bug original tomaba `check <grupo_id>` (1 arg). El fix agrega
    fecha_desde/fecha_hasta al dispatch de main(), no solo a cmd_check."""
    old_argv = sys.argv
    try:
        sys.argv = ["backfill_jobs.py", "check", "42"]
        rc = backfill_jobs.main()
        assert rc == 2, "con solo grupo_id (sin fechas) main() debe rechazar el comando"
    finally:
        sys.argv = old_argv


# ── cmd_end(): Issue #184 -- JSON_MERGE_PATCH en vez de reemplazo de detalle,
# mismo defecto que #132 ya corrigio en cron_jobs.py. Ademas, estado invalido
# se rechaza antes de tocar la DB en vez de dejar que MySQL lo rechace con un
# error opaco de ENUM. ──

def test_end_estado_invalido_rechaza_sin_tocar_la_db(capsys):
    """La validacion corre antes de db_connect() -- no necesita MySQL
    disponible para fallar limpio."""
    rc = cmd_end("1", "no-es-un-estado", "TEST184X", "2024-01-01", "2024-01-31", "1.0")

    assert rc != 0
    err = capsys.readouterr().err
    assert "[ERROR]" in err
    assert "no-es-un-estado" in err


def test_end_hace_merge_no_pisa_detalle_previo(monkeypatch):
    """Caso central de #184, calcado de test_stale_sobrevive_al_end_posterior
    en test_cron_jobs.py: un detalle escrito ANTES de `end` (ej. por un
    chequeo hipotetico que corriera antes del cierre) debe sobrevivir al
    UPDATE de `end`, en vez de perderse por un reemplazo directo."""
    conn = _try_connect()
    grupo = "TEST184A"
    try:
        _limpiar(conn, grupo)
        detalle_previo = {
            "subtipo": "backfill_ventas",
            "grupo_id": grupo,
            "chequeo_previo": {"algo": "valor"},
        }
        job_id = _insertar_job_con_detalle(conn, "ejecutando", detalle_previo)

        monkeypatch.setattr(sys, "stdin", io.StringIO("dep=5 rango=x rc=10\n"))
        rc = cmd_end(str(job_id), "exitoso", grupo, "2024-01-01", "2024-01-31", "12.5")

        assert rc == 0
        fila = _leer_fila(conn, job_id)
        assert fila["estado"] == "exitoso"
        assert fila["fecha_fin"] is not None
        # Lo que ya estaba en detalle antes de `end` sigue ahi.
        assert fila["detalle"]["chequeo_previo"] == {"algo": "valor"}
        # Y lo que `end` agrega tambien esta.
        assert fila["detalle"]["duracion_seg"] == 12.5
        assert fila["detalle"]["grupo_id"] == grupo
        assert fila["detalle"]["chunks_fallidos"] == ["dep=5 rango=x rc=10"]
    finally:
        _limpiar(conn, grupo)
        conn.close()


# ── SUBTIPO configurable (Issue #186): la corrida de comparacion no debe ──────
# confundirse con el backfill real, ni al revés -- cada una lleva su propio
# rastro de resumibilidad en jobs_historial pese a compartir grupo/rango.

def test_corrida_de_comparacion_no_cuenta_como_backfill_ventas_completo(capsys, monkeypatch):
    conn = _try_connect()
    grupo = "TEST186A"
    try:
        _limpiar(conn, grupo)
        monkeypatch.setattr(backfill_jobs, "SUBTIPO", "backfill_comparacion")
        _insertar_corrida_exitosa(conn, grupo, "2024-08-01", "2026-08-01")  # subtipo real hardcodeado en el helper

        # El check corre con SUBTIPO parcheado a backfill_comparacion -- la
        # corrida de backfill_ventas ya completa no debe contar como "hecho"
        # para un subtipo distinto.
        cmd_check(grupo, "2024-08-01", "2026-08-01")

        assert capsys.readouterr().out.strip() == "0"
    finally:
        _limpiar(conn, grupo)
        conn.close()


def test_corrida_de_backfill_ventas_no_cuenta_como_comparacion_completa(capsys, monkeypatch):
    """Misma garantia en la direccion opuesta: si backfill_comparacion ya
    completo un grupo/rango, eso no debe hacer que backfill_ventas lo
    saltee -- son ciclos de vida independientes."""
    conn = _try_connect()
    grupo = "TEST186B"
    try:
        _limpiar(conn, grupo)
        monkeypatch.setattr(backfill_jobs, "SUBTIPO", "backfill_comparacion")
        cmd_start(grupo, "2024-08-01", "2026-08-01")
        job_id = capsys.readouterr().out.strip()
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        cmd_end(job_id, "exitoso", grupo, "2024-08-01", "2026-08-01", "10.0")

        monkeypatch.setattr(backfill_jobs, "SUBTIPO", "backfill_ventas")
        cmd_check(grupo, "2024-08-01", "2026-08-01")

        assert capsys.readouterr().out.strip() == "0"
    finally:
        _limpiar(conn, grupo)
        conn.close()


def test_comparacion_resumible_dentro_de_su_propio_subtipo(capsys, monkeypatch):
    """El caso positivo: dentro del MISMO subtipo, check/start/end siguen
    dando resumibilidad -- #186 no rompe lo que #104 ya garantizaba, solo lo
    aisla por subtipo."""
    conn = _try_connect()
    grupo = "TEST186C"
    try:
        _limpiar(conn, grupo)
        monkeypatch.setattr(backfill_jobs, "SUBTIPO", "backfill_comparacion")

        cmd_start(grupo, "2024-08-01", "2026-08-01")
        job_id = capsys.readouterr().out.strip()
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        cmd_end(job_id, "exitoso", grupo, "2024-08-01", "2026-08-01", "5.0")

        cmd_check(grupo, "2024-08-01", "2026-08-01")

        assert capsys.readouterr().out.strip() == "1"
        fila = _leer_fila(conn, int(job_id))
        assert fila["detalle"]["subtipo"] == "backfill_comparacion"
    finally:
        _limpiar(conn, grupo)
        conn.close()
