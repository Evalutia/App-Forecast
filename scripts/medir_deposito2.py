#!/usr/bin/env python3
"""
medir_deposito2.py — Issue #197.

Mide cuánto de la brecha del −4,5% (#196) explica el depósito 2 (el "salón de
ventas" que #193 identificó como remito invisible para nuestra extracción),
extrayéndolo directamente del web service hacia las tablas `_comparacion`
aisladas de #186 -- nunca toca `ventas_historicas`/`stock_diario` de
producción.

Es el centro del diagnóstico: si el volumen de depósito 2 explica la brecha,
responde sola la pregunta que se le mandó a Rodrigo el 2026-09-10 por #193,
sin depender de su respuesta.

Uso -- dos pasos, en la VM (no desde el host: la extracción necesita los certs
mTLS que sólo viven en el contenedor `etl`):

  1. Extracción (una sola vez, dura horas -- ventana de 13 meses, un solo
     depósito, corre en background con nohup para sobrevivir a la sesión SSH):

       docker compose exec -e S_DEPOSITOS=2 \
         -e BACKFILL_FROM=<primer día de la ventana de #196> \
         -e BACKFILL_TO=<último día> \
         etl bash -c 'nohup /bin/bash /app/services/etl/run_backfill_comparacion.sh \
           > /app/data/backfill_197_deposito2.log 2>&1 & disown'

     `run_backfill_comparacion.sh` ya sabe escribir en `ventas_historicas_comparacion`
     en vez de `ventas_historicas` (#186) y usa `get_grupos.py` (todos los
     grupos, 201 incluido) salvo que se pase `GROUPS` explícito.

  2. Este script, desde el host con túnel SSH (necesita `openpyxl` para leer
     el archivo del cliente, que el contenedor `etl` no tiene -- mismo patrón
     que #195/#196). Antes de calcular nada, verifica que
     `ventas_historicas_comparacion` esté libre de filas de una corrida
     anterior (`derivar_inicio_extraccion` + `verificar_extraccion_fresca`,
     automático -- no hace falta pasarle cuándo arrancó la extracción, se
     deriva de `jobs_historial`):

       ssh -f -N -L 13307:localhost:3307 <vm>
       MYSQL_HOST=127.0.0.1 MYSQL_PORT=13307 MYSQL_USER=root MYSQL_PASSWORD=... \
         python3 scripts/medir_deposito2.py

Las tablas `_comparacion` son temporales por diseño (#186): quedan documentadas
así acá también, y el `DROP` se ejecuta recién cuando cierre #201 (el informe
final), no en este ticket -- ver la cabecera de `infra/sql/26-tablas-
comparacion.sql` para el DROP exacto.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cargador_archivos_cliente import (  # noqa: E402
    MESES_ES,
    comparar_catalogo,
    leer_skus_nuestros,
    leer_ventas,
)
from comparar_ventas_mensual import (  # noqa: E402
    agregado_mensual_por_tabla,
    conectar,
    construir_dataset_discrepancias,
    leer_agregado_mensual_nuestro,
    restringir_agregados,
    totales_mensuales_nuestros,
    ventana_desde_ventas_cliente,
)

# Deriva la etiqueta ("Ago") de cada mes desde el mismo diccionario que ya usa
# el parser del archivo del cliente (#195), en vez de mantener una segunda
# lista de abreviaturas en paralelo que puede desincronizarse de esa.
MESES_ES_NOMBRE = {i: m for m, i in MESES_ES.items()}

TABLA_DEPOSITO2 = "ventas_historicas_comparacion"

# `ventas_historicas_comparacion` NO tiene columna `deposito_id` (mismo motivo
# por el que existe este ticket: tampoco la tiene `ventas_historicas`). Así que
# no hay forma de filtrar por depósito desde los datos si la tabla alguna vez
# tuviera filas de más de un depósito mezcladas -- el único filtro real es
# operativo: que la extracción que la pobló haya corrido con `S_DEPOSITOS=2`
# sobre una tabla vacía, una sola vez. `verificar_extraccion_fresca` no puede
# demostrar eso desde los datos, pero sí puede detectar el síntoma más
# probable de que no se cumplió: filas con `ts_carga` de otra corrida.


def deficit_mensual(filas):
    """
    [FilaDiscrepancia] -> {(y,m): unidades_de_deficit}, sumando sólo las filas
    con `categoria == 'deficit'`.

    Es la brecha que #196 midió, la misma que este ticket contrasta contra el
    volumen de depósito 2. Se reporta como magnitud positiva ("cuánto nos
    falta"), no como el signo crudo de `diff_abs` (negativo por convención:
    nuestro − cliente).
    """
    deficit = {}
    for f in filas:
        if f.categoria != "deficit":
            continue
        clave = (f.year, f.month)
        deficit[clave] = deficit.get(clave, 0) + abs(f.diff_abs)
    return deficit


def comparar_contra_deficit(totales_deposito2, deficit):
    """
    {(y,m): u_deposito2}, {(y,m): u_deficit} -> {(y,m): {'deposito2', 'deficit',
    'pct_explicado'}}

    La unión de meses de ambos lados -- un mes con déficit pero sin venta de
    depósito 2 igual tiene que aparecer (0% explicado, una respuesta real), y
    uno con venta de depósito 2 pero sin déficit medido también (pct_explicado
    en None: sin denominador, no hay porcentaje que calcular, y NO es un 0%
    -- confundirlo con un 0% sugeriría falsamente que depósito 2 no aporta
    nada ese mes).

    No clampea a 100: si depósito 2 vendió más que todo el déficit del mes, el
    porcentaje pasa de 100 y esa es información real (compensa otras causas),
    no un error a esconder.
    """
    meses = set(totales_deposito2) | set(deficit)
    resultado = {}
    for mes in meses:
        u_dep2 = totales_deposito2.get(mes, 0)
        u_deficit = deficit.get(mes, 0)
        pct = (u_dep2 / u_deficit * 100) if u_deficit else None
        resultado[mes] = {"deposito2": u_dep2, "deficit": u_deficit, "pct_explicado": pct}
    return resultado


def leer_agregado_mensual_deposito2(conn, ventana):
    """
    {(sku,y,m): unidades}, TODO lo extraído en `ventas_historicas_comparacion`
    -- que hoy sólo tiene depósito 2, porque así se corrió la extracción
    (`S_DEPOSITOS=2`). Comparte la lógica de query/normalización con
    `leer_agregado_mensual_nuestro` de #196 vía `agregado_mensual_por_tabla`
    (el nombre de tabla sigue hardcodeado acá, como literal -- nunca llega
    como variable desde afuera, ver la nota de esa función sobre por qué).
    """
    return agregado_mensual_por_tabla(conn, ventana, TABLA_DEPOSITO2)


def derivar_inicio_extraccion(conn):
    """
    conn -> datetime | None: el `fecha_inicio` más temprano entre los últimos
    N jobs `backfill_comparacion` exitosos, donde N = cantidad total de grupos
    (`SELECT COUNT(*) FROM grupos`) -- es decir, el arranque de la corrida más
    reciente de `run_backfill_comparacion.sh` (#186), que siempre procesa
    todos los grupos en una sola invocación (`get_grupos.py`, sin exclusiones).

    None si todavía no hay esa cantidad de jobs exitosos (extracción incompleta
    o nunca corrida) -- `main()` lo trata como "no hay nada que verificar
    todavía", no como "está todo bien".

    Se deriva de `jobs_historial` en vez de pedirle a quien corre este script
    que anote a mano cuándo arrancó la extracción: un dato tipeado a mano es
    un dato que alguien se va a olvidar de pasar (pasó en la primera versión
    de este chequeo, que dependía de una env var que nadie iba a setear
    siguiendo las instrucciones de "Uso" de acá arriba).
    """
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM grupos")
        total_grupos = cur.fetchone()[0]
        cur.execute(
            "SELECT MIN(fecha_inicio) FROM ("
            "  SELECT fecha_inicio FROM jobs_historial"
            "  WHERE tipo_job='backfill' AND detalle->>'$.subtipo'='backfill_comparacion'"
            "    AND estado='exitoso'"
            "  ORDER BY id DESC LIMIT %s"
            ") ultimos",
            (total_grupos,),
        )
        return cur.fetchone()[0]


def verificar_extraccion_fresca(conn, cutoff):
    """
    (conn, datetime) -> int: cuántas filas de `ventas_historicas_comparacion`
    tienen `ts_carga` ANTERIOR a `cutoff` (el arranque de la extracción de
    depósito 2 más reciente, ver `derivar_inicio_extraccion`). Debería dar 0
    siempre.

    Existe porque `ventas_historicas_comparacion` no tiene `deposito_id`: si
    alguna vez quedaran filas de una corrida anterior con otro alcance de
    depósito (por ejemplo, si no se recreó la tabla vacía antes de correr, o
    si se re-corrió con un `S_DEPOSITOS` distinto sobre la misma tabla), el
    merge (`INSERT ... ON DUPLICATE KEY UPDATE`) sólo pisa las filas que la
    extracción actual efectivamente devuelve -- una fila vieja de un SKU/fecha
    que no vendió en depósito 2 nunca se toca, ni se borra, y quedaría sumada
    en `leer_agregado_mensual_deposito2` como si fuera depósito 2. `ts_carga`
    es la única señal disponible para detectar eso desde los datos.
    """
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {TABLA_DEPOSITO2} WHERE ts_carga < %s", (cutoff,))
        return cur.fetchone()[0]


def contar_produccion(conn):
    """(COUNT(*) ventas_historicas, COUNT(*) stock_diario) -- para el chequeo
    de "producción intacta" antes/después que pide el criterio de aceptación."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ventas_historicas")
        ventas = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM stock_diario")
        stock = cur.fetchone()[0]
    return ventas, stock


# ── informe ──────────────────────────────────────────────────────────────────

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

        # Recalcula la brecha de #196 en vivo (no un número hardcodeado): si
        # producción cambió desde entonces, este informe se sigue leyendo
        # contra la brecha real de HOY, no una foto vieja.
        agregados_todos = leer_agregado_mensual_nuestro(conn, ventana)
        agregados_comunes = restringir_agregados(agregados_todos, comunes)
        filas = construir_dataset_discrepancias(ventas_cliente, agregados_comunes, comunes, ventana)
        deficit = deficit_mensual(filas)
        deficit_total = sum(deficit.values())

        cutoff = derivar_inicio_extraccion(conn)
        if cutoff is None:
            raise RuntimeError(
                f"No se encontraron jobs 'backfill_comparacion' exitosos para todos los "
                f"grupos -- la extracción de depósito 2 no corrió completa todavía. "
                f"Ver services/etl/run_backfill_comparacion.sh.")
        viejas = verificar_extraccion_fresca(conn, cutoff)
        if viejas:
            raise RuntimeError(
                f"{viejas} filas de {TABLA_DEPOSITO2} tienen ts_carga anterior a "
                f"{cutoff} (arranque de la extracción más reciente) -- la tabla no está "
                f"limpia de una corrida anterior, el resultado no es confiable. "
                f"Recrear vacía y re-extraer.")

        agregados_dep2 = leer_agregado_mensual_deposito2(conn, ventana)
        agregados_dep2_comunes = restringir_agregados(agregados_dep2, comunes)
        totales_dep2 = totales_mensuales_nuestros(agregados_dep2_comunes)
        dep2_total = sum(totales_dep2.values())

        comparacion = comparar_contra_deficit(totales_dep2, deficit)

        print("=" * 78)
        print(f"DEPÓSITO 2 vs. DÉFICIT DE #196 ({len(comunes)} SKUs comunes)")
        print("=" * 78)
        for year, month in ventana:
            d = comparacion.get((year, month), {"deposito2": 0, "deficit": 0, "pct_explicado": None})
            pct_txt = f"{d['pct_explicado']:5.1f}%" if d["pct_explicado"] is not None else "(sin déficit)"
            print(f"  {MESES_ES_NOMBRE[month]}/{year % 100:02d}: "
                  f"depósito 2 {d['deposito2']:>6}u   déficit {d['deficit']:>6}u   {pct_txt}")

        pct_total = (dep2_total / deficit_total * 100) if deficit_total else None
        print()
        print(f"  TOTAL: depósito 2 {dep2_total}u sobre un déficit de {deficit_total}u"
              + (f"  ->  {pct_total:.1f}% explicado" if pct_total is not None else ""))

        print()
        print("=" * 78)
        print("VERIFICACIÓN: PRODUCCIÓN INTACTA")
        print("=" * 78)
        ventas_n, stock_n = contar_produccion(conn)
        print(f"  ventas_historicas: {ventas_n} filas")
        print(f"  stock_diario:      {stock_n} filas")
        print("  (comparar a mano contra el conteo baseline tomado antes de la extracción)")

        with conn.cursor() as cur:
            cur.execute(f"SELECT MIN(ts_carga), MAX(ts_carga), COUNT(*) FROM {TABLA_DEPOSITO2}")
            ts_min, ts_max, n = cur.fetchone()
        print(f"  {TABLA_DEPOSITO2}: {n} filas, ts_carga entre {ts_min} y {ts_max}")
        print("  (tiene que caer entera dentro de la ventana de esta extracción -- si ts_carga")
        print("   arranca en una fecha muy anterior, hay filas de una corrida vieja mezcladas)")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
