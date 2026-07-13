#!/usr/bin/env python3
"""
run_calc_stock_resumen.py — Calcula y persiste stock_resumen_365.

Precalcula, por SKU, el resumen de disponibilidad de stock sobre los últimos 365
días (dias_con_stock, dias_sin_stock, total_dias, ventas_365). Reemplaza la
agregación en vivo de stock_diario que hacían GetResumenGlobal/GetStockAnalysis/
GetTopVentasPerdidas/GetStockoutDistribution (ResultadosService.cs) — issue #59/#60:
con ~25M filas en stock_diario y la VM de producción con RAM insuficiente
(issue #60), esa agregación tardaba minutos por request HTTP. Acá se paga el
costo una sola vez por noche.

Cubre TODOS los SKUs de articulos, no solo los que tienen stock_minimo > 0:
GetStockAnalysis() no filtra por ese umbral, a diferencia de las otras 3 funciones
(ver sesión /grill-me de #60, 2026-07-10). Guarda solo conteos crudos, no tasas ni
categorías derivadas — cada función consumidora aplica su propia fórmula/umbral
sobre estos números (no son todas iguales entre sí).

Regenera la tabla completa en una única transacción atómica (DELETE + INSERT),
igual que run_calc_planilla.py.

Uso:
  MYSQL_HOST=mysql MYSQL_DB=evalutia MYSQL_USER=evalutia \\
  MYSQL_PASSWORD=evalutia python run_calc_stock_resumen.py
"""

import datetime as dt
import json
import os
import sys
import time

import pymysql

VENTANA_DIAS = 365

# ── Conexión ───────────────────────────────────────────────────────────────────

def db_connect() -> pymysql.Connection:
    return pymysql.connect(
        host      = os.environ["MYSQL_HOST"],
        port      = int(os.environ.get("MYSQL_PORT", "3306")),
        user      = os.environ["MYSQL_USER"],
        password  = os.environ["MYSQL_PASSWORD"],
        database  = os.environ["MYSQL_DB"],
        autocommit= False,
        charset   = "utf8mb4",
    )

# ── jobs_historial ─────────────────────────────────────────────────────────────

def job_start(conn: pymysql.Connection) -> int:
    """Registra inicio del job. Hace commit propio (separado de la tx de escritura)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs_historial (tipo_job, estado, fecha_inicio) "
            "VALUES ('etl', 'ejecutando', NOW(6))"
        )
        job_id = cur.lastrowid
    conn.commit()
    return int(job_id)


def job_end(conn: pymysql.Connection, job_id: int, estado: str, detalle: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs_historial "
            "   SET estado = %s, fecha_fin = NOW(6), detalle = %s "
            " WHERE id = %s",
            (estado, json.dumps(detalle, ensure_ascii=False), job_id),
        )
    conn.commit()

# ── Cálculo ────────────────────────────────────────────────────────────────────

# LEFT JOIN desde articulos: cubre todos los SKUs, no solo los que tienen filas
# en stock_diario dentro de la ventana (quedan en total_dias=0, dias_con_stock=0).
_SQL_RESUMEN_STOCK = """
    SELECT
        a.sku,
        COUNT(agg.fecha) AS total_dias,
        COALESCE(SUM(CASE WHEN agg.total > a.stock_minimo THEN 1 ELSE 0 END), 0) AS dias_con_stock
    FROM articulos a
    LEFT JOIN (
        SELECT sku, fecha, SUM(cantidad) AS total
        FROM stock_diario
        WHERE fecha BETWEEN %s AND %s
        GROUP BY sku, fecha
    ) agg ON agg.sku = a.sku
    GROUP BY a.sku
"""

_SQL_VENTAS_365 = """
    SELECT sku, SUM(cantidad) AS ventas_365
    FROM ventas_historicas
    WHERE fecha BETWEEN %s AND %s
    GROUP BY sku
"""


def combinar(stock_rows: list[tuple], ventas_rows: list[tuple]) -> list[dict]:
    """
    Combina el resumen de stock por SKU (ya agregado en SQL) con las ventas de la
    misma ventana. SKUs sin ventas quedan con ventas_365=0, no se excluyen — el
    universo de SKUs lo define stock_rows (que ya cubre todo articulos vía LEFT JOIN).
    """
    ventas_365 = {sku: int(total) for sku, total in ventas_rows}

    filas = []
    for sku, total_dias, dias_con_stock in stock_rows:
        total_dias = int(total_dias)
        dias_con_stock = int(dias_con_stock)
        filas.append({
            "sku":            sku,
            "dias_con_stock": dias_con_stock,
            "dias_sin_stock": total_dias - dias_con_stock,
            "total_dias":     total_dias,
            "ventas_365":     ventas_365.get(sku, 0),
        })
    return filas


def calcular_filas(conn: pymysql.Connection) -> list[dict]:
    hoy = dt.date.today()
    desde = hoy - dt.timedelta(days=VENTANA_DIAS)

    print(f"[STOCK_RESUMEN] Ventana: {desde} -> {hoy} ({VENTANA_DIAS} dias)")

    with conn.cursor() as cur:
        cur.execute(_SQL_RESUMEN_STOCK, (desde, hoy))
        stock_rows = cur.fetchall()

    with conn.cursor() as cur:
        cur.execute(_SQL_VENTAS_365, (desde, hoy))
        ventas_rows = cur.fetchall()

    filas = combinar(stock_rows, ventas_rows)
    print(f"[STOCK_RESUMEN] {len(filas)} SKUs procesados")
    return filas

# ── Escritura atómica ──────────────────────────────────────────────────────────

_SQL_INSERT = """
    INSERT INTO stock_resumen_365
        (sku, dias_con_stock, dias_sin_stock, total_dias, ventas_365, ts_carga)
    VALUES
        (%(sku)s, %(dias_con_stock)s, %(dias_sin_stock)s, %(total_dias)s, %(ventas_365)s, NOW(6))
"""

def escribir_resumen(conn: pymysql.Connection, filas: list[dict]) -> None:
    """
    DELETE + INSERT en una única transacción.
    Usamos DELETE (no TRUNCATE) para que sea rollbackeable — mismo criterio que
    escribir_planilla() en run_calc_planilla.py. Si algo falla, el caller hace
    rollback y la tabla queda con los datos de la noche anterior.
    """
    with conn.cursor() as cur:
        cur.execute("SET time_zone = '+00:00'")
        cur.execute("DELETE FROM stock_resumen_365")
        if filas:
            cur.executemany(_SQL_INSERT, filas)
    conn.commit()

# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    conn = db_connect()
    job_id = job_start(conn)
    print(f"[STOCK_RESUMEN] Job id={job_id} iniciado")

    try:
        filas = calcular_filas(conn)
        escribir_resumen(conn, filas)

        duracion = round(time.time() - t0, 2)
        detalle = {
            "subtipo":          "calc_stock_resumen",
            "skus_procesados":  len(filas),
            "ventana_dias":     VENTANA_DIAS,
            "filas_insertadas": len(filas),
            "duracion_seg":     duracion,
        }
        job_end(conn, job_id, "exitoso", detalle)
        print(f"[STOCK_RESUMEN] Completado OK en {duracion}s")

    except Exception as exc:
        conn.rollback()
        duracion = round(time.time() - t0, 2)
        detalle = {
            "subtipo":      "calc_stock_resumen",
            "error":        str(exc),
            "duracion_seg": duracion,
        }
        job_end(conn, job_id, "fallido", detalle)
        print(f"[STOCK_RESUMEN][ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
