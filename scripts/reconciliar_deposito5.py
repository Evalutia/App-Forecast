#!/usr/bin/env python3
"""
reconciliar_deposito5.py — Issue #199.

Reconcilia los movimientos de julio del depósito 5 (archivo 2 del cliente,
#195) contra nuestro `stock_diario`, y deja establecido con qué alcance ese
archivo puede o no confirmar la hipótesis de #193 sobre el remito a depósito 2.

Solo lectura: no escribe nada en la base ni toca los archivos.

Uso (desde el host, con túnel SSH a producción -- ver scripts/
cargador_archivos_cliente.py para el patrón completo):

  ssh -f -N -L 13307:localhost:3307 <vm>
  MYSQL_HOST=127.0.0.1 MYSQL_PORT=13307 MYSQL_USER=root MYSQL_PASSWORD=... \
    python3 scripts/reconciliar_deposito5.py

El archivo tiene tres tipos de documento -- Ajuste de Entrada (+403), Ajuste
de Salida (−819), Entrada de Mercadería (+466) -- y el planteo original era
que las −819 unidades de salida eran stock perdido sin explicar. La
verificación de #195 mostró que eso es sólo parte de la historia:

1. **El 100% de las +466 unidades de Entrada de Mercadería es la contrapartida
   exacta de salidas del mismo mes** (`emparejar_recodificaciones`, #195): son
   códigos de SKU retirados y re-ingresados con otro nombre, no stock perdido.
2. **Hay un par que se cancela dentro del mismo tipo**: C00477 aparece con
   +50 de Ajuste de Entrada y −50 de Ajuste de Salida -- una corrección de
   error tipeado, neto cero. Es distinto de una recodificación (que empareja
   Salida contra Entrada de Mercadería, no Entrada contra Salida).

Descontando ambos, la salida neta genuina son 303 unidades (no las ~353 del
planteo original del issue, que sólo descontaba la recodificación y no el
autocancelante -- ver la nota en `desglose_salida`).

**Límite de alcance para #193, explícito**: la fila `Total General` del
archivo imprime `Doc.: AJE,AJS,EMR,SMR` -- una whitelist de tipos de
documento. Que SMR (presumiblemente remito) haya vuelto vacío es evidencia A
FAVOR de la hipótesis de #193, pero sólo si SMR es efectivamente el código de
remito -- dato no confirmado. Una transferencia con cualquier otro código
quedó excluida POR EL FILTRO, no por ausencia real. De este archivo no se
puede concluir "no hay transferencias", sólo "no hay ninguno de los cuatro
tipos pedidos". El informe de este script repite esa limitación explícita,
para que nadie la lea como una confirmación que el archivo no sostiene.
"""

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cargador_archivos_cliente import (  # noqa: E402
    AJUSTE_ENTRADA,
    AJUSTE_SALIDA,
    ENTRADA_MERCADERIA,
    emparejar_recodificaciones,
    leer_movimientos,
)
from comparar_ventas_mensual import conectar  # noqa: E402

DEPOSITO_ARCHIVO = "5"

# Ventana de contexto alrededor de julio de 2026 (el mes que cubre el
# archivo), suficiente para calcular "último valor antes de julio" y "último
# valor durante julio" sin asumir que stock_diario tiene una fila por día.
DESDE_CONTEXTO = "2026-06-01"
HASTA_CONTEXTO = "2026-07-31"
FIN_JUNIO = "2026-06-30"
INICIO_JULIO = "2026-07-01"
FIN_JULIO = "2026-07-31"


@dataclass(frozen=True)
class Autocancelante:
    """Un SKU con entradas y salidas que se cancelan exactamente en el mes."""
    sku: str
    entrada: int
    salida: int


def identificar_autocancelantes(movimientos):
    """
    [Movimiento] -> (Autocancelante, ...)

    Un SKU que aparece con Ajuste de Entrada Y Ajuste de Salida en el mismo
    archivo, y cuyas unidades netean exactamente a 0 -- el patrón de una
    corrección de error tipeado, no de una recodificación (que va de Ajuste de
    Salida a Entrada de Mercadería, un tipo de documento distinto).

    Si el neto no da exactamente 0, no se marca: eso ya no es "un error
    corregido", es otra cosa, y descartarlo en silencio escondería una
    diferencia real.
    """
    por_sku = {}
    for m in movimientos:
        tipos = por_sku.setdefault(m.sku, {})
        tipos[m.tipo_documento] = tipos.get(m.tipo_documento, 0) + m.unidades

    resultado = []
    for sku, tipos in por_sku.items():
        if AJUSTE_ENTRADA in tipos and AJUSTE_SALIDA in tipos:
            entrada, salida = tipos[AJUSTE_ENTRADA], tipos[AJUSTE_SALIDA]
            if entrada + salida == 0:
                resultado.append(Autocancelante(sku=sku, entrada=entrada, salida=salida))
    return tuple(resultado)


def _skus_recodificados(pares):
    return {sku for p in pares for sku in p.origenes}


def desglose_salida(movimientos, pares_recodificacion, autocancelantes):
    """
    Reparte el total de Ajuste de Salida en tres categorías con causa
    conocida, más el resto genuino -- las cuatro suman exactamente el total,
    no hay dónde esconder un residuo sin categorizar (mismo criterio que
    `resumen_categorias` de #196).

    Nota sobre el "~353" del planteo original del issue: esa cifra salía de
    819 − 466 (sólo descontando la recodificación), sin descontar también el
    autocancelante C00477 (−50). Con los dos descontados, la salida
    verdaderamente sin explicar es 303, no 353 -- son 50 unidades que ya
    tienen causa conocida (un error tipeado, corregido el mismo mes) y no
    deberían viajar al cruce contra `stock_diario` como si fueran misteriosas.
    """
    origenes_recod = _skus_recodificados(pares_recodificacion)
    autocancel_skus = {a.sku for a in autocancelantes}

    solapados = origenes_recod & autocancel_skus
    if solapados:
        # Las dos categorías se arman de fuentes independientes
        # (emparejar_recodificaciones matchea Ajuste de Salida contra Entrada
        # de Mercadería; identificar_autocancelantes matchea Ajuste de Salida
        # contra Ajuste de Entrada) -- nada impide, en un archivo futuro, que
        # el mismo SKU caiga en ambas. Si pasara, el if/elif de abajo lo
        # clasificaría en silencio bajo la primera que encuentre, escondiendo
        # la causa real (un error tipeado) detrás de "recodificación".
        raise ValueError(
            f"SKU(s) clasificados a la vez como recodificación y autocancelante: "
            f"{sorted(solapados)} -- revisar a mano antes de confiar en el desglose.")

    total = 0
    recod = 0
    autocancel = 0
    for m in movimientos:
        if m.tipo_documento != AJUSTE_SALIDA:
            continue
        total += abs(m.unidades)
        if m.sku in origenes_recod:
            recod += abs(m.unidades)
        elif m.sku in autocancel_skus:
            autocancel += abs(m.unidades)

    return {
        "total": total,
        "recodificacion": recod,
        "autocancelante": autocancel,
        "genuina": total - recod - autocancel,
    }


def skus_salida_genuina(movimientos, pares_recodificacion, autocancelantes):
    """
    [Movimiento] de Ajuste de Salida que NO son recodificación ni
    autocancelante -- el subconjunto a cruzar contra `stock_diario` para ver
    si aparecen como caída de stock sin venta asociada.
    """
    origenes_recod = _skus_recodificados(pares_recodificacion)
    autocancel_skus = {a.sku for a in autocancelantes}
    return tuple(
        m for m in movimientos
        if m.tipo_documento == AJUSTE_SALIDA
        and m.sku not in origenes_recod
        and m.sku not in autocancel_skus
    )


def valor_a_fecha(serie, fecha):
    """
    {fecha_str: cantidad}, fecha_str -> cantidad | None

    Forward-fill: el último valor disponible en o antes de `fecha`. None si no
    hay ninguna fila en o antes de esa fecha -- ausencia de dato no es lo
    mismo que stock cero, y `stock_diario` no garantiza una fila por día.
    """
    candidatos = [f for f in serie if f <= fecha]
    if not candidatos:
        return None
    return serie[max(candidatos)]


@dataclass(frozen=True)
class ContinuidadPar:
    """Resultado de comparar el stock combinado (origen+destino) antes/después."""
    origenes: tuple
    destino: str
    origen_fin_junio: int | None
    origen_fin_julio: int | None
    destino_fin_junio: int | None
    destino_fin_julio: int | None
    combinado_fin_junio: int | None
    combinado_fin_julio: int | None

    @property
    def salto_combinado(self):
        """
        Diferencia del stock COMBINADO (todos los orígenes + destino) entre
        fin de junio y fin de julio. Cerca de 0 es la firma de una
        renumeración limpia (el total no se mueve, sólo cambia de SKU). Un
        salto grande indica que, además del cambio de código, hubo un
        movimiento de stock real sin explicar en el combinado.

        None si falta cualquiera de los dos lados -- no se puede calcular un
        salto sin los dos extremos.
        """
        if self.combinado_fin_junio is None or self.combinado_fin_julio is None:
            return None
        return self.combinado_fin_julio - self.combinado_fin_junio


def _suma_origenes(valores):
    """
    [int|None] -> int | None, para sumar VARIOS orígenes del mismo lado.

    None sólo si TODOS son None -- con al menos un SKU con dato real, el resto
    ausente se trata como 0 (un origen sin historial de stock_diario en la
    ventana es la situación normal de un SKU que ya casi no tenía stock, no
    necesariamente una falla de datos).
    """
    presentes = [v for v in valores if v is not None]
    return sum(presentes) if presentes else None


def _combinar(origen, destino, destino_es_tambien_origen):
    """
    int|None, int|None, bool -> int|None

    Si el destino YA es uno de los orígenes (`C00482 -> C00482`, o `I01874`
    que es a la vez origen y destino en `HX030+I01874 -> I01874`, dos pares
    reales del archivo), su valor ya está incluido en `origen` -- sumarlo de
    nuevo lo contaría dos veces. En ese caso el combinado ES `origen`, sin más.

    Si son SKUs distintos, es la suma de ambos -- y None si CUALQUIERA de los
    dos falta por completo: no se puede afirmar continuidad del total sin
    conocer los dos lados (distinto del criterio permisivo de
    `_suma_origenes`, donde un origen individual faltante entre varios se
    trata como 0 -- acá "todo un lado sin dato" es una laguna real, no una
    ausencia esperable).
    """
    if destino_es_tambien_origen:
        return origen
    if origen is None or destino is None:
        return None
    return origen + destino


def evaluar_continuidad(par, series_por_sku):
    """
    Recodificacion, {sku: {fecha: cantidad}} -> ContinuidadPar

    `series_por_sku` ya viene filtrada a depósito 5 y cargada por el llamador
    (I/O); esta función es pura sobre esas series.
    """
    origen_junio = _suma_origenes(
        valor_a_fecha(series_por_sku.get(sku, {}), FIN_JUNIO) for sku in par.origenes)
    origen_julio = _suma_origenes(
        valor_a_fecha(series_por_sku.get(sku, {}), FIN_JULIO) for sku in par.origenes)
    destino_junio = valor_a_fecha(series_por_sku.get(par.destino, {}), FIN_JUNIO)
    destino_julio = valor_a_fecha(series_por_sku.get(par.destino, {}), FIN_JULIO)

    destino_es_tambien_origen = par.destino in par.origenes
    combinado_junio = _combinar(origen_junio, destino_junio, destino_es_tambien_origen)
    combinado_julio = _combinar(origen_julio, destino_julio, destino_es_tambien_origen)

    return ContinuidadPar(
        origenes=par.origenes, destino=par.destino,
        origen_fin_junio=origen_junio, origen_fin_julio=origen_julio,
        destino_fin_junio=destino_junio, destino_fin_julio=destino_julio,
        combinado_fin_junio=combinado_junio, combinado_fin_julio=combinado_julio,
    )


# ── I/O contra MySQL ─────────────────────────────────────────────────────────

def leer_series_stock_deposito5(conn, skus):
    """
    {sku} -> {sku: {fecha_iso: cantidad}}, sólo depósito 5, ventana de
    contexto alrededor de julio 2026. `stock_diario.deposito_id` existe (a
    diferencia de `ventas_historicas`, ver #197) -- por eso este cruce sí se
    puede hacer directo contra producción, sin extracción aparte.
    """
    skus = sorted(set(skus))
    if not skus:
        return {}
    placeholders = ",".join(["%s"] * len(skus))
    series = {}
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT sku, fecha, cantidad FROM stock_diario "
            f"WHERE deposito_id = %s AND fecha BETWEEN %s AND %s AND sku IN ({placeholders})",
            (DEPOSITO_ARCHIVO, DESDE_CONTEXTO, HASTA_CONTEXTO, *skus),
        )
        for sku, fecha, cantidad in cur.fetchall():
            series.setdefault(sku, {})[fecha.isoformat()] = int(cantidad)
    return series


def leer_ventas_julio(conn, skus):
    """
    {sku} -> {sku: unidades_vendidas_julio_2026}, TODOS los depósitos (
    `ventas_historicas` no distingue depósito, mismo límite que #197). Sirve
    para chequear si una caída de stock coincide con una venta registrada.
    """
    skus = sorted(set(skus))
    if not skus:
        return {}
    placeholders = ",".join(["%s"] * len(skus))
    ventas = {}
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT sku, SUM(cantidad) FROM ventas_historicas "
            f"WHERE fecha BETWEEN %s AND %s AND sku IN ({placeholders}) "
            f"GROUP BY sku",
            (INICIO_JULIO, FIN_JULIO, *skus),
        )
        for sku, total in cur.fetchall():
            ventas[sku] = int(total)
    return ventas


# ── informe ──────────────────────────────────────────────────────────────────

def main():
    if not os.environ.get("MYSQL_PASSWORD"):
        print("Falta MYSQL_PASSWORD -- sin conexión no hay nada que cruzar.", file=sys.stderr)
        return 1

    movimientos, filtros = leer_movimientos()
    pares = emparejar_recodificaciones(movimientos)
    autocancelantes = identificar_autocancelantes(movimientos)
    desglose = desglose_salida(movimientos, pares, autocancelantes)

    print("=" * 78)
    print("DESGLOSE DE AJUSTE DE SALIDA (−819 unidades)")
    print("=" * 78)
    print(f"  Recodificación de SKU ({len(pares)} pares, #195): {desglose['recodificacion']}u")
    print(f"  Autocancelante dentro del mes:          {desglose['autocancelante']}u")
    for a in autocancelantes:
        print(f"    {a.sku}: +{a.entrada} (Ajuste de Entrada) / {a.salida} (Ajuste de Salida)")
    print(f"  Salida genuina (a cruzar contra stock):  {desglose['genuina']}u")
    print(f"  TOTAL: {desglose['total']}u "
          f"(cuadra: {desglose['recodificacion'] + desglose['autocancelante'] + desglose['genuina']}u)")

    conn = conectar()
    try:
        print()
        print("=" * 78)
        print("CONTINUIDAD DE STOCK POR PAR DE RECODIFICACIÓN (depósito 5)")
        print("=" * 78)
        todos_los_skus = {sku for p in pares for sku in (*p.origenes, p.destino)}
        series = leer_series_stock_deposito5(conn, todos_los_skus)
        for par in pares:
            c = evaluar_continuidad(par, series)
            salto = c.salto_combinado
            salto_txt = f"{salto:+d}" if salto is not None else "(sin datos suficientes)"
            print(f"  {' + '.join(par.origenes):<28} -> {par.destino:<10} "
                  f"combinado fin-jun={c.combinado_fin_junio} fin-jul={c.combinado_fin_julio} "
                  f"salto={salto_txt}")

        print()
        print("=" * 78)
        print(f"SALIDA GENUINA ({desglose['genuina']}u) vs. STOCK Y VENTAS DE JULIO")
        print("=" * 78)
        genuinas = skus_salida_genuina(movimientos, pares, autocancelantes)
        skus_genuinos = {m.sku for m in genuinas}
        series_genuinas = leer_series_stock_deposito5(conn, skus_genuinos)
        ventas_julio = leer_ventas_julio(conn, skus_genuinos)
        for m in genuinas:
            junio = valor_a_fecha(series_genuinas.get(m.sku, {}), FIN_JUNIO)
            julio = valor_a_fecha(series_genuinas.get(m.sku, {}), FIN_JULIO)
            venta = ventas_julio.get(m.sku, 0)
            print(f"  {m.sku:<10} ajuste={m.unidades:+d}  stock fin-jun={junio} fin-jul={julio}  "
                  f"venta_julio={venta}")

        print()
        print("=" * 78)
        print("LÍMITE DE ALCANCE PARA #193")
        print("=" * 78)
        print(f"  Filtros del reporte: {', '.join(filtros.lineas)}")
        print(f"  Whitelist de documentos: {', '.join(filtros.doc) or '(ninguna)'}")
        print("  SMR devolvió 0 filas -- evidencia A FAVOR de la hipótesis de #193,")
        print("  SÓLO SI 'SMR' es efectivamente el código de remito (no confirmado).")
        print("  Una transferencia con cualquier otro código quedó excluida POR EL FILTRO,")
        print("  no por ausencia real. De este archivo NO se puede concluir 'no hay")
        print("  transferencias' -- sólo 'no hay ninguno de los cuatro tipos pedidos'.")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
