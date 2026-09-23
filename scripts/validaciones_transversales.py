#!/usr/bin/env python3
"""
validaciones_transversales.py — Issue #198.

Tres barridos de validación sobre el dataset de discrepancias de #196:
negativos (devoluciones/notas de crédito), pisado multi-grupo (#114/#162), y
concentración por género. Los tres responden la misma pregunta: ¿la brecha se
concentra en algún subconjunto identificable de SKUs?

Solo lectura: no escribe nada en la base ni toca los archivos.

Uso (desde el host, con túnel SSH a producción -- ver scripts/
cargador_archivos_cliente.py para el patrón completo):

  ssh -f -N -L 13307:localhost:3307 <vm>
  MYSQL_HOST=127.0.0.1 MYSQL_PORT=13307 MYSQL_USER=root MYSQL_PASSWORD=... \
    python3 scripts/validaciones_transversales.py
"""

import os
import sys
from dataclasses import dataclass, replace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cargador_archivos_cliente import (  # noqa: E402
    comparar_catalogo,
    leer_movimientos,
    leer_skus_nuestros,
    leer_ventas,
    normalizar_sku,
)
from comparar_ventas_mensual import (  # noqa: E402
    agregado_mensual_por_tabla,
    cohorte_de_mes,
    conectar,
    construir_dataset_discrepancias,
    rango_fechas,
    restringir_agregados,
    ventana_desde_ventas_cliente,
)

# ── 1. Negativos (devoluciones / notas de crédito, #80) ──────────────────────


@dataclass(frozen=True)
class CeldaNegativa:
    """Una celda mensual negativa del archivo del cliente, con su contraparte
    (o ausencia) en nuestros datos diarios."""
    sku: str
    year: int
    month: int
    cohorte: str
    valor_cliente: int
    dias_negativos_nuestro: int
    unidades_negativas_nuestro: int

    @property
    def tiene_contraparte(self):
        return self.dias_negativos_nuestro > 0


def construir_negativos_cliente(ventas_cliente, comunes):
    """
    {sku: ArticuloCliente}, {sku} -> (CeldaNegativa, ...)

    Sólo las celdas con valor < 0, restringidas al conjunto común. Los campos
    "nuestro" se completan después con `adjuntar_contraparte_nuestro` -- acá
    quedan en 0, esta función es pura sobre el lado del cliente solamente.
    """
    celdas = []
    for sku in sorted(comunes):
        articulo = ventas_cliente.get(sku)
        if articulo is None:
            continue
        for (year, month), valor in articulo.ventas.items():
            if valor is not None and valor < 0:
                celdas.append(CeldaNegativa(
                    sku=sku, year=year, month=month, cohorte=cohorte_de_mes(year, month),
                    valor_cliente=valor, dias_negativos_nuestro=0, unidades_negativas_nuestro=0,
                ))
    return tuple(celdas)


def adjuntar_contraparte_nuestro(celdas, negativos_nuestro):
    """
    (CeldaNegativa, ...), {(sku,y,m): (dias, unidades)} -> (CeldaNegativa, ...)

    Completa `dias_negativos_nuestro`/`unidades_negativas_nuestro` desde lo
    leído de `ventas_historicas`. Separado de `construir_negativos_cliente`
    para que esa función siga siendo pura sin depender de I/O.
    """
    resultado = []
    for c in celdas:
        dias, unidades = negativos_nuestro.get((c.sku, c.year, c.month), (0, 0))
        resultado.append(replace(c, dias_negativos_nuestro=dias, unidades_negativas_nuestro=unidades))
    return tuple(resultado)


def resumen_negativos_cliente(celdas):
    """
    {total, con_contraparte, sin_contraparte, por_cohorte: {cohorte: {...}}}

    Es la dirección principal del criterio de aceptación: de las celdas
    negativas del cliente, cuántas tienen ALGUNA actividad negativa nuestra
    ese mes (no exige que coincida el valor exacto -- la escala mes-vs-día no
    lo permite, sólo que exista contraparte).
    """
    resumen = {"total": len(celdas), "con_contraparte": 0, "sin_contraparte": 0, "por_cohorte": {}}
    for c in celdas:
        clave = "con_contraparte" if c.tiene_contraparte else "sin_contraparte"
        resumen[clave] += 1
        por_cohorte = resumen["por_cohorte"].setdefault(
            c.cohorte, {"total": 0, "con_contraparte": 0, "sin_contraparte": 0})
        por_cohorte["total"] += 1
        por_cohorte[clave] += 1
    return resumen


def resumen_negativos_nuestro(negativos_nuestro_por_sku_mes, negativos_cliente_set):
    """
    {(sku,y,m): dias_negativos}, {(sku,y,m)} -> resumen

    Dirección inversa: de los (sku,mes) donde NOSOTROS tenemos al menos un día
    con cantidad negativa, cuántos caen en un mes que el cliente también
    reportó negativo, y cuántos en un mes que para el cliente neteó a
    positivo/cero o no aparece en el archivo -- ilustra por qué las dos
    escalas (mensual vs. diaria) no son directamente comparables 1 a 1.
    """
    claves = [k for k, dias in negativos_nuestro_por_sku_mes.items() if dias > 0]
    coincide = sum(1 for k in claves if k in negativos_cliente_set)
    return {
        "total_meses_con_negativo_nuestro": len(claves),
        "coincide_con_cliente": coincide,
        "neteado_o_ausente_del_lado_cliente": len(claves) - coincide,
    }


# ── 2. Pisado multi-grupo (#114/#162) ─────────────────────────────────────────

def clasificar_grupos(n_grupos):
    """0 -> 'sin_grupo' (no debería pasar en catálogo real, pero no se asume).
    1 -> 'unico'. 2+ -> 'multi' (candidato al pisado de #114/#162)."""
    if n_grupos == 0:
        return "sin_grupo"
    if n_grupos == 1:
        return "unico"
    return "multi"


POBLACIONES_GRUPO = ("sin_grupo", "unico", "multi")


def resumen_por_poblacion_grupo(filas, grupos_por_sku):
    """
    [FilaDiscrepancia], {sku: n_grupos} -> {poblacion: {'skus','unidades_deficit'}}

    El tamaño de población es SKUs distintos, no cantidad de filas (un SKU
    aparece una vez por mes en el dataset de #196). Sólo suma unidades de
    déficit -- el eje de "¿el pisado multi-grupo empeora la brecha?".
    """
    skus_por_poblacion = {p: set() for p in POBLACIONES_GRUPO}
    deficit_por_poblacion = {p: 0 for p in POBLACIONES_GRUPO}
    for f in filas:
        poblacion = clasificar_grupos(grupos_por_sku.get(f.sku, 0))
        skus_por_poblacion[poblacion].add(f.sku)
        if f.categoria == "deficit":
            deficit_por_poblacion[poblacion] += abs(f.diff_abs)
    return {
        p: {"skus": len(skus_por_poblacion[p]), "unidades_deficit": deficit_por_poblacion[p]}
        for p in POBLACIONES_GRUPO
    }


# ── 3. Concentración por género ───────────────────────────────────────────────

SIN_GENERO = "(sin género)"


def resumen_por_genero(filas, generos_por_sku):
    """
    [FilaDiscrepancia], {sku: genero_descripcion} -> {genero: {'unidades_deficit',
    'pct_del_total'}}, listo para ordenar por unidades_deficit descendente.

    Un SKU del conjunto común sin género nuestro cargado cae bajo
    `SIN_GENERO`, no se descarta en silencio.
    """
    deficit_por_genero = {}
    for f in filas:
        if f.categoria != "deficit":
            continue
        genero = generos_por_sku.get(f.sku) or SIN_GENERO
        deficit_por_genero[genero] = deficit_por_genero.get(genero, 0) + abs(f.diff_abs)
    total = sum(deficit_por_genero.values())
    return {
        genero: {"unidades_deficit": u, "pct_del_total": (u / total * 100) if total else 0.0}
        for genero, u in deficit_por_genero.items()
    }


def _normalizar_genero(texto):
    return " ".join(str(texto).split()).upper()


def comparar_clasificacion_genero(movimientos, generos_nuestro):
    """
    (Movimiento, ...), {sku: genero_descripcion} -> {'coincide','difiere',
    'sin_dato_archivo','sin_dato_nuestro','ejemplos'}

    Contrasta el género que trae cada banda del archivo de movimientos (#195)
    contra `articulos.genero_descripcion`, por SKU (no por fila -- un SKU
    puede repetirse en varios tipos de documento). Normaliza espacios/mayúsculas
    antes de comparar para no contar una diferencia de formato como una
    diferencia real de clasificación.

    En el archivo de hoy toda fila de detalle cae bajo una banda `Genero:`
    previa, así que `m.genero` nunca es None en la práctica -- pero
    `parsear_movimientos` (#195) lo inicializa en None y sólo lo llena al ver
    esa banda, así que un archivo futuro con una fila de detalle ANTES de la
    primera banda de género sí podría traer `None`. Se guarda explícito acá
    (no como `_normalizar_genero(None) == "NONE"`, que lo compararía como si
    fuera un género real y contaría un falso "difiere"), y se queda con el
    primer valor NO nulo que aparezca para ese SKU, no literalmente la primera
    fila -- si la primera ocurrencia trae None y una posterior sí trae dato,
    el dato real no se descarta.
    """
    genero_archivo_por_sku = {}
    for m in movimientos:
        if m.genero is not None and genero_archivo_por_sku.get(m.sku) is None:
            genero_archivo_por_sku[m.sku] = m.genero
        else:
            genero_archivo_por_sku.setdefault(m.sku, None)

    coincide = difiere = sin_dato_nuestro = sin_dato_archivo = 0
    ejemplos = []
    for sku, genero_archivo in genero_archivo_por_sku.items():
        if genero_archivo is None:
            sin_dato_archivo += 1
            continue
        genero_nuestro = generos_nuestro.get(sku)
        if genero_nuestro is None:
            sin_dato_nuestro += 1
            continue
        if _normalizar_genero(genero_archivo) == _normalizar_genero(genero_nuestro):
            coincide += 1
        else:
            difiere += 1
            if len(ejemplos) < 10:
                ejemplos.append((sku, genero_archivo, genero_nuestro))
    return {"coincide": coincide, "difiere": difiere, "sin_dato_nuestro": sin_dato_nuestro,
            "sin_dato_archivo": sin_dato_archivo, "ejemplos": ejemplos}


# ── I/O contra MySQL ──────────────────────────────────────────────────────────

def leer_negativos_nuestro(conn, ventana):
    """{(sku,y,m): (dias_con_cantidad_negativa, suma_de_esas_unidades)}, TODO
    el catálogo, restringido a filas con `cantidad < 0`.

    Suma en vez de sobrescribir si dos variantes de casing/acento del mismo
    SKU llegan sin colapsar en el GROUP BY -- mismo invariante que
    `agregado_mensual_por_tabla` (#196/#197) protege para el mismo riesgo."""
    desde, hasta = rango_fechas(ventana)
    resultado = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sku, YEAR(fecha), MONTH(fecha), COUNT(*), SUM(cantidad) "
            "FROM ventas_historicas WHERE cantidad < 0 AND fecha BETWEEN %s AND %s "
            "GROUP BY sku, YEAR(fecha), MONTH(fecha)",
            (desde, hasta),
        )
        for sku, y, m, dias, unidades in cur.fetchall():
            clave = (normalizar_sku(sku), y, m)
            dias_prev, unidades_prev = resultado.get(clave, (0, 0))
            resultado[clave] = (dias_prev + int(dias), unidades_prev + int(unidades))
    return resultado


def leer_grupos_por_sku(conn, skus):
    """{sku: n_grupos}, vía `articulo_grupo` (many-to-many, post-#121). Suma
    en vez de sobrescribir por el mismo motivo que `leer_negativos_nuestro`."""
    skus = sorted(set(skus))
    if not skus:
        return {}
    placeholders = ",".join(["%s"] * len(skus))
    resultado = {}
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT sku, COUNT(*) FROM articulo_grupo WHERE sku IN ({placeholders}) "
            f"GROUP BY sku",
            skus,
        )
        for sku, n in cur.fetchall():
            clave = normalizar_sku(sku)
            resultado[clave] = resultado.get(clave, 0) + int(n)
    return resultado


def leer_generos(conn, skus):
    """{sku: genero_descripcion}, para los SKUs pedidos."""
    skus = sorted(set(skus))
    if not skus:
        return {}
    placeholders = ",".join(["%s"] * len(skus))
    resultado = {}
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT sku, genero_descripcion FROM articulos WHERE sku IN ({placeholders})",
            skus,
        )
        for sku, genero in cur.fetchall():
            if genero:
                resultado[normalizar_sku(sku)] = genero
    return resultado


# ── informe ────────────────────────────────────────────────────────────────────

def main():
    if not os.environ.get("MYSQL_PASSWORD"):
        print("Falta MYSQL_PASSWORD -- sin conexión no hay nada que comparar.", file=sys.stderr)
        return 1

    ventas_cliente = leer_ventas()
    ventana = ventana_desde_ventas_cliente(ventas_cliente)
    movimientos, _ = leer_movimientos()

    conn = conectar()
    try:
        nuestros = leer_skus_nuestros(conn)
        cobertura = comparar_catalogo(list(ventas_cliente), nuestros)
        comunes = set(cobertura.comunes)

        agregados_todos = agregado_mensual_por_tabla(conn, ventana, "ventas_historicas")
        agregados_comunes = restringir_agregados(agregados_todos, comunes)
        filas = construir_dataset_discrepancias(ventas_cliente, agregados_comunes, comunes, ventana)

        print("=" * 78)
        print("1 · LOS 331 NEGATIVOS (devoluciones / notas de crédito, #80)")
        print("=" * 78)
        negativos_nuestro = leer_negativos_nuestro(conn, ventana)
        celdas = construir_negativos_cliente(ventas_cliente, comunes)
        celdas = adjuntar_contraparte_nuestro(celdas, negativos_nuestro)
        r1 = resumen_negativos_cliente(celdas)
        print(f"  Celdas negativas del cliente (conjunto común): {r1['total']}")
        print(f"  Con contraparte (algún día negativo nuestro ese mes): "
              f"{r1['con_contraparte']} ({100*r1['con_contraparte']/r1['total']:.1f}%)"
              if r1['total'] else "")
        print(f"  Sin contraparte: {r1['sin_contraparte']}")
        for cohorte, d in sorted(r1["por_cohorte"].items()):
            print(f"    [{cohorte}] total={d['total']} con_contraparte={d['con_contraparte']} "
                  f"sin_contraparte={d['sin_contraparte']}")

        negativos_cliente_set = {(c.sku, c.year, c.month) for c in celdas}
        negativos_nuestro_dias = {k: v[0] for k, v in negativos_nuestro.items() if k[0] in comunes}
        r1b = resumen_negativos_nuestro(negativos_nuestro_dias, negativos_cliente_set)
        print(f"\n  Dirección inversa -- de nuestros (sku,mes) con algún día negativo: "
              f"{r1b['total_meses_con_negativo_nuestro']}")
        print(f"    coincide con mes negativo del cliente: {r1b['coincide_con_cliente']}")
        print(f"    neteado a positivo o ausente del lado cliente: "
              f"{r1b['neteado_o_ausente_del_lado_cliente']}")

        print()
        print("=" * 78)
        print("2 · PISADO MULTI-GRUPO (#114/#162)")
        print("=" * 78)
        grupos_por_sku = leer_grupos_por_sku(conn, comunes)
        r2 = resumen_por_poblacion_grupo(filas, grupos_por_sku)
        for poblacion in POBLACIONES_GRUPO:
            d = r2[poblacion]
            tasa = (d["unidades_deficit"] / d["skus"]) if d["skus"] else 0.0
            print(f"  {poblacion:<10} {d['skus']:>5} SKUs   déficit={d['unidades_deficit']:>7}u"
                  f"   ({tasa:.2f} u/SKU)")

        print()
        print("=" * 78)
        print("3 · CONCENTRACIÓN POR GÉNERO")
        print("=" * 78)
        generos_por_sku = leer_generos(conn, comunes)
        r3 = resumen_por_genero(filas, generos_por_sku)
        for genero, d in sorted(r3.items(), key=lambda kv: -kv[1]["unidades_deficit"])[:15]:
            print(f"  {genero:<30} {d['unidades_deficit']:>7}u   {d['pct_del_total']:5.1f}%")

        r3b = comparar_clasificacion_genero(movimientos, generos_por_sku)
        total_genero = r3b["coincide"] + r3b["difiere"]
        print(f"\n  Clasificación de género, archivo de movimientos vs. nuestro dato: "
              f"{r3b['coincide']}/{total_genero} coincide" if total_genero else "")
        print(f"    sin dato nuestro: {r3b['sin_dato_nuestro']}")
        for sku, ga, gn in r3b["ejemplos"]:
            print(f"    {sku}: archivo='{ga}' nuestro='{gn}'")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
