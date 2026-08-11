#!/usr/bin/env python3
"""
diagnostico_planillas_cliente.py — Issue #127.

Contrasta las planillas de reposición que emite el sistema del cliente contra
lo que calculamos nosotros, y produce las tres salidas que el issue pide:

  1. Coincidencia de datos base (venta mensual) por SKU y mes.
  2. Denominador de SU rotación mensual: ¿divide por días naturales del mes o
     por días con stock? Se resuelve por dos vías independientes -- despeje
     sobre los meses con quiebre (ver `clasificar_hipotesis`) y, cuando el
     archivo lo trae, comprobación directa contra sus propias columnas
     `C/STK`/`VTA`/`DDSTK`.
  3. Brecha entre nuestra ROT.S y su columna `Rot. Manual`, la rotación que la
     persona que arma el pedido elige a mano. Es el criterio experto, no la
     verdad: interesa la magnitud y el patrón del desvío, no un veredicto.

Solo lectura: no escribe nada en la base ni toca los archivos.

Requiere `openpyxl` además de `pymysql` (ver services/etl/requirements-dev.txt).
La imagen del contenedor etl NO trae openpyxl, así que la forma práctica de
correrlo es desde el host, apuntando a la base que se quiera analizar:

  MYSQL_HOST=... MYSQL_PORT=... MYSQL_USER=... MYSQL_PASSWORD=... \
    python3 scripts/diagnostico_planillas_cliente.py

Contra producción, con un túnel al MySQL de la VM:

  ssh -f -N -L 13307:localhost:3307 <vm>
  MYSQL_HOST=127.0.0.1 MYSQL_PORT=13307 ... python3 scripts/diagnostico_planillas_cliente.py

**Correrlo contra una réplica con `stock_diario` incompleto da resultados
equivocados**: los días faltantes de un mes se leen como días sin stock y
fabrican meses "con quiebre" inexistentes. Pasó al escribir este script y llegó
a invertir el veredicto (#127), así que ahora esos meses se detectan y se
excluyen -- pero conviene igual mirar el aviso de cobertura que imprime.

Con las planillas en otra ubicación:
  PLANILLAS_DIR=/ruta/a/los/xlsx python3 scripts/diagnostico_planillas_cliente.py
"""

import glob
import os
import statistics
from collections import defaultdict

import pymysql

# openpyxl se importa dentro de leer_planilla(), no acá: las funciones puras de
# este módulo (y sus tests) no necesitan leer Excel, y la imagen del contenedor
# etl no lo trae. Un import de módulo rompería la colección de toda la suite en
# un entorno sin la librería, no sólo la de estos tests.

DIR_POR_DEFECTO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "fixtures", "planillas_cliente")

MESES_ES = {m: i for i, m in enumerate(
    ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"], start=1)}

# El cliente publica sus rotaciones redondeadas a 4 decimales. La tolerancia es
# relativa porque el error de reconstrucción escala con la magnitud del valor:
# una absoluta dejaría fuera a los SKUs de rotación alta.
TOL_REL = 0.002
TOL_ABS = 0.0002


def coincide(a: float, b: float) -> bool:
    return abs(a - b) <= max(TOL_ABS, TOL_REL * abs(b))


# ── Funciones puras ───────────────────────────────────────────────────────────

def parse_mes(label) -> tuple[int, int] | None:
    """
    'Vta.Jul/25' o 'Jul/25' -> (2025, 7). None si no es una etiqueta de mes.
    Las ventanas difieren entre planillas (FONENG arranca un mes después que
    las otras dos), así que se parsea de los headers en vez de hardcodearse.
    """
    if not isinstance(label, str):
        return None
    txt = label.strip()
    if txt.startswith("Vta."):
        txt = txt[4:]
    if "/" not in txt:
        return None
    mes, _, anio = txt.partition("/")
    if mes not in MESES_ES or not anio.isdigit():
        return None
    return (2000 + int(anio) if len(anio) == 2 else int(anio), MESES_ES[mes])


def factor_implicito(vta: float, rot_cliente: float, dias: int) -> float | None:
    """
    Despeja el factor estacional que el cliente aplicó, asumiendo que su
    rotación es (vta / dias) / factor. `dias` es el denominador de la hipótesis
    que se esté probando. None si no se puede despejar -- incluida venta nula o
    negativa, que daría un factor 0 o negativo y contaminaría la calibración.
    """
    if not rot_cliente or dias <= 0 or vta is None or vta <= 0:
        return None
    return (vta / dias) / rot_cliente


def mes_con_stock_incompleto(dias_nat: int, dias_observados: int | None) -> bool:
    """
    True si el "quiebre" de ese mes puede ser en realidad falta de datos:
    nuestro stock_diario no tiene una fila por cada día del mes, así que los
    días ausentes se leen como días sin stock.

    Pasó de verdad (#127): la réplica local sólo tenía stock hasta el 14 de
    julio y eso fabricó 75 meses "con quiebre" inexistentes que invertían el
    veredicto. Esos meses no discriminan nada y se excluyen.
    """
    if dias_observados is None:
        return False
    return dias_observados < dias_nat


def clasificar_hipotesis(vta: float, rot_cliente: float, dias_con_stock: int,
                         dias_nat: int, factor: float | None) -> str:
    """
    Para un mes CON quiebre (dias_con_stock < dias_nat), determina qué
    denominador reproduce la rotación publicada por el cliente:

      'naturales'  -> (vta / dias_naturales) / factor
      'con_stock'  -> (vta / dias_con_stock) / factor
      'ambiguo'    -> las dos dan lo mismo (no discrimina)
      'ninguna'    -> ninguna reproduce el valor observado

    Requiere el factor estacional ya calibrado; sin él no hay nada que decidir.
    """
    if factor is None or factor == 0 or rot_cliente is None:
        return "ninguna"
    if dias_nat <= 0 or dias_con_stock <= 0:
        return "ninguna"

    ok_nat = coincide((vta / dias_nat) / factor, rot_cliente)
    ok_stk = coincide((vta / dias_con_stock) / factor, rot_cliente)

    if ok_nat and ok_stk:
        return "ambiguo"
    if ok_nat:
        return "naturales"
    if ok_stk:
        return "con_stock"
    return "ninguna"


# ── Lectura de las planillas ──────────────────────────────────────────────────

def leer_planilla(path: str) -> dict:
    """
    {sku: {'vta': {(y,m): float}, 'rot': {(y,m): float|None},
           'rot_desestac': float|None, 'rot_manual': float|None,
           'dias_con_stock': float|None, 'vta_total': float|None,
           'ddstk': float|None}}

    Los tres últimos sólo aparecen en los `rot-ok` (columnas `C/STK`, `VTA` y
    `DDSTK`): son los días con stock acumulados de la ventana de 360 días del
    cliente, y permiten comprobar directamente lo que la salida 2 deduce por
    despeje.
    """
    import openpyxl  # diferido a propósito, ver nota del encabezado

    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)["Ventas"]
    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        return {}

    col_vta, col_rot, sueltas = {}, {}, {}
    for idx, h in enumerate(filas[0]):
        if not isinstance(h, str):
            continue
        etiqueta = h.strip()
        if etiqueta in ("Rotacion DesEstac.", "Rot. Manual", "C/STK", "VTA", "DDSTK"):
            sueltas.setdefault(etiqueta, idx)   # setdefault: 'SIN STOCK' aparece repetida
        elif etiqueta.startswith("Vta."):
            if (ym := parse_mes(etiqueta)):
                col_vta[ym] = idx
        elif (ym := parse_mes(etiqueta)):
            col_rot[ym] = idx

    def num(fila, idx):
        if idx is None or idx >= len(fila):
            return None
        v = fila[idx]
        return float(v) if isinstance(v, (int, float)) else None

    datos = {}
    for fila in filas[1:]:
        sku = fila[0]
        if not sku:
            continue
        datos[str(sku).strip()] = {
            "vta": {ym: (num(fila, i) or 0.0) for ym, i in col_vta.items()},
            "rot": {ym: num(fila, i) for ym, i in col_rot.items()},
            "rot_desestac": num(fila, sueltas.get("Rotacion DesEstac.")),
            "rot_manual": num(fila, sueltas.get("Rot. Manual")),
            "dias_con_stock": num(fila, sueltas.get("C/STK")),
            "vta_total": num(fila, sueltas.get("VTA")),
            "ddstk": num(fila, sueltas.get("DDSTK")),
        }
    return datos


def pares_de_planillas(directorio: str) -> list[tuple[str, str, str | None]]:
    """[(nombre_pedido, path_bruto, path_rot_ok)] descubiertos en el directorio."""
    pares = []
    for bruto in sorted(glob.glob(os.path.join(directorio, "*_bruto.*"))):
        base = os.path.basename(bruto).rsplit("_bruto.", 1)[0]
        rot_ok = glob.glob(os.path.join(directorio, base + "_rot-ok.*"))
        pares.append((base, bruto, rot_ok[0] if rot_ok else None))
    return pares


# ── Lectura de producción ─────────────────────────────────────────────────────

def db_connect():
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "mysql"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ.get("MYSQL_DB", "evalutia"),
    )


def cargar_cobertura_stock(conn) -> tuple[object, object]:
    """(primera, ultima) fecha con registro en stock_diario, para detectar los
    meses que la base cubre sólo en parte."""
    with conn.cursor() as cur:
        cur.execute("SELECT MIN(fecha), MAX(fecha) FROM stock_diario")
        return cur.fetchone()


def cargar_nuestros_datos(conn, skus: set[str]) -> tuple[dict, dict, dict]:
    """(por_sku_mes, factores, sugerencias) para los SKUs pedidos."""
    if not skus:
        return {}, {}, {}
    marcas = ",".join(["%s"] * len(skus))
    args = list(skus)

    por_sku_mes, factores, sugerencias = {}, {}, {}
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT sku, year, month, ventas_cantidad, dias_con_stock,
                   dias_naturales_mes, rotacion_diaria_real,
                   rotacion_diaria_desestacionalizada, estado_mes
            FROM planilla_ventas_calculada WHERE sku IN ({marcas})
        """, args)
        for sku, y, m, vq, ds, dn, rot, rot_des, estado in cur.fetchall():
            por_sku_mes[(sku, y, m)] = {
                "vta": float(vq or 0), "ds": int(ds or 0), "dn": int(dn or 0),
                "rot": float(rot) if rot is not None else None,
                "rot_desestac": float(rot_des) if rot_des is not None else None,
                "estado": estado,
            }

        cols = ", ".join(f"factor_mes_{i:02d}" for i in range(1, 13))
        cur.execute(f"SELECT sku, {cols} FROM articulos WHERE sku IN ({marcas})", args)
        for fila in cur.fetchall():
            factores[fila[0]] = {i: (float(f) if f else None)
                                 for i, f in enumerate(fila[1:], start=1)}

        cur.execute(f"SELECT sku, rotacion_sugerida FROM planilla_sugerencias "
                    f"WHERE sku IN ({marcas})", args)
        for sku, rots in cur.fetchall():
            sugerencias[sku] = float(rots) if rots is not None else None

    return por_sku_mes, factores, sugerencias


# ── Salidas ───────────────────────────────────────────────────────────────────

def pct(n, d):
    return f"{100 * n / d:5.1f}%" if d else "    -"


def salida_1_datos_base(planillas, nuestros):
    print("\n" + "=" * 78)
    print("1 · COINCIDENCIA DE DATOS BASE (venta mensual)")
    print("=" * 78)
    tot = ok = sin_fila = 0
    tipos = defaultdict(int)
    skus_con_dif = set()
    for pedido, datos in planillas.items():
        p_tot = p_ok = p_sin = 0
        for sku, d in datos.items():
            for ym, vta in d["vta"].items():
                nuestro = nuestros.get((sku, ym[0], ym[1]))
                p_tot += 1
                if nuestro is None:
                    p_sin += 1
                    continue
                if abs(nuestro["vta"] - vta) < 0.5:
                    p_ok += 1
                else:
                    skus_con_dif.add(sku)
                    if vta == 0:
                        tipos["cliente en 0, nosotros > 0"] += 1
                    elif nuestro["vta"] == 0:
                        tipos["nosotros en 0, cliente > 0"] += 1
                    else:
                        tipos["ambos > 0, distintos"] += 1
        print(f"  {pedido:34s} {pct(p_ok, p_tot - p_sin)} de {p_tot - p_sin:5d} comparables"
              f"   ({p_sin} sin fila nuestra)")
        tot += p_tot; ok += p_ok; sin_fila += p_sin
    print(f"  {'TOTAL':34s} {pct(ok, tot - sin_fila)} de {tot - sin_fila:5d} comparables")
    total_dif = sum(tipos.values())
    if total_dif:
        print(f"  Naturaleza de las {total_dif} diferencias ({len(skus_con_dif)} SKUs afectados):")
        for k, v in sorted(tipos.items(), key=lambda x: -x[1]):
            print(f"    {k:28s} {v:5d}  {pct(v, total_dif)}")


def salida_2_denominador(planillas, planillas_rot_ok, nuestros, factores, cobertura):
    print("\n" + "=" * 78)
    print("2 · DENOMINADOR DE LA ROTACIÓN DEL CLIENTE")
    print("=" * 78)
    primera, ultima = cobertura
    print(f"  Cobertura de stock_diario: {primera} .. {ultima}")

    def cobertura_parcial(y, m, dn):
        """Días del mes efectivamente cubiertos por stock_diario."""
        if primera is None or ultima is None:
            return None
        import datetime as dt
        ini, fin = dt.date(y, m, 1), dt.date(y, m, dn)
        p = primera if isinstance(primera, dt.date) else primera.date()
        u = ultima if isinstance(ultima, dt.date) else ultima.date()
        return (min(fin, u) - max(ini, p)).days + 1 if max(ini, p) <= min(fin, u) else 0

    # Vía directa: sus propias columnas C/STK y DDSTK (sólo en los `rot-ok`).
    directos = ddstk_ok = 0
    for datos in planillas_rot_ok.values():
        for d in datos.values():
            cs, vt, dd = d.get("dias_con_stock"), d.get("vta_total"), d.get("ddstk")
            if cs and vt and dd and cs > 0:
                directos += 1
                if coincide(vt / cs, dd):
                    ddstk_ok += 1
    if directos:
        print(f"\n  Vía directa (columnas propias del cliente en los `rot-ok`):")
        print(f"    su DDSTK == VTA / C/STK en {pct(ddstk_ok, directos)} de {directos} SKUs"
              f"  ->  su demanda diaria divide por DÍAS CON STOCK")

    # El último mes de cada planilla es el mes en curso al generarse: viene
    # incompleto, así que no dice nada sobre el denominador.
    mes_ref = {}
    for pedido, datos in planillas.items():
        meses = {ym for d in datos.values() for ym in d["rot"]}
        mes_ref[pedido] = max(meses) if meses else None
    print("\n  Vía indirecta (despeje sobre meses con quiebre)")
    print("    Mes de referencia excluido: "
          + ", ".join(f"{p}={r[0]}-{r[1]:02d}" for p, r in mes_ref.items() if r))

    # Paso 1: calibrar el factor con los meses SIN quiebre, donde ambas
    # hipótesis coinciden y el despeje es inequívoco.
    val_ok = val_tot = 0
    implicitos = defaultdict(list)
    for pedido, datos in planillas.items():
        for sku, d in datos.items():
            for ym, rot_cli in d["rot"].items():
                if ym == mes_ref[pedido]:
                    continue
                nuestro = nuestros.get((sku, ym[0], ym[1]))
                if not nuestro or not rot_cli or nuestro["ds"] != nuestro["dn"]:
                    continue
                f_imp = factor_implicito(d["vta"].get(ym, 0.0), rot_cli, nuestro["dn"])
                if f_imp is None:
                    continue
                implicitos[(sku, ym[1])].append(f_imp)
                if f_nuestro := (factores.get(sku) or {}).get(ym[1]):
                    val_tot += 1
                    if abs(f_imp - f_nuestro) < 0.01:
                        val_ok += 1
    print(f"    Factor estacional: el nuestro reproduce el suyo en {pct(val_ok, val_tot)} "
          f"de {val_tot} meses sin quiebre")

    # Paso 2: discriminar en los meses CON quiebre real.
    conteo = defaultdict(int)
    calibrado = fallback = excluidos_cobertura = 0
    ejemplos = []
    for pedido, datos in planillas.items():
        for sku, d in datos.items():
            for ym, rot_cli in d["rot"].items():
                if ym == mes_ref[pedido]:
                    continue
                nuestro = nuestros.get((sku, ym[0], ym[1]))
                if not nuestro or not rot_cli:
                    continue
                if not (0 < nuestro["ds"] < nuestro["dn"]):
                    continue
                if mes_con_stock_incompleto(nuestro["dn"],
                                            cobertura_parcial(ym[0], ym[1], nuestro["dn"])):
                    excluidos_cobertura += 1
                    continue
                cal = implicitos.get((sku, ym[1]))
                if cal:
                    factor = statistics.median(cal); calibrado += 1
                else:
                    factor = (factores.get(sku) or {}).get(ym[1]); fallback += 1
                veredicto = clasificar_hipotesis(d["vta"].get(ym, 0.0), rot_cli,
                                                 nuestro["ds"], nuestro["dn"], factor)
                conteo[veredicto] += 1
                if veredicto in ("naturales", "con_stock") and len(ejemplos) < 6:
                    ejemplos.append(f"      {sku} {ym[0]}-{ym[1]:02d}: vta={d['vta'].get(ym, 0):.0f} "
                                    f"ds={nuestro['ds']}/{nuestro['dn']} rot={rot_cli:.4f} "
                                    f"factor={factor:.3f} -> {veredicto}")
    total = sum(conteo.values())
    print(f"    Meses con quiebre evaluados: {total}"
          f"   (factor calibrado: {calibrado}, fallback al nuestro: {fallback};"
          f" excluidos por cobertura parcial: {excluidos_cobertura})")
    for k in ("naturales", "con_stock", "ambiguo", "ninguna"):
        print(f"      {k:12s} {conteo[k]:6d}  {pct(conteo[k], total)}")
    for e in ejemplos:
        print(e)

    print("\n  VEREDICTO:", end=" ")
    nat, stk = conteo["naturales"], conteo["con_stock"]
    if nat + stk == 0:
        print("sin casos discriminantes — no se puede concluir")
    elif stk >= 0.9 * (nat + stk):
        print("su denominador son los DÍAS CON STOCK (igual que el nuestro)")
    elif nat >= 0.9 * (nat + stk):
        print("su denominador son los DÍAS NATURALES del mes")
    else:
        print(f"mezclado ({nat} naturales vs {stk} con stock) — revisar")


def salida_3_rot_manual(planillas_rot_ok, planillas_bruto, sugerencias):
    print("\n" + "=" * 78)
    print("3 · NUESTRA ROT.S CONTRA SU `Rot. Manual`")
    print("=" * 78)
    ratios, sin_rots, sin_manual, comparados = [], 0, 0, 0
    sobre = sub = 0
    coincide_bruto = 0
    for pedido, datos in planillas_rot_ok.items():
        p_ratios = []
        bruto = planillas_bruto.get(pedido, {})
        for sku, d in datos.items():
            manual = d.get("rot_manual")
            if not manual or manual <= 0:
                sin_manual += 1
                continue
            # ¿el humano intervino, o quedó el valor que traía el sistema?
            base = (bruto.get(sku) or {}).get("rot_manual")
            if base is not None and abs(base - manual) < 1e-9:
                coincide_bruto += 1
            nuestra = sugerencias.get(sku)
            if nuestra is None:
                sin_rots += 1
                continue
            r = nuestra / manual
            p_ratios.append(r); ratios.append(r); comparados += 1
            if r > 1.10:
                sobre += 1
            elif r < 0.90:
                sub += 1
        if p_ratios:
            print(f"  {pedido:34s} n={len(p_ratios):4d}  mediana = {statistics.median(p_ratios):.3f}")
    if not ratios:
        print("  Sin datos comparables.")
        return
    print(f"\n  Comparados: {comparados}"
          f"   (descartados: {sin_manual} sin `Rot. Manual`, {sin_rots} sin ROT.S nuestra)")
    print(f"  De los comparables, {coincide_bruto} traen el mismo valor que el `bruto`"
          f" (el humano no lo tocó)")
    print(f"  Mediana ROT.S / Rot.Manual : {statistics.median(ratios):.3f}")
    print(f"  Media                      : {statistics.mean(ratios):.3f}"
          f"   (muy por encima de la mediana = cola larga a la derecha)")
    print(f"  Nos vamos ALTO (>+10%)     : {sobre:5d}  {pct(sobre, comparados)}")
    print(f"  Nos vamos BAJO (<-10%)     : {sub:5d}  {pct(sub, comparados)}")
    print(f"  Dentro de ±10%             : {comparados - sobre - sub:5d}  "
          f"{pct(comparados - sobre - sub, comparados)}")


def main() -> None:
    directorio = os.environ.get("PLANILLAS_DIR", DIR_POR_DEFECTO)
    pares = pares_de_planillas(directorio)
    if not pares:
        raise SystemExit(f"[ERROR] No se encontraron planillas en {directorio}")

    print(f"Planillas: {directorio}")
    planillas_bruto, planillas_rot_ok = {}, {}
    for nombre, bruto, rot_ok in pares:
        planillas_bruto[nombre] = leer_planilla(bruto)
        if rot_ok:
            planillas_rot_ok[nombre] = leer_planilla(rot_ok)
        print(f"  {nombre:34s} {len(planillas_bruto[nombre]):5d} SKUs"
              f"{'  (+ rot-ok)' if rot_ok else '  (sin rot-ok)'}")

    skus = ({s for d in planillas_bruto.values() for s in d}
            | {s for d in planillas_rot_ok.values() for s in d})
    conn = db_connect()
    try:
        cobertura = cargar_cobertura_stock(conn)
        nuestros, factores, sugerencias = cargar_nuestros_datos(conn, skus)
    finally:
        conn.close()
    print(f"  {'':34s} {len(skus)} SKUs únicos, "
          f"{len({s for (s, _, _) in nuestros})} con datos nuestros")

    salida_1_datos_base(planillas_bruto, nuestros)
    salida_2_denominador(planillas_bruto, planillas_rot_ok, nuestros, factores, cobertura)
    salida_3_rot_manual(planillas_rot_ok, planillas_bruto, sugerencias)
    print()


if __name__ == "__main__":
    main()
