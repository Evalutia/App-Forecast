#!/usr/bin/env python3
"""
run_calc_planilla.py — Calcula y persiste planilla_ventas_calculada.

Lee ventas_historicas + stock_diario, calcula rotaciones y estado_mes
por SKU×mes para una ventana de 13 meses (mes actual + 12 anteriores completos).
Regenera la tabla completa en una única transacción atómica (DELETE + INSERT).

Umbrales estado_mes (documentar también en frontend — el cliente puede pedir ajustarlos):
  normal          : dias_con_stock >= 90% de dias_naturales_mes
  quiebre_parcial : dias_con_stock >  0  y  < 90% de dias_naturales_mes
  sin_stock       : dias_con_stock == 0

Uso:
  MYSQL_HOST=mysql MYSQL_DB=evalutia MYSQL_USER=evalutia \\
  MYSQL_PASSWORD=evalutia python run_calc_planilla.py
"""

import calendar
import datetime as dt
import json
import os
import sys
import time

import pymysql

# ── Parámetros ─────────────────────────────────────────────────────────────────

VENTANA_MESES        = 13     # mes actual + 12 anteriores completos
ESTADO_UMBRAL_NORMAL = 0.90   # fracción de días naturales necesaria para "normal"

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

# ── Helpers de fecha ───────────────────────────────────────────────────────────

def ventana_meses(n: int) -> list[tuple[int, int]]:
    """Retorna lista de (year, month) de los últimos n meses inclusive el actual.
    Orden: más reciente primero."""
    hoy = dt.date.today()
    y, m = hoy.year, hoy.month
    resultado = []
    for _ in range(n):
        resultado.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return resultado


def dias_naturales_mes(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]

# ── Lógica de negocio ──────────────────────────────────────────────────────────

def clasificar_estado(dias_stock: int, dias_naturales: int) -> str:
    """
    Clasifica el estado del mes según disponibilidad de stock.
    Umbral configurable: ESTADO_UMBRAL_NORMAL (default 90%).
    """
    if dias_stock == 0:
        return "sin_stock"
    if dias_stock / dias_naturales >= ESTADO_UMBRAL_NORMAL:
        return "normal"
    return "quiebre_parcial"

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

def calcular_filas(conn: pymysql.Connection) -> tuple[list[dict], int]:
    """
    Retorna (filas_para_insert, skus_omitidos).
    skus_omitidos: SKUs que tienen ventas pero no existe en articulos (FK violation evitada).
    """
    meses = ventana_meses(VENTANA_MESES)
    meses_set = set(meses)

    # Rango de fechas para acotar las queries
    primer_mes = meses[-1]
    ultimo_mes  = meses[0]
    fecha_desde = dt.date(primer_mes[0], primer_mes[1], 1)
    fecha_hasta = dt.date(
        ultimo_mes[0], ultimo_mes[1],
        dias_naturales_mes(ultimo_mes[0], ultimo_mes[1])
    )

    print(f"[PLANILLA] Ventana: {fecha_desde} → {fecha_hasta}  ({VENTANA_MESES} meses)")

    # ── Ventas por SKU×mes (solo SKUs que existen en articulos) ───────────────
    sql_ventas = """
        SELECT
            vh.sku,
            YEAR(vh.fecha)  AS yr,
            MONTH(vh.fecha) AS mo,
            SUM(vh.cantidad) AS ventas_cantidad
        FROM ventas_historicas vh
        INNER JOIN articulos a ON a.sku = vh.sku
        WHERE vh.fecha BETWEEN %s AND %s
        GROUP BY vh.sku, YEAR(vh.fecha), MONTH(vh.fecha)
    """
    with conn.cursor() as cur:
        cur.execute(sql_ventas, (fecha_desde, fecha_hasta))
        ventas_raw = cur.fetchall()

    ventas: dict[tuple, int] = {}
    for sku, yr, mo, cant in ventas_raw:
        if (yr, mo) in meses_set:
            ventas[(sku, yr, mo)] = int(cant)

    # ── Días con stock por SKU×mes ─────────────────────────────────────────────
    # Un día "tiene stock" cuando el total de todos los depósitos supera stock_minimo.
    sql_stock = """
        SELECT
            agg.sku,
            YEAR(agg.fecha)  AS yr,
            MONTH(agg.fecha) AS mo,
            COUNT(DISTINCT agg.fecha) AS dias_con_stock
        FROM (
            SELECT
                sd.sku,
                sd.fecha,
                SUM(sd.cantidad) AS stock_total
            FROM stock_diario sd
            WHERE sd.fecha BETWEEN %s AND %s
            GROUP BY sd.sku, sd.fecha
        ) agg
        INNER JOIN articulos a ON a.sku = agg.sku
        WHERE agg.stock_total > COALESCE(a.stock_minimo, 0)
        GROUP BY agg.sku, YEAR(agg.fecha), MONTH(agg.fecha)
    """
    with conn.cursor() as cur:
        cur.execute(sql_stock, (fecha_desde, fecha_hasta))
        stock_raw = cur.fetchall()

    dias_stock: dict[tuple, int] = {}
    for sku, yr, mo, dias in stock_raw:
        if (yr, mo) in meses_set:
            dias_stock[(sku, yr, mo)] = int(dias)

    # ── SKUs omitidos (ventas sin articulo) ────────────────────────────────────
    sql_huerfanos = """
        SELECT COUNT(DISTINCT vh.sku)
        FROM ventas_historicas vh
        LEFT JOIN articulos a ON a.sku = vh.sku
        WHERE a.sku IS NULL
          AND vh.fecha BETWEEN %s AND %s
    """
    with conn.cursor() as cur:
        cur.execute(sql_huerfanos, (fecha_desde, fecha_hasta))
        skus_omitidos = int(cur.fetchone()[0])

    if skus_omitidos:
        print(f"[PLANILLA][WARN] {skus_omitidos} SKU(s) con ventas sin registro en articulos — omitidos.")

    # ── Construir filas ────────────────────────────────────────────────────────
    todas_keys = (set(ventas.keys()) | set(dias_stock.keys()))

    filas = []
    for (sku, yr, mo) in todas_keys:
        dn = dias_naturales_mes(yr, mo)
        ds = dias_stock.get((sku, yr, mo), 0)
        vq = ventas.get((sku, yr, mo), 0)

        rot_real  = round(vq / ds, 4) if ds > 0 else None
        rot_bruta = round(vq / dn, 4)

        filas.append({
            "sku":                               sku,
            "year":                              yr,
            "month":                             mo,
            "ventas_cantidad":                   vq,
            "dias_con_stock":                    ds,
            "dias_naturales_mes":                dn,
            "rotacion_diaria_real":              rot_real,
            "rotacion_diaria_bruta":             rot_bruta,
            "rotacion_diaria_desestacionalizada": None,  # TODO issue #2/#3/#5
            "estado_mes":                        clasificar_estado(ds, dn),
        })

    print(f"[PLANILLA] {len({f['sku'] for f in filas})} SKUs · {len(filas)} filas calculadas")
    return filas, skus_omitidos

# ── Escritura atómica ──────────────────────────────────────────────────────────

_SQL_INSERT = """
    INSERT INTO planilla_ventas_calculada
        (sku, year, month,
         ventas_cantidad, dias_con_stock, dias_naturales_mes,
         rotacion_diaria_real, rotacion_diaria_bruta, rotacion_diaria_desestacionalizada,
         estado_mes, ts_carga)
    VALUES
        (%(sku)s, %(year)s, %(month)s,
         %(ventas_cantidad)s, %(dias_con_stock)s, %(dias_naturales_mes)s,
         %(rotacion_diaria_real)s, %(rotacion_diaria_bruta)s,
         %(rotacion_diaria_desestacionalizada)s,
         %(estado_mes)s, NOW(6))
"""

def escribir_planilla(conn: pymysql.Connection, filas: list[dict]) -> None:
    """
    DELETE + INSERT en una única transacción.
    Usamos DELETE (no TRUNCATE) para que sea rollbackeable.
    Si algo falla, el caller hace rollback → tabla queda con datos anteriores.
    """
    with conn.cursor() as cur:
        cur.execute("SET time_zone = '+00:00'")
        cur.execute("DELETE FROM planilla_ventas_calculada")
        if filas:
            cur.executemany(_SQL_INSERT, filas)
    conn.commit()

# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    conn = db_connect()
    job_id = job_start(conn)
    print(f"[PLANILLA] Job id={job_id} iniciado")

    try:
        filas, skus_omitidos = calcular_filas(conn)
        escribir_planilla(conn, filas)

        duracion = round(time.time() - t0, 2)
        detalle = {
            "subtipo":           "calc_planilla",
            "skus_procesados":   len({f["sku"] for f in filas}),
            "meses_calculados":  VENTANA_MESES,
            "filas_insertadas":  len(filas),
            "skus_omitidos":     skus_omitidos,
            "duracion_seg":      duracion,
            "umbral_normal_pct": int(ESTADO_UMBRAL_NORMAL * 100),
        }
        job_end(conn, job_id, "exitoso", detalle)
        print(f"[PLANILLA] Completado OK en {duracion}s")

    except Exception as exc:
        conn.rollback()
        duracion = round(time.time() - t0, 2)
        detalle = {
            "subtipo":      "calc_planilla",
            "error":        str(exc),
            "duracion_seg": duracion,
        }
        job_end(conn, job_id, "fallido", detalle)
        print(f"[PLANILLA][ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
