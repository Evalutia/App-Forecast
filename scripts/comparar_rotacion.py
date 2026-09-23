#!/usr/bin/env python3
"""
comparar_rotacion.py — Issue #200.

Compara nuestra rotación contra la del cliente, despeja los días con stock de
sus columnas de rotación mensual para verificar `stock_diario` a escala
completa (13 meses × 5.428 SKUs), y cuantifica el impacto de que
`articulos.estado` esté muerto (los 5.656 artículos en 'activo', pese a que el
cliente marca 709 como discontinuados).

Solo lectura: no escribe nada en la base ni toca los archivos.

Uso (desde el host, con túnel SSH a producción -- ver scripts/
cargador_archivos_cliente.py para el patrón completo):

  ssh -f -N -L 13307:localhost:3307 <vm>
  MYSQL_HOST=127.0.0.1 MYSQL_PORT=13307 MYSQL_USER=root MYSQL_PASSWORD=... \
    python3 scripts/comparar_rotacion.py

## Por qué NO se lee `planilla_ventas_calculada`

Dos razones verificadas (issue): la ventana de la planilla (hoy Sep/25→Sep/26)
no coincide con la del archivo del cliente (Ago/25→Ago/26, sólo 12 de 13 meses
en común), y la tabla se trunca y reconstruye en cada corrida de
`run_calc_planilla.py` -- en dos semanas hasta esos 12 meses se pierden. Este
script recalcula todo desde `ventas_historicas` + `stock_diario` para la
ventana EXACTA del archivo, mismo precedente que el oráculo de QA de #108
(`scripts/qa_planilla_oracle.py`): reproduce desde tablas crudas, no confía en
lo persistido.

## Las fórmulas, verificadas contra el código real (no de memoria)

Todas las funciones puras de acá son un port directo de dos fuentes de verdad,
leídas en el momento de escribir este módulo:

- `services/etl/run_calc_planilla.py`: `clasificar_estado`, `clasificar_
  frecuencia` (dentro de `calcular_filas`), `rotacion_ajustada`, y las
  fórmulas de `rotacion_diaria_real`/`rotacion_diaria_desestacionalizada`
  (`round(vq/ds, 4)` y `round(rot_real/factor, 4)`). La query de días con
  stock (`leer_dias_con_stock`, acá abajo) reusa el `FORCE INDEX
  (idx_stock_fecha)` de `_SQL_STOCK` -- issue #153, 9,6x medido contra
  producción; omitirlo en una tabla de 120M+ filas es el mismo patrón que
  tumbó un contenedor local en aquel incidente.
- `apps/frontend/.../planillaResumen.ts`: `rotacionDesestacionalizadaMes` y
  `calcularRotDesEstac` -- la fórmula exacta de la columna "Rotacion
  DesEstac." que exporta nuestra propia planilla, la misma que hay que
  comparar contra la columna homónima del cliente para que la verificación
  sea sobre EL CÁLCULO, no sólo sobre el insumo (criterio de aceptación).

## Una decisión explícita: ningún mes es "de referencia"

`clasificar_estado_mes`/`calcularRotDesEstac` en producción tratan el mes MÁS
RECIENTE de la ventana como caso especial (todavía en curso, no se le aplica
el umbral de quiebre con el mismo rigor). Acá NO se aplica esa excepción: la
ventana del archivo del cliente (Ago/25→Ago/26) está completamente cerrada
para cuando se corre este diagnóstico -- ningún mes de los 13 es "hoy", así
que los 13 se clasifican con la misma regla, sin trato especial. Es lo que
hace al resultado "reproducible con independencia de cuándo se corra"
(criterio de aceptación #1): no depende de qué día es hoy, sólo de la ventana
fija del archivo.

Distinto es el conteo de `frecuencia_nivel`: ESE sí excluye estructuralmente
el mes más reciente de los 12 que cuenta (así está definido el algoritmo en
`run_calc_planilla.py`, con independencia de si ese mes está "en curso" o no)
-- se replica igual acá, ver `frecuencia_por_sku`.
"""

import os
import sys
from calendar import monthrange

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cargador_archivos_cliente import comparar_catalogo, leer_skus_nuestros, leer_ventas  # noqa: E402
from comparar_ventas_mensual import (  # noqa: E402
    agregado_mensual_por_tabla,
    conectar,
    rango_fechas,
    ventana_desde_ventas_cliente,
)
from diagnostico_planillas_cliente import TOL_ABS, TOL_REL, coincide  # noqa: E402

# ── Umbrales, idénticos a run_calc_planilla.py (verificados en el código real,
# no reintroducidos de memoria) ────────────────────────────────────────────────

ESTADO_UMBRAL_NORMAL = 1.00  # #36/#37: cualquier día de quiebre cuenta, sin piso
FREQ_ALTA_MIN = 9
FREQ_BAJA_MAX = 3

# A/D del cliente -> nuestro ENUM de tres valores ('activo','inactivo','discontinuo').
# El cliente no tiene equivalente de 'inactivo' -- su vocabulario es binario.
MAPEO_ESTADO_CLIENTE = {"A": "activo", "D": "discontinuo"}

# Margen para la comparación de días con stock despejados: el despeje viene de
# dividir venta (entera) por una rotación que el cliente publica redondeada a
# 4 decimales, así que un ±1 día de margen absorbe el redondeo y los efectos
# de borde de mes -- no tiene sentido aplicarle la tolerancia relativa de
# `coincide()` (pensada para magnitudes de rotación, no para un conteo de días
# donde 0,002 relativo es una fracción de día).
MARGEN_DIAS = 1


# ── Funciones puras: fórmulas de run_calc_planilla.py ────────────────────────

def dias_naturales(year, month):
    return monthrange(year, month)[1]


def clasificar_estado(dias_stock, dias_nat):
    """Port de run_calc_planilla.clasificar_estado. Sin la excepción de "mes
    de referencia" -- ver la nota de cabecera del módulo."""
    if dias_stock == 0:
        return "sin_stock"
    if dias_nat and dias_stock / dias_nat >= ESTADO_UMBRAL_NORMAL:
        return "normal"
    return "quiebre_parcial"


def clasificar_frecuencia(n_meses_con_ventas):
    if n_meses_con_ventas >= FREQ_ALTA_MIN:
        return "alta"
    if n_meses_con_ventas <= FREQ_BAJA_MAX:
        return "baja"
    return "media"


def rotacion_ajustada(vq, ds, dn, nivel):
    """Port de run_calc_planilla.rotacion_ajustada."""
    if nivel == "alta":
        return round(vq / ds, 4) if ds > 0 else None
    if nivel == "baja":
        return round(vq / dn, 4)
    r_alta = vq / ds if ds > 0 else None
    r_baja = vq / dn
    if r_alta is None:
        return round(r_baja, 4)
    return round((r_alta + r_baja) / 2, 4)


def rotacion_diaria_real(venta, dias_stock):
    return round(venta / dias_stock, 4) if dias_stock > 0 else None


def rotacion_diaria_desestacionalizada(rot_real, factor):
    if rot_real is None or not factor:
        return None
    return round(rot_real / factor, 4)


def rotacion_desestac_mes(estado_mes, rot_real, rot_desestac, rot_ajustada):
    """
    Port de `rotacionDesestacionalizadaMes` (planillaResumen.ts) -- el valor
    que aporta cada mes al promedio de "Rotacion DesEstac.".
    """
    if estado_mes == "normal":
        return rot_desestac
    if estado_mes != "quiebre_parcial" or rot_desestac is None:
        return None
    if rot_real == 0:
        return rot_desestac
    if rot_ajustada is not None and rot_real is not None and rot_real > 0:
        return rot_ajustada * (rot_desestac / rot_real)
    return None


def promedio_rot_desestac(valores):
    """
    Port de `calcularRotDesEstac` -- promedio de los meses con valor. A
    diferencia del frontend, acá NUNCA se excluye el último mes: la ventana es
    histórica completa, ningún mes de los 13 es el mes calendario en curso.
    """
    presentes = [v for v in valores if v is not None]
    return sum(presentes) / len(presentes) if presentes else None


def despejar_dias_con_stock(venta, rotacion_cliente):
    """
    venta / rotación = días con stock, despejado de las columnas mensuales del
    cliente (rotación diaria del mes, sin desestacionalizar -- ver
    scripts/fixtures/planillas_cliente/README.md: "su demanda diaria divide
    por DÍAS CON STOCK", confirmado en #127 contra sus propias columnas
    C/STK/VTA/DDSTK).

    None si no se puede despejar: sin venta, venta negativa (una devolución
    neta superando la venta del mes, posible desde #80 -- dividir un neto
    negativo por una rotación no tiene una lectura física de "días con stock",
    a diferencia de sumar negativos en un agregado), o rotación nula o cero
    (un cero real no debería pasar con venta positiva, pero no se divide por
    cero igual).
    """
    if venta is None or venta < 0 or not rotacion_cliente:
        return None
    return venta / rotacion_cliente


def desvio_relativo(nuestro, cliente):
    """(nuestro − cliente) / cliente. None sin base para calcular un %."""
    if not cliente:
        return None
    return (nuestro - cliente) / cliente


def resumen_direccionalidad(deltas):
    """
    [float] -> {'n','mediana','bajo','alto'}

    `bajo`/`alto` cuentan desvíos más allá de ±1% -- separa "sistemáticamente
    por debajo" (consistente con la brecha de venta de depósito 2 propagándose
    a la rotación, #196/#197) de "disperso" (indicaría una fórmula distinta,
    no un insumo distinto).
    """
    if not deltas:
        return {"n": 0, "mediana": None, "bajo": 0, "alto": 0}
    ordenados = sorted(deltas)
    n = len(ordenados)
    mitad = n // 2
    mediana = (ordenados[mitad] if n % 2
               else (ordenados[mitad - 1] + ordenados[mitad]) / 2)
    return {
        "n": n,
        "mediana": mediana,
        "bajo": sum(1 for d in deltas if d < -0.01),
        "alto": sum(1 for d in deltas if d > 0.01),
    }


def bucket_venta(venta):
    """Clasifica una venta mensual en un bucket de magnitud, para ver si el
    despeje es numéricamente frágil sólo a bajo volumen."""
    if venta < 5:
        return "venta<5"
    if venta < 20:
        return "venta 5-19"
    return "venta>=20"


def es_despeje_imposible(despejado, dias_naturales):
    """
    Un despejado > días naturales del mes es matemáticamente imposible si la
    rotación mensual del cliente fuera literalmente venta/días_con_stock DE
    ESE MES -- ningún mes tiene más días con stock que días naturales. Si esto
    aparece con frecuencia, la columna mensual del cliente probablemente usa
    un denominador distinto (p. ej. una ventana rodante más larga), no el mes
    calendario a secas.
    """
    return despejado > dias_naturales


def coincide_dias(despejado, real, margen=MARGEN_DIAS):
    """Compara un valor despejado (float) contra nuestro conteo entero de días
    con stock, con margen absoluto de `margen` días -- ver la nota de cabecera
    sobre por qué no es la tolerancia relativa de `coincide()`."""
    if despejado is None or real is None:
        return False
    return abs(round(despejado) - real) <= margen


def frecuencia_por_sku(ventas_por_sku_mes, ventana):
    """
    {sku: {(y,m): venta}}, [(y,m),...] -> {sku: nivel}

    Cuenta meses con venta > 0 sobre los primeros 12 de los 13 meses de
    `ventana` (excluye el último estructuralmente, igual que
    `run_calc_planilla.py` excluye `meses_ordenados[0]` de `meses_con_ventas`
    -- es una regla fija del algoritmo, no atada a si ese mes está "en curso").
    """
    meses_contables = ventana[:-1]
    niveles = {}
    for sku, por_mes in ventas_por_sku_mes.items():
        n = sum(1 for ym in meses_contables if (por_mes.get(ym) or 0) > 0)
        niveles[sku] = clasificar_frecuencia(n)
    return niveles


# ── I/O contra MySQL ─────────────────────────────────────────────────────────

def leer_dias_con_stock(conn, ventana):
    """
    {(sku,y,m): dias_con_stock}, TODO el catálogo. Reusa el `FORCE INDEX
    (idx_stock_fecha)` de `_SQL_STOCK` (run_calc_planilla.py, #153) -- la
    misma agregación (stock_diario agrupado por sku+fecha en un rango de
    fechas ancho, contra 120M+ filas) que sin el índice correcto escaneaba la
    tabla completa y tumbó un contenedor local.
    """
    desde, hasta = rango_fechas(ventana)
    dias = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT agg.sku, YEAR(agg.fecha) AS yr, MONTH(agg.fecha) AS mo,
                   COUNT(DISTINCT agg.fecha) AS dias_con_stock
            FROM (
                SELECT sd.sku, sd.fecha, SUM(sd.cantidad) AS stock_total
                FROM stock_diario sd FORCE INDEX (idx_stock_fecha)
                WHERE sd.fecha BETWEEN %s AND %s
                GROUP BY sd.sku, sd.fecha
            ) agg
            INNER JOIN articulos a ON a.sku = agg.sku
            WHERE agg.stock_total > COALESCE(a.stock_minimo, 0)
            GROUP BY agg.sku, YEAR(agg.fecha), MONTH(agg.fecha)
            """,
            (desde, hasta),
        )
        for sku, y, m, ds in cur.fetchall():
            dias[(sku, y, m)] = int(ds)
    return dias


def leer_factores(conn, skus):
    """{sku: {mes(1-12): factor|None}}, sólo para los SKUs pedidos."""
    skus = sorted(set(skus))
    if not skus:
        return {}
    placeholders = ",".join(["%s"] * len(skus))
    cols = ", ".join(f"factor_mes_{i:02d}" for i in range(1, 13))
    factores = {}
    with conn.cursor() as cur:
        cur.execute(f"SELECT sku, {cols} FROM articulos WHERE sku IN ({placeholders})", skus)
        for fila in cur.fetchall():
            sku, *valores = fila
            factores[sku] = {i: (float(v) if v is not None else None)
                             for i, v in enumerate(valores, start=1)}
    return factores


def leer_sugerencias(conn, skus):
    """{sku: rotacion_sugerida|None}, para los SKUs pedidos."""
    skus = sorted(set(skus))
    if not skus:
        return {}
    placeholders = ",".join(["%s"] * len(skus))
    sugerencias = {}
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT sku, rotacion_sugerida FROM planilla_sugerencias WHERE sku IN ({placeholders})",
            skus,
        )
        for sku, rot in cur.fetchall():
            sugerencias[sku] = float(rot) if rot is not None else None
    return sugerencias


def leer_skus_sin_factor(conn, skus):
    """{sku, ...} de los SKUs pedidos SIN ningún factor_mes_NN cargado (los
    12 NULL) -- la población excluida del criterio de aceptación #3."""
    skus = sorted(set(skus))
    if not skus:
        return set()
    placeholders = ",".join(["%s"] * len(skus))
    cond = " AND ".join(f"factor_mes_{i:02d} IS NULL" for i in range(1, 13))
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT sku FROM articulos WHERE sku IN ({placeholders}) AND {cond}",
            skus,
        )
        return {r[0] for r in cur.fetchall()}


# ── informe ──────────────────────────────────────────────────────────────────

def _calcular_rotacion_por_sku(sku, ventas_sku, dias_stock_sku, factores_sku, nivel, ventana):
    """
    Para un SKU: {(y,m): {'estado','rot_real','rot_desestac','rot_ajustada',
    'dias_stock'}} sobre toda la ventana, más el promedio de "Rotacion
    DesEstac." (criterio de aceptación #1/#2). Función pura salvo por recibir
    los datos ya leídos.
    """
    por_mes = {}
    for year, month in ventana:
        dn = dias_naturales(year, month)
        ds = dias_stock_sku.get((year, month), 0)
        vq = ventas_sku.get((year, month), 0)
        estado = clasificar_estado(ds, dn)
        rot_real = rotacion_diaria_real(vq, ds)
        factor = (factores_sku or {}).get(month)
        rot_desestac = rotacion_diaria_desestacionalizada(rot_real, factor)
        rot_aj = (rotacion_ajustada(vq, ds, dn, nivel) if estado == "quiebre_parcial" else None)
        por_mes[(year, month)] = {
            "estado": estado, "dias_stock": ds, "rot_real": rot_real,
            "rot_desestac": rot_desestac, "rot_ajustada": rot_aj,
        }
    valores_mes = [rotacion_desestac_mes(d["estado"], d["rot_real"], d["rot_desestac"], d["rot_ajustada"])
                  for d in por_mes.values()]
    return por_mes, promedio_rot_desestac(valores_mes)


def main():
    if not os.environ.get("MYSQL_PASSWORD"):
        print("Falta MYSQL_PASSWORD -- sin conexión no hay nada que comparar.", file=sys.stderr)
        return 1

    ventas_cliente = leer_ventas()
    ventana = ventana_desde_ventas_cliente(ventas_cliente)

    conn = conectar()
    try:
        nuestros = leer_skus_nuestros(conn)
        cobertura = comparar_catalogo(list(ventas_cliente), nuestros)
        comunes = set(cobertura.comunes)

        con_rot = {sku: a for sku, a in ventas_cliente.items()
                   if sku in comunes and a.rot_desestac is not None}
        print("=" * 78)
        print(f"ROTACIÓN DESESTACIONALIZADA ({len(con_rot)} SKUs con rotación cargada)")
        print("=" * 78)

        ventas_todos = agregado_mensual_por_tabla(conn, ventana, "ventas_historicas")
        dias_stock_todos = leer_dias_con_stock(conn, ventana)
        factores = leer_factores(conn, con_rot)
        sin_factor = leer_skus_sin_factor(conn, comunes)

        ventas_por_sku = {}
        for (sku, y, m), total in ventas_todos.items():
            if sku in comunes:
                ventas_por_sku.setdefault(sku, {})[(y, m)] = total
        niveles = frecuencia_por_sku(ventas_por_sku, ventana)

        dias_stock_por_sku = {}
        for (sku, y, m), ds in dias_stock_todos.items():
            if sku in comunes:
                dias_stock_por_sku.setdefault(sku, {})[(y, m)] = ds

        comparables = 0
        ok = 0
        excluidos = 0
        sin_nivel = 0
        deltas = []
        for sku, articulo in con_rot.items():
            if sku in sin_factor:
                excluidos += 1
                continue
            if sku not in niveles:
                # Sin ninguna fila en ventas_historicas en toda la ventana --
                # frecuencia_por_sku no tiene de dónde calcular un nivel real.
                # Se sigue comparando (con fallback a 'media'), pero contado
                # aparte para que no quede escondido dentro de "comparables".
                sin_nivel += 1
            _, promedio = _calcular_rotacion_por_sku(
                sku, ventas_por_sku.get(sku, {}), dias_stock_por_sku.get(sku, {}),
                factores.get(sku, {}), niveles.get(sku, "media"), ventana)
            comparables += 1
            if promedio is not None and coincide(promedio, articulo.rot_desestac):
                ok += 1
            delta = desvio_relativo(promedio, articulo.rot_desestac) if promedio is not None else None
            if delta is not None:
                deltas.append(delta)
        print(f"  Comparables: {comparables} (excluidos sin factor_mes_*: {excluidos})")
        if sin_nivel:
            print(f"  [AVISO] {sin_nivel} SKU(s) sin ninguna fila en ventas_historicas en la ventana "
                  f"-- se les asumió frecuencia 'media' (fallback, no un nivel real calculado)")
        if comparables:
            print(f"  Nuestro cálculo reproduce el de ellos en {ok}/{comparables} "
                  f"({100 * ok / comparables:.1f}%), tolerancia TOL_REL={TOL_REL} TOL_ABS={TOL_ABS}")
        else:
            print("  (ningún SKU comparable -- todos sin factor_mes_*)")
        d = resumen_direccionalidad(deltas)
        if d["n"]:
            print(f"  Direccionalidad del desvío (nuestro-cliente)/cliente: "
                  f"mediana={d['mediana']*100:+.1f}%  "
                  f"por debajo(<-1%)={d['bajo']} ({100*d['bajo']/d['n']:.1f}%)  "
                  f"por encima(>+1%)={d['alto']} ({100*d['alto']/d['n']:.1f}%)")

        print()
        print("=" * 78)
        print("DÍAS CON STOCK DESPEJADOS (13 meses, todo el conjunto común)")
        print("=" * 78)
        total_mes = ok_mes = imposibles = 0
        buckets = {"venta<5": [0, 0], "venta 5-19": [0, 0], "venta>=20": [0, 0]}
        for sku, articulo in ventas_cliente.items():
            if sku not in comunes:
                continue
            for ym in ventana:
                venta = articulo.ventas.get(ym)
                rot_cliente = articulo.rotaciones.get(ym)
                despejado = despejar_dias_con_stock(venta, rot_cliente)
                if despejado is None:
                    continue
                dn = dias_naturales(*ym)
                real = dias_stock_por_sku.get(sku, {}).get(ym, 0)
                total_mes += 1
                if es_despeje_imposible(despejado, dn):
                    imposibles += 1
                b = bucket_venta(venta)
                buckets[b][1] += 1
                if coincide_dias(despejado, real):
                    ok_mes += 1
                    buckets[b][0] += 1
        print(f"  SKU-mes comparables (con despeje posible): {total_mes}")
        if total_mes:
            print(f"  Despejado > días naturales del mes (imposible si fuera venta/dias_con_stock "
                  f"de ESE mes): {imposibles} ({100*imposibles/total_mes:.1f}%)")
        print("  Por magnitud de venta del mes:")
        for b, (ok_b, tot_b) in buckets.items():
            if tot_b:
                print(f"    {b:<12} {ok_b}/{tot_b} ({100*ok_b/tot_b:.1f}%)")
        if total_mes:
            print(f"  Coinciden dentro de ±{MARGEN_DIAS} día: {ok_mes} ({100*ok_mes/total_mes:.1f}%)")

        print()
        print("=" * 78)
        print("IMPACTO DEL ESTADO MUERTO (articulos.estado siempre 'activo')")
        print("=" * 78)
        discontinuados = {sku for sku, a in ventas_cliente.items()
                          if sku in comunes and a.estado == "D"}
        sugerencias = leer_sugerencias(conn, discontinuados)
        con_sugerencia = {sku for sku in discontinuados
                          if (sugerencias.get(sku) or 0) > 0}
        print(f"  SKUs discontinuados por el cliente, en el conjunto común: {len(discontinuados)}")
        print(f"  De esos, reciben sugerencia de reposición nuestra HOY: {len(con_sugerencia)} "
              f"({100*len(con_sugerencia)/len(discontinuados):.1f}%)" if discontinuados else "")
        print(f"  Mapeo A/D -> estado: {MAPEO_ESTADO_CLIENTE}")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
