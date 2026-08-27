#!/usr/bin/env python3
"""
comparar_extraccion_vs_produccion.py — Issue #187: compara el almacén de
comparación de #186 (ventas_historicas_comparacion / stock_diario_comparacion,
poblado por run_backfill_comparacion.sh) contra lo ya guardado en producción,
y reporta las discrepancias clasificadas.

Solo SELECTs -- no escribe ni corrige nada (mismo criterio que
qa_planilla_oracle.py / diagnostico_planillas_cliente.py: divergencia => se
reporta, no se parchea acá). El rango y los SKUs comparados salen de lo que
#186 ya extrajo (MIN/MAX(fecha), DISTINCT sku de las tablas _comparacion) --
no hace falta pasarle fechas a mano, así que corre igual contra el dataset
chico de prueba de #186 o, más adelante, contra la corrida completa de #188.

Uso (en el contenedor etl, que ya tiene pymysql y las credenciales):
  cat scripts/comparar_extraccion_vs_produccion.py | docker compose exec -T etl python -

Exit code: 0 si no hay diferencias o todas quedaron CERRADAS por un patrón
confirmado sin ambigüedad; 2 si queda al menos una que necesita revisión
humana -- tenga o no un patrón nombrado. "Tiene nombre" no es lo mismo que
"segura para ignorar": ninguna de las categorías que este script reconoce hoy
(clamp_negativos_pre_80_posible, solo_en_produccion, solo_en_comparacion)
cierra sola -- todas tienen causa plausible, pero solo se puede confirmar
mirando el detalle día a día, que este script no tiene (ventas es SUM por
mes). El campo requiere_revision queda como mecanismo real para el día que
aparezca una categoría que sí se pueda cerrar con certeza desde este nivel de
agregación -- hoy, honestamente, ninguna la tiene.

## Nota sobre las categorías de clasificación (desvío del planteo original
del issue, documentado a propósito -- ver también .claude/CONTEXTO.md,
sección "#187")

El issue pedía clasificar las diferencias contra #174, #126 y #161. Al
implementar, #126 (ajustes de fin de mes) y el patrón GRAVITY de #161 resultaron
no aplicables a este script, y se documenta por qué en vez de forzarlos:

- Ambos son hallazgos de la reconciliación CLIENTE vs NOSOTROS. Este script
  compara un eje distinto: NUESTRA extracción ya guardada vs. una extracción
  FRESCA del mismo WS, con el mismo código actual. #126 es sobre qué cuenta
  Rodrigo como venta en su propio sistema -- no tiene relación con lo que
  nuestro WS devuelve en dos momentos distintos. El patrón de #161 se investigó
  a fondo (cuatro rondas, más la auditoría de 4 agentes de esa misma sesión) y
  la conclusión fue que la extracción YA es fiel al WS -- si eso es cierto, dos
  llamadas al mismo WS para el mismo período no deberían diferir por esa causa.
- En su lugar se implementa la categoría que sí describe una diferencia
  posible entre dos extracciones propias (#174: negativos clampeados a 0 antes
  del deploy de #80, nunca backfilleados fuera de esa ventana -- solo aplica a
  VENTAS, stock nunca puede ser negativo por esquema, CHECK(cantidad>=0)) y dos
  categorías nuevas, más honestas sobre lo que este script puede detectar de
  verdad: filas que solo existen de un lado (posible recuperación de un fallo
  silencioso ya corregido, o una regresión nueva -- hay que mirar cuál) y
  magnitudes fijas recurrentes (mismo método de detección que destapó el
  patrón de #161, generalizado -- sin asumir que la causa vaya a ser la
  misma). Ninguna de las tres cierra sola -- ver "Exit code" arriba y el
  campo requiere_revision de clasificar().

## Límite de alcance conocido (encontrado al verificar con datos sembrados,
no un descuido)

El rango comparado sale de MIN/MAX(fecha) de las tablas _comparacion, no de
lo que #186 se propuso extraer. Si una corrida de #186 falla parcialmente en
el borde de su ventana (el último chunk antes de BACKFILL_TO nunca se
completó), ese hueco reduce el MIN/MAX real de la tabla de comparación -- y
una fila que solo existe en producción justo en esa fecha nunca se compara,
porque cae fuera del rango que este script termina mirando. No es lo mismo
que "no hay diferencia": es "nunca se intentó comparar esa fecha". Detectarlo
de verdad requeriría cruzar contra jobs_historial (subtipo
backfill_comparacion) para saber qué grupos/rangos declaró #186 -- no lo hace
este script, fuera de alcance de #187 tal como está planteado. Si #188 corre
con chunks fallidos, revisar jobs_historial a mano antes de confiar en que
"sin diferencias" en el borde de la ventana signifique que todo coincide.
"""

import collections
import datetime as dt
import os
import sys

import pymysql

FECHA_LIMITE_BACKFILL_80 = dt.date(2024, 8, 12)  # antes de esto, negativos quedaron clampeados para siempre (#174)


def connect():
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "mysql"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ.get("MYSQL_DB", "evalutia"),
    )


def clasificar(diff):
    """
    Devuelve (categoria, explicacion, requiere_revision). categoria=None si
    no matchea ningún patrón conocido -- candidato real a investigar, siempre
    con requiere_revision=True. Función pura, sin acceso a DB, para poder
    testearla sin fixture de MySQL.

    requiere_revision distingue "tiene nombre y causa conocida, cerrado" de
    "tiene nombre pero sigue siendo una señal real que alguien tiene que
    mirar". La primera version de este script devolvía False para el patrón
    de #174 (clamp de negativos pre-#80), tratándolo como cerrado -- pero a
    nivel mes (la granularidad real de este script para ventas) no alcanza
    para confirmarlo: #126 ya documentó meses con ventas positivas Y una
    devolución grande mezcladas en el mismo mes, así que un delta negativo
    antes del backfill es CONSISTENTE con el patrón, no una prueba de que sea
    esa la causa. Hoy ninguna categoría devuelve False -- el campo queda
    como mecanismo real para el día que aparezca una que sí se pueda
    confirmar con certeza desde este nivel de agregación (tres rondas de
    /code-review post-implement: orden de los checks, mezcla de tipos en la
    detección de magnitud, y esta última sobre qué cuenta como "cerrado").
    """
    # Filas de un solo lado primero: #174 es una explicación de VALOR (el
    # clamp cambia una cantidad, no borra la fila entera), así que solo
    # aplica cuando los dos lados tienen dato. Chequearla antes de esto
    # etiquetaría una fila enteramente ausente como "ya explicada" y la
    # escondería del reporte.
    if diff["produccion"] is None:
        return ("solo_en_comparacion",
                "no existe en producción -- posible recuperación de un fallo silencioso ya corregido, o dato nuevo del WS",
                True)
    if diff["comparacion"] is None:
        return ("solo_en_produccion",
                "no existe en la re-extracción -- posible regresión, revisar antes de descartar",
                True)

    # #174 es específico de ventas -- el clamp de #80 afectaba
    # ventas_historicas.cantidad (UNSIGNED hasta ese fix). stock_diario nunca
    # tuvo ese problema: cantidad es UNSIGNED con CHECK (cantidad >= 0) desde
    # siempre (infra/sql/02-tablas.sql), un valor negativo ahí ni existe --
    # aplicar esta categoría a un diff de stock etiquetaría con una causa que
    # no puede ser la real (hallazgo de /code-review post-implement, tercera
    # ronda: ninguno de los tests originales cubría un stock con esa fecha
    # porque el escenario en sí es imposible dado el esquema).
    if diff["tipo"] == "ventas":
        # Ventas solo tiene granularidad de mes en este script (SUM por
        # sku/año/mes). El mes límite (agosto 2024) tiene cobertura PARCIAL
        # (el backfill arranca el día 12) -- sin dato diario no se puede
        # saber si una diferencia de ese mes cae antes o después, así que
        # solo se considera un mes ENTERAMENTE anterior.
        antes_del_backfill = (diff["anio"], diff["mes"]) < (FECHA_LIMITE_BACKFILL_80.year, FECHA_LIMITE_BACKFILL_80.month)
        if antes_del_backfill and diff["delta"] < 0:
            # requiere_revision=True (no cierra sola): a nivel mes no se puede
            # confirmar que la baja sea EL clamp y no otra causa -- #126 ya
            # documentó meses con ventas positivas Y una devolución grande
            # mezcladas (ej. C00190 feb-2026), así que "produccion==0" no
            # sirve como filtro (excluiría esos casos reales), y sin dato
            # diario tampoco se puede confirmar con certeza -- hallazgo de
            # /code-review: clasificar con delta<0 solo no alcanza para
            # cerrar sin revisión (ej. producción=50, comparación=45 antes
            # del backfill no es necesariamente el clamp).
            return ("clamp_negativos_pre_80_posible",
                    f"anterior a {FECHA_LIMITE_BACKFILL_80.isoformat()} -- consistente con el patrón de #174, "
                    "pero a nivel mes no se puede confirmar sin mirar el detalle diario",
                    True)

    return (None, None, True)


def detectar_magnitud_fija_recurrente(diffs_sin_clasificar, minimo_ocurrencias=3, minimo_skus_mismo_dia=2):
    """
    Mismo método que destapó el patrón de #161 (GRAVITY): un delta EXACTO que
    se repite varias veces para el mismo SKU, o el mismo delta el mismo día
    en varios SKUs distintos -- firma de un mecanismo sistemático, no de ruido
    disperso. No asume que la causa sea la misma que #161 (ese caso se
    investigó y no era un bug de extracción) -- solo señala el patrón.

    Agrupa también por `tipo` (ventas/stock) -- sin esto, un delta de ventas
    (unidades vendidas por mes) y un delta de stock (unidades en depósito por
    día) que coinciden en magnitud por casualidad se mezclarían como si fuera
    un solo patrón sistemático, cuando son dos métricas sin relación
    (hallazgo de /code-review post-implement).

    minimo_skus_mismo_dia es el umbral independiente del segundo chequeo
    (antes hardcodeado en 2, sin que un caller pudiera subirlo junto con
    minimo_ocurrencias -- mismo hallazgo de /code-review).
    """
    por_sku_delta = collections.defaultdict(list)
    por_fecha_delta = collections.defaultdict(list)
    for d in diffs_sin_clasificar:
        por_sku_delta[(d["tipo"], d["sku"], d["delta"])].append(d)
        fecha_key = d.get("fecha") or (d["anio"], d["mes"])
        por_fecha_delta[(d["tipo"], fecha_key, d["delta"])].append(d)

    hallazgos = []
    for (tipo, sku, delta), ocurrencias in sorted(por_sku_delta.items(), key=lambda kv: -len(kv[1])):
        if len(ocurrencias) >= minimo_ocurrencias:
            hallazgos.append(f"  [{tipo}] SKU {sku}: delta exacto {delta:+d} se repite {len(ocurrencias)} veces")
    for (tipo, fecha_key, delta), ocurrencias in por_fecha_delta.items():
        skus = {d["sku"] for d in ocurrencias}
        if len(skus) >= minimo_skus_mismo_dia:
            # Ventas agrupa por (año, mes) -- "el mismo día" es literalmente
            # falso ahí (la fecha_key es una tupla de mes, no un date). Stock
            # sí tiene fecha exacta. Hallazgo de /code-review: el mensaje
            # decía "el mismo día" sin importar cuál era, mezclando la
            # distinción de granularidad que el resto del script cuida.
            periodo = f"{fecha_key[0]}-{fecha_key[1]:02d}" if tipo == "ventas" else str(fecha_key)
            unidad = "el mismo mes" if tipo == "ventas" else "el mismo día"
            hallazgos.append(f"  [{tipo}] {periodo}: delta exacto {delta:+d} en {len(skus)} SKUs distintos {unidad} ({sorted(skus)})")
    return hallazgos


def _rango_y_skus(cur, tabla_comparacion):
    cur.execute(f"SELECT MIN(fecha), MAX(fecha), COUNT(DISTINCT sku) FROM {tabla_comparacion}")
    return cur.fetchone()


def comparar_ventas(cur):
    desde, hasta, n_skus = _rango_y_skus(cur, "ventas_historicas_comparacion")
    if desde is None:
        print("ventas_historicas_comparacion: vacía -- nada para comparar (¿corriste run_backfill_comparacion.sh?)")
        return []
    print(f"Ventas: comparando {n_skus} SKUs, {desde} .. {hasta}")

    cur.execute(
        "SELECT sku, YEAR(fecha), MONTH(fecha), SUM(cantidad) FROM ventas_historicas_comparacion "
        "GROUP BY sku, YEAR(fecha), MONTH(fecha)"
    )
    nuevo = {(sku, y, m): int(v) for sku, y, m, v in cur.fetchall()}

    cur.execute(
        "SELECT sku, YEAR(fecha), MONTH(fecha), SUM(cantidad) FROM ventas_historicas "
        "WHERE fecha BETWEEN %s AND %s AND sku IN (SELECT DISTINCT sku FROM ventas_historicas_comparacion) "
        "GROUP BY sku, YEAR(fecha), MONTH(fecha)",
        (desde, hasta),
    )
    viejo = {(sku, y, m): int(v) for sku, y, m, v in cur.fetchall()}

    diffs = []
    for sku, y, m in set(nuevo) | set(viejo):
        v_nuevo, v_viejo = nuevo.get((sku, y, m)), viejo.get((sku, y, m))
        if v_nuevo == v_viejo:
            continue
        diffs.append({
            "tipo": "ventas", "sku": sku, "anio": y, "mes": m,
            "produccion": v_viejo, "comparacion": v_nuevo,
            "delta": (v_nuevo or 0) - (v_viejo or 0),
        })
    return diffs


def comparar_stock(cur):
    desde, hasta, n_skus = _rango_y_skus(cur, "stock_diario_comparacion")
    if desde is None:
        print("stock_diario_comparacion: vacía -- nada para comparar")
        return []
    print(f"Stock: comparando {n_skus} SKUs, {desde} .. {hasta}")

    cur.execute("SELECT sku, fecha, deposito_id, cantidad FROM stock_diario_comparacion")
    nuevo = {(sku, fecha, dep): int(c) for sku, fecha, dep, c in cur.fetchall()}

    cur.execute(
        "SELECT sku, fecha, deposito_id, cantidad FROM stock_diario "
        "WHERE fecha BETWEEN %s AND %s AND sku IN (SELECT DISTINCT sku FROM stock_diario_comparacion)",
        (desde, hasta),
    )
    viejo = {(sku, fecha, dep): int(c) for sku, fecha, dep, c in cur.fetchall()}

    diffs = []
    for sku, fecha, dep in set(nuevo) | set(viejo):
        v_nuevo, v_viejo = nuevo.get((sku, fecha, dep)), viejo.get((sku, fecha, dep))
        if v_nuevo == v_viejo:
            continue
        diffs.append({
            "tipo": "stock", "sku": sku, "anio": fecha.year, "mes": fecha.month,
            "fecha": fecha, "deposito_id": dep,
            "produccion": v_viejo, "comparacion": v_nuevo,
            "delta": (v_nuevo or 0) - (v_viejo or 0),
        })
    return diffs


def cargar_catalogo(cur, skus):
    if not skus:
        return {}
    placeholders = ",".join(["%s"] * len(skus))
    cur.execute(
        f"SELECT a.sku, a.marca_nombre, g.descripcion FROM articulos a "
        f"LEFT JOIN grupos g ON g.id = a.grupo_id WHERE a.sku IN ({placeholders})",
        tuple(skus),
    )
    return {sku: (marca, grupo) for sku, marca, grupo in cur.fetchall()}


def reportar(diffs, catalogo):
    if not diffs:
        print("\nSin diferencias -- producción y la re-extracción coinciden exactamente en el rango comparado.")
        return []

    for d in diffs:
        d["categoria"], d["explicacion"], d["requiere_revision"] = clasificar(d)

    # "categoria" (tiene nombre/causa conocida) y "requiere_revision" (segura
    # para ignorar o no) son ejes distintos -- #174 tiene categoría Y está
    # cerrada; "solo_en_produccion" tiene categoría pero sigue siendo una
    # señal real (posible regresión) hasta que alguien la revise. Mezclar los
    # dos ejes fue el hallazgo de la segunda ronda de /code-review: todo lo
    # que requiere revisión entra al mismo bucket para el reporte y el exit
    # code, tenga nombre o no.
    cerradas = [d for d in diffs if d["categoria"] and not d["requiere_revision"]]
    necesitan_revision = [d for d in diffs if d["requiere_revision"]]

    print(f"\n=== {len(diffs)} diferencias encontradas ===")
    print(f"  {len(cerradas)} explicadas por un patrón conocido, sin acción")
    print(f"  {len(necesitan_revision)} necesitan revisión humana"
          f" ({sum(1 for d in necesitan_revision if d['categoria'])} con patrón nombrado pero aún abierto, "
          f"{sum(1 for d in necesitan_revision if not d['categoria'])} sin ningún patrón conocido)\n")

    if cerradas:
        por_cat = collections.Counter(d["categoria"] for d in cerradas)
        print("Desglose de lo cerrado (patrón conocido, sin acción):")
        for cat, n in por_cat.most_common():
            print(f"  {cat}: {n}")
        print()

    if necesitan_revision:
        por_cat_abierta = collections.Counter(d["categoria"] for d in necesitan_revision if d["categoria"])
        if por_cat_abierta:
            print("Desglose de lo que necesita revisión pero ya tiene patrón nombrado:")
            for cat, n in por_cat_abierta.most_common():
                print(f"  {cat}: {n}")
            print()

        # Presencia (solo_en_produccion/solo_en_comparacion) vs. valor (las
        # demás) son dos preguntas distintas: "¿existe la fila?" no tiene una
        # "magnitud" bien definida por delta (produccion o comparacion es
        # None, y (v or 0) sobre un lado real en 0 da delta=0 aunque la
        # anomalía sea real). Mezclarlas en el mismo ranking/agrupado por
        # abs(delta) escondía filas de presencia con valor 0 del top-20 y
        # podía agrupar varias como un falso "delta 0 recurrente" -- hallazgo
        # de /code-review, sexta ronda. Las de presencia se listan COMPLETAS
        # (no son tantas como para truncar) en vez de competir por magnitud.
        solo_un_lado = [d for d in necesitan_revision if d["categoria"] in ("solo_en_produccion", "solo_en_comparacion")]
        con_valor_en_ambos = [d for d in necesitan_revision if d["categoria"] not in ("solo_en_produccion", "solo_en_comparacion")]

        if solo_un_lado:
            print(f"\nExisten solo de un lado ({len(solo_un_lado)}, se listan todas -- no aplica magnitud):")
            for d in sorted(solo_un_lado, key=lambda x: (x["tipo"], x["sku"], x["anio"], x["mes"])):
                extra = f" dep={d['deposito_id']}" if "deposito_id" in d else ""
                print(f"  [{d['tipo']}] {d['sku']} {d['anio']}-{d['mes']:02d}{extra} [{d['categoria']}]: "
                      f"producción={d['produccion']} comparación={d['comparacion']}")

        if con_valor_en_ambos:
            magnitud_total = sum(abs(d["delta"]) for d in con_valor_en_ambos)
            print(f"\nCon valor en ambos lados pero distinto: {len(con_valor_en_ambos)} filas, "
                  f"{magnitud_total} unidades de magnitud total")

            # Separado por tipo -- ventas mide unidades vendidas por mes,
            # stock mide unidades en depósito por día. Sumarlos juntos en una
            # sola magnitud mezclaría dos métricas sin relación entre sí
            # (mismo hallazgo de /code-review que ya corrigió
            # detectar_magnitud_fija_recurrente más arriba; acá aplica igual).
            por_grupo = collections.Counter()
            por_marca = collections.Counter()
            por_fecha = collections.Counter()
            for d in con_valor_en_ambos:
                marca, grupo = catalogo.get(d["sku"], (None, None))
                por_grupo[(d["tipo"], grupo or "(sin grupo)")] += abs(d["delta"])
                por_marca[(d["tipo"], marca or "(sin marca)")] += abs(d["delta"])
                por_fecha[(d["tipo"], d["anio"], d["mes"])] += abs(d["delta"])

            print("\nConcentración por grupo (magnitud absoluta, por tipo):")
            for (tipo, grupo), mag in por_grupo.most_common(10):
                print(f"  [{tipo}] {grupo}: {mag}")
            print("\nConcentración por marca (magnitud absoluta, por tipo):")
            for (tipo, marca), mag in por_marca.most_common(10):
                print(f"  [{tipo}] {marca}: {mag}")
            print("\nConcentración por mes (magnitud absoluta, por tipo):")
            for (tipo, y, m), mag in sorted(por_fecha.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
                print(f"  [{tipo}] {y}-{m:02d}: {mag}")

            hallazgos_magnitud = detectar_magnitud_fija_recurrente(con_valor_en_ambos)
            if hallazgos_magnitud:
                print("\nMagnitudes fijas recurrentes (mismo método que destapó #161 -- no asume la misma causa):")
                for h in hallazgos_magnitud:
                    print(h)

            print("\nDetalle de las 20 diferencias de valor que necesitan revisión, de mayor magnitud:")
            for d in sorted(con_valor_en_ambos, key=lambda x: -abs(x["delta"]))[:20]:
                extra = f" dep={d['deposito_id']}" if "deposito_id" in d else ""
                etiqueta = f" [{d['categoria']}]" if d["categoria"] else " [sin patrón conocido]"
                print(f"  [{d['tipo']}] {d['sku']} {d['anio']}-{d['mes']:02d}{extra}{etiqueta}: "
                      f"producción={d['produccion']} comparación={d['comparacion']} delta={d['delta']:+d}")
    elif cerradas:
        print("Todas las diferencias quedaron explicadas por patrones ya conocidos y cerrados -- nada para revisar.")

    return necesitan_revision


def main():
    # try/finally sobre la conexion -- mismo patron que diagnostico_planillas_cliente.py
    # (el otro precedente citado en la cabecera de este archivo). Sin esto,
    # una excepcion en cualquiera de las funciones de abajo deja la conexion
    # abierta hasta que el proceso termine (hallazgo de /code-review).
    conn = connect()
    try:
        cur = conn.cursor()
        diffs = comparar_ventas(cur) + comparar_stock(cur)
        skus = sorted({d["sku"] for d in diffs})
        catalogo = cargar_catalogo(cur, skus)
        necesitan_revision = reportar(diffs, catalogo)
    finally:
        conn.close()

    print(f"\n=== RESULTADO: {'TODO CERRADO' if not necesitan_revision else f'{len(necesitan_revision)} NECESITAN REVISIÓN'} ===")
    sys.exit(0 if not necesitan_revision else 2)


if __name__ == "__main__":
    main()
