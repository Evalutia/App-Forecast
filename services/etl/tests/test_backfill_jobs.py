import json
import os

import pytest

import backfill_jobs
from backfill_jobs import cmd_check


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
    import sys

    old_argv = sys.argv
    try:
        sys.argv = ["backfill_jobs.py", "check", "42"]
        rc = backfill_jobs.main()
        assert rc == 2, "con solo grupo_id (sin fechas) main() debe rechazar el comando"
    finally:
        sys.argv = old_argv
