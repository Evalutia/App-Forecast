#!/usr/bin/env python3
"""
backfill_jobs.py - Bookkeeping en jobs_historial para el backfill historico
de ventas (Issue #44). Un registro por grupo (tipo_job='backfill',
detalle.subtipo='backfill_ventas'), no un estado global para los ~65 grupos.

Subcomandos:
  check <grupo_id>
      Imprime "1" si ese grupo ya tiene una corrida 'exitoso' registrada
      (permite resumir sin re-extraer grupos ya completos), "0" si no.

  start <grupo_id> <fecha_desde> <fecha_hasta>
      Inserta una fila 'ejecutando' y imprime el job_id (lastrowid).

  end <job_id> <estado> <grupo_id> <fecha_desde> <fecha_hasta> <duracion_seg>
      Actualiza la fila a estado ('exitoso'|'fallido'), fecha_fin y detalle.
      Lee de stdin (opcional) una lista de fallas, una por linea de texto
      libre (ej. "dep=5 rango=2024-01-01..2024-01-30 rc=10"); se guardan
      en detalle.chunks_fallidos como array. Sin stdin -> array vacio.
"""

import json
import os
import sys
import pymysql

SUBTIPO = "backfill_ventas"

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

def cmd_check(grupo_id: str) -> int:
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM jobs_historial "
                " WHERE tipo_job = 'backfill' AND estado = 'exitoso' "
                "   AND detalle->>'$.subtipo' = %s "
                "   AND detalle->>'$.grupo_id' = %s "
                " LIMIT 1",
                (SUBTIPO, str(grupo_id)),
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
    fallas = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
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
            cur.execute(
                "UPDATE jobs_historial SET estado = %s, fecha_fin = NOW(6), detalle = %s WHERE id = %s",
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
    if sub == "check" and len(args) == 1:
        return cmd_check(args[0])
    if sub == "start" and len(args) == 3:
        return cmd_start(*args)
    if sub == "end" and len(args) == 6:
        return cmd_end(*args)
    print(f"[ERROR] Subcomando/args invalidos: {sys.argv[1:]}", file=sys.stderr)
    return 2

if __name__ == "__main__":
    sys.exit(main())
