#!/usr/bin/env python3
# get_grupos_backfill.py - resuelve la lista de grupos a procesar en el
# backfill historico de ventas (Issue #44).
#
# A diferencia de get_grupos.py (usado por el daily real), excluye por
# default los grupos que ya aplican modelo econometrico (hoy solo el 201,
# que ya tiene 10 anios cargados y el issue #44 excluye explicitamente).
#
# Prioridad:
#   1) Override manual: env GROUPS o GRUPOS, si vienen seteados (permite
#      forzar un grupo puntual para la corrida piloto o un reproceso).
#   2) Tabla grupos: SELECT id FROM grupos WHERE aplica_modelo_econometrico = FALSE.
#
# Imprime los codigos separados por espacio en stdout, ej: "5 6 10 92"

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
            cur.execute(
                "SELECT id FROM grupos WHERE aplica_modelo_econometrico = FALSE ORDER BY id"
            )
            return [str(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()

def main():
    codes = from_env()
    if codes is None:
        codes = from_db()
    if not codes:
        print("[ERROR] No se obtuvo ningun grupo para backfill (ni override ni tabla grupos)", file=sys.stderr)
        return 1
    print(" ".join(codes))
    return 0

if __name__ == "__main__":
    sys.exit(main())
