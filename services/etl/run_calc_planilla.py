#!/usr/bin/env python3
"""
run_calc_planilla.py — Calcula y persiste planilla_ventas_calculada.

Lee ventas_historicas + stock_diario, calcula rotaciones y estado_mes
por SKU×mes para una ventana de 13 meses (mes actual + 12 anteriores completos).
Regenera la tabla completa en una única transacción atómica (DELETE + INSERT).

Umbrales estado_mes (replica el criterio del cliente — Issue #36/#37, verificado contra
su Excel de referencia vía openpyxl: colorea como quiebre el 100% de los meses con al
menos 1 día sin stock, sin piso mínimo — no usan un umbral del 90%):
  normal          : dias_con_stock == dias_naturales_mes (todos los días con stock)
  quiebre_parcial : dias_con_stock >  0  y  < dias_naturales_mes (al menos 1 día sin stock)
  sin_stock       : dias_con_stock == 0

Uso:
  MYSQL_HOST=mysql MYSQL_DB=evalutia MYSQL_USER=evalutia \\
  MYSQL_PASSWORD=evalutia python run_calc_planilla.py
"""

import calendar
import datetime as dt
import json
import os
import sys
import time

import pymysql

from parsers import redondear

# ── Parámetros ─────────────────────────────────────────────────────────────────

VENTANA_MESES        = 13     # mes actual + 12 anteriores completos

# Fracción de días naturales necesaria para "normal". 100% = replica el criterio del
# cliente: cualquier día de quiebre cuenta, sin piso. Issue #36/#37, sesión 2026-06-17.
ESTADO_UMBRAL_NORMAL = 1.00

# INVARIANTE de ventas_historicas (issue #64): la tabla guarda una fila por
# SKU por dia calendario, tenga o no venta real -- cantidad=0 es "sin venta
# ese dia", no ausencia de fila. SUM(cantidad) es seguro (los ceros no
# afectan la suma), pero cualquier COUNT/COUNT(DISTINCT fecha) sobre esta
# tabla necesita filtrar `cantidad != 0` explicitamente o termina contando
# dias del mes en vez de eventos reales. FREQ_ALTA_MIN/FREQ_BAJA_MAX de abajo
# escapan a esto hoy porque se calculan via SUM > 0, no via conteo de filas.

# Umbrales de frecuencia de quiebre (Issue #27)
# Medida: cantidad de meses cerrados (de 12) con ventas_cantidad > 0
FREQ_ALTA_MIN  = 9   # >= 9 meses con ventas → alta frecuencia
FREQ_BAJA_MAX  = 3   # <= 3 meses con ventas → baja frecuencia
                     # 4–8 meses → media frecuencia

# Umbrales de frecuencia de venta por tickets (Issue #61/#63, mail del cliente
# 2026-06-XX). Distinto de FREQ_ALTA_MIN/FREQ_BAJA_MAX de arriba -- ese mide
# meses con ventas en el año para elegir formula de rotacion en quiebre; esto
# mide tickets (dias con venta) EN EL MES para elegir el blending
# Historico/Promedio/Real de ese mes puntual.
#
# Issue #67: son los defaults -- main() los sobreescribe con lo que haya en
# configuracion_sistema (editable por el admin) antes de calcular. Quedan
# como constantes de modulo (no parametros de funcion) para no tocar la
# firma de valor_ajustado_y_criterio() ni los 14 tests que ya la llaman sin
# pasarlos explicitamente.
TICKETS_BAJO_MAX = 2   # <= 2 tickets → usa Historico
TICKETS_ALTO_MIN = 5   # >= 5 tickets → usa VentaRealMes/Extrapolacion
                       # 3-4 tickets → promedio de ambos

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

# ── Helpers de fecha ───────────────────────────────────────────────────────────

def ventana_meses(n: int, hoy: dt.date | None = None) -> list[tuple[int, int]]:
    """Retorna lista de (year, month) de los últimos n meses inclusive el actual.
    Orden: más reciente primero.

    `hoy` es inyectable para poder testear cualquier día del mes sin esperar
    a que llegue; en producción se usa la fecha real (default)."""
    hoy = hoy or dt.date.today()
    y, m = hoy.year, hoy.month
    resultado = []
    for _ in range(n):
        resultado.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return resultado


def dias_naturales_mes(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]

# ── Lógica de negocio ──────────────────────────────────────────────────────────

def clasificar_estado(dias_stock: int, dias_naturales: int) -> str:
    """
    Clasifica el estado del mes según disponibilidad de stock.
    Umbral configurable: ESTADO_UMBRAL_NORMAL (default 100% — cualquier día de
    quiebre cuenta, replica el criterio observado en la planilla del cliente).
    """
    if dias_stock == 0:
        return "sin_stock"
    if dias_stock / dias_naturales >= ESTADO_UMBRAL_NORMAL:
        return "normal"
    return "quiebre_parcial"


def clasificar_estado_mes(dias_stock: int, dias_naturales: int, es_mes_referencia: bool) -> str:
    """
    Clasifica estado_mes, exceptuando el mes de referencia (en curso) del umbral
    de ESTADO_UMBRAL_NORMAL: dias_naturales_mes ahí siempre es el total del mes
    calendario, no los días que de verdad transcurrieron, así que el umbral da
    falso positivo de quiebre casi todo el mes sin importar si el stock estuvo
    perfecto (más aún con el umbral en 100%, donde un solo día de diferencia ya
    alcanza para disparar el falso positivo).

    dias_stock == 0 sí es una señal confiable a mitad de mes (cuenta días reales
    ya observados en stock_diario), por eso sin_stock se preserva.
    """
    if es_mes_referencia:
        return "normal" if dias_stock > 0 else "sin_stock"
    return clasificar_estado(dias_stock, dias_naturales)

# ── Frecuencia de venta por tickets (Issue #61/#63) ─────────────────────────────
# A nivel de modulo (no anidada en calcular_filas) para que sea testeable en
# aislamiento -- criterio de aceptacion de #63 pide tests unitarios del blending.

def meses_disponibles_historico(
    fec_alta: dt.date | None, meses: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """
    Filtra `meses` a los que el SKU ya existía según `fec_alta` (fin del mes
    >= fec_alta). Sin fec_alta (dato faltante, ~1% de los casos) se asume
    que el SKU ya existía en todos los meses -- mismo comportamiento que un
    SKU antiguo, el caso ampliamente mayoritario.
    """
    if fec_alta is None:
        return list(meses)
    return [
        (yr, mo) for (yr, mo) in meses
        if fec_alta <= dt.date(yr, mo, dias_naturales_mes(yr, mo))
    ]


def calcular_historico(
    sku: str,
    fec_alta: dt.date | None,
    meses_cerrados: list[tuple[int, int]],
    ventas: dict[tuple, int],
    estados: dict[tuple, str],
    extrapolaciones: dict[tuple, float | None],
) -> float | None:
    """
    Promedio de ventas_cantidad en los meses cerrados disponibles para este
    SKU. Un mes sin fila en ventas_historicas SI cuenta como "disponible con
    0 ventas" (dato real) cuando el SKU ya existia ese mes -- solo se
    excluyen los meses anteriores a fec_alta (no existia todavia).

    Issue #163 (mismo criterio que #116 ya aplico a rotacion_ajustada en
    run_calc_sugerencias.py):
    - Meses 'sin_stock' se excluyen del promedio (ni suma ni denominador) --
      no son "vendio cero", son "no sabemos" o "no tenia para vender".
    - Meses 'quiebre_parcial' aportan su venta extrapolada (proyectada al
      mes completo), no la venta cruda deprimida por el propio quiebre --
      la venta cruda subestima la demanda real de ese mes por construccion.

    `estados`/`extrapolaciones` faltan una clave (sku, yr, mo) cuando ese
    mes no tiene fila ni en ventas_historicas ni en stock_diario -- se trata
    como 'normal'/0, mismo comportamiento historico que este docstring ya
    documentaba para "sin fila en ventas".

    Retorna None si no hay ningun mes disponible (SKU recien agregado) o si
    todos los meses disponibles fueron sin_stock (no queda ningun dato
    utilizable para promediar).
    """
    disponibles = meses_disponibles_historico(fec_alta, meses_cerrados)
    if not disponibles:
        return None

    valores = []
    for (yr, mo) in disponibles:
        key = (sku, yr, mo)
        estado = estados.get(key, "normal")
        if estado == "sin_stock":
            continue
        if estado == "quiebre_parcial":
            extrap = extrapolaciones.get(key)
            valores.append(extrap if extrap is not None else float(ventas.get(key, 0)))
        else:
            valores.append(float(ventas.get(key, 0)))

    if not valores:
        return None
    return round(sum(valores) / len(valores), 2)


def extrapolacion_mes(
    ventas: int, dias_con_stock: int, dias_naturales: int, p: float = 1.0
) -> float | None:
    """
    Estima cuanto se habria vendido en el mes completo, para los meses con
    quiebre de stock. None si no hay base sobre la cual proyectar (sin_stock:
    dias_con_stock=0) -- valor_ajustado_y_criterio() lo hace caer a Historico.

    Issue #129 (planteado por el cliente): antes esto era
    `(ventas / dias_con_stock) * dias_naturales`, que proyecta el ritmo de los
    dias observados al mes entero **sin mirar en que momento se corto el
    stock**. Un articulo que se agota el dia 6 de 30 se multiplicaba por 5; uno
    que se agota el dia 1, por 30. Y el sesgo va en la peor direccion: los dias
    posteriores a una reposicion arrastran la demanda que quedo sin atender
    mientras no hubo stock, asi que ese ritmo es mas alto que el sostenido y
    extrapolarlo al mes entero infla por construccion.

    Issue #144 (contrapropuesta de Rodrigo a #129): generaliza el criterio con
    un exponente `p`. Con `w = (dias_con_stock / dias_naturales) ** p`:

        estimacion = ventas * (1 + w * (dias_naturales / dias_con_stock - 1))

    `p=1` (default -- el valor en produccion) da algebraicamente lo mismo que
    la formula de #129, `ventas * (2 - dias_con_stock / dias_naturales)`: con
    p=1, w = dias_con_stock/dias_naturales y el termino w * (D/d - 1) se
    simplifica a `1 - dias_con_stock/dias_naturales`. `p<1` (Rodrigo pidio
    p=0.5) proyecta mas -- y pierde el tope de x2 que tiene p=1, crece sin
    limite a medida que quedan menos dias observados. `p>1` proyecta menos.
    Cambiar el exponente es cambiar un valor, no reescribir la formula.

    Cual `p` predice mejor la demanda real de un mes con quiebre se midio
    contra la historia real en #144 (ver .claude/CONTEXTO.md) -- produccion
    sigue en p=1 hasta que el cliente decida lo contrario con esa evidencia
    en mano.

    Venta <= 0 no se extrapola (desde #80 un mes puede cerrar en negativo por
    notas de credito, y amplificar una devolucion no significa nada) --
    tampoco depende de `p`.
    """
    if dias_con_stock <= 0 or dias_naturales <= 0:
        return None
    if ventas <= 0:
        return float(ventas)
    d_sobre_D = dias_con_stock / dias_naturales
    w = d_sobre_D ** p
    return round(ventas * (1 + w * (1 / d_sobre_D - 1)), 2)


def _venta_real_o_extrapolada(
    ventas_real: int, extrapolacion: float | None, es_quiebre: bool
) -> float | None:
    """
    Nucleo compartido entre venta_o_extrapolacion() y
    valor_ajustado_y_criterio() -- "cuanto vendio el mes, en su version sin
    corregir por historico": la venta real si no hubo quiebre, la
    extrapolacion si lo hubo. Extraido en #137 (code review) para que un
    cambio futuro a esta regla no pueda divergir entre las dos funciones
    que la usan -- exactamente la clase de bug que #137 elimino para el
    split ETL/frontend, ahora tambien cerrada adentro del propio ETL.
    """
    return extrapolacion if es_quiebre else float(ventas_real)


def venta_o_extrapolacion(
    estado_mes: str, ventas_cantidad: int, extrapolacion: float | None
) -> float | None:
    """
    Issue #137: "V/E" de la hoja de detalle -- venta real del mes, o su
    extrapolacion si hubo quiebre. Hasta ahora se recalculaba en el browser
    (TypeScript, reimplementando esta misma formula en exportPlanilla.ts) en
    vez de leerse persistida como VAj -- las dos solo coincidian si el ETL
    habia vuelto a correr despues del ultimo cambio de formula (#129 dejo
    una ventana real de una hora en produccion con VAj y V/E
    contradiciendose en la misma fila). Se persiste aca, calculada por la
    misma funcion en la misma corrida que valor_ajustado_y_criterio(), para
    que la desincronizacion quede estructuralmente imposible.

    NO es lo mismo que `valor_no_historico` en valor_ajustado_y_criterio:
    ese tiene un fallback a ventas_cantidad cuando es_quiebre y
    extrapolacion es None (sin_stock sin historico) -- V/E en cambio queda
    en None para sin_stock siempre, sin excepcion (mismo criterio que la
    hoja "Criterios" promete: "Vacia si el mes no tuvo stock").
    """
    if estado_mes == "sin_stock":
        return None
    es_quiebre = estado_mes != "normal"
    return _venta_real_o_extrapolada(ventas_cantidad, extrapolacion, es_quiebre)


def valor_ajustado_y_criterio(
    tickets: int,
    ventas_real: int,
    extrapolacion: float | None,
    historico: float | None,
    es_quiebre: bool,
) -> tuple[float | None, str | None]:
    """
    Blending Historico/Promedio/Real-Extrapolado (mail del cliente,
    2026-06-27, ver .claude/CONTEXTO.md sesion 2026-07-14):

      Sin quiebre: tickets<=2 -> Historico | 3-4 -> (Historico+VentaRealMes)/2 | >=5 -> VentaRealMes
      Con quiebre: tickets<=2 -> Historico | 3-4 -> (Historico+Extrapolacion)/2 | >=5 -> Extrapolacion

    `es_quiebre` cubre estado_mes in (quiebre_parcial, sin_stock) -- el mail
    solo distingue "stock todo el mes" de "quiebre", sin_stock es un caso
    extremo de quiebre, no un tercer estado en su logica.

    Fallbacks (no cubiertos por el mail, decididos en la sesion de grill-me):
    - sin_stock (Extrapolacion indefinida, dias_con_stock=0): cae a Historico
      sin importar la cantidad de tickets. Si tampoco hay Historico (SKU sin
      meses disponibles), usa VentaRealMes como ultimo recurso.
    - Historico faltante (SKU sin ningun mes disponible) en tickets<=4: usa
      el componente disponible (VentaRealMes/Extrapolacion) sin promediar,
      en vez de dejar el valor en None.

    Issue #182: redondea con ROUND_HALF_UP (parsers.redondear), no con el
    round() nativo de Python (banker's rounding) -- el caso `promedio`
    ((historico + valor_no_historico) / 2) produce medios centavos seguido,
    con sesgo sistemico hacia el par en esta columna que el cliente ve
    directo (valor_ajustado).
    """
    if es_quiebre and extrapolacion is None:
        if historico is not None:
            return (redondear(historico, 2), "historico")
        return (redondear(float(ventas_real), 2), "real_extrapolado")

    valor_no_historico = _venta_real_o_extrapolada(ventas_real, extrapolacion, es_quiebre)

    if tickets >= TICKETS_ALTO_MIN:
        return (redondear(valor_no_historico, 2), "real_extrapolado")

    if historico is None:
        return (redondear(valor_no_historico, 2), "real_extrapolado")

    if tickets <= TICKETS_BAJO_MAX:
        return (redondear(historico, 2), "historico")

    return (redondear((historico + valor_no_historico) / 2, 2), "promedio")

# ── jobs_historial ─────────────────────────────────────────────────────────────

def job_start(conn: pymysql.Connection) -> int:
    """Registra inicio del job. Hace commit propio (separado de la tx de escritura)."""
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

# ── Cálculo ────────────────────────────────────────────────────────────────────

def cargar_factores(conn: pymysql.Connection) -> dict[str, dict[int, float | None]]:
    """Preload de factores estacionales por SKU×mes. factors[sku][1..12]."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sku, factor_mes_01, factor_mes_02, factor_mes_03, factor_mes_04, "
            "       factor_mes_05, factor_mes_06, factor_mes_07, factor_mes_08, "
            "       factor_mes_09, factor_mes_10, factor_mes_11, factor_mes_12 "
            "FROM articulos"
        )
        rows = cur.fetchall()
    return {
        row[0]: {i + 1: (float(row[i + 1]) if row[i + 1] is not None else None) for i in range(12)}
        for row in rows
    }


def cargar_configuracion(conn: pymysql.Connection) -> dict[str, int]:
    """
    Issue #67: umbrales de tickets editables por el admin via
    configuracion_sistema. Si la tabla esta vacia o falta una clave (no
    debería pasar -- la migracion la siembra -- pero no confiar en eso en
    tiempo de ejecucion), cae al default hardcodeado en vez de romper el
    calculo de toda la noche por un dato de configuracion faltante.
    """
    defaults = {"tickets_bajo_max": TICKETS_BAJO_MAX, "tickets_alto_min": TICKETS_ALTO_MIN}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT clave, valor FROM configuracion_sistema WHERE clave IN (%s, %s)",
            (*defaults.keys(),),
        )
        rows = cur.fetchall()
    valores = dict(defaults)
    for clave, valor in rows:
        try:
            valores[clave] = int(valor)
        except (TypeError, ValueError):
            print(f"[PLANILLA] Config '{clave}' invalida ({valor!r}), uso default {defaults[clave]}")

    if valores["tickets_bajo_max"] >= valores["tickets_alto_min"]:
        print(
            f"[PLANILLA] Config invalida: tickets_bajo_max ({valores['tickets_bajo_max']}) "
            f">= tickets_alto_min ({valores['tickets_alto_min']}), uso defaults"
        )
        valores = dict(defaults)

    return valores


def cargar_fec_alta(conn: pymysql.Connection) -> dict[str, dt.date | None]:
    """Preload de fec_alta por SKU -- usado para acotar los 'meses disponibles'
    del calculo de Historico (Issue #63) a los meses donde el SKU ya existia."""
    with conn.cursor() as cur:
        cur.execute("SELECT sku, fec_alta FROM articulos")
        rows = cur.fetchall()
    return {row[0]: (row[1].date() if row[1] else None) for row in rows}


def cargar_tickets(
    conn: pymysql.Connection, fecha_desde: dt.date, fecha_hasta: dt.date, meses_set: set[tuple[int, int]]
) -> dict[tuple, int]:
    """
    Tickets por SKU×mes (Issue #61: dia con al menos una fila de VENTA real,
    cantidad != 0). `ventas_historicas` guarda una fila por SKU por dia
    calendario aunque no haya venta -- el filtro `cantidad != 0` evita
    contar dias del mes en vez de tickets reales (bug de #64, ver
    CONTEXTO.md para el detalle de como se detecto).
    """
    sql_tickets = """
        SELECT
            vh.sku,
            YEAR(vh.fecha)  AS yr,
            MONTH(vh.fecha) AS mo,
            COUNT(DISTINCT vh.fecha) AS tickets
        FROM ventas_historicas vh
        INNER JOIN articulos a ON a.sku = vh.sku
        WHERE vh.fecha BETWEEN %s AND %s
          AND vh.cantidad != 0
        GROUP BY vh.sku, YEAR(vh.fecha), MONTH(vh.fecha)
    """
    with conn.cursor() as cur:
        cur.execute(sql_tickets, (fecha_desde, fecha_hasta))
        tickets_raw = cur.fetchall()

    tickets: dict[tuple, int] = {}
    for sku, yr, mo, n in tickets_raw:
        if (yr, mo) in meses_set:
            tickets[(sku, yr, mo)] = int(n)
    return tickets


# Días con stock por SKU×mes. FORCE INDEX (issue #153, diagnóstico #149): sin el hint,
# MySQL elige idx_stock_sku_fecha (sku primero) y no puede hacer seek por rango de
# fecha sola -- termina escaneando la tabla entera (120,5M de 121M filas medido en
# producción) antes de filtrar. idx_stock_fecha (fecha primero) evita eso: medido
# 61,2min -> 6,4min (9,6x) contra producción con datos reales, ver CONTEXTO.md.
_SQL_STOCK = """
    SELECT
        agg.sku,
        YEAR(agg.fecha)  AS yr,
        MONTH(agg.fecha) AS mo,
        COUNT(DISTINCT agg.fecha) AS dias_con_stock
    FROM (
        SELECT
            sd.sku,
            sd.fecha,
            SUM(sd.cantidad) AS stock_total
        FROM stock_diario sd FORCE INDEX (idx_stock_fecha)
        WHERE sd.fecha BETWEEN %s AND %s
        GROUP BY sd.sku, sd.fecha
    ) agg
    INNER JOIN articulos a ON a.sku = agg.sku
    WHERE agg.stock_total > COALESCE(a.stock_minimo, 0)
    GROUP BY agg.sku, YEAR(agg.fecha), MONTH(agg.fecha)
"""

# Issue #145: detectar si entró stock (importación) a mitad de un mes con
# quiebre -- consulta separada de _SQL_STOCK a propósito, en vez de
# reutilizar su subquery interna: esta necesita el detalle día a día, no el
# agregado mensual, y tocar _SQL_STOCK (ya verificado con datos reales en
# #153) para exponer ese detalle arriesgaba la lógica de dias_con_stock que
# ya está en producción. El costo es otro scan de stock_diario por corrida
# (mismo FORCE INDEX de #153, ~6min más) -- aceptado a cambio de no tocar
# código ya probado.
_SQL_STOCK_DIARIO = """
    SELECT sku, fecha, SUM(cantidad) AS stock_total
    FROM stock_diario FORCE INDEX (idx_stock_fecha)
    WHERE fecha BETWEEN %s AND %s
    GROUP BY sku, fecha
"""


def detectar_ingreso_durante_mes(dias_ordenados: list[float], stock_minimo: float = 0.0) -> bool:
    """
    Issue #145/#164: True si el stock total del SKU pasa de "sin stock" a
    "con stock" en algún punto de `dias_ordenados` -- ya ordenada
    cronológicamente, un día por elemento, dentro de un mismo mes.

    Distingue "el artículo se agotó y no repuso" (quiebre común) de "se
    quedó sin stock y entró una importación a mitad de mes" (pedido de
    Rodrigo): en el segundo caso la venta baja no significa que el artículo
    no venda, significa que no había qué vender hasta que llegó el barco.

    El umbral de "con stock" es `stock > stock_minimo` -- el mismo que ya
    usa dias_con_stock/_SQL_STOCK, no `stock > 0` literal. Antes de #164
    usaba `<= 0`: el 88% del catálogo tiene stock_minimo > 0 (NOT NULL
    DEFAULT 0), así que para esos SKUs el flag era estructuralmente
    inalcanzable -- 61% de los meses quiebre_parcial nunca tocan stock=0,
    solo caen por debajo de stock_minimo (ver CONTEXTO.md, auditoría
    2026-08-19, hallazgo C2).

    Solo usa los días con fila real en stock_diario ese mes -- no rellena
    huecos de calendario sin dato, mismo criterio que ya usa dias_con_stock
    (tampoco asume un valor para un día sin fila).
    """
    sin_stock = False
    for stock in dias_ordenados:
        if stock <= stock_minimo:
            sin_stock = True
        elif sin_stock:
            return True
    return False


def cargar_ingreso_durante_quiebre(
    conn: pymysql.Connection, fecha_desde: dt.date, fecha_hasta: dt.date, meses_set: set[tuple[int, int]]
) -> dict[tuple, bool]:
    """Por SKU×mes, si hubo un ingreso de stock a mitad del mes (issue #145).

    Issue #164: el umbral de "tiene stock" es `stock > stock_minimo`, el
    mismo que ya usa dias_con_stock/_SQL_STOCK -- no `stock > 0` literal.
    stock_minimo se precarga por SKU (consulta aparte, mismo patrón que
    cargar_factores/cargar_fec_alta) en vez de meterlo en _SQL_STOCK_DIARIO
    con un JOIN: eso cambiaría su plan de ejecución (hoy una sola tabla con
    el FORCE INDEX de #153) y arriesgaría el guardrail que ya lo cubre.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT sku, COALESCE(stock_minimo, 0) FROM articulos")
        stock_minimo_por_sku = {sku: float(sm) for sku, sm in cur.fetchall()}

    with conn.cursor() as cur:
        cur.execute(_SQL_STOCK_DIARIO, (fecha_desde, fecha_hasta))
        rows = cur.fetchall()

    por_sku_mes: dict[tuple, list[tuple[dt.date, float]]] = {}
    for sku, fecha, stock_total in rows:
        yr, mo = fecha.year, fecha.month
        if (yr, mo) not in meses_set:
            continue
        por_sku_mes.setdefault((sku, yr, mo), []).append((fecha, float(stock_total)))

    resultado: dict[tuple, bool] = {}
    for key, dias in por_sku_mes.items():
        sku = key[0]
        dias_ordenados = [stock for _, stock in sorted(dias)]
        stock_minimo = stock_minimo_por_sku.get(sku, 0.0)
        resultado[key] = detectar_ingreso_durante_mes(dias_ordenados, stock_minimo)
    return resultado


def calcular_filas(conn: pymysql.Connection) -> tuple[list[dict], int, int, int]:
    """
    Retorna (filas_para_insert, skus_omitidos, mes_referencia_normal, mes_referencia_sin_stock).
    skus_omitidos: SKUs que tienen ventas pero no existe en articulos (FK violation evitada).
    mes_referencia_normal/sin_stock: conteo de filas del mes de referencia en cada rama
    del override de clasificar_estado_mes (observabilidad en jobs_historial).
    """
    factors = cargar_factores(conn)
    fec_altas = cargar_fec_alta(conn)
    meses = ventana_meses(VENTANA_MESES)
    meses_set = set(meses)

    # Rango de fechas para acotar las queries
    primer_mes = meses[-1]
    ultimo_mes  = meses[0]
    fecha_desde = dt.date(primer_mes[0], primer_mes[1], 1)
    fecha_hasta = dt.date(
        ultimo_mes[0], ultimo_mes[1],
        dias_naturales_mes(ultimo_mes[0], ultimo_mes[1])
    )

    print(f"[PLANILLA] Ventana: {fecha_desde} → {fecha_hasta}  ({VENTANA_MESES} meses)")

    # ── Ventas por SKU×mes (solo SKUs que existen en articulos) ───────────────
    sql_ventas = """
        SELECT
            vh.sku,
            YEAR(vh.fecha)  AS yr,
            MONTH(vh.fecha) AS mo,
            SUM(vh.cantidad) AS ventas_cantidad
        FROM ventas_historicas vh
        INNER JOIN articulos a ON a.sku = vh.sku
        WHERE vh.fecha BETWEEN %s AND %s
        GROUP BY vh.sku, YEAR(vh.fecha), MONTH(vh.fecha)
    """
    with conn.cursor() as cur:
        cur.execute(sql_ventas, (fecha_desde, fecha_hasta))
        ventas_raw = cur.fetchall()

    ventas: dict[tuple, int] = {}
    for sku, yr, mo, cant in ventas_raw:
        if (yr, mo) in meses_set:
            ventas[(sku, yr, mo)] = int(cant)

    # ── Tickets por SKU×mes (Issue #61, fix #64: ver cargar_tickets) ───────────
    tickets = cargar_tickets(conn, fecha_desde, fecha_hasta, meses_set)

    # ── Días con stock por SKU×mes ─────────────────────────────────────────────
    # Un día "tiene stock" cuando el total de todos los depósitos supera stock_minimo.
    with conn.cursor() as cur:
        cur.execute(_SQL_STOCK, (fecha_desde, fecha_hasta))
        stock_raw = cur.fetchall()

    dias_stock: dict[tuple, int] = {}
    for sku, yr, mo, dias in stock_raw:
        if (yr, mo) in meses_set:
            dias_stock[(sku, yr, mo)] = int(dias)

    # ── Ingreso de stock a mitad de un mes con quiebre (Issue #145) ───────────
    ingreso_quiebre = cargar_ingreso_durante_quiebre(conn, fecha_desde, fecha_hasta, meses_set)

    # ── SKUs omitidos (ventas sin articulo) ────────────────────────────────────
    sql_huerfanos = """
        SELECT COUNT(DISTINCT vh.sku)
        FROM ventas_historicas vh
        LEFT JOIN articulos a ON a.sku = vh.sku
        WHERE a.sku IS NULL
          AND vh.fecha BETWEEN %s AND %s
    """
    with conn.cursor() as cur:
        cur.execute(sql_huerfanos, (fecha_desde, fecha_hasta))
        skus_omitidos = int(cur.fetchone()[0])

    if skus_omitidos:
        print(f"[PLANILLA][WARN] {skus_omitidos} SKU(s) con ventas sin registro en articulos — omitidos.")

    # ── Construir filas (paso 1: calcular datos por mes) ──────────────────────
    todas_keys = (set(ventas.keys()) | set(dias_stock.keys()))

    filas = []
    for (sku, yr, mo) in todas_keys:
        dn = dias_naturales_mes(yr, mo)
        ds = dias_stock.get((sku, yr, mo), 0)
        vq = ventas.get((sku, yr, mo), 0)

        rot_real  = round(vq / ds, 4) if ds > 0 else None
        rot_bruta = round(vq / dn, 4)

        factor = (factors.get(sku) or {}).get(mo)
        rot_desest = round(rot_real / factor, 4) if rot_real is not None and factor else None
        estado_mes = clasificar_estado_mes(ds, dn, (yr, mo) == ultimo_mes)

        filas.append({
            "sku":                               sku,
            "year":                              yr,
            "month":                             mo,
            "ventas_cantidad":                   vq,
            "dias_con_stock":                    ds,
            "dias_naturales_mes":                dn,
            "rotacion_diaria_real":              rot_real,
            "rotacion_diaria_bruta":             rot_bruta,
            "rotacion_diaria_desestacionalizada": rot_desest,
            "estado_mes":                        estado_mes,
            "frecuencia_nivel":                  None,  # se rellena en paso 2
            "rotacion_ajustada":                 None,  # se rellena en paso 2
            "tickets_mes":                       tickets.get((sku, yr, mo), 0),
            "valor_historico":                   None,  # se rellena en paso 2
            "valor_ajustado":                    None,  # se rellena en paso 2
            "criterio_frecuencia":               None,  # se rellena en paso 2
            "venta_o_extrapolacion":              None,  # se rellena en paso 2
            # Issue #145: solo tiene sentido marcarlo en un mes de quiebre --
            # un "ingreso durante quiebre" en un mes normal o sin_stock no es
            # lo que el cliente pidió distinguir.
            "ingreso_durante_quiebre":           (
                estado_mes == "quiebre_parcial"
                and ingreso_quiebre.get((sku, yr, mo), False)
            ),
        })

    # ── Paso 2: frecuencia de quiebre por SKU ─────────────────────────────────
    # Mes de referencia = meses[0] (más reciente). Los 12 cerrados son meses[1..12].
    meses_ordenados = sorted(meses, reverse=True)          # más reciente primero
    meses_cerrados  = set(meses_ordenados[1:])             # excluye el mes actual

    # Contar meses cerrados con ventas > 0 por SKU
    meses_con_ventas: dict[str, int] = {}
    for (sku, yr, mo), vq in ventas.items():
        if (yr, mo) in meses_cerrados and vq > 0:
            meses_con_ventas[sku] = meses_con_ventas.get(sku, 0) + 1

    def clasificar_frecuencia(n_meses_con_ventas: int) -> str:
        if n_meses_con_ventas >= FREQ_ALTA_MIN:
            return "alta"
        if n_meses_con_ventas <= FREQ_BAJA_MAX:
            return "baja"
        return "media"

    def rotacion_ajustada(vq: int, ds: int, dn: int, nivel: str) -> float | None:
        if nivel == "alta":
            return round(vq / ds, 4) if ds > 0 else None
        if nivel == "baja":
            return round(vq / dn, 4)
        # media: promedio de ambas fórmulas
        r_alta = vq / ds if ds > 0 else None
        r_baja = vq / dn
        if r_alta is None:
            return round(r_baja, 4)
        return round((r_alta + r_baja) / 2, 4)

    # estado_mes y extrapolacion por (sku, year, month), calculados una sola vez
    # sobre `filas` (Issue #163) -- calcular_historico() los necesita para excluir
    # meses sin_stock y usar la extrapolacion (no la venta cruda) en quiebre_parcial.
    estados_mes: dict[tuple, str] = {}
    extrapolaciones_mes: dict[tuple, float | None] = {}
    for fila in filas:
        key = (fila["sku"], fila["year"], fila["month"])
        estados_mes[key] = fila["estado_mes"]
        extrapolaciones_mes[key] = extrapolacion_mes(
            fila["ventas_cantidad"], fila["dias_con_stock"], fila["dias_naturales_mes"],
        )

    # Historico por SKU (una sola vez, no varia mes a mes dentro de la misma corrida)
    historicos: dict[str, float | None] = {}
    for sku in {f["sku"] for f in filas}:
        historicos[sku] = calcular_historico(
            sku, fec_altas.get(sku), meses_cerrados, ventas, estados_mes, extrapolaciones_mes,
        )

    # Anotar frecuencia_nivel, rotacion_ajustada y frecuencia de tickets en cada fila
    for fila in filas:
        sku = fila["sku"]
        n   = meses_con_ventas.get(sku, 0)
        nivel = clasificar_frecuencia(n)
        fila["frecuencia_nivel"] = nivel

        if fila["estado_mes"] == "quiebre_parcial":
            fila["rotacion_ajustada"] = rotacion_ajustada(
                fila["ventas_cantidad"],
                fila["dias_con_stock"],
                fila["dias_naturales_mes"],
                nivel,
            )

        # Issue #61/#63: frecuencia de venta por tickets del mes
        historico = historicos.get(sku)
        # Issue #129: la extrapolacion ahora pondera por cuanto del mes se pudo
        # observar, en vez de proyectar el ritmo de los dias con stock al mes
        # entero. Ver extrapolacion_mes(). Reutiliza el valor ya calculado
        # arriba (Issue #163) en vez de volver a invocar extrapolacion_mes().
        extrapolacion = extrapolaciones_mes[(sku, fila["year"], fila["month"])]
        es_quiebre = fila["estado_mes"] != "normal"

        # Issue #182: mismo redondeo (ROUND_HALF_UP) que valor_ajustado_y_criterio()
        # usa sobre este mismo `historico` mas abajo -- con round() nativo, un
        # historico exactamente en un borde de medio centavo podia guardar un
        # valor en valor_historico y OTRO en valor_ajustado para la misma fila.
        fila["valor_historico"] = redondear(historico, 2) if historico is not None else None
        fila["valor_ajustado"], fila["criterio_frecuencia"] = valor_ajustado_y_criterio(
            fila["tickets_mes"],
            fila["ventas_cantidad"],
            extrapolacion,
            historico,
            es_quiebre,
        )
        fila["venta_o_extrapolacion"] = venta_o_extrapolacion(
            fila["estado_mes"], fila["ventas_cantidad"], extrapolacion,
        )

    skus_procesados = len({f["sku"] for f in filas})
    dist = {lvl: sum(1 for f in filas if f["frecuencia_nivel"] == lvl and f["month"] == meses[0][1] and f["year"] == meses[0][0]) for lvl in ("alta","media","baja")}
    print(f"[PLANILLA] {skus_procesados} SKUs · {len(filas)} filas · frecuencia: alta={dist['alta']} media={dist['media']} baja={dist['baja']}")

    filas_mes_ref = [f for f in filas if (f["year"], f["month"]) == ultimo_mes]
    mes_referencia_normal    = sum(1 for f in filas_mes_ref if f["estado_mes"] == "normal")
    mes_referencia_sin_stock = sum(1 for f in filas_mes_ref if f["estado_mes"] == "sin_stock")
    print(f"[PLANILLA] Mes de referencia {ultimo_mes}: normal={mes_referencia_normal} sin_stock={mes_referencia_sin_stock}")

    return filas, skus_omitidos, mes_referencia_normal, mes_referencia_sin_stock

# ── Escritura atómica ──────────────────────────────────────────────────────────

_SQL_INSERT = """
    INSERT INTO planilla_ventas_calculada
        (sku, year, month,
         ventas_cantidad, dias_con_stock, dias_naturales_mes,
         rotacion_diaria_real, rotacion_diaria_bruta, rotacion_diaria_desestacionalizada,
         estado_mes, frecuencia_nivel, rotacion_ajustada,
         tickets_mes, valor_historico, valor_ajustado, criterio_frecuencia,
         venta_o_extrapolacion, ingreso_durante_quiebre, ts_carga)
    VALUES
        (%(sku)s, %(year)s, %(month)s,
         %(ventas_cantidad)s, %(dias_con_stock)s, %(dias_naturales_mes)s,
         %(rotacion_diaria_real)s, %(rotacion_diaria_bruta)s,
         %(rotacion_diaria_desestacionalizada)s,
         %(estado_mes)s, %(frecuencia_nivel)s, %(rotacion_ajustada)s,
         %(tickets_mes)s, %(valor_historico)s, %(valor_ajustado)s, %(criterio_frecuencia)s,
         %(venta_o_extrapolacion)s, %(ingreso_durante_quiebre)s, NOW(6))
"""

def escribir_planilla(conn: pymysql.Connection, filas: list[dict]) -> None:
    """
    DELETE + INSERT en una única transacción.
    Usamos DELETE (no TRUNCATE) para que sea rollbackeable.
    Si algo falla, el caller hace rollback → tabla queda con datos anteriores.
    """
    with conn.cursor() as cur:
        cur.execute("SET time_zone = '+00:00'")
        cur.execute("DELETE FROM planilla_ventas_calculada")
        if filas:
            cur.executemany(_SQL_INSERT, filas)
    conn.commit()

# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    global TICKETS_BAJO_MAX, TICKETS_ALTO_MIN

    t0 = time.time()
    conn = db_connect()
    job_id = job_start(conn)
    print(f"[PLANILLA] Job id={job_id} iniciado")

    try:
        config = cargar_configuracion(conn)
        TICKETS_BAJO_MAX = config["tickets_bajo_max"]
        TICKETS_ALTO_MIN = config["tickets_alto_min"]
        print(f"[PLANILLA] Umbrales de tickets: bajo<={TICKETS_BAJO_MAX} alto>={TICKETS_ALTO_MIN}")

        filas, skus_omitidos, mes_ref_normal, mes_ref_sin_stock = calcular_filas(conn)
        escribir_planilla(conn, filas)

        duracion = round(time.time() - t0, 2)
        detalle = {
            "subtipo":                  "calc_planilla",
            "skus_procesados":          len({f["sku"] for f in filas}),
            "meses_calculados":         VENTANA_MESES,
            "filas_insertadas":         len(filas),
            "skus_omitidos":            skus_omitidos,
            "duracion_seg":             duracion,
            "umbral_normal_pct":        int(ESTADO_UMBRAL_NORMAL * 100),
            "mes_referencia_normal":    mes_ref_normal,
            "mes_referencia_sin_stock": mes_ref_sin_stock,
        }
        job_end(conn, job_id, "exitoso", detalle)
        print(f"[PLANILLA] Completado OK en {duracion}s")

    except Exception as exc:
        conn.rollback()
        duracion = round(time.time() - t0, 2)
        detalle = {
            "subtipo":      "calc_planilla",
            "error":        str(exc),
            "duracion_seg": duracion,
        }
        job_end(conn, job_id, "fallido", detalle)
        print(f"[PLANILLA][ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
