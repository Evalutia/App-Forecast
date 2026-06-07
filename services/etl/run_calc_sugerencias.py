#!/usr/bin/env python3
"""
run_calc_sugerencias.py — Calcula rotacion_sugerida y fiabilidad_porcentaje
por SKU y persiste en planilla_sugerencias.

Algoritmo:
  - Toma los meses con estado_mes='normal' de planilla_ventas_calculada
    (hasta MAX_MESES meses, los más recientes).
  - Si un SKU tiene < MIN_MESES_NORMAL meses normal → rotacion_sugerida = NULL.
  - Rotación sugerida: promedio ponderado con pesos lineales
    (más reciente = mayor peso).
  - Fiabilidad: max(0, (1 - std/mean) * 100) — CV inverso.
    Alta fiabilidad = rotación estable mes a mes.
  - Una sola transacción atómica (ON DUPLICATE KEY UPDATE), no bloqueante.

Uso:
  MYSQL_HOST=mysql MYSQL_DB=evalutia MYSQL_USER=evalutia \
  MYSQL_PASSWORD=evalutia python run_calc_sugerencias.py
"""

import json
import os
import sys
import time
from collections import defaultdict

import pymysql

MODELO           = "weighted_avg_13m"
MIN_MESES_NORMAL = 3
MAX_MESES        = 13

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

def calcular_sugerencias(conn: pymysql.Connection) -> tuple[list[dict], int, int]:
    """
    Retorna (filas, skus_con_sugerencia, skus_sin_datos).

    skus_sin_datos: SKUs con < MIN_MESES_NORMAL meses normal — se insertan con NULL
    para que el ON DUPLICATE KEY UPDATE limpie valores stale de ciclos anteriores.
    """
    sql = """
        SELECT sku, year, month, rotacion_diaria_real
        FROM planilla_ventas_calculada
        WHERE estado_mes = 'normal'
          AND rotacion_diaria_real IS NOT NULL
          AND rotacion_diaria_real > 0
        ORDER BY sku, year DESC, month DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    # Agrupar por SKU, retener solo los MAX_MESES más recientes (ya vienen DESC)
    por_sku: dict[str, list[float]] = defaultdict(list)
    for sku, _year, _month, rot in rows:
        vals = por_sku[sku]
        if len(vals) < MAX_MESES:
            vals.append(float(rot))

    filas = []
    skus_con_sugerencia = 0
    skus_sin_datos      = 0

    for sku, valores in por_sku.items():
        n = len(valores)

        if n < MIN_MESES_NORMAL:
            skus_sin_datos += 1
            filas.append({
                "sku":                  sku,
                "rotacion_sugerida":    None,
                "fiabilidad_porcentaje": None,
                "modelo":               MODELO,
            })
            continue

        # valores[0] = mes más reciente → peso n
        # valores[-1] = mes más antiguo → peso 1
        pesos  = list(range(n, 0, -1))
        suma_p = sum(pesos)
        rotacion_sugerida = sum(p * v for p, v in zip(pesos, valores)) / suma_p

        # CV sobre todos los valores (sin ponderar — mide variabilidad real del SKU)
        mean = sum(valores) / n
        if mean > 0:
            std = (sum((v - mean) ** 2 for v in valores) / n) ** 0.5
            cv  = std / mean
            fiabilidad = max(0.0, (1.0 - cv) * 100.0)
        else:
            fiabilidad = 0.0

        skus_con_sugerencia += 1
        filas.append({
            "sku":                   sku,
            "rotacion_sugerida":     round(rotacion_sugerida, 4),
            "fiabilidad_porcentaje": round(fiabilidad, 2),
            "modelo":                MODELO,
        })

    return filas, skus_con_sugerencia, skus_sin_datos

# ── Escritura atómica ──────────────────────────────────────────────────────────

_SQL_UPSERT = """
    INSERT INTO planilla_sugerencias
        (sku, rotacion_sugerida, fiabilidad_porcentaje, modelo, ts_generacion, ts_carga)
    VALUES
        (%(sku)s, %(rotacion_sugerida)s, %(fiabilidad_porcentaje)s,
         %(modelo)s, NOW(6), NOW(6))
    ON DUPLICATE KEY UPDATE
        rotacion_sugerida     = VALUES(rotacion_sugerida),
        fiabilidad_porcentaje = VALUES(fiabilidad_porcentaje),
        modelo                = VALUES(modelo),
        ts_generacion         = NOW(6),
        actualizado_en        = NOW(6)
"""


def escribir_sugerencias(conn: pymysql.Connection, filas: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.execute("SET time_zone = '+00:00'")
        if filas:
            cur.executemany(_SQL_UPSERT, filas)
    conn.commit()

# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    t0     = time.time()
    conn   = db_connect()
    job_id = job_start(conn)
    print(f"[SUGERENCIAS] Job id={job_id} iniciado")

    try:
        filas, skus_con_sugerencia, skus_sin_datos = calcular_sugerencias(conn)
        escribir_sugerencias(conn, filas)

        duracion = round(time.time() - t0, 2)
        detalle  = {
            "subtipo":              "calc_sugerencias",
            "modelo":               MODELO,
            "skus_con_sugerencia":  skus_con_sugerencia,
            "skus_sin_datos":       skus_sin_datos,
            "filas_upserted":       len(filas),
            "duracion_seg":         duracion,
            "min_meses_normal":     MIN_MESES_NORMAL,
            "max_meses":            MAX_MESES,
        }
        job_end(conn, job_id, "exitoso", detalle)
        print(
            f"[SUGERENCIAS] OK en {duracion}s — "
            f"{skus_con_sugerencia} SKUs con sugerencia, "
            f"{skus_sin_datos} sin datos suficientes"
        )

    except Exception as exc:
        conn.rollback()
        duracion = round(time.time() - t0, 2)
        detalle  = {
            "subtipo":      "calc_sugerencias",
            "error":        str(exc),
            "duracion_seg": duracion,
        }
        job_end(conn, job_id, "fallido", detalle)
        print(f"[SUGERENCIAS][ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
