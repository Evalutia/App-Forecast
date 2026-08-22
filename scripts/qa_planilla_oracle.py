#!/usr/bin/env python3
"""
qa_planilla_oracle.py — Oráculo de QA de la planilla de reposición (Issue #108).

Reproduce desde las tablas CRUDAS (ventas_historicas, stock_diario, articulos,
configuracion_sistema) cada número que la planilla exportada muestra para un
set de SKUs testigo, y lo compara contra lo persistido por el pipeline
(planilla_ventas_calculada, planilla_sugerencias). Solo SELECTs — no escribe.

Las fórmulas replicadas son las de run_calc_planilla.py / run_calc_sugerencias.py
/ exportPlanilla.ts; si este script y el pipeline divergen, gana el diagnóstico:
no parchear acá (criterio de #108: discrepancia => issue nuevo).

Uso (en el contenedor etl, que ya tiene pymysql y las credenciales):
  cat scripts/qa_planilla_oracle.py | docker compose exec -T etl python - [SKU ...]
Sin argumentos usa: I02418 + selección automática de perfiles (alta frecuencia
estable, baja frecuencia con quiebre, alta reciente con sin_datos).
"""

import calendar
import datetime as dt
import os
import sys

import pymysql

TOL = 0.01  # tolerancia por redondeos (valores almacenados con 2-4 decimales)

# Umbrales (mismos defaults que run_calc_planilla.py; los de tickets se pisan
# con configuracion_sistema, #67)
FREQ_ALTA_MIN, FREQ_BAJA_MAX = 9, 3
TICKETS_BAJO_MAX, TICKETS_ALTO_MIN = 2, 5
MIN_MESES_CON_DATOS, MAX_MESES = 3, 13
UMBRAL_DIAS_STOCK_VIEJO = 7  # Issue #116, mismo umbral que run_calc_sugerencias.py
MAX_DIAS_HASTA_QUIEBRE = 999.99  # Issue #183, mismo cap que run_calc_sugerencias.py


def connect():
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "mysql"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ.get("MYSQL_DB", "evalutia"),
    )


def dias_mes(y, m):
    return calendar.monthrange(y, m)[1]


def idx2ym(idx):
    return (idx - 1) // 12, (idx - 1) % 12 + 1


def ok(cond):
    return "OK" if cond else "**MISMATCH**"


def feq(a, b, tol=TOL):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def main():
    conn = connect()
    cur = conn.cursor()

    # ── Ventana global y configuración ─────────────────────────────────────────
    cur.execute("SELECT MIN(year*12+month), MAX(year*12+month) FROM planilla_ventas_calculada")
    mn, mx = cur.fetchone()
    ventana = [idx2ym(i) for i in range(mn, mx + 1)]
    ref = ventana[-1]
    cerrados = ventana[:-1]
    print(f"Ventana: {ventana[0][0]}-{ventana[0][1]:02d} .. {ref[0]}-{ref[1]:02d} "
          f"({len(ventana)} meses; referencia {ref[0]}-{ref[1]:02d})\n")

    global TICKETS_BAJO_MAX, TICKETS_ALTO_MIN
    cur.execute("SELECT clave, valor FROM configuracion_sistema "
                "WHERE clave IN ('tickets_bajo_max','tickets_alto_min')")
    cfg = dict(cur.fetchall())
    TICKETS_BAJO_MAX = int(cfg.get("tickets_bajo_max", TICKETS_BAJO_MAX))
    TICKETS_ALTO_MIN = int(cfg.get("tickets_alto_min", TICKETS_ALTO_MIN))
    print(f"Umbrales de tickets vigentes: bajo<={TICKETS_BAJO_MAX}, alto>={TICKETS_ALTO_MIN}\n")

    # ── Selección de SKUs testigo ──────────────────────────────────────────────
    skus = sys.argv[1:]
    if not skus:
        skus = ["I02418"]
        # alta frecuencia estable: frecuencia alta en mes de referencia + mejor fiabilidad
        cur.execute(
            "SELECT p.sku FROM planilla_ventas_calculada p "
            "JOIN planilla_sugerencias s ON s.sku=p.sku "
            "WHERE p.year=%s AND p.month=%s AND p.frecuencia_nivel='alta' "
            "  AND s.fiabilidad_porcentaje IS NOT NULL AND p.sku<>'I02418' "
            "ORDER BY s.fiabilidad_porcentaje DESC LIMIT 1", ref)
        skus += [r[0] for r in cur.fetchall()]
        # baja frecuencia con quiebre: nivel baja + al menos un mes quiebre_parcial
        cur.execute(
            "SELECT p.sku FROM planilla_ventas_calculada p "
            "WHERE p.frecuencia_nivel='baja' AND p.estado_mes='quiebre_parcial' "
            "  AND p.sku NOT IN (%s,%s) "
            "GROUP BY p.sku ORDER BY COUNT(*) DESC, p.sku LIMIT 1", (skus[0], skus[-1]))
        skus += [r[0] for r in cur.fetchall()]
        # alta reciente: menos meses presentes (ejercita sin_datos de #106)
        cur.execute(
            "SELECT sku FROM planilla_ventas_calculada GROUP BY sku "
            "ORDER BY COUNT(*) ASC, sku LIMIT 1")
        skus += [r[0] for r in cur.fetchall()]
    print("SKUs testigo:", ", ".join(skus), "\n")

    fallas_total = 0
    for sku in skus:
        fallas_total += verificar_sku(cur, sku, ventana, cerrados, ref)

    # ── Chequeo global: fiabilidad acotada ─────────────────────────────────────
    cur.execute("SELECT MIN(fiabilidad_porcentaje), MAX(fiabilidad_porcentaje), COUNT(*) "
                "FROM planilla_sugerencias WHERE fiabilidad_porcentaje IS NOT NULL")
    fmin, fmax, n = cur.fetchone()
    en_rango = 0 <= float(fmin) and float(fmax) <= 100
    print(f"\n## Global: fiabilidad_porcentaje en [{fmin}, {fmax}] sobre {n} SKUs -> {ok(en_rango)}")
    fallas_total += 0 if en_rango else 1

    print(f"\n=== RESULTADO: {'TODO OK' if fallas_total == 0 else f'{fallas_total} MISMATCH(es)'} ===")
    conn.close()
    sys.exit(0 if fallas_total == 0 else 2)


def verificar_sku(cur, sku, ventana, cerrados, ref):
    print(f"\n## SKU {sku}")
    fallas = 0

    cur.execute("SELECT descripcion, estado, stock_minimo, fec_alta, "
                "factor_mes_01,factor_mes_02,factor_mes_03,factor_mes_04,factor_mes_05,factor_mes_06,"
                "factor_mes_07,factor_mes_08,factor_mes_09,factor_mes_10,factor_mes_11,factor_mes_12 "
                "FROM articulos WHERE sku=%s", (sku,))
    art = cur.fetchone()
    if not art:
        print("  (no existe en articulos)")
        return 1
    descripcion, estado_art, stock_min, fec_alta, *factores_raw = art
    fec_alta = fec_alta.date() if fec_alta else None
    factores = {i + 1: (float(f) if f is not None else None) for i, f in enumerate(factores_raw)}
    print(f"  {descripcion} | Estado Art.={estado_art} | stock_minimo={stock_min} | fec_alta={fec_alta}")

    # ── Filas almacenadas del pipeline ─────────────────────────────────────────
    cur.execute("SELECT year, month, ventas_cantidad, dias_con_stock, dias_naturales_mes, "
                "rotacion_diaria_real, rotacion_diaria_desestacionalizada, estado_mes, "
                "frecuencia_nivel, rotacion_ajustada, tickets_mes, valor_historico, "
                "valor_ajustado, criterio_frecuencia, venta_o_extrapolacion, "
                "ingreso_durante_quiebre "
                "FROM planilla_ventas_calculada WHERE sku=%s ORDER BY year, month", (sku,))
    stored = {(r[0], r[1]): r for r in cur.fetchall()}
    faltantes = [ym for ym in ventana if ym not in stored]
    print(f"  Meses presentes: {len(stored)}/{len(ventana)}"
          + (f" (sin_datos en API/export para: {faltantes})" if faltantes else ""))

    # ── Recomputo desde tablas crudas ──────────────────────────────────────────
    y0, m0 = ventana[0]
    desde = dt.date(y0, m0, 1)
    hasta = dt.date(ref[0], ref[1], dias_mes(*ref))
    cur.execute("SELECT YEAR(fecha), MONTH(fecha), SUM(cantidad), "
                "COUNT(DISTINCT CASE WHEN cantidad<>0 THEN fecha END) "
                "FROM ventas_historicas WHERE sku=%s AND fecha BETWEEN %s AND %s "
                "GROUP BY YEAR(fecha), MONTH(fecha)", (sku, desde, hasta))
    raw_v = {(y, m): (int(v or 0), int(t or 0)) for y, m, v, t in cur.fetchall()}
    cur.execute("SELECT yr, mo, COUNT(*) FROM ("
                "  SELECT YEAR(fecha) yr, MONTH(fecha) mo, fecha, SUM(cantidad) tot "
                "  FROM stock_diario WHERE sku=%s AND fecha BETWEEN %s AND %s "
                "  GROUP BY fecha) d WHERE d.tot > %s GROUP BY yr, mo",
                (sku, desde, hasta, stock_min or 0))
    raw_ds = {(y, m): int(c) for y, m, c in cur.fetchall()}

    # Issue #145/#164: detalle día a día (no el agregado de arriba) para poder
    # detectar si el stock pasó de "sin stock" a "con stock" en algún punto del
    # mes -- mismo criterio que detectar_ingreso_durante_mes() en
    # run_calc_planilla.py: el umbral de "sin stock" es stock<=stock_minimo
    # (no stock<=0 literal, corregido en #164 -- 88% del catálogo tiene
    # stock_minimo>0, así que el umbral viejo dejaba el flag inalcanzable
    # para la mayoría de los SKUs).
    cur.execute("SELECT fecha, SUM(cantidad) FROM stock_diario "
                "WHERE sku=%s AND fecha BETWEEN %s AND %s GROUP BY fecha ORDER BY fecha",
                (sku, desde, hasta))
    dias_stock_diario = list(cur.fetchall())
    raw_ingreso: dict[tuple, bool] = {}
    for ym in ventana:
        y, m = ym
        serie = [float(t) for f, t in dias_stock_diario if (f.year, f.month) == ym]
        sin_stock, ingreso = False, False
        for stock in serie:
            if stock <= (stock_min or 0):
                sin_stock = True
            elif sin_stock:
                ingreso = True
                break
        raw_ingreso[ym] = ingreso

    # Histórico (promedio de meses cerrados disponibles según fec_alta)
    disponibles = [ym for ym in cerrados
                   if fec_alta is None or fec_alta <= dt.date(ym[0], ym[1], dias_mes(*ym))]
    historico = (round(sum(raw_v.get(ym, (0, 0))[0] for ym in disponibles) / len(disponibles), 2)
                 if disponibles else None)

    # Frecuencia anual (meses cerrados con ventas > 0)
    n_con_ventas = sum(1 for ym in cerrados if raw_v.get(ym, (0, 0))[0] > 0)
    nivel = ("alta" if n_con_ventas >= FREQ_ALTA_MIN
             else "baja" if n_con_ventas <= FREQ_BAJA_MAX else "media")

    # ── Comparación mes a mes ──────────────────────────────────────────────────
    for ym in sorted(stored):
        y, m = ym
        (s_vta, s_ds, s_dn, s_rot, s_rde, s_est, s_niv, s_raj, s_tick, s_hist,
         s_vaj, s_crit, s_ve, s_ingreso) = stored[ym][2:]
        r_vta, r_tick = raw_v.get(ym, (0, 0))
        r_ds = raw_ds.get(ym, 0)
        dn = dias_mes(y, m)
        es_ref = ym == ref

        if es_ref:
            r_est = "normal" if r_ds > 0 else "sin_stock"
        else:
            r_est = ("sin_stock" if r_ds == 0
                     else "normal" if r_ds >= dn else "quiebre_parcial")
        r_rot = round(r_vta / r_ds, 4) if r_ds > 0 else None
        f = factores.get(m)
        r_rde = round(r_rot / f, 4) if (r_rot is not None and f) else None
        r_raj = None
        if r_est == "quiebre_parcial":
            if nivel == "alta":
                r_raj = round(r_vta / r_ds, 4) if r_ds > 0 else None
            elif nivel == "baja":
                r_raj = round(r_vta / dn, 4)
            else:
                r_raj = (round(r_vta / dn, 4) if r_ds == 0
                         else round((r_vta / r_ds + r_vta / dn) / 2, 4))

        # Blending. Issue #129: la extrapolacion pondera por cuanto del mes se
        # pudo observar -- ventas * (2 - dias_con_stock/dias_naturales) -- en vez
        # de proyectar el ritmo de los dias con stock al mes entero. Replica
        # exacta de extrapolacion_mes() en run_calc_planilla.py; si divergen,
        # este oraculo reporta mismatches falsos en todos los meses con quiebre.
        if r_ds <= 0 or dn <= 0:
            extrap = None
        elif r_vta <= 0:
            extrap = float(r_vta)
        else:
            extrap = round(r_vta * (2 - r_ds / dn), 2)
        es_quiebre = r_est != "normal"
        # Issue #137: "V/E" (venta real o extrapolacion) -- None para
        # sin_stock siempre (mismo criterio que venta_o_extrapolacion() en
        # run_calc_planilla.py), vta real si no hubo quiebre, extrap si lo
        # hubo. r_ds<=0 <=> sin_stock (invariante ya verificado: quiebre_parcial
        # siempre tiene dias_con_stock>0), asi que "extrap if es_quiebre" ya
        # da None para sin_stock sin necesitar un caso aparte.
        r_ve = extrap if es_quiebre else float(r_vta)
        if es_quiebre and extrap is None:
            r_vaj, r_crit = ((round(historico, 2), "historico") if historico is not None
                             else (round(float(r_vta), 2), "real_extrapolado"))
        else:
            vnh = extrap if es_quiebre else float(r_vta)
            if r_tick >= TICKETS_ALTO_MIN or historico is None:
                r_vaj, r_crit = round(vnh, 2), "real_extrapolado"
            elif r_tick <= TICKETS_BAJO_MAX:
                r_vaj, r_crit = round(historico, 2), "historico"
            else:
                r_vaj, r_crit = round((historico + vnh) / 2, 2), "promedio"

        checks = [
            ("vta", s_vta, r_vta, int(s_vta) == r_vta),
            ("dias_stock", s_ds, r_ds, int(s_ds) == r_ds),
            ("tickets", s_tick, r_tick, int(s_tick) == r_tick),
            ("estado", s_est, r_est, s_est == r_est),
            ("rot", s_rot, r_rot, feq(s_rot, r_rot)),
            ("rot_desest", s_rde, r_rde, feq(s_rde, r_rde)),
            ("rot_ajust", s_raj, r_raj, feq(s_raj, r_raj)),
            ("hist", s_hist, historico, feq(s_hist, historico)),
            ("vaj", s_vaj, r_vaj, feq(s_vaj, r_vaj)),
            ("criterio", s_crit, r_crit, s_crit == r_crit),
            ("venta_o_extrap", s_ve, r_ve, feq(s_ve, r_ve)),
            ("ingreso_quiebre", bool(s_ingreso), r_est == "quiebre_parcial" and raw_ingreso.get(ym, False),
             bool(s_ingreso) == (r_est == "quiebre_parcial" and raw_ingreso.get(ym, False))),
        ]
        malos = [c for c in checks if not c[3]]
        for nombre, sv, rv, _bien in malos:
            print(f"    {y}-{m:02d} {nombre}: almacenado={sv} recomputado={rv} -> MISMATCH")
        fallas += len(malos)
    if fallas == 0:
        print(f"  Meses: {len(stored)} filas x 12 campos verificados contra tablas crudas -> OK")
    niv_ref = stored.get(ref, [None] * 9)[8] if ref in stored else None
    if niv_ref is not None and niv_ref != nivel:
        print(f"    frecuencia_nivel: almacenado={niv_ref} recomputado={nivel} -> MISMATCH")
        fallas += 1

    # ── Columnas resumen del export (fórmulas de exportPlanilla.ts sobre lo
    #    almacenado; lo almacenado ya quedó verificado contra crudo arriba) ─────
    meses_orden = [stored[ym] for ym in sorted(stored)]
    ult_es_ref = sorted(stored)[-1] == ref if stored else False
    excl_ult = meses_orden[:-1] if ult_es_ref else meses_orden  # sin_datos al final no llega a stored

    vta_total = sum(int(r[2]) for r in excl_ult)
    sum_v = sum(int(r[2]) for r in meses_orden)
    sum_d = sum(int(r[3]) for r in meses_orden)
    ddstk = round(sum_v / sum_d, 4) if sum_d else None
    vals = []
    for r in excl_ult:
        est, rde, raj, rot = r[7], r[6], r[9], r[5]
        if est == "normal" and rde is not None:
            vals.append(float(rde))
        elif est == "quiebre_parcial" and raj is not None:
            if rde is not None and rot and float(rot) > 0:
                vals.append(float(raj) * (float(rde) / float(rot)))
            else:
                vals.append(float(raj))
    rot_desestac = round(sum(vals) / len(vals), 4) if vals else None
    print(f"  Resumen export: VTA={vta_total} DDSTK={ddstk} RotDesEstac={rot_desestac} "
          f"EstadoArt={estado_art} frecuencia={nivel} ({n_con_ventas} meses c/venta)")

    # ── ROT.S / Fiabilidad / QBK (algoritmo de run_calc_sugerencias.py) ────────
    # Issue #116: un mes normal/quiebre_parcial cuenta aunque haya vendido 0
    # -- ya no se exige "> 0" (ver mismo comentario en run_calc_sugerencias.py).
    #
    # fecha de referencia para la guarda de stock viejo: se usa ts_generacion
    # (cuando el pipeline calculo por ultima vez), no la fecha de HOY -- si
    # corremos el oraculo dias despues de la ultima corrida del job, comparar
    # contra "hoy" da un MISMATCH falso por el solo paso del tiempo, no por un
    # bug real (hallazgo de /code-review).
    cur.execute("SELECT rotacion_sugerida, fiabilidad_porcentaje, dias_hasta_quiebre, ts_generacion "
                "FROM planilla_sugerencias WHERE sku=%s", (sku,))
    sug_row = cur.fetchone() or (None, None, None, None)
    sug = sug_row[:3]
    fecha_ref_qbk = sug_row[3].date() if sug_row[3] else dt.date.today()

    elegibles = []
    meses_elegibles = []
    for ym in sorted(stored, reverse=True):
        if ym == ref:
            continue
        r = stored[ym]
        est, rot, raj = r[7], r[5], r[9]
        v = (float(rot) if est == "normal" and rot is not None
             else float(raj) if est == "quiebre_parcial" and raj is not None
             else None)
        if v is not None and len(elegibles) < MAX_MESES:
            elegibles.append(v)
            meses_elegibles.append(ym)
    if len(elegibles) < MIN_MESES_CON_DATOS:
        r_rots = r_fiab = r_qbk = None
    else:
        n = len(elegibles)
        # Issue #181: pesos por distancia calendario real desde `ref`, no por
        # posicion en la lista -- mismo criterio que
        # _pesos_por_distancia_calendario() en run_calc_sugerencias.py (ver
        # ahi el razonamiento completo). Sin esto el oraculo diverge del
        # pipeline real para cualquier SKU con meses elegibles no
        # consecutivos, y reporta un MISMATCH falso en ROT.S.
        ref_ordinal = ref[0] * 12 + ref[1]
        distancias = [ref_ordinal - (yr * 12 + mo) for yr, mo in meses_elegibles]
        max_distancia = max(distancias)
        pesos = [max_distancia - d + 1 for d in distancias]
        # max(0, ...): mismo recorte que run_calc_sugerencias.py (hallazgo de
        # /code-review -- ventas_cantidad signed puede dar un mes con
        # rotacion neta negativa, y chk_sugerencias_rotacion exige >= 0).
        r_rots = round(max(0.0, sum(p * v for p, v in zip(pesos, elegibles)) / sum(pesos)), 4)
        mean = sum(elegibles) / n
        if mean > 0:
            cv = (sum((v - mean) ** 2 for v in elegibles) / n) ** 0.5 / mean
            r_fiab = round(max(0.0, (1.0 - cv) * 100.0), 2)
        else:
            r_fiab = 0.0
        cur.execute("SELECT SUM(cantidad), MAX(fecha) FROM stock_diario "
                    "WHERE sku=%s AND fecha=(SELECT MAX(fecha) FROM stock_diario WHERE sku=%s)",
                    (sku, sku))
        stock_row = cur.fetchone()
        stock = max(0.0, float(stock_row[0] or 0))
        fecha_stock = stock_row[1]
        # Issue #116: QBK es None si el stock conocido esta mas viejo que el umbral
        stock_fresco = fecha_stock is not None and (fecha_ref_qbk - fecha_stock).days <= UMBRAL_DIAS_STOCK_VIEJO
        # Issue #183: mismo cap que run_calc_sugerencias.py -- sin esto, un
        # SKU con rotacion minima y stock alto (el caso que ese ticket
        # corrige) queda con el valor real sin acotar aca, y el oraculo
        # reporta un MISMATCH falso contra el valor ya acotado en la DB.
        r_qbk = (min(MAX_DIAS_HASTA_QUIEBRE, round(stock / r_rots, 2))
                 if r_rots > 0 and stock_fresco else None)
    for nombre, sv, rv, tol in [("ROT.S", sug[0], r_rots, TOL),
                                ("Fiabilidad", sug[1], r_fiab, 0.5),
                                ("QBK", sug[2], r_qbk, 1.0)]:
        bien = feq(sv, rv, tol)
        print(f"  {nombre}: almacenado={sv} recomputado={rv} -> {ok(bien)}")
        fallas += 0 if bien else 1

    return fallas


if __name__ == "__main__":
    main()
