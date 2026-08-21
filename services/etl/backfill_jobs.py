#!/usr/bin/env python3
"""
backfill_jobs.py - Bookkeeping en jobs_historial para el backfill historico
de ventas (Issue #44). Un registro por grupo (tipo_job='backfill',
detalle.subtipo='backfill_ventas'), no un estado global para los ~65 grupos.

Subcomandos:
  check <grupo_id> <fecha_desde> <fecha_hasta>
      Imprime "1" si ese grupo ya tiene una corrida 'exitoso' registrada
      para ESE MISMO rango de fechas (permite resumir sin re-extraer grupos
      ya completos), "0" si no -- un grupo completado con un rango distinto
      (ej. el backfill de 2 anios de #44) no cuenta como hecho para un
      rango nuevo (#104).

  start <grupo_id> <fecha_desde> <fecha_hasta>
      Inserta una fila 'ejecutando' y imprime el job_id (lastrowid).

  end <job_id> <estado> <grupo_id> <fecha_desde> <fecha_hasta> <duracion_seg>
      Actualiza la fila a estado ('exitoso'|'fallido'), fecha_fin y detalle.
      Rechaza (rc != 0) un <estado> fuera del ENUM de jobs_historial.estado
      antes de tocar la DB (ver ESTADOS_VALIDOS). Lee de stdin (opcional)
      una lista de fallas, una por linea de texto libre (ej. "dep=5
      rango=2024-01-01..2024-01-30 rc=10"); se guardan en
      detalle.chunks_fallidos como array. Sin stdin -> array vacio.
"""

import json
import os
import sys
import pymysql

SUBTIPO = "backfill_ventas"

# Valores validos de jobs_historial.estado (infra/sql/02-tablas.sql +
# infra/sql/22-jobs-historial-estado-omitido.sql). cmd_end los valida antes
# del UPDATE para fallar con un mensaje claro en vez de dejar que MySQL
# rechace el ENUM con un error opaco (Issue #184).
ESTADOS_VALIDOS = {"en_cola", "ejecutando", "exitoso", "fallido", "omitido"}

def db_connect():
    return pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DB"],
        autocommit=False,
        charset="utf8mb4",
    )

def cmd_check(grupo_id: str, fecha_desde: str, fecha_hasta: str) -> int:
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM jobs_historial "
                " WHERE tipo_job = 'backfill' AND estado = 'exitoso' "
                "   AND detalle->>'$.subtipo' = %s "
                "   AND detalle->>'$.grupo_id' = %s "
                "   AND detalle->>'$.fecha_desde' = %s "
                "   AND detalle->>'$.fecha_hasta' = %s "
                " LIMIT 1",
                (SUBTIPO, str(grupo_id), fecha_desde, fecha_hasta),
            )
            print("1" if cur.fetchone() else "0")
    finally:
        conn.close()
    return 0

def cmd_start(grupo_id: str, fecha_desde: str, fecha_hasta: str) -> int:
    conn = db_connect()
    try:
        detalle = {
            "subtipo": SUBTIPO,
            "grupo_id": str(grupo_id),
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
        }
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO jobs_historial (tipo_job, estado, fecha_inicio, detalle) "
                "VALUES ('backfill', 'ejecutando', NOW(6), %s)",
                (json.dumps(detalle, ensure_ascii=False),),
            )
            job_id = cur.lastrowid
        conn.commit()
        print(job_id)
    finally:
        conn.close()
    return 0

def cmd_end(job_id: str, estado: str, grupo_id: str, fecha_desde: str, fecha_hasta: str, duracion_seg: str) -> int:
    if estado not in ESTADOS_VALIDOS:
        print(
            f"[ERROR] estado invalido: {estado!r} (validos: {sorted(ESTADOS_VALIDOS)})",
            file=sys.stderr,
        )
        return 2
    fallas = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
    # subtipo/grupo_id/fecha_desde/fecha_hasta ya quedaron en detalle desde
    # `start` y el merge de abajo no los toca -- se re-envian igual (a
    # diferencia de cron_jobs.py cmd_end, que solo agrega claves nuevas) para
    # que un job_id/grupo_id desalineado entre `start` y `end` se note en el
    # dato final en vez de quedar enmascarado por el merge.
    detalle = {
        "subtipo": SUBTIPO,
        "grupo_id": str(grupo_id),
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "duracion_seg": float(duracion_seg),
        "chunks_fallidos": fallas,
    }
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            # Issue #184: JSON_MERGE_PATCH en vez de un simple %s -- mismo
            # patron que #132 ya aplico en cron_jobs.py. Hoy nada escribe en
            # detalle de un job de backfill antes de este `end`, pero un
            # reemplazo directo es un landmine para el primer chequeo futuro
            # que quiera dejar algo ahi antes del cierre.
            cur.execute(
                "UPDATE jobs_historial "
                "   SET estado = %s, fecha_fin = NOW(6), "
                "       detalle = JSON_MERGE_PATCH(COALESCE(detalle, JSON_OBJECT()), CAST(%s AS JSON)) "
                " WHERE id = %s",
                (estado, json.dumps(detalle, ensure_ascii=False), job_id),
            )
        conn.commit()
    finally:
        conn.close()
    return 0

def main() -> int:
    if len(sys.argv) < 2:
        print("[ERROR] Uso: backfill_jobs.py check|start|end ...", file=sys.stderr)
        return 2
    sub = sys.argv[1]
    args = sys.argv[2:]
    if sub == "check" and len(args) == 3:
        return cmd_check(*args)
    if sub == "start" and len(args) == 3:
        return cmd_start(*args)
    if sub == "end" and len(args) == 6:
        return cmd_end(*args)
    print(f"[ERROR] Subcomando/args invalidos: {sys.argv[1:]}", file=sys.stderr)
    return 2

if __name__ == "__main__":
    sys.exit(main())
