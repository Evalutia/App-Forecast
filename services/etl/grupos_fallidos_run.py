#!/usr/bin/env python3
"""
grupos_fallidos_run.py - Issue #157: registro de que grupos de
ConsStockVenta fallaron en la corrida de ESTA noche, para que el paso
"MERGE STAGING -> VENTAS" del .kjb pueda excluir solo esos grupos en vez
de saltear el merge entero -- antes de este ticket, un solo grupo fallido
en run_extract_sales_chunk.sh congelaba los ~66 (ver .claude/CONTEXTO.md,
seccion #157).

Efimero por diseño, igual que ventas_historicas_stage: `reset` lo vacia al
arrancar cada corrida (run_extract_sales_chunk.sh), no es un historico.

Subcomandos:
  reset             Vacia la tabla. Se llama una vez, al arrancar la
                     extraccion, antes del loop de grupos.
  marcar <grupo>     Registra un grupo como fallido esta corrida.
                     Idempotente (INSERT IGNORE).

                     Se llama de forma PESIMISTA, al ENTRAR a cada grupo
                     (antes de intentar ninguno de sus depositos), no solo
                     cuando algo falla -- si el proceso muere a mitad de
                     camino (OOM, timeout) entre un deposito que ya
                     escribio filas en stage y el siguiente, la marca
                     puesta al entrar sobrevive, y el merge excluye ese
                     grupo en vez de mergear datos parciales.
  desmarcar <grupo>  Quita el grupo de la tabla -- se llama al final,
                     solo si TODOS sus depositos salieron bien esta
                     corrida. El timing es seguro: el MERGE corre recien
                     despues de que run_extract_sales_chunk.sh termina del
                     todo, nunca en paralelo.
  listar            Imprime los grupo_id fallidos de esta corrida,
                     separados por coma, ordenados -- usado para armar el
                     motivo dinamico que ve jobs_historial (mismo criterio
                     que #131 pidio para el resto de los pasos: "con el
                     detalle de cuales"). Vacio (sin salto de linea extra)
                     si no fallo ninguno.
"""
import os
import sys

import pymysql


def db_connect():
    return pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DB"],
        charset="utf8mb4",
    )


def _parse_grupo_id(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        print(f"grupo invalido, se esperaba un entero: {raw!r}", file=sys.stderr)
        return None


def cmd_reset(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ventas_grupos_fallidos_run")
    conn.commit()


def cmd_marcar(conn, grupo_id):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT IGNORE INTO ventas_grupos_fallidos_run (grupo_id) VALUES (%s)",
            (grupo_id,),
        )
    conn.commit()


def cmd_desmarcar(conn, grupo_id):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ventas_grupos_fallidos_run WHERE grupo_id = %s", (grupo_id,))
    conn.commit()


def cmd_listar(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT grupo_id FROM ventas_grupos_fallidos_run ORDER BY grupo_id")
        print(",".join(str(row[0]) for row in cur.fetchall()))


def main():
    USO = "uso: grupos_fallidos_run.py reset|marcar <grupo>|desmarcar <grupo>|listar"
    if len(sys.argv) < 2:
        print(USO, file=sys.stderr)
        return 2

    sub = sys.argv[1]
    grupo_id = None
    if sub in ("marcar", "desmarcar"):
        if len(sys.argv) < 3:
            print(USO, file=sys.stderr)
            return 2
        grupo_id = _parse_grupo_id(sys.argv[2])
        if grupo_id is None:
            return 2

    conn = db_connect()
    try:
        if sub == "reset":
            cmd_reset(conn)
        elif sub == "marcar":
            cmd_marcar(conn, grupo_id)
        elif sub == "desmarcar":
            cmd_desmarcar(conn, grupo_id)
        elif sub == "listar":
            cmd_listar(conn)
        else:
            print(f"subcomando desconocido: {sub}", file=sys.stderr)
            return 2
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
