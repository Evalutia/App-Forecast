#!/usr/bin/env python3
"""
comparar_ventas_mensual.py — Issue #196.

La comparación maestra: las 13 columnas mensuales de venta del archivo de
ventas del cliente, celda por celda, contra `ventas_historicas` agregada por
mes. Consume el cargador de #195 y es el dataset del que van a tirar #197
(depósito 2) y #198 (validaciones transversales).

Solo lectura: no escribe nada en la base ni toca los archivos.

Uso (desde el host, con túnel SSH a producción -- ver scripts/
cargador_archivos_cliente.py para el patrón completo):

  ssh -f -N -L 13307:localhost:3307 <vm>
  MYSQL_HOST=127.0.0.1 MYSQL_PORT=13307 MYSQL_USER=root MYSQL_PASSWORD=... \
    python3 scripts/comparar_ventas_mensual.py

Ya está medido el agregado y hay señal fuerte: estamos consistentemente 4-6%
por debajo del cliente, los 13 meses, sin excepción (−4,5% sobre el total sin
restringir). Un bug de extracción es episódico; esto tiene la forma de un canal
de venta excluido de manera permanente. Este script baja esa brecha a nivel
SKU/mes, la parte por cohorte de extracción y deja disponible la descomposición
diaria de cada mes que difiere, sin la cual nadie debería categorizar una
causa.

Dos cortes obligatorios, ambos explicados en el issue:

1. **Descomposición diaria.** Un agregado mensual puede tapar un hueco de día
   completo al compensarse con sobre-conteo del mismo mes (#188). Por eso toda
   fila con diferencia no nula trae la lista de (día, cantidad) de nuestro lado,
   calculada desde `ventas_historicas` -- no para que el cliente la vea (sólo
   tenemos SU total mensual, no su detalle diario), sino para inspeccionar si
   NUESTRA venta está pareja a lo largo del mes (consistente con un canal
   excluido siempre) o concentrada en unos pocos días (consistente con un
   incidente puntual de extracción).

2. **Cohorte de extracción.** La ventana está cortada por la fecha de carga:
   todo lo anterior al 2026-07-24 es del extractor viejo, desde ahí es del
   extractor nuevo de #192. Sin este corte, cada discrepancia queda confundida
   entre "diferencia real con el cliente" y "extractor viejo". Julio de 2026
   queda partido a la mitad -- no se le puede poner una sola etiqueta sin
   mentir, así que existe la cohorte 'mixto'.

La comparación real va siempre restringida al conjunto común de SKUs que
estableció #195 (su archivo trae 5.428, nuestro catálogo 5.656): comparar
totales sin restringir sesga a nuestro favor. Aparte, este script reproduce los
totales SIN restringir como chequeo de que el cargador y la agregación están
bien enganchados -- es la tabla que ya se verificó a mano contra el archivo
real, no la comparación diagnóstica.
"""

import calendar
import datetime as dt
import os
import sys
from dataclasses import dataclass, replace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cargador_archivos_cliente import (  # noqa: E402
    Cobertura,
    comparar_catalogo,
    leer_skus_nuestros,
    leer_ventas,
    normalizar_sku,
)

# 2026-07-24: fecha real de corte entre el extractor viejo y el nuevo de #192,
# medida contra `ts_carga` en producción (ver .claude/CONTEXTO.md, cierre de
# #195). No es una fecha de negocio -- es puramente operativa, así que vive acá
# como constante y no en config.
FECHA_CORTE_COHORTE = dt.date(2026, 7, 24)


def generar_ventana(inicio, n_meses):
    """(2025, 8), 13 -> [(2025,8), (2025,9), ..., (2026,8)], cruzando el año."""
    year, month = inicio
    ventana = []
    for _ in range(n_meses):
        ventana.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return ventana


def ventana_desde_ventas_cliente(ventas_cliente):
    """
    {sku: ArticuloCliente} -> [(y,m), ...], sacada de los meses realmente
    presentes en el archivo, no de una constante hardcodeada.

    El archivo de hoy cubre Ago/25→Ago/26, pero el próximo que mande el cliente
    va a estar corrido -- mismo motivo por el que `cargador_archivos_cliente.
    parse_mes` ya lee el header en vez de asumir una ventana fija. Si la
    ventana quedara fija acá, el archivo nuevo se compararía en silencio contra
    meses viejos: el mes que se corrió hacia afuera se leería como "no vendió"
    (falso déficit/superávit) y el mes nuevo jamás se compararía.

    Se arma con la UNIÓN de los meses de todos los artículos (no todos tienen
    el mismo diccionario poblado), y falla fuerte si el resultado no es
    contiguo -- un header roto no debe colarse como una ventana con huecos.
    """
    meses = sorted({m for a in ventas_cliente.values() for m in a.ventas})
    if not meses:
        raise ValueError("El archivo de ventas no trae ninguna columna de mes reconocible.")
    esperado = generar_ventana(meses[0], len(meses))
    if meses != esperado:
        raise ValueError(f"La ventana de meses del archivo no es contigua: {meses}")
    return meses


def cohorte_de_mes(year, month):
    """
    (year, month) -> 'pre' | 'post' | 'mixto', según si el mes cae antes,
    después, o a caballo de FECHA_CORTE_COHORTE.
    """
    primer_dia = dt.date(year, month, 1)
    ultimo_dia = dt.date(year, month, calendar.monthrange(year, month)[1])
    if ultimo_dia < FECHA_CORTE_COHORTE:
        return "pre"
    if primer_dia >= FECHA_CORTE_COHORTE:
        return "post"
    return "mixto"


@dataclass(frozen=True)
class FilaDiscrepancia:
    """
    Una fila (SKU, mes) del dataset de discrepancias.

    `cliente_original` preserva la distinción nulo/no-vendió del archivo del
    cliente (#195); `cliente_numerico` es la misma información llevada a 0 para
    poder restar, que es matemáticamente correcto porque el cliente nunca
    escribe un 0 explícito -- "no vendió" y "vendió 0" son el mismo hecho acá.
    """
    sku: str
    year: int
    month: int
    cohorte: str
    cliente_original: int | None
    cliente_numerico: int
    nuestro: int
    diff_abs: int
    diff_rel: float | None
    categoria: str
    dias_nuestro: tuple | None = None
    dias_con_venta_nuestra: int | None = None

    @property
    def dias_naturales_mes(self):
        return calendar.monthrange(self.year, self.month)[1]


def _categoria(diff_abs):
    if diff_abs == 0:
        return "coincide"
    return "deficit" if diff_abs < 0 else "superavit"


def construir_dataset_discrepancias(ventas_cliente, agregados_nuestro, comunes, ventana):
    """
    {sku: ArticuloCliente}, {(sku,y,m): int}, {sku}, [(y,m), ...]
      -> [FilaDiscrepancia]

    Una fila por cada (SKU en `comunes`, mes en `ventana`) -- incluidos los que
    coinciden, porque "coincide" es una categoría tan real como las otras y el
    criterio de aceptación pide una fila por cada combinación, no sólo las que
    difieren.

    Recorre `comunes` directo, no la unión de los SKUs que aparecen en
    `ventas_cliente`/`agregados_nuestro` -- un SKU del catálogo común que no
    vendió de NINGÚN lado en toda la ventana tiene que aparecer igual, como
    'coincide'. Intersecar antes de recorrer lo hacía desaparecer del dataset
    en vez de aparecer con diff 0, aunque el `.get(..., default)` de cada
    lookup ya tolera que falte en cualquiera de los dos dicts.
    """
    filas = []
    for sku in sorted(comunes):
        articulo = ventas_cliente.get(sku)
        for year, month in ventana:
            cliente_original = articulo.ventas.get((year, month)) if articulo else None
            cliente_numerico = cliente_original or 0
            nuestro = agregados_nuestro.get((sku, year, month), 0)
            diff_abs = nuestro - cliente_numerico
            diff_rel = (diff_abs / cliente_numerico) if cliente_numerico else None
            filas.append(FilaDiscrepancia(
                sku=sku, year=year, month=month,
                cohorte=cohorte_de_mes(year, month),
                cliente_original=cliente_original,
                cliente_numerico=cliente_numerico,
                nuestro=nuestro,
                diff_abs=diff_abs,
                diff_rel=diff_rel,
                categoria=_categoria(diff_abs),
            ))
    return filas


def adjuntar_descomposicion_diaria(filas, diario):
    """
    Adjunta a cada fila con diferencia no nula la lista de (día, cantidad) de
    nuestro lado, sacada de `diario` ({(sku,y,m): [(día, cantidad), ...]}).

    Las filas que coinciden no la necesitan -- pedirle a alguien que revise el
    detalle diario de un mes donde ya sabemos que no hay diferencia sería puro
    ruido. Si el mes difiere pero no hay filas diarias en `diario` (no debería
    pasar, pero un dataset real da sorpresas), no explota: día vacío en vez de
    KeyError, para que un hueco de datos no tire abajo toda la corrida.

    No recibe un dict de días naturales por mes: `FilaDiscrepancia.
    dias_naturales_mes` lo calcula solo con `calendar.monthrange`, un dato
    derivable de `year`/`month` que ya tiene la fila -- no hace falta ni vale
    la pena threadearlo como parámetro aparte.
    """
    resultado = []
    for fila in filas:
        if fila.diff_abs == 0:
            resultado.append(fila)
            continue
        dias = tuple(diario.get((fila.sku, fila.year, fila.month), ()))
        resultado.append(replace(
            fila,
            dias_nuestro=dias,
            dias_con_venta_nuestra=sum(1 for _, cant in dias if cant),
        ))
    return resultado


CATEGORIAS = ("coincide", "deficit", "superavit")


def resumen_categorias(filas):
    """
    {categoria: {'filas': n, 'unidades': abs(sum(diff)), 'pct_unidades': pct}}

    El denominador de `pct_unidades` es el total de unidades de diferencia
    (deficit + superavit); 'coincide' aporta 0 unidades por definición, así que
    aparece con 0% sin dividir por cero. deficit% + superavit% suman 100% por
    construcción -- es justamente lo que pide el criterio de aceptación de
    "100% de las unidades de diferencia asignado a una categoría con nombre":
    acá no hay dónde esconder un residuo sin categorizar.
    """
    total_diferencia = sum(abs(f.diff_abs) for f in filas)
    resumen = {c: {"filas": 0, "unidades": 0} for c in CATEGORIAS}
    for f in filas:
        if f.categoria not in resumen:
            # `_categoria()` y `CATEGORIAS` son dos fuentes separadas del mismo
            # vocabulario; si alguna vez divergen (se agrega una categoría acá
            # sin tocar la otra), mejor este mensaje que un KeyError críptico
            # a mitad de una corrida contra producción.
            raise ValueError(
                f"Categoría '{f.categoria}' no está en CATEGORIAS {CATEGORIAS} -- "
                f"¿se agregó en _categoria() sin actualizar la constante?")
        resumen[f.categoria]["filas"] += 1
        resumen[f.categoria]["unidades"] += abs(f.diff_abs)
    for c in CATEGORIAS:
        unidades = resumen[c]["unidades"]
        resumen[c]["pct_unidades"] = (unidades / total_diferencia * 100) if total_diferencia else 0.0
    return resumen


def resumen_por_cohorte(filas):
    """
    {cohorte: {'unidades_cliente', 'unidades_nuestro', 'diff', 'brecha_relativa'}}

    Es la evidencia directa para la hipótesis del extractor: si la brecha
    relativa de 'post' (extractor nuevo, #192) es del mismo orden que la de
    'pre' (extractor viejo), el extractor no es la causa principal y hay que
    mirar para otro lado (depósito 2, #197).
    """
    resumen = {}
    for f in filas:
        r = resumen.setdefault(f.cohorte, {"unidades_cliente": 0, "unidades_nuestro": 0})
        r["unidades_cliente"] += f.cliente_numerico
        r["unidades_nuestro"] += f.nuestro
    for r in resumen.values():
        r["diff"] = r["unidades_nuestro"] - r["unidades_cliente"]
        r["brecha_relativa"] = (r["diff"] / r["unidades_cliente"]) if r["unidades_cliente"] else None
    return resumen


@dataclass(frozen=True)
class UnidadesExcluidas:
    unidades_solo_cliente: int
    unidades_solo_nuestras: int


def unidades_excluidas_por_restriccion(cobertura: Cobertura, ventas_cliente_sin_restringir,
                                       agregados_nuestro_sin_restringir):
    """
    Cuánto suman, en la ventana, los SKUs que quedan afuera al restringir al
    conjunto común -- para poder decir "la comparación ignora N unidades suyas
    y M nuestras", no sólo "ignora X SKUs".

    Asume que `cobertura` se calculó contra el mismo `ventas_cliente_sin_restringir`
    que se le pasa acá; si viniera de un snapshot distinto, un SKU de
    `solo_cliente` podría faltar en el dict. Se valida explícito en vez de
    dejar que un `KeyError` críptico aborte la corrida.
    """
    faltantes = [sku for sku in cobertura.solo_cliente if sku not in ventas_cliente_sin_restringir]
    if faltantes:
        raise ValueError(
            f"`cobertura` no coincide con `ventas_cliente_sin_restringir`: "
            f"faltan {', '.join(faltantes)}. ¿Se calcularon contra snapshots distintos?")

    unidades_cliente = sum(
        (v or 0)
        for sku in cobertura.solo_cliente
        for v in ventas_cliente_sin_restringir[sku].ventas.values()
    )
    unidades_nuestras = sum(
        cant for (sku, _, _), cant in agregados_nuestro_sin_restringir.items()
        if sku in cobertura.solo_nuestros
    )
    return UnidadesExcluidas(unidades_solo_cliente=unidades_cliente,
                             unidades_solo_nuestras=unidades_nuestras)


def totales_mensuales_cliente(ventas_cliente):
    """
    {(y,m): unidades}, sumando TODOS los SKUs del archivo sin restringir al
    conjunto común. Es el chequeo de reproducibilidad del criterio de
    aceptación #5 -- tiene que dar exactamente la tabla ya verificada a mano
    contra el archivo real, no la comparación diagnóstica del ticket.
    """
    totales = {}
    for articulo in ventas_cliente.values():
        for mes, cantidad in articulo.ventas.items():
            totales[mes] = totales.get(mes, 0) + (cantidad or 0)
    return totales


# ── I/O contra MySQL ─────────────────────────────────────────────────────────

def _en_lotes(items, tam=200):
    items = list(items)
    for i in range(0, len(items), tam):
        yield items[i:i + tam]


def _conectar():
    import pymysql
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "mysql"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ.get("MYSQL_DB", "evalutia"),
    )


def _rango_fechas(ventana):
    y0, m0 = ventana[0]
    y1, m1 = ventana[-1]
    desde = dt.date(y0, m0, 1)
    hasta = dt.date(y1, m1, calendar.monthrange(y1, m1)[1])
    return desde, hasta


def totales_mensuales_nuestros(agregados):
    """
    {(sku,y,m): unidades} -> {(y,m): unidades}. Función pura: reduce el
    agregado por SKU a un total por mes.

    Antes esto se pedía con una segunda query a `ventas_historicas` (mismo
    rango de fechas que `leer_agregado_mensual_nuestro`, sólo cambiaba el
    GROUP BY) -- un segundo scan completo de la ventana para un dato que ya
    estaba en el primer resultado. Se deriva en Python en vez de pagar el scan
    dos veces.
    """
    totales = {}
    for (_, y, m), total in agregados.items():
        clave = (y, m)
        totales[clave] = totales.get(clave, 0) + total
    return totales


def leer_agregado_mensual_nuestro(conn, ventana):
    """
    {(sku,y,m): unidades}, TODO el catálogo, un solo GROUP BY (más simple y más
    rápido que un IN con miles de SKUs -- MySQL escanea el rango de fechas una
    sola vez, con `idx_ventas_fecha`/`idx_ventas_sku_fecha`: verificado con
    `EXPLAIN` contra producción que usa `range` sobre el índice, no un scan
    completo -- distinto del patrón que tumbó el contenedor local en #153, que
    era una subquery correlacionada sin índice).

    No filtra por SKU: se pide una sola vez y el llamador lo recorta en Python
    para el conjunto común y para "unidades excluidas por la restricción" al
    mismo tiempo, en vez de pagar el mismo scan dos veces.

    Las claves se normalizan con `normalizar_sku` -- la misma función que ya
    usa `comparar_catalogo` sobre `articulos` y sobre el archivo del cliente.
    La colación de `ventas_historicas.sku` es `utf8mb4_0900_ai_ci` (case/acento
    insensible), así que dos filas con distinto casing para el mismo artículo
    colapsan en el mismo GROUP BY de MySQL -- pero si alguna vez quedaran
    variantes sin colapsar (dos SKUs que la colación ve iguales y `GROUP BY`
    no, por venir de casts distintos), sin esta normalización quedarían con
    claves Python distintas de las de `cobertura` (que sí está normalizada) y
    `restringir_agregados` las descartaría en silencio. Se suman en vez de
    pisarse, por si acaso.
    """
    desde, hasta = _rango_fechas(ventana)
    agregados = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sku, YEAR(fecha), MONTH(fecha), SUM(cantidad) "
            "FROM ventas_historicas WHERE fecha BETWEEN %s AND %s "
            "GROUP BY sku, YEAR(fecha), MONTH(fecha)",
            (desde, hasta),
        )
        for sku, y, m, total in cur.fetchall():
            clave = (normalizar_sku(sku), y, m)
            agregados[clave] = agregados.get(clave, 0) + int(total)
    return agregados


def restringir_agregados(agregados, comunes):
    """Filtra {(sku,y,m): unidades} a los SKUs de `comunes`. Función pura."""
    comunes = set(comunes)
    return {clave: total for clave, total in agregados.items() if clave[0] in comunes}


def leer_diario_nuestro(conn, skus, ventana):
    """
    {(sku,y,m): [(día_del_mes, cantidad), ...]}, sólo para los SKUs pedidos --
    a diferencia del agregado mensual, acá sí conviene filtrar en SQL: sólo
    hace falta el detalle diario de los SKU-mes que ya salieron con diferencia,
    que son muchos menos que el catálogo completo.

    El `IN (...)` matchea sin importar el casing (colación `_ai_ci` de la
    columna), pero la fila que vuelve trae el casing tal cual está guardado en
    la tabla -- se normaliza con `normalizar_sku` antes de armar la clave, para
    que `adjuntar_descomposicion_diaria` (que busca por `fila.sku`, ya
    normalizado) no falle el lookup en silencio por una diferencia de
    mayúsculas que a MySQL ya le dio lo mismo.
    """
    skus = sorted(normalizar_sku(s) for s in set(skus))
    if not skus:
        return {}
    desde, hasta = _rango_fechas(ventana)
    diario = {}
    with conn.cursor() as cur:
        for lote in _en_lotes(skus):
            placeholders = ",".join(["%s"] * len(lote))
            cur.execute(
                f"SELECT sku, fecha, cantidad FROM ventas_historicas "
                f"WHERE fecha BETWEEN %s AND %s AND sku IN ({placeholders})",
                (desde, hasta, *lote),
            )
            for sku, fecha, cantidad in cur.fetchall():
                clave = (normalizar_sku(sku), fecha.year, fecha.month)
                diario.setdefault(clave, []).append((fecha.day, int(cantidad)))
    for lista in diario.values():
        lista.sort()
    return diario


# ── informe ──────────────────────────────────────────────────────────────────

def main():
    if not os.environ.get("MYSQL_PASSWORD"):
        print("Falta MYSQL_PASSWORD -- sin conexión no hay nada que comparar.", file=sys.stderr)
        return 1

    ventas_cliente = leer_ventas()
    ventana = ventana_desde_ventas_cliente(ventas_cliente)
    conn = _conectar()
    try:
        nuestros = leer_skus_nuestros(conn)
        cobertura = comparar_catalogo(list(ventas_cliente), nuestros)
        comunes = set(cobertura.comunes)
        agregados_todos = leer_agregado_mensual_nuestro(conn, ventana)

        print("=" * 78)
        print("CHEQUEO DE REPRODUCIBILIDAD (sin restringir al conjunto común)")
        print("=" * 78)
        totales_cliente = totales_mensuales_cliente(ventas_cliente)
        totales_nuestros = totales_mensuales_nuestros(agregados_todos)
        for year, month in ventana:
            tc = totales_cliente.get((year, month), 0)
            tn = totales_nuestros.get((year, month), 0)
            delta = (tn - tc) / tc * 100 if tc else float("nan")
            print(f"  {year}-{month:02d}: ellos {tc:>7}  nosotros {tn:>7}  Δ {delta:+.1f}%")
        print(f"  TOTAL: ellos {sum(totales_cliente.values())}  "
              f"nosotros {sum(totales_nuestros.values())}")

        print()
        print("=" * 78)
        print(f"COMPARACIÓN RESTRINGIDA AL CONJUNTO COMÚN ({len(comunes)} SKUs)")
        print("=" * 78)
        excluidas = unidades_excluidas_por_restriccion(cobertura, ventas_cliente, agregados_todos)
        print(f"  Unidades excluidas por la restricción: "
              f"{excluidas.unidades_solo_cliente} suyas, "
              f"{excluidas.unidades_solo_nuestras} nuestras")

        agregados = restringir_agregados(agregados_todos, comunes)
        filas = construir_dataset_discrepancias(ventas_cliente, agregados, comunes, ventana)

        con_diferencia = [f for f in filas if f.diff_abs != 0]
        skus_a_bajar_a_dia = {f.sku for f in con_diferencia}
        diario = leer_diario_nuestro(conn, skus_a_bajar_a_dia, ventana)
        filas = adjuntar_descomposicion_diaria(filas, diario)

        print()
        print("  -- categorías (100% de las unidades de diferencia) --")
        for categoria, datos in resumen_categorias(filas).items():
            print(f"    {categoria:<10} {datos['filas']:>6} filas  "
                  f"{datos['unidades']:>8} u  {datos['pct_unidades']:5.1f}%")

        print()
        print("  -- por cohorte de extracción --")
        for cohorte, datos in sorted(resumen_por_cohorte(filas).items()):
            br = datos["brecha_relativa"]
            br_txt = f"{br * 100:+.1f}%" if br is not None else "(sin base)"
            print(f"    {cohorte:<8} ellos {datos['unidades_cliente']:>7}  "
                  f"nosotros {datos['unidades_nuestro']:>7}  brecha {br_txt}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
