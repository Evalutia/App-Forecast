#!/usr/bin/env python3
"""
run_calc_planilla.py — Calcula y persiste planilla_ventas_calculada.

Lee ventas_historicas + stock_diario, calcula rotaciones y estado_mes
por SKU×mes para una ventana de 13 meses (mes actual + 12 anteriores completos).
Regenera la tabla completa en una única transacción atómica (DELETE + INSERT).

Umbrales estado_mes (replica el criterio del cliente — Issue #36/#37, verificado contra
su Excel de referencia vía openpyxl: colorea como quiebre el 100% de los meses con al
menos 1 día sin stock, sin piso mínimo — no usan un umbral del 90%):
  normal          : dias_con_stock == dias_naturales_mes (todos los días con stock)
  quiebre_parcial : dias_con_stock >  0  y  < dias_naturales_mes (al menos 1 día sin stock)
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

# Fracción de días naturales necesaria para "normal". 100% = replica el criterio del
# cliente: cualquier día de quiebre cuenta, sin piso. Issue #36/#37, sesión 2026-06-17.
ESTADO_UMBRAL_NORMAL = 1.00

# Umbrales de frecuencia de quiebre (Issue #27)
# Medida: cantidad de meses cerrados (de 12) con ventas_cantidad > 0
FREQ_ALTA_MIN  = 9   # >= 9 meses con ventas → alta frecuencia
FREQ_BAJA_MAX  = 3   # <= 3 meses con ventas → baja frecuencia
                     # 4–8 meses → media frecuencia

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

def ventana_meses(n: int, hoy: dt.date | None = None) -> list[tuple[int, int]]:
    """Retorna lista de (year, month) de los últimos n meses inclusive el actual.
    Orden: más reciente primero.

    `hoy` es inyectable para poder testear cualquier día del mes sin esperar
    a que llegue; en producción se usa la fecha real (default)."""
    hoy = hoy or dt.date.today()
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
    Umbral configurable: ESTADO_UMBRAL_NORMAL (default 100% — cualquier día de
    quiebre cuenta, replica el criterio observado en la planilla del cliente).
    """
    if dias_stock == 0:
        return "sin_stock"
    if dias_stock / dias_naturales >= ESTADO_UMBRAL_NORMAL:
        return "normal"
    return "quiebre_parcial"


def clasificar_estado_mes(dias_stock: int, dias_naturales: int, es_mes_referencia: bool) -> str:
    """
    Clasifica estado_mes, exceptuando el mes de referencia (en curso) del umbral
    de ESTADO_UMBRAL_NORMAL: dias_naturales_mes ahí siempre es el total del mes
    calendario, no los días que de verdad transcurrieron, así que el umbral da
    falso positivo de quiebre casi todo el mes sin importar si el stock estuvo
    perfecto (más aún con el umbral en 100%, donde un solo día de diferencia ya
    alcanza para disparar el falso positivo).

    dias_stock == 0 sí es una señal confiable a mitad de mes (cuenta días reales
    ya observados en stock_diario), por eso sin_stock se preserva.
    """
    if es_mes_referencia:
        return "normal" if dias_stock > 0 else "sin_stock"
    return clasificar_estado(dias_stock, dias_naturales)

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

def cargar_factores(conn: pymysql.Connection) -> dict[str, dict[int, float | None]]:
    """Preload de factores estacionales por SKU×mes. factors[sku][1..12]."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sku, factor_mes_01, factor_mes_02, factor_mes_03, factor_mes_04, "
            "       factor_mes_05, factor_mes_06, factor_mes_07, factor_mes_08, "
            "       factor_mes_09, factor_mes_10, factor_mes_11, factor_mes_12 "
            "FROM articulos"
        )
        rows = cur.fetchall()
    return {
        row[0]: {i + 1: (float(row[i + 1]) if row[i + 1] is not None else None) for i in range(12)}
        for row in rows
    }


def calcular_filas(conn: pymysql.Connection) -> tuple[list[dict], int, int, int]:
    """
    Retorna (filas_para_insert, skus_omitidos, mes_referencia_normal, mes_referencia_sin_stock).
    skus_omitidos: SKUs que tienen ventas pero no existe en articulos (FK violation evitada).
    mes_referencia_normal/sin_stock: conteo de filas del mes de referencia en cada rama
    del override de clasificar_estado_mes (observabilidad en jobs_historial).
    """
    factors = cargar_factores(conn)
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

    # ── Construir filas (paso 1: calcular datos por mes) ──────────────────────
    todas_keys = (set(ventas.keys()) | set(dias_stock.keys()))

    filas = []
    for (sku, yr, mo) in todas_keys:
        dn = dias_naturales_mes(yr, mo)
        ds = dias_stock.get((sku, yr, mo), 0)
        vq = ventas.get((sku, yr, mo), 0)

        rot_real  = round(vq / ds, 4) if ds > 0 else None
        rot_bruta = round(vq / dn, 4)

        factor = (factors.get(sku) or {}).get(mo)
        rot_desest = round(rot_real / factor, 4) if rot_real is not None and factor else None

        filas.append({
            "sku":                               sku,
            "year":                              yr,
            "month":                             mo,
            "ventas_cantidad":                   vq,
            "dias_con_stock":                    ds,
            "dias_naturales_mes":                dn,
            "rotacion_diaria_real":              rot_real,
            "rotacion_diaria_bruta":             rot_bruta,
            "rotacion_diaria_desestacionalizada": rot_desest,
            "estado_mes":                        clasificar_estado_mes(ds, dn, (yr, mo) == ultimo_mes),
            "frecuencia_nivel":                  None,  # se rellena en paso 2
            "rotacion_ajustada":                 None,  # se rellena en paso 2
        })

    # ── Paso 2: frecuencia de quiebre por SKU ─────────────────────────────────
    # Mes de referencia = meses[0] (más reciente). Los 12 cerrados son meses[1..12].
    meses_ordenados = sorted(meses, reverse=True)          # más reciente primero
    meses_cerrados  = set(meses_ordenados[1:])             # excluye el mes actual

    # Contar meses cerrados con ventas > 0 por SKU
    meses_con_ventas: dict[str, int] = {}
    for (sku, yr, mo), vq in ventas.items():
        if (yr, mo) in meses_cerrados and vq > 0:
            meses_con_ventas[sku] = meses_con_ventas.get(sku, 0) + 1

    def clasificar_frecuencia(n_meses_con_ventas: int) -> str:
        if n_meses_con_ventas >= FREQ_ALTA_MIN:
            return "alta"
        if n_meses_con_ventas <= FREQ_BAJA_MAX:
            return "baja"
        return "media"

    def rotacion_ajustada(vq: int, ds: int, dn: int, nivel: str) -> float | None:
        if nivel == "alta":
            return round(vq / ds, 4) if ds > 0 else None
        if nivel == "baja":
            return round(vq / dn, 4)
        # media: promedio de ambas fórmulas
        r_alta = vq / ds if ds > 0 else None
        r_baja = vq / dn
        if r_alta is None:
            return round(r_baja, 4)
        return round((r_alta + r_baja) / 2, 4)

    # Anotar frecuencia_nivel y rotacion_ajustada en cada fila
    for fila in filas:
        sku = fila["sku"]
        n   = meses_con_ventas.get(sku, 0)
        nivel = clasificar_frecuencia(n)
        fila["frecuencia_nivel"] = nivel

        if fila["estado_mes"] == "quiebre_parcial":
            fila["rotacion_ajustada"] = rotacion_ajustada(
                fila["ventas_cantidad"],
                fila["dias_con_stock"],
                fila["dias_naturales_mes"],
                nivel,
            )

    skus_procesados = len({f["sku"] for f in filas})
    dist = {lvl: sum(1 for f in filas if f["frecuencia_nivel"] == lvl and f["month"] == meses[0][1] and f["year"] == meses[0][0]) for lvl in ("alta","media","baja")}
    print(f"[PLANILLA] {skus_procesados} SKUs · {len(filas)} filas · frecuencia: alta={dist['alta']} media={dist['media']} baja={dist['baja']}")

    filas_mes_ref = [f for f in filas if (f["year"], f["month"]) == ultimo_mes]
    mes_referencia_normal    = sum(1 for f in filas_mes_ref if f["estado_mes"] == "normal")
    mes_referencia_sin_stock = sum(1 for f in filas_mes_ref if f["estado_mes"] == "sin_stock")
    print(f"[PLANILLA] Mes de referencia {ultimo_mes}: normal={mes_referencia_normal} sin_stock={mes_referencia_sin_stock}")

    return filas, skus_omitidos, mes_referencia_normal, mes_referencia_sin_stock

# ── Escritura atómica ──────────────────────────────────────────────────────────

_SQL_INSERT = """
    INSERT INTO planilla_ventas_calculada
        (sku, year, month,
         ventas_cantidad, dias_con_stock, dias_naturales_mes,
         rotacion_diaria_real, rotacion_diaria_bruta, rotacion_diaria_desestacionalizada,
         estado_mes, frecuencia_nivel, rotacion_ajustada, ts_carga)
    VALUES
        (%(sku)s, %(year)s, %(month)s,
         %(ventas_cantidad)s, %(dias_con_stock)s, %(dias_naturales_mes)s,
         %(rotacion_diaria_real)s, %(rotacion_diaria_bruta)s,
         %(rotacion_diaria_desestacionalizada)s,
         %(estado_mes)s, %(frecuencia_nivel)s, %(rotacion_ajustada)s, NOW(6))
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
        filas, skus_omitidos, mes_ref_normal, mes_ref_sin_stock = calcular_filas(conn)
        escribir_planilla(conn, filas)

        duracion = round(time.time() - t0, 2)
        detalle = {
            "subtipo":                  "calc_planilla",
            "skus_procesados":          len({f["sku"] for f in filas}),
            "meses_calculados":         VENTANA_MESES,
            "filas_insertadas":         len(filas),
            "skus_omitidos":            skus_omitidos,
            "duracion_seg":             duracion,
            "umbral_normal_pct":        int(ESTADO_UMBRAL_NORMAL * 100),
            "mes_referencia_normal":    mes_ref_normal,
            "mes_referencia_sin_stock": mes_ref_sin_stock,
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
