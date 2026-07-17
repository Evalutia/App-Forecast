#!/usr/bin/env python3
# get_grupos.py - resuelve la lista de grupos a procesar en el loop del ETL.
#
# Prioridad (Issue #42):
#   1) Override manual: env GROUPS o GRUPOS, si vienen seteados (debug/reproceso
#      de un grupo puntual sin tocar la tabla).
#   2) Tabla grupos (fuente de verdad) via SELECT id FROM grupos.
#
# Imprime los codigos separados por espacio en stdout, ej: "5 6 10 201"

import os
import re
import sys
import pymysql

def from_env():
    raw = os.environ.get("GROUPS") or os.environ.get("GRUPOS")
    if not raw:
        return None
    codes = re.findall(r"\d+", raw)
    return codes or None

def from_db():
    conn = pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DB"],
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM grupos ORDER BY id")
            return [str(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()

def main():
    codes = from_env()
    if codes is None:
        codes = from_db()
    if not codes:
        print("[ERROR] No se obtuvo ningun grupo (ni override ni tabla grupos)", file=sys.stderr)
        return 1
    print(" ".join(codes))
    return 0

if __name__ == "__main__":
    sys.exit(main())
