#!/usr/bin/env python3
"""
verificar_rotacion_vs_ddstk.py — Issue #116: mide la proporción de artículos
con ROT.S > 2×DDSTK, comparando el criterio de elegibilidad viejo (excluía
meses cerrados con rotación 0) contra el nuevo (los cuenta). Solo lectura,
no escribe nada -- reproduce ambos algoritmos directamente sobre
planilla_ventas_calculada, que ya contiene exactamente la ventana de 13
meses vigente (run_calc_planilla.py la trunca y reconstruye en cada corrida).

Uso (en el contenedor etl, que ya tiene pymysql y las credenciales):
  cat scripts/verificar_rotacion_vs_ddstk.py | docker compose exec -T etl python -
"""

import os
from collections import defaultdict

import pymysql

MIN_MESES_CON_DATOS = 3
MAX_MESES           = 13


def connect():
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "mysql"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ.get("MYSQL_DB", "evalutia"),
    )


def rotacion_sugerida(valores: list[float]) -> float | None:
    n = len(valores)
    if n < MIN_MESES_CON_DATOS:
        return None
    pesos = list(range(n, 0, -1))
    # max(0, ...): mismo recorte que run_calc_sugerencias.py (ventas_cantidad
    # signed desde el #80 puede dar un mes con rotacion neta negativa).
    return max(0.0, sum(p * v for p, v in zip(pesos, valores)) / sum(pesos))


def main() -> None:
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT sku, year, month, estado_mes, rotacion_diaria_real, rotacion_ajustada,
               ventas_cantidad, dias_con_stock
        FROM planilla_ventas_calculada
        ORDER BY sku, year DESC, month DESC
        """
    )
    rows = cur.fetchall()

    cur.execute("SELECT year, month FROM planilla_ventas_calculada ORDER BY year DESC, month DESC LIMIT 1")
    ref = cur.fetchone()
    conn.close()

    por_sku = defaultdict(list)
    for r in rows:
        por_sku[r[0]].append(r)

    total_comparables = 0
    viejo_mayor_2x     = 0
    nuevo_mayor_2x     = 0
    nuevo_gana_sugerencia = 0  # SKUs sin ROT.S bajo el criterio viejo, con ROT.S bajo el nuevo

    for filas in por_sku.values():
        # DDSTK: suma sobre TODAS las filas del SKU en la ventana (incluye mes de referencia)
        sum_v = sum(f[6] for f in filas)
        sum_d = sum(f[7] for f in filas)
        ddstk = (sum_v / sum_d) if sum_d else None
        if not ddstk:
            continue

        elegibles_viejo: list[float] = []
        elegibles_nuevo: list[float] = []
        for _sku, year, month, estado, rot_real, rot_aj, *_resto in filas:
            if ref and (year, month) == ref:
                continue
            valor = None
            if estado == "normal" and rot_real is not None:
                valor = float(rot_real)
            elif estado == "quiebre_parcial" and rot_aj is not None:
                valor = float(rot_aj)
            if valor is None:
                continue
            if len(elegibles_nuevo) < MAX_MESES:
                elegibles_nuevo.append(valor)
            if valor > 0 and len(elegibles_viejo) < MAX_MESES:
                elegibles_viejo.append(valor)

        rots_viejo = rotacion_sugerida(elegibles_viejo)
        rots_nuevo = rotacion_sugerida(elegibles_nuevo)

        if rots_viejo is None and rots_nuevo is not None:
            nuevo_gana_sugerencia += 1

        if rots_viejo is None:
            continue
        total_comparables += 1
        if rots_viejo > 2 * ddstk:
            viejo_mayor_2x += 1
        if rots_nuevo is not None and rots_nuevo > 2 * ddstk:
            nuevo_mayor_2x += 1

    print(f"SKUs comparables (ROT.S viejo + DDSTK calculables): {total_comparables}")
    if total_comparables:
        pct_viejo = 100 * viejo_mayor_2x / total_comparables
        pct_nuevo = 100 * nuevo_mayor_2x / total_comparables
        print(f"  Criterio VIEJO -- ROT.S > 2xDDSTK: {viejo_mayor_2x} ({pct_viejo:.1f}%)")
        print(f"  Criterio NUEVO -- ROT.S > 2xDDSTK: {nuevo_mayor_2x} ({pct_nuevo:.1f}%)")
    print(f"SKUs que ganan sugerencia con el criterio nuevo (antes NULL por < {MIN_MESES_CON_DATOS} meses): {nuevo_gana_sugerencia}")


if __name__ == "__main__":
    main()
