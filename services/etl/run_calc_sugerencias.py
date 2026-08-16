#!/usr/bin/env python3
"""
run_calc_sugerencias.py — Calcula rotacion_sugerida, fiabilidad_porcentaje
y dias_hasta_quiebre por SKU y persiste en planilla_sugerencias.

Algoritmo rotacion_sugerida:
  - Toma los meses con estado_mes IN ('normal', 'quiebre_parcial') de
    planilla_ventas_calculada (hasta MAX_MESES meses, los más recientes),
    excluyendo el mes de referencia. Usa rotacion_diaria_real en meses normales
    y rotacion_ajustada (ya corregida por nivel de frecuencia) en quiebre_parcial.
    Desde Issue #36/#37 el umbral de estado_mes es 100% (cualquier día de
    quiebre cuenta) — restringir esto a solo 'normal' dejaría sin sugerencia a
    muchos más SKUs de los que quedaban afuera con el umbral del 90% anterior.
  - Issue #116: un mes normal o quiebre_parcial cuenta SIEMPRE que exista la
    fila, venda 0 o no -- antes se descartaba con un filtro "> 0" en SQL, lo
    que sesgaba la sugerencia hacia arriba en cualquier SKU con ventas
    intermitentes (medía "cuánto vende cuando vende", no "cuánto vende").
    Los meses 'sin_stock'/'sin_datos' se siguen excluyendo (no son "vendió
    cero", son "no sabemos" o "no tenía para vender").
  - Si un SKU tiene < MIN_MESES_CON_DATOS meses con datos → rotacion_sugerida = NULL.
  - Promedio ponderado con pesos lineales (más reciente = mayor peso).

Algoritmo fiabilidad_porcentaje:
  - CV inverso: max(0, (1 - std/mean) * 100). Alta fiabilidad = rotación estable.
  - Al incluir los meses en cero (ver arriba), la intermitencia ya penaliza
    la fiabilidad correctamente: un SKU que vende 3 de 12 meses tiene alta
    variabilidad real, no solo 3 valores estables.
  - Issue #142: un SKU con desvío cero (std=0 -- todos sus meses elegibles
    con el MISMO valor, sea 0 o cualquier otro) da fiabilidad=100, exactamente
    lo que promete la hoja "Criterios" ("100% = rotación idéntica todos los
    meses"). Antes caía a 0% para el caso real de 272 SKUs en cero porque el
    CV no se puede calcular con mean=0. Un mean<=0 con variabilidad real
    (std!=0 -- cancelación de valores positivos/negativos por notas de
    crédito, #80) mantiene el 0% previo -- sin datos reales para verificar
    ese camino, ver nota en calcular_rotacion_y_fiabilidad.

Algoritmo dias_hasta_quiebre (QBK):
  - stock_actual = SUM de todos los depósitos en MAX(fecha) por SKU desde stock_diario.
  - dias_hasta_quiebre = max(0, stock_actual) / rotacion_sugerida.
  - NULL si rotacion_sugerida es NULL o 0. Stock negativo se trata como 0.
  - Issue #116: también NULL si ese MAX(fecha) tiene más de
    UMBRAL_DIAS_STOCK_VIEJO días de antigüedad respecto a hoy -- evita
    reportar días-hasta-quiebre sobre un stock congelado de un SKU que
    desapareció del feed (visto en producción: 1 artículo así).

Una sola transacción atómica (ON DUPLICATE KEY UPDATE), no bloqueante.

Uso:
  MYSQL_HOST=mysql MYSQL_DB=evalutia MYSQL_USER=evalutia \
  MYSQL_PASSWORD=evalutia python run_calc_sugerencias.py
"""

import datetime as dt
import json
import os
import sys
import time
from collections import defaultdict

import pymysql

MODELO                  = "weighted_avg_13m_v2"  # Issue #116: bump por cambio de criterio de elegibilidad
MIN_MESES_CON_DATOS     = 3
MAX_MESES               = 13
UMBRAL_DIAS_STOCK_VIEJO = 7

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

# ── Mes de referencia ──────────────────────────────────────────────────────────

def cargar_mes_referencia(conn: pymysql.Connection) -> tuple[int, int] | None:
    """
    Mes de referencia = el más reciente en planilla_ventas_calculada (no dt.date.today(),
    para no desincronizarse de run_calc_planilla.py si el job corre a caballo de medianoche).
    None si la tabla está vacía (ej. antes de la primera corrida de run_calc_planilla.py).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT year, month FROM planilla_ventas_calculada "
            "ORDER BY year DESC, month DESC LIMIT 1"
        )
        row = cur.fetchone()
    return (row[0], row[1]) if row else None

# ── Stock actual ───────────────────────────────────────────────────────────────

def cargar_stock_actual(conn: pymysql.Connection) -> dict[str, tuple[float, dt.date]]:
    """
    Retorna {sku: (stock_actual, fecha_stock)} usando el último registro
    disponible por SKU (MAX fecha individual) sumando todos los depósitos.
    Stock negativo se normaliza a 0. fecha_stock se usa en
    calcular_dias_hasta_quiebre() para detectar stock congelado (Issue #116).
    """
    sql = """
        SELECT sd.sku, SUM(sd.cantidad) AS stock_actual, ult.ultima_fecha
        FROM stock_diario sd
        INNER JOIN (
            SELECT sku, MAX(fecha) AS ultima_fecha
            FROM stock_diario
            GROUP BY sku
        ) ult ON sd.sku = ult.sku AND sd.fecha = ult.ultima_fecha
        GROUP BY sd.sku, ult.ultima_fecha
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return {sku: (max(0.0, float(cant)), fecha) for sku, cant, fecha in cur.fetchall()}

# ── Cálculo puro (sin DB, unit-testeable) ──────────────────────────────────────

def calcular_rotacion_y_fiabilidad(valores: list[float]) -> tuple[float | None, float | None]:
    """
    Promedio ponderado (más reciente = mayor peso) + fiabilidad (CV inverso)
    sobre una lista de rotaciones mensuales ya elegibles (ver SQL de
    calcular_sugerencias() para qué cuenta como elegible -- Issue #116).
    (None, None) si hay menos de MIN_MESES_CON_DATOS valores.
    """
    n = len(valores)
    if n < MIN_MESES_CON_DATOS:
        return None, None

    # valores[0] = mes más reciente → peso n; valores[-1] = más antiguo → peso 1
    pesos  = list(range(n, 0, -1))
    suma_p = sum(pesos)
    # Issue #116 (hallazgo de /code-review): ventas_cantidad es signed desde
    # el #80 -- un mes con devoluciones/notas de credito que superan la venta
    # puede dar rotacion negativa. Sin recortar, el promedio ponderado podia
    # terminar negativo y violar chk_sugerencias_rotacion CHECK (>= 0) al
    # escribir, abortando el batch entero por un solo SKU.
    rotacion_sugerida = max(0.0, sum(p * v for p, v in zip(pesos, valores)) / suma_p)

    # CV sobre todos los valores (sin ponderar — mide variabilidad real del SKU)
    mean = sum(valores) / n
    std  = (sum((v - mean) ** 2 for v in valores) / n) ** 0.5
    # Issue #142: la hoja "Criterios" promete "100% = rotación idéntica todos
    # los meses" -- eso es, literalmente, desvío cero (std=0), sin importar
    # el signo del valor constante. El CV (std/mean) no se puede calcular
    # con mean=0 y antes caía directo al 0% del else -- el caso real de 272
    # SKUs en cero. Usar std==0 en vez de "todos exactamente cero" (code
    # review) generaliza bien: una rotación constante en -10 tiene la MISMA
    # estabilidad que una constante en 0 y merece el mismo 100%, no un 0%
    # solo por el signo. mean=0 por CANCELACION (ej. [-5, 5, 0], std != 0)
    # sigue sin calificar -- eso es inestable de verdad, no "idéntica".
    if std == 0:
        fiabilidad = 100.0
    elif mean > 0:
        cv = std / mean
        fiabilidad = max(0.0, (1.0 - cv) * 100.0)
    else:
        # mean <= 0 con variabilidad real (std != 0): devoluciones/notas de
        # credito (#80) oscilando mes a mes. Sin datos reales para validar
        # este camino (nota del propio issue #142) -- se preserva el
        # comportamiento previo en vez de adivinar una formula nueva.
        fiabilidad = 0.0

    return round(rotacion_sugerida, 4), round(fiabilidad, 2)


def calcular_dias_hasta_quiebre(
    stock_actual: float,
    rotacion_sugerida: float | None,
    fecha_stock: dt.date | None,
    fecha_referencia: dt.date,
    umbral_dias: int = UMBRAL_DIAS_STOCK_VIEJO,
) -> float | None:
    """
    None si no hay rotacion_sugerida (o es <= 0), o si el stock conocido
    tiene más de `umbral_dias` de antigüedad respecto a `fecha_referencia`
    (Issue #116: evita reportar días-hasta-quiebre sobre un stock congelado
    de un SKU que desapareció del feed). Stock negativo se trata como 0.
    """
    if rotacion_sugerida is None or rotacion_sugerida <= 0:
        return None
    if fecha_stock is None or (fecha_referencia - fecha_stock).days > umbral_dias:
        return None
    return round(max(0.0, stock_actual) / rotacion_sugerida, 2)

# ── Cálculo ────────────────────────────────────────────────────────────────────

def calcular_sugerencias(
    conn: pymysql.Connection,
    stock_por_sku: dict[str, tuple[float, dt.date]],
    mes_referencia: tuple[int, int] | None,
    fecha_referencia: dt.date | None = None,
) -> tuple[list[dict], int, int, int, int]:
    """
    Retorna (filas, skus_con_sugerencia, skus_sin_datos, skus_con_quiebre, skus_huerfanos).

    skus_sin_datos: SKUs con < MIN_MESES_CON_DATOS meses utilizables (pero al menos
    1) — se insertan con NULL para que el ON DUPLICATE KEY UPDATE limpie valores
    stale de ciclos anteriores.

    skus_huerfanos (Issue #142): SKUs que YA tienen una fila en planilla_sugerencias
    de una corrida anterior pero este ciclo no aparecen ni siquiera en skus_sin_datos
    -- perdieron TODOS sus meses elegibles (0, no "menos de MIN_MESES_CON_DATOS").
    La garantía de "el upsert limpia valores stale" del docstring de arriba solo
    cubre SKUs que siguen apareciendo en la consulta con al menos una fila; un SKU
    que deja de tener NINGUNA fila elegible nunca entra al loop principal y su fila
    vieja (rotación, modelo, todo) queda huérfana para siempre -- 7 casos reales
    encontrados con el modelo retirado `weighted_avg_13m` (pre-#116), con valores
    en NULL de pura casualidad, no por ningún mecanismo de limpieza.

    mes_referencia: (year, month) a excluir del cálculo. Desde Issue #34, el mes en
    curso puede llegar con estado_mes='normal' (antes solo pasaba en meses cerrados),
    pero su rotacion_diaria_real es parcial — incluirlo sesgaría la sugerencia hacia
    abajo cada vez que el job corra a mitad de mes.

    Incluye meses 'quiebre_parcial' además de 'normal' (Issue #36/#37): con el umbral
    de estado_mes en 100%, cualquier día de quiebre saca a un mes de 'normal', así que
    restringirse solo a 'normal' dejaría a muchos SKUs sin suficientes meses para
    calcular sugerencia. Para 'quiebre_parcial' se usa rotacion_ajustada (ya corregida
    por nivel de frecuencia en run_calc_planilla.py), no rotacion_diaria_real.

    Issue #116: ya no se exige "rotacion > 0" -- un mes normal/quiebre_parcial
    cuenta aunque haya vendido 0, esa es la corrección del issue (ver
    calcular_rotacion_y_fiabilidad).
    """
    fecha_referencia = fecha_referencia or dt.date.today()

    sql = """
        SELECT
            sku, year, month, estado_mes,
            CASE WHEN estado_mes = 'normal' THEN rotacion_diaria_real
                 ELSE rotacion_ajustada
            END AS rotacion_valor
        FROM planilla_ventas_calculada
        WHERE (
                (estado_mes = 'normal' AND rotacion_diaria_real IS NOT NULL)
             OR (estado_mes = 'quiebre_parcial' AND rotacion_ajustada IS NOT NULL)
        )
    """
    params: tuple = ()
    if mes_referencia is not None:
        sql += " AND (year, month) != (%s, %s)"
        params = mes_referencia
    sql += " ORDER BY sku, year DESC, month DESC"

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    # Agrupar por SKU, retener solo los MAX_MESES más recientes (ya vienen DESC)
    por_sku: dict[str, list[float]] = defaultdict(list)
    for sku, _year, _month, _estado, rot in rows:
        vals = por_sku[sku]
        if len(vals) < MAX_MESES:
            vals.append(float(rot))

    filas = []
    skus_con_sugerencia = 0
    skus_sin_datos      = 0
    skus_con_quiebre    = 0

    for sku, valores in por_sku.items():
        rotacion_sugerida, fiabilidad = calcular_rotacion_y_fiabilidad(valores)

        if rotacion_sugerida is None:
            skus_sin_datos += 1
            filas.append({
                "sku":                   sku,
                "rotacion_sugerida":     None,
                "fiabilidad_porcentaje": None,
                "dias_hasta_quiebre":    None,
                "modelo":                MODELO,
            })
            continue

        stock, fecha_stock = stock_por_sku.get(sku, (0.0, None))
        dias_hasta_quiebre = calcular_dias_hasta_quiebre(
            stock, rotacion_sugerida, fecha_stock, fecha_referencia
        )
        if dias_hasta_quiebre is not None:
            skus_con_quiebre += 1

        skus_con_sugerencia += 1
        filas.append({
            "sku":                   sku,
            "rotacion_sugerida":     rotacion_sugerida,
            "fiabilidad_porcentaje": fiabilidad,
            "dias_hasta_quiebre":    dias_hasta_quiebre,
            "modelo":                MODELO,
        })

    # Issue #142: SKUs con fila existente en planilla_sugerencias que este
    # ciclo no tienen NI UN mes elegible (ni siquiera entraron a por_sku) --
    # sin esto, su fila vieja (rotacion/modelo/fiabilidad) queda huerfana
    # para siempre, invisible al loop de arriba.
    #
    # Code review: filtrar por "ya esta limpio" (rotacion_sugerida IS NULL
    # Y modelo ya es el actual) en vez de traer TODOS los sku previos -- sin
    # esto, un SKU discontinuado hace anios se re-selecciona y se re-upsertea
    # (bump de ts_generacion/actualizado_en) en CADA corrida para siempre, y
    # skus_huerfanos deja de distinguir "recien encontrado" de "ya limpio
    # desde hace meses", tapando un pico real de huerfanos nuevos detras del
    # ruido acumulado.
    skus_huerfanos = 0
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sku FROM planilla_sugerencias "
            "WHERE rotacion_sugerida IS NOT NULL OR modelo != %s",
            (MODELO,),
        )
        skus_por_limpiar = {row[0] for row in cur.fetchall()}
    for sku in skus_por_limpiar - por_sku.keys():
        skus_huerfanos += 1
        filas.append({
            "sku":                   sku,
            "rotacion_sugerida":     None,
            "fiabilidad_porcentaje": None,
            "dias_hasta_quiebre":    None,
            "modelo":                MODELO,
        })

    return filas, skus_con_sugerencia, skus_sin_datos, skus_con_quiebre, skus_huerfanos

# ── Escritura atómica ──────────────────────────────────────────────────────────

_SQL_UPSERT = """
    INSERT INTO planilla_sugerencias
        (sku, rotacion_sugerida, fiabilidad_porcentaje, dias_hasta_quiebre,
         modelo, ts_generacion, ts_carga)
    VALUES
        (%(sku)s, %(rotacion_sugerida)s, %(fiabilidad_porcentaje)s,
         %(dias_hasta_quiebre)s, %(modelo)s, NOW(6), NOW(6))
    ON DUPLICATE KEY UPDATE
        rotacion_sugerida     = VALUES(rotacion_sugerida),
        fiabilidad_porcentaje = VALUES(fiabilidad_porcentaje),
        dias_hasta_quiebre    = VALUES(dias_hasta_quiebre),
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
        stock_por_sku  = cargar_stock_actual(conn)
        mes_referencia = cargar_mes_referencia(conn)
        filas, skus_con_sugerencia, skus_sin_datos, skus_con_quiebre, skus_huerfanos = calcular_sugerencias(
            conn, stock_por_sku, mes_referencia
        )
        escribir_sugerencias(conn, filas)

        duracion = round(time.time() - t0, 2)
        detalle  = {
            "subtipo":              "calc_sugerencias",
            "modelo":               MODELO,
            "skus_con_sugerencia":  skus_con_sugerencia,
            "skus_con_quiebre":     skus_con_quiebre,
            "skus_sin_datos":       skus_sin_datos,
            "skus_huerfanos":       skus_huerfanos,
            "filas_upserted":       len(filas),
            "duracion_seg":         duracion,
            "min_meses_con_datos":  MIN_MESES_CON_DATOS,
            "max_meses":            MAX_MESES,
            "mes_referencia_excluido": mes_referencia,
        }
        job_end(conn, job_id, "exitoso", detalle)
        print(
            f"[SUGERENCIAS] OK en {duracion}s — "
            f"{skus_con_sugerencia} SKUs con sugerencia, "
            f"{skus_con_quiebre} con días hasta quiebre, "
            f"{skus_sin_datos} sin datos suficientes, "
            f"{skus_huerfanos} huerfanos limpiados"
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
