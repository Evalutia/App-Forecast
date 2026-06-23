#!/usr/bin/env python3
# get_skus_modelo.py - resuelve la lista de SKUs que reciben modelo econometrico.
#
# Prioridad (Issue #43):
#   1) Override manual: env SKUS, si viene seteado (debug/reproceso puntual).
#   2) articulos JOIN grupos WHERE aplica_modelo_econometrico = TRUE.
#
# Imprime los SKUs separados por coma en stdout (formato que espera --skus de
# predict.py), ej: "C00184,I01088". Lista vacia -> imprime "" y sale 0; quien
# decide si abortar por lista vacia es run_predict.sh, no este script.

import os
import sys
import pymysql

def from_env():
    raw = os.environ.get("SKUS")
    if not raw:
        return None
    skus = [s.strip() for s in raw.split(",") if s.strip()]
    return skus or None

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
            cur.execute("""
                SELECT a.sku
                FROM articulos a
                JOIN grupos g ON g.id = a.grupo_id
                WHERE g.aplica_modelo_econometrico = TRUE
            """)
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

def main():
    skus = from_env()
    if skus is None:
        skus = from_db()
    print(",".join(skus))
    return 0

if __name__ == "__main__":
    sys.exit(main())
