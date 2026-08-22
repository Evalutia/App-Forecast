#!/usr/bin/env python3
"""
cron_jobs.py - Bookkeeping en jobs_historial para el cron nocturno
(Issue #111). Hermano de backfill_jobs.py, mismo patron de subcomandos
invocados desde bash.

Por que existe: hasta #111 la corrida nocturna solo dejaba rastro en
jobs_historial si llegaba a los pasos CALC finales (run_calc_planilla /
run_calc_sugerencias / run_calc_stock_resumen, que registran su propio
job). Todo lo anterior -- truncate del staging, extraccion SOAP de
articulos/ventas/stock, merges -- fallaba en silencio: la unica huella
quedaba en `docker logs` de ofelia, que se pierde al recrear el
contenedor. Eso dejo 4 noches (24-27/07/2026) sin diagnostico posible y
10 dias de planilla congelada sin que nadie se enterara.

Subcomandos:
  start
      Inserta una fila 'ejecutando' (tipo_job='etl',
      detalle.subtipo='cron_diario') e imprime el job_id.

  end <job_id> <exit_code> <duracion_seg>
      Cierra la fila: 'exitoso' si exit_code == 0, 'fallido' si no. El
      detalle se combina con JSON_MERGE_PATCH (Issue #132) en vez de
      reemplazarse entero -- para que lo que haya escrito `stale` ANTES de
      esta llamada (atraso "al entrar a la noche") sobreviva.

  skip <motivo>
      Issue #132: registra una noche salteada (ej. lock de backfill) como
      fila terminal, estado='omitido' (ver infra/sql/22-*, agrega el valor
      al ENUM). Antes se guardaba como 'exitoso' -- indistinguible de una
      corrida real y buena (29-31/07/2026: tres noches salteadas, las tres
      contadas como buenas). Ni 'exitoso' ni 'fallido' describen un skip
      intencional -- no corrio nada que pudiera fallar, pero tampoco es una
      corrida real.

  stale <job_id|-> [umbral_dias]
      Imprime cuantos dias de atraso tiene el dato de ventas
      (CURDATE() - MAX(fecha) de ventas_historicas) y sale con codigo 1
      si supera el umbral (default 2). Issue #132: si <job_id> no es "-",
      tambien guarda el resultado bajo detalle.atraso de esa fila (JSON_SET,
      mismo patron que `coherencia`) -- antes esto solo se imprimia a
      stdout, invisible fuera del log efimero de Docker, y no corria en la
      rama de skip. Se llama ANTES de `start`->kitchen a proposito (mide el
      atraso "al entrar a la noche"); sobrevive al `end` posterior porque
      `end` ahora hace merge, no reemplazo.

  coherencia <job_id|-> [fecha_desde [fecha_hasta]]
      Issue #115. Compara, para cada sku-dia con venta en el rango, la venta
      registrada contra la caida real de stock (stock_diario) de un dia
      para el otro -- la firma que destapo #114 (SKU duplicado en el merge
      -> venta ~2x o ~3x la caida real). Guarda el resultado bajo
      detalle.coherencia de la fila <job_id> en jobs_historial (JSON_SET,
      no pisa exit_code/duracion_seg que ya escribio `end`). Si <job_id> es
      "-" no escribe nada -- sirve para correrlo a mano sobre un rango
      arbitrario (ej. verificar la reparacion de #123). Sin fechas, mide el
      dia de ayer (lo que el cron acaba de cargar). No bloqueante: un
      chequeo caido (DB abajo, consulta rota) se loguea y devuelve !=0, pero
      nunca levanta una excepcion que corte la corrida.

  stock_gaps <job_id|-> [fecha_desde [fecha_hasta]]
      Issue #133. Pregunta distinta de `coherencia`: fechas en el rango sin
      NINGUNA fila en stock_diario (ausencia total de dato, no calidad del
      dato). A diferencia de ventas -- recuperable en la corrida siguiente
      via SALES_FORCE_START/END, ver run_ofelia.sh -- un dia de stock
      perdido no se puede volver a pedir (ConsStockXml devuelve siempre la
      foto de HOY). Guarda el resultado bajo detalle.stock_gaps de la fila
      <job_id> (JSON_SET, mismo patron que `coherencia`). Sin fechas, mide
      los ultimos 7 dias terminando ayer (no 1, como coherencia -- misma
      ventana que la recuperacion de ventas). No bloqueante: un chequeo
      caido se loguea y devuelve !=0, pero nunca corta la corrida.

      Issue #155: ademas del hueco TOTAL de arriba, detecta el hueco
      PARCIAL -- una fecha que SI tiene filas en stock_diario, pero no de
      todos los depositos configurados (ej. 5 de los 6 depositos de
      S_DEPOSITOS escriben bien un dia, uno falla). stock_total suma todos
      los depositos, asi que un deposito faltante subestima el stock real y
      puede fabricar quiebres que no existieron -- silencioso para el hueco
      TOTAL de #133, porque la fecha "tiene datos". La cantidad esperada de
      depositos sale de la variable de entorno S_DEPOSITOS (Issue #139,
      misma fuente que usa la extraccion) -- nunca hardcodeada, para que el
      chequeo no mienta el dia que se agregue un deposito nuevo. Mismo
      alcance informativo que el hueco TOTAL: un dia de stock perdido de un
      deposito puntual tampoco se puede volver a pedir (ConsStockXml
      siempre trae la foto de HOY, sin importar el deposito) -- esto avisa,
      no repara.

  catalogo_gap
      Issue #170. A diferencia de `coherencia`/`stock_gaps` (invocados desde
      run_ofelia.sh, afuera de Kettle, despues de que kitchen.sh termina),
      este corre DESDE ADENTRO de job_etl_diario.kjb, justo despues del
      merge de ventas y antes del TRUNCATE del stage al final -- necesita
      ventas_historicas_stage todavia poblado con los datos de la corrida.
      Cuenta filas/SKUs que el INNER JOIN con articulos del merge descarto
      en silencio por falta de registro en el catalogo (mismo mecanismo que
      tumbo 51.024 filas en #111). Sin job_id explicito (Kettle no lo
      conoce, igual que mark_step_failed) -- escribe bajo detalle.
      catalogo_gap de la fila 'ejecutando' del cron, identificable sin
      ambiguedad porque no-overlap=true de ofelia garantiza que nunca hay
      mas de una. No bloqueante: un chequeo caido se loguea y devuelve !=0,
      pero nunca corta la corrida.

  abort <motivo>
      Issue #132: fallo ANTES de poder registrar `start` (ej. run_ofelia.sh
      aborta por un archivo faltante, como paso el 2026-08-11 con
      lock_backfill.sh) -- sin esto la unica huella era el log efimero de
      Docker, que se pierde al recrear el contenedor. Fila terminal
      'fallido' propia, sin job_id previo que cerrar.

  mark_step_failed <paso> <motivo>
      Issue #131: auditoria de un paso de job_etl_diario.kjb que fallo en
      una rama "marca y sigue" (no aborta la cadena de Kettle). Fila
      terminal 'fallido' propia -- lo que de verdad vuelve 'fallida' la fila
      OFICIAL de la corrida (la de `start`/`end`) es que el propio .kjb,
      al final, chequea el marker que este mismo llamado deja (ver
      mark_step_failed.sh) y termina en la rama de fallo en vez de SUCCESS,
      lo que hace que kitchen.sh salga con codigo != 0.

  last_run [umbral_horas]
      Issue #132: heartbeat del propio cron -- distinto de `stale`, que mide
      la frescura del DATO. Esto mide si el cron SIQUIERA INTENTO correr:
      imprime hace cuanto fue la ultima fila de tipo_job='etl' /
      subtipo='cron_diario' (de CUALQUIER estado -- un intento fallido
      todavia cuenta) y sale con codigo 1 si pasa el umbral (default 30h).
      Pensado para invocarse a mano o desde un watchdog externo -- si el
      scheduler (Ofelia) esta caido, run_ofelia.sh nunca corre y nada
      *adentro* del propio bookkeeping puede detectarlo (paso el
      2026-08-01: sin corrida no hay error, y sin error no hay señal).
"""

import datetime as dt
import json
import os
import sys

import pymysql

SUBTIPO = "cron_diario"
UMBRAL_ATRASO_DIAS = 2  # el cron extrae "ayer": 1 dia de atraso es lo normal
TOLERANCIA_RATIO = 0.1  # ratio venta/caida fuera de [0.9, 1.1] cuenta como anomalo
# Issue #166: umbrales del consumidor minimo (log [ALERTA] visible en
# `docker logs`) -- hasta que exista algo mas sofisticado, "alguien revisa
# docker logs cuando aparece [ALERTA]" ES el proceso, documentado aca a
# proposito en vez de dejarlo implicito. pct_anomalo tiene ruido de fondo
# esperable (variabilidad dia a dia, ver CONTEXTO.md #166) por eso necesita
# un umbral -- se alerta cuando SUPERA 5% (5.0% exacto todavia no alerta,
# comparacion estricta `>`), no cuando lo alcanza.
UMBRAL_ALERTA_PCT_ANOMALO = 5.0
# Volumen de casos venta=0-con-caida-real: metrica nueva de #166, sin
# historial propio para calibrar un umbral basado en ruido esperado -- se
# usa un numero chico y redondo (revisar si genera demasiado ruido en la
# practica y ajustar).
UMBRAL_ALERTA_VENTA_CERO_CON_CAIDA = 10
# Issue #132: 30h (no 24h) le da margen a una corrida que arranca tarde o se
# alarga sin que eso solo ya dispare el heartbeat -- el umbral es para
# detectar que el scheduler no corrio EN ABSOLUTO, no para medir puntualidad.
UMBRAL_LAST_RUN_HORAS = 30
# Issue #185: filas 'etl' 'ejecutando' sin detalle.subtipo (esquema anterior
# a #111, que introdujo el campo) nunca matchean el filtro por SUBTIPO de
# _cerrar_zombis y quedan colgadas para siempre. A diferencia de esas (donde
# no-overlap=true de ofelia garantiza que 'ejecutando' es siempre zombie), una
# fila sin subtipo es de un esquema mas viejo sin esa garantia documentada --
# el umbral evita tocar algo que, en teoria, todavia pudiera estar corriendo.
UMBRAL_ZOMBI_SIN_SUBTIPO_HORAS = 24


def db_connect():
    return pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DB"],
        autocommit=False,
        charset="utf8mb4",
    )


def _insert(conn, estado: str, detalle: dict, terminal: bool) -> int:
    fin = "NOW(6)" if terminal else "NULL"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs_historial (tipo_job, estado, fecha_inicio, fecha_fin, detalle) "
            f"VALUES ('etl', %s, NOW(6), {fin}, %s)",
            (estado, json.dumps(detalle, ensure_ascii=False)),
        )
        job_id = cur.lastrowid
    conn.commit()
    return int(job_id)


def _cerrar_zombis(conn) -> int:
    """
    Cierra corridas del cron que quedaron en 'ejecutando' porque el proceso
    murio sin poder registrar su final (contenedor recreado a mitad de la
    noche, kill, reboot). Sin esto el registro miente para siempre y no se
    puede responder "corrio bien anoche?".

    Es seguro asumir que estan muertas: ofelia ejecuta este job con
    no-overlap=true, asi que nunca hay dos corridas del cron en paralelo.
    Acotado a tipo_job='etl' + subtipo del cron para no tocar backfills ni
    los jobs propios de los pasos CALC.

    Issue #185: ademas del subtipo actual, tambien cierra filas 'etl'
    'ejecutando' SIN subtipo -- esquema anterior a #111, que introdujo el
    campo. Esas nunca matchean el filtro de arriba (detalle->>'$.subtipo' =
    SUBTIPO) y quedaban colgadas para siempre, porque #111 solo empezo a
    taggear subtipo hacia adelante, no reparo lo viejo.

    OJO -- "sin subtipo" NO es exclusivo de esas filas viejas: los tres
    scripts de CALC (run_calc_planilla.py/run_calc_sugerencias.py/
    run_calc_stock_resumen.py) insertan su propia fila 'etl' 'ejecutando'
    via su propio job_start() sin tocar detalle en absoluto (columna NULL),
    HOY, cada noche -- serian indistinguibles de una fila pre-#111 por
    subtipo solo. Por eso el segundo UPDATE no se limita a "sin subtipo +
    antiguedad": tambien exige fecha_inicio anterior al MIN(fecha_inicio) de
    la primera fila que SI tiene subtipo=SUBTIPO -- ese valor es, por
    construccion, el momento en que #111 empezo a taggear, asi que ninguna
    fila de CALC creada desde entonces (todas las de ahora en mas) puede
    caer antes de ese corte. Si todavia no existe ninguna fila con SUBTIPO
    (corte NULL, DB nueva/de test) esta segunda limpieza no toca nada -- mas
    vale no actuar que cerrar de mas.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs_historial "
            "   SET estado = 'fallido', fecha_fin = NOW(6), "
            "       detalle = JSON_SET(COALESCE(detalle, JSON_OBJECT()), "
            "                          '$.resultado', 'interrumpido') "
            " WHERE tipo_job = 'etl' AND estado = 'ejecutando' "
            "   AND detalle->>'$.subtipo' = %s",
            (SUBTIPO,),
        )
        cerradas = cur.rowcount

        cur.execute(
            "SELECT MIN(fecha_inicio) FROM jobs_historial "
            " WHERE tipo_job = 'etl' AND detalle->>'$.subtipo' = %s",
            (SUBTIPO,),
        )
        corte_subtipo = cur.fetchone()[0]

        if corte_subtipo is not None:
            cur.execute(
                "UPDATE jobs_historial "
                "   SET estado = 'fallido', fecha_fin = NOW(6), "
                "       detalle = JSON_SET(COALESCE(detalle, JSON_OBJECT()), "
                "                          '$.resultado', 'interrumpido_sin_subtipo') "
                " WHERE tipo_job = 'etl' AND estado = 'ejecutando' "
                "   AND detalle->>'$.subtipo' IS NULL "
                "   AND fecha_inicio < %s "
                "   AND fecha_inicio < DATE_SUB(NOW(6), INTERVAL %s HOUR)",
                (corte_subtipo, UMBRAL_ZOMBI_SIN_SUBTIPO_HORAS),
            )
            cerradas += cur.rowcount
    conn.commit()
    return cerradas


def cmd_start() -> int:
    conn = db_connect()
    try:
        zombis = _cerrar_zombis(conn)
        if zombis:
            print(f"[CRON] {zombis} corrida(s) anterior(es) sin cerrar -> marcadas 'fallido'.",
                  file=sys.stderr)
        print(_insert(conn, "ejecutando", {"subtipo": SUBTIPO}, terminal=False))
    finally:
        conn.close()
    return 0


def cmd_end(job_id: str, exit_code: str, duracion_seg: str) -> int:
    codigo = int(exit_code)
    detalle_nuevo = {
        "exit_code": codigo,
        "duracion_seg": float(duracion_seg),
        "resultado": "ok" if codigo == 0 else "error",
    }
    # Issue #136: 137 = 128+9 (SIGKILL). En esta maquina, con memoria muy
    # ajustada (ver docker-compose mem_limit), un SIGKILL casi siempre es el
    # OOM killer del kernel -- pero es una inferencia, no una confirmacion
    # contra dmesg del host (eso exigiria leer logs del host desde el
    # contenedor). Se marca igual para que la fila sea legible sin tener que
    # saber de memoria que "137" significa SIGKILL.
    if codigo == 137:
        detalle_nuevo["posible_oom"] = True
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            # Issue #132: JSON_MERGE_PATCH en vez de un simple %s -- antes esta
            # UPDATE reemplazaba detalle entero, asi que cualquier cosa escrita
            # ANTES de `end` (ej. detalle.atraso de `stale`, que corre a
            # proposito antes de arrancar kitchen) se perdia sin dejar rastro.
            # subtipo tambien sobrevive porque ya esta en el detalle que dejo
            # `start` y el patch no lo toca.
            cur.execute(
                "UPDATE jobs_historial "
                "   SET estado = %s, fecha_fin = NOW(6), "
                "       detalle = JSON_MERGE_PATCH(COALESCE(detalle, JSON_OBJECT()), CAST(%s AS JSON)) "
                " WHERE id = %s",
                ("exitoso" if codigo == 0 else "fallido",
                 json.dumps(detalle_nuevo, ensure_ascii=False), job_id),
            )
        conn.commit()
    finally:
        conn.close()
    return 0


def cmd_skip(motivo: str) -> int:
    # Issue #132: estado='omitido' (no 'exitoso') -- antes un skip por lock de
    # backfill quedaba indistinguible de una corrida real y buena (29-31/07
    # /2026: tres noches salteadas, las tres contadas como buenas). Requiere
    # el valor en el ENUM (infra/sql/22-jobs-historial-estado-omitido.sql,
    # mismo patron defensivo que 18-jobs-historial-eval-elegibilidad.sql).
    conn = db_connect()
    try:
        print(_insert(
            conn, "omitido",
            {"subtipo": SUBTIPO, "resultado": "omitido", "motivo": motivo},
            terminal=True,
        ))
    finally:
        conn.close()
    return 0


def cmd_stale(job_id: str = "-", umbral_dias: str = str(UMBRAL_ATRASO_DIAS)) -> int:
    """
    Atraso medido sobre el DATO, no sobre el bookkeeping: una noche salteada
    o un job que muere antes del merge dejan el dato viejo igual, y eso es lo
    que ve el cliente en la planilla.

    Issue #132: si <job_id> no es "-", el resultado tambien queda en
    detalle.atraso de esa fila (JSON_SET, no pisa nada -- mismo patron que
    `coherencia`). Antes esto solo se imprimia a stdout: invisible fuera del
    log efimero de Docker, y ademas no corria en la rama de skip. Toda la
    funcion es best-effort, igual que `coherencia` (conexion incluida,
    hallazgo de /code-review -- antes solo el UPDATE de guardado estaba
    protegido y una caida de MySQL en el SELECT principal tiraba un
    traceback sin manejar en vez del mensaje limpio que el docstring ya
    prometia): un fallo se loguea pero nunca cambia el codigo de salida mas
    alla del 1 que ya usa para "hay atraso".
    """
    umbral = int(umbral_dias)
    try:
        conn = db_connect()
    except Exception as e:
        print(f"[CRON][STALE] no se pudo conectar a MySQL: {e}", file=sys.stderr)
        return 1

    try:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT DATEDIFF(CURDATE(), MAX(fecha)) FROM ventas_historicas")
                atraso = cur.fetchone()[0]
        except Exception as e:
            print(f"[CRON][STALE] chequeo fallo (no bloquea el ETL): {e}", file=sys.stderr)
            return 1

        if atraso is None:
            print("[CRON] Sin datos en ventas_historicas -- no se puede medir atraso.")
            return 1

        atraso = int(atraso)

        if job_id and job_id != "-":
            resultado = {"atraso_dias": atraso, "umbral_dias": umbral}
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE jobs_historial "
                        "   SET detalle = JSON_SET(COALESCE(detalle, JSON_OBJECT()), "
                        "                          '$.atraso', CAST(%s AS JSON)) "
                        " WHERE id = %s",
                        (json.dumps(resultado, ensure_ascii=False), job_id),
                    )
                conn.commit()
            except Exception as e:
                print(f"[CRON][STALE] no se pudo guardar en jobs_historial (job {job_id}): {e}",
                      file=sys.stderr)
    finally:
        conn.close()

    if atraso > umbral:
        print(f"[CRON][ATRASO] ventas_historicas tiene {atraso} dias de atraso "
              f"(umbral {umbral}). La planilla que ve el cliente esta desactualizada.")
        return 1

    print(f"[CRON] Atraso de ventas_historicas: {atraso} dia(s) (umbral {umbral}).")
    return 0


def _calcular_coherencia(conn, fecha_desde: str, fecha_hasta: str) -> dict:
    """
    Para cada sku-dia en [fecha_desde, fecha_hasta] donde el stock bajo de un
    dia para el otro, compara venta contra caida de stock. Query de
    referencia: issue #115 / diagnostico #114. Alcance honesto: detecta
    duplicacion o perdida de venta contrastada contra el stock -- no valida
    que el stock mismo este bien.

    stock_diario se consulta desde un dia antes de fecha_desde porque cada
    fila necesita el stock del dia anterior (sp) ademas del propio (sh).

    Issue #166: el anchor de la query paso de ventas_historicas (INNER JOIN,
    con v.cantidad>0 en el WHERE) a la caida real de stock (LEFT JOIN a
    ventas_historicas) -- con el INNER JOIN viejo, un dia con caida de stock
    real pero venta registrada en 0 (o sin ninguna fila de venta) nunca
    llegaba siquiera a evaluarse: quedaba completamente afuera de la
    comparacion, el mismo punto ciego que investigo #161 un dia antes de la
    auditoria que encontro esto. Esos casos se cuentan aparte
    (num_venta_cero_con_caida/unidades_venta_cero_con_caida), sin mezclarse
    con num_observaciones/num_anomalos -- esa metrica sigue midiendo
    exactamente lo mismo que antes, solo entre los dias que SI tienen
    venta>0 registrada.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(v.cantidad, 0) AS venta, (sp.st - sh.st) AS caida
            FROM (
                SELECT sku, fecha, SUM(cantidad) AS st
                FROM stock_diario
                WHERE fecha BETWEEN DATE_SUB(%(desde)s, INTERVAL 1 DAY) AND %(hasta)s
                GROUP BY sku, fecha
            ) sh
            JOIN (
                SELECT sku, fecha, SUM(cantidad) AS st
                FROM stock_diario
                WHERE fecha BETWEEN DATE_SUB(%(desde)s, INTERVAL 1 DAY) AND %(hasta)s
                GROUP BY sku, fecha
            ) sp ON sp.sku = sh.sku AND sp.fecha = DATE_SUB(sh.fecha, INTERVAL 1 DAY)
            LEFT JOIN ventas_historicas v ON v.sku = sh.sku AND v.fecha = sh.fecha
            WHERE sh.fecha BETWEEN %(desde)s AND %(hasta)s
              AND (sp.st - sh.st) > 0
            """,
            {"desde": fecha_desde, "hasta": fecha_hasta},
        )
        filas = cur.fetchall()

    # Hallazgo de /code-review: una venta neta negativa (nota de credito que
    # supera la venta del dia, #80 permite cantidad firmada) no es "venta>0"
    # ni "venta==0" -- con un chequeo de igualdad estricta quedaba fuera de
    # las dos categorias, invisible por completo, la misma clase de punto
    # ciego que este ticket vino a cerrar. Se agrupa junto a venta=0 bajo
    # "sin venta positiva pese a la caida real" (venta<=0): ninguna de las
    # dos explica una caida de stock con una venta positiva registrada.
    con_venta = [(venta, caida) for venta, caida in filas if venta > 0]
    sin_venta = [(venta, caida) for venta, caida in filas if venta <= 0]

    total = len(con_venta)
    anomalos = sum(
        1 for venta, caida in con_venta
        if abs((float(venta) / float(caida)) - 1.0) > TOLERANCIA_RATIO
    )
    pct = round(100.0 * anomalos / total, 2) if total else None

    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "num_observaciones": total,
        "num_anomalos": anomalos,
        "pct_anomalo": pct,
        "num_venta_cero_con_caida": len(sin_venta),
        "unidades_venta_cero_con_caida": sum(int(caida) for _v, caida in sin_venta),
    }


def _ayer_iso() -> str:
    """Code review de #133: antes duplicado en cmd_coherencia y cmd_stock_gaps."""
    return (dt.date.today() - dt.timedelta(days=1)).isoformat()


def cmd_coherencia(job_id: str, fecha_desde: str = None, fecha_hasta: str = None) -> int:
    """
    No bloqueante (#115): un chequeo caido -- DB abajo, tabla renombrada, lo
    que sea -- se loguea y jamas propaga una excepcion. El costo de un falso
    positivo frenando el pipeline es peor que un dia de demora en detectar
    (la leccion de #111/#114).
    """
    if fecha_desde is None:
        fecha_desde = fecha_hasta = _ayer_iso()
    elif fecha_hasta is None:
        fecha_hasta = fecha_desde

    try:
        conn = db_connect()
    except Exception as e:
        print(f"[CRON][COHERENCIA] no se pudo conectar a MySQL: {e}", file=sys.stderr)
        return 1

    try:
        resultado = _calcular_coherencia(conn, fecha_desde, fecha_hasta)
    except Exception as e:
        print(f"[CRON][COHERENCIA] chequeo fallo (no bloquea el ETL): {e}", file=sys.stderr)
        conn.close()
        return 1

    if job_id and job_id != "-":
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE jobs_historial "
                    "   SET detalle = JSON_SET(COALESCE(detalle, JSON_OBJECT()), "
                    "                          '$.coherencia', CAST(%s AS JSON)) "
                    " WHERE id = %s",
                    (json.dumps(resultado, ensure_ascii=False), job_id),
                )
            conn.commit()
        except Exception as e:
            print(f"[CRON][COHERENCIA] no se pudo guardar en jobs_historial (job {job_id}): {e}",
                  file=sys.stderr)
    conn.close()

    if resultado["num_observaciones"] == 0:
        print(f"[CRON][COHERENCIA] {fecha_desde}..{fecha_hasta}: sin observaciones "
              f"(ningun sku con caida de stock y venta registrada en el rango).")
    else:
        print(f"[CRON][COHERENCIA] {fecha_desde}..{fecha_hasta}: "
              f"{resultado['pct_anomalo']}% anomalo "
              f"({resultado['num_anomalos']}/{resultado['num_observaciones']} filas, "
              f"ratio venta/caida fuera de [{1 - TOLERANCIA_RATIO:.1f}, {1 + TOLERANCIA_RATIO:.1f}]).")

    if resultado["num_venta_cero_con_caida"] > 0:
        print(f"[CRON][COHERENCIA] {fecha_desde}..{fecha_hasta}: "
              f"{resultado['num_venta_cero_con_caida']} caso(s) de venta=0 con caida real de stock "
              f"({resultado['unidades_venta_cero_con_caida']} unidad(es), punto ciego de #161).")

    # Issue #166: el consumidor minimo -- hasta que exista algo mas
    # sofisticado, este [ALERTA] en docker logs ES el proceso (documentado
    # como tal, no un placeholder). Dos disparadores independientes, ninguno
    # necesita al otro: un pct_anomalo alto sobre pocas observaciones no
    # dice lo mismo que un volumen grande de venta=0-con-caida.
    if resultado["pct_anomalo"] is not None and resultado["pct_anomalo"] > UMBRAL_ALERTA_PCT_ANOMALO:
        print(f"[CRON][COHERENCIA][ALERTA] {fecha_desde}..{fecha_hasta}: "
              f"pct_anomalo {resultado['pct_anomalo']}% supera el umbral de {UMBRAL_ALERTA_PCT_ANOMALO}% "
              "-- revisar manualmente.")
    if resultado["num_venta_cero_con_caida"] > UMBRAL_ALERTA_VENTA_CERO_CON_CAIDA:
        print(f"[CRON][COHERENCIA][ALERTA] {fecha_desde}..{fecha_hasta}: "
              f"{resultado['num_venta_cero_con_caida']} casos de venta=0 con caida real "
              f"supera el umbral de {UMBRAL_ALERTA_VENTA_CERO_CON_CAIDA} -- revisar manualmente.")

    return 0


def _depositos_esperados_desde_env() -> list:
    """
    Issue #155 / #139: S_DEPOSITOS vive en la variable de entorno (mismo
    origen que usan run_extract_stockxml.sh, run_extract_sales_chunk.sh y
    run_backfill_ventas.sh), nunca hardcodeada aca -- si se agrega un
    deposito nuevo a la extraccion, el chequeo de huecos parciales lo sabe
    sin tocar codigo. Mismo criterio de parseo que esos scripts bash: lista
    separada por comas, cada token sin espacios. Vacia (variable no seteada,
    o seteada vacia) es una respuesta valida -- no hay contra que comparar,
    ver _calcular_stock_gaps.
    """
    crudo = os.environ.get("S_DEPOSITOS", "")
    return sorted({token.strip() for token in crudo.split(",") if token.strip()})


def _calcular_stock_gaps(
    conn, fecha_desde: str, fecha_hasta: str, depositos_esperados: list = None
) -> dict:
    """
    Fechas en [fecha_desde, fecha_hasta] sin NINGUNA fila en stock_diario --
    pregunta distinta de _calcular_coherencia (que compara venta contra
    caida de stock para fechas CON dato): esto detecta la ausencia total de
    dato para un dia. Issue #133: a diferencia de ventas (recuperable, el WS
    acepta rangos historicos), un dia de stock perdido no se puede volver a
    pedir -- ConsStockXml devuelve siempre la foto de HOY sin importar la
    fecha pedida (ver assert_ventana_no_peligrosa en run_extract_stockxml.sh).
    Calcula el calendario completo en Python en vez de un generate_series en
    SQL -- mas simple, y el rango nunca es mas que unos pocos dias.

    Issue #155: ademas del hueco TOTAL, detecta el hueco PARCIAL -- una
    fecha CON filas en stock_diario, pero no de todos los depositos de
    `depositos_esperados` (por defecto, S_DEPOSITOS via
    _depositos_esperados_desde_env -- explicito solo para tests). Un dia sin
    NINGUNA fila ya cuenta como hueco TOTAL y a proposito no se repite aca
    (evita que el mismo dia aparezca duplicado bajo dos etiquetas distintas
    con el mismo significado). Igual que el hueco TOTAL, esto es
    informativo, no reparable: un deposito que no escribio un dia puntual
    tampoco se puede volver a pedir -- ConsStockXml siempre trae la foto de
    HOY, no la del dia pedido, sin importar el deposito.

    Nota (no bloqueante, sin evidencia de que pase hoy): run_extract_stockxml.py
    prioriza el IdDeposito que viene en el cuerpo de la respuesta del WS sobre
    el token de S_DEPOSITOS, y solo cae a este ultimo si el campo viene vacio
    (ver deposito_val alli). Si el WS alguna vez devolviera el deposito en un
    formato distinto al token plano de S_DEPOSITOS (padding, prefijo), ese
    deposito_id no matchearia contra `depositos_esperados` y la fecha
    quedaria marcada como hueco PARCIAL permanente sin serlo -- falso
    positivo, no falso negativo, asi que no esconde un problema real, pero
    vale tenerlo presente si este chequeo empieza a reportar ruido persistente.
    """
    desde = dt.date.fromisoformat(fecha_desde)
    hasta = dt.date.fromisoformat(fecha_hasta)
    todas_las_fechas = set()
    d = desde
    while d <= hasta:
        todas_las_fechas.add(d)
        d += dt.timedelta(days=1)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT fecha, deposito_id FROM stock_diario "
            "WHERE fecha BETWEEN %(desde)s AND %(hasta)s",
            {"desde": fecha_desde, "hasta": fecha_hasta},
        )
        depositos_por_fecha = {}
        for fecha, deposito_id in cur.fetchall():
            depositos_por_fecha.setdefault(fecha, set()).add(deposito_id)

    faltantes = sorted(todas_las_fechas - set(depositos_por_fecha))

    if depositos_esperados is None:
        depositos_esperados = _depositos_esperados_desde_env()
    esperados = set(depositos_esperados)

    dias_con_depositos_faltantes = []
    if esperados:
        for fecha in sorted(depositos_por_fecha):
            faltan = sorted(esperados - depositos_por_fecha[fecha])
            if faltan:
                dias_con_depositos_faltantes.append(
                    {"fecha": fecha.isoformat(), "depositos_faltantes": faltan}
                )

    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "dias_sin_datos": [d.isoformat() for d in faltantes],
        "num_dias_sin_datos": len(faltantes),
        "depositos_esperados": sorted(esperados),
        "dias_con_depositos_faltantes": dias_con_depositos_faltantes,
        "num_dias_con_depositos_faltantes": len(dias_con_depositos_faltantes),
    }


def cmd_stock_gaps(job_id: str, fecha_desde: str = None, fecha_hasta: str = None) -> int:
    """
    Issue #133: hace visible un hueco de stock que NO se puede recuperar --
    mismo criterio de no-bloqueo que cmd_coherencia (un chequeo caido se
    loguea y jamas frena el ETL), pero pregunta distinta (presencia/ausencia
    de dato, no calidad del dato).

    Default de 7 dias terminando ayer si NO se pasa ninguna fecha (no 1 dia,
    como coherencia) -- misma ventana que la recuperacion de ventas (ver
    SALES_FORCE_START/END en run_ofelia.sh), para que un hueco de hace un
    par de noches siga visible en corridas sucesivas. Si se pasa solo
    fecha_desde, se acota a ESE unico dia (mismo criterio que cmd_coherencia)
    -- code review: la version anterior ignoraba fecha_desde en ese caso y
    recalculaba fecha_hasta como "ayer" igual, corriendo silenciosamente
    sobre una ventana distinta a la pedida.

    Issue #155: el mismo resultado (bajo la misma clave detalle.stock_gaps)
    ahora tambien trae el hueco PARCIAL por deposito -- ver
    _calcular_stock_gaps. Informativo, igual que el hueco TOTAL: no hay
    reparacion posible para ninguno de los dos.
    """
    if fecha_desde is None:
        fecha_hasta = _ayer_iso()
        fecha_desde = (dt.date.fromisoformat(fecha_hasta) - dt.timedelta(days=6)).isoformat()
    elif fecha_hasta is None:
        fecha_hasta = fecha_desde

    try:
        conn = db_connect()
    except Exception as e:
        print(f"[CRON][STOCK_GAPS] no se pudo conectar a MySQL: {e}", file=sys.stderr)
        return 1

    try:
        resultado = _calcular_stock_gaps(conn, fecha_desde, fecha_hasta)
    except Exception as e:
        print(f"[CRON][STOCK_GAPS] chequeo fallo (no bloquea el ETL): {e}", file=sys.stderr)
        conn.close()
        return 1

    if job_id and job_id != "-":
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE jobs_historial "
                    "   SET detalle = JSON_SET(COALESCE(detalle, JSON_OBJECT()), "
                    "                          '$.stock_gaps', CAST(%s AS JSON)) "
                    " WHERE id = %s",
                    (json.dumps(resultado, ensure_ascii=False), job_id),
                )
            conn.commit()
        except Exception as e:
            print(f"[CRON][STOCK_GAPS] no se pudo guardar en jobs_historial (job {job_id}): {e}",
                  file=sys.stderr)
    conn.close()

    dias_con_depositos_faltantes = resultado["dias_con_depositos_faltantes"]
    hay_hueco_total = resultado["num_dias_sin_datos"] > 0
    hay_hueco_parcial = bool(dias_con_depositos_faltantes)

    if not hay_hueco_total and not hay_hueco_parcial:
        print(f"[CRON][STOCK_GAPS] {fecha_desde}..{fecha_hasta}: sin huecos "
              f"(stock_diario tiene datos todos los dias del rango).")
        return 0

    # Issue #176: mismo defecto estructural que #166 -- nadie consumia esto
    # mas alla de un [INFO] en stdout. A diferencia de coherencia (que tiene
    # ruido de fondo esperable dia a dia y por eso necesita un umbral), un
    # hueco de stock es ya en si mismo el caso raro -- no hay reparacion
    # posible (ver docstring de _calcular_stock_gaps), asi que cualquier
    # ocurrencia se marca [ALERTA] directamente, sin umbral separado.
    if hay_hueco_total:
        print(f"[CRON][STOCK_GAPS][ALERTA] {fecha_desde}..{fecha_hasta}: "
              f"{resultado['num_dias_sin_datos']} dia(s) sin ningun dato de stock: "
              f"{', '.join(resultado['dias_sin_datos'])}")

    if hay_hueco_parcial:
        detalle_por_dia = "; ".join(
            f"{item['fecha']}: deposito(s) faltante(s) {', '.join(item['depositos_faltantes'])}"
            for item in dias_con_depositos_faltantes
        )
        print(f"[CRON][STOCK_GAPS][ALERTA] {fecha_desde}..{fecha_hasta}: "
              f"{len(dias_con_depositos_faltantes)} dia(s) con hueco PARCIAL "
              f"(algun deposito de {', '.join(resultado['depositos_esperados'])} no "
              f"escribio ese dia, aunque la fecha tiene datos de otros): {detalle_por_dia}")

    return 0


def _calcular_catalogo_gap(conn) -> dict:
    """
    Issue #170: cuenta cuantas filas/SKUs de ventas_historicas_stage se van a
    perder en el merge de esta corrida por no tener registro en articulos --
    el mecanismo de silent-drop que ya tumbo 51.024 filas en #111 (39 SKUs
    nuevos sin catalogo, el 02/08/2026) y que la auditoria de datos confirmo
    de nuevo con I02855-I02860 (2 años sin sincronizar, cero visibilidad
    hasta ahora).

    JOIN/WHERE calcado del step "MERGE STAGING -> VENTAS (con snapshot)" de
    job_etl_diario.kjb (LEFT en vez de INNER, invertido para contar los
    huerfanos en vez de descartarlos) -- si ese SQL cambia, este debe
    cambiar junto para no medir una pregunta distinta de la que de verdad
    se mergea. El NOT EXISTS contra ventas_grupos_fallidos_run excluye del
    conteo los grupos que ya fallaron en la extraccion de esta corrida
    (#157) -- esos son una causa distinta, ya visible en su propia tabla, no
    hace falta contarlos de nuevo aca.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT TRIM(s.sku))
            FROM ventas_historicas_stage s
            LEFT JOIN articulos a ON a.sku = TRIM(s.sku)
            WHERE s.sku IS NOT NULL
              AND a.sku IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM ventas_grupos_fallidos_run f WHERE f.grupo_id = s.grupo_id
              )
            """
        )
        filas, skus = cur.fetchone()
    return {"filas": int(filas), "skus": int(skus)}


def cmd_catalogo_gap() -> int:
    """
    Issue #170: corre DENTRO del .kjb, justo despues del merge de ventas y
    antes de "TRUNCATE VENTAS_STAGE END" -- a diferencia de `coherencia`/
    `stock_gaps` (que corren desde run_ofelia.sh, afuera de Kettle, despues
    de que kitchen.sh termina), este chequeo necesita ventas_historicas_stage
    todavia poblado con los datos de ESTA corrida, asi que no puede esperar
    a que el job termine. Por el mismo motivo que mark_step_failed.sh (#131),
    Kettle no le pasa el job_id de la fila oficial (ese vive en
    run_ofelia.sh) -- en vez de una fila de auditoria propia y desconectada
    como hace mark_step_failed, esto agrega detalle.catalogo_gap directo a
    la fila 'ejecutando' del cron (identificable sin ambiguedad: no-overlap
    =true de ofelia garantiza que nunca hay mas de una).

    No bloqueante, mismo criterio que `coherencia`/`stock_gaps`: un chequeo
    caido se loguea y nunca corta la corrida -- el dato ya se perdio en el
    merge de todas formas, frenar aca no lo recupera.
    """
    try:
        conn = db_connect()
    except Exception as e:
        print(f"[CRON][CATALOGO_GAP] no se pudo conectar a MySQL: {e}", file=sys.stderr)
        return 1

    try:
        resultado = _calcular_catalogo_gap(conn)
    except Exception as e:
        print(f"[CRON][CATALOGO_GAP] chequeo fallo (no bloquea el ETL): {e}", file=sys.stderr)
        conn.close()
        return 1

    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs_historial "
                "   SET detalle = JSON_SET(COALESCE(detalle, JSON_OBJECT()), "
                "                          '$.catalogo_gap', CAST(%s AS JSON)) "
                " WHERE tipo_job = 'etl' AND estado = 'ejecutando' "
                "   AND detalle->>'$.subtipo' = %s "
                " ORDER BY id DESC LIMIT 1",
                (json.dumps(resultado, ensure_ascii=False), SUBTIPO),
            )
        conn.commit()
    except Exception as e:
        print(f"[CRON][CATALOGO_GAP] no se pudo guardar en jobs_historial: {e}", file=sys.stderr)
    conn.close()

    if resultado["filas"] == 0:
        print("[CRON][CATALOGO_GAP] sin filas huerfanas (todos los SKUs de esta corrida ya estan en articulos).")
        return 0

    # Issue #170: igual que stock_gaps, cualquier ocurrencia es el caso raro
    # y se marca directo sin umbral separado -- es exactamente el mecanismo
    # que ya causo un incidente real (#111).
    print(f"[CRON][CATALOGO_GAP][ALERTA] {resultado['filas']} fila(s) / "
          f"{resultado['skus']} SKU(s) de ventas_historicas_stage no se mergearon "
          "a ventas_historicas por no tener registro en articulos todavia -- "
          "revisar manualmente (mismo mecanismo que #111).")
    return 0


def cmd_abort(motivo: str) -> int:
    """
    Issue #132: fallo de run_ofelia.sh ANTES de poder llamar a `start` (ej.
    falta un archivo requerido, como paso el 2026-08-11 con
    lock_backfill.sh). Sin esto la unica huella era `docker logs` de ofelia,
    efimero -- se pierde al recrear el contenedor. No hay job_id previo que
    cerrar: es su propia fila terminal, igual que `skip`.
    """
    conn = db_connect()
    try:
        print(_insert(
            conn, "fallido",
            {"subtipo": SUBTIPO, "resultado": "abortado_temprano", "motivo": motivo},
            terminal=True,
        ))
    finally:
        conn.close()
    return 0


def cmd_mark_step_failed(paso: str, motivo: str) -> int:
    """
    Issue #131: auditoria de un paso de job_etl_diario.kjb que fallo en una
    rama "marca y sigue" (no aborta la cadena de Kettle -- ver
    mark_step_failed.sh, invocado desde el .kjb). Fila terminal 'fallido'
    propia, desconectada del job_id de la corrida oficial (esa la abren/
    cierran `start`/`end`, afuera de Kettle). Lo que de verdad vuelve
    'fallida' la fila oficial es que el propio .kjb, al final de la cadena,
    revisa el marker que este mismo llamado deja y termina en la rama de
    fallo en vez de SUCCESS -- eso es lo que cambia el exit code de
    kitchen.sh, que es lo unico que run_ofelia.sh de verdad mira.
    """
    conn = db_connect()
    try:
        print(_insert(
            conn, "fallido",
            {"subtipo": SUBTIPO, "resultado": "paso_fallido", "paso": paso, "motivo": motivo},
            terminal=True,
        ))
    finally:
        conn.close()
    return 0


def cmd_last_run(umbral_horas: str = str(UMBRAL_LAST_RUN_HORAS)) -> int:
    """
    Issue #132: heartbeat del propio cron, no del dato. Cuenta cualquier fila
    de tipo_job='etl' + subtipo='cron_diario' sin importar su estado -- un
    intento fallido (o incluso 'abortado_temprano') todavia demuestra que
    run_ofelia.sh corrio. Si el SCHEDULER (Ofelia) esta caido, en cambio,
    run_ofelia.sh nunca se ejecuta y no aparece ninguna fila nueva -- ni
    buena ni mala (el caso del 2026-08-01). Pensado para invocarse a mano o
    desde un watchdog externo al propio cron (por definicion, nada que viva
    *adentro* del cron puede detectar que el cron no corrio).
    """
    umbral = float(umbral_horas)
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            # fecha_inicio es TIMESTAMP: MySQL lo devuelve convertido al
            # time_zone de LA SESION, no en UTC -- el contenedor de mysql
            # corre en America/Montevideo (UTC-3, ver docker-compose.yml),
            # asi que sin este SET la comparacion contra dt.utcnow() de mas
            # abajo quedaria sesgada ~3h (mismo motivo por el que
            # run_calc_planilla.py/run_calc_sugerencias.py/etc. hacen este
            # mismo SET antes de comparar fechas de la DB contra Python).
            cur.execute("SET time_zone = '+00:00'")
            cur.execute(
                "SELECT MAX(fecha_inicio) FROM jobs_historial "
                "WHERE tipo_job = 'etl' AND detalle->>'$.subtipo' = %s",
                (SUBTIPO,),
            )
            ultimo = cur.fetchone()[0]
    finally:
        conn.close()

    if ultimo is None:
        print("[CRON][LAST_RUN] jobs_historial no tiene ninguna corrida del cron registrada todavia.")
        return 1

    horas = (dt.datetime.utcnow() - ultimo).total_seconds() / 3600.0
    if horas > umbral:
        print(f"[CRON][LAST_RUN] la ultima corrida registrada fue hace {horas:.1f}h "
              f"(umbral {umbral}h) -- el cron podria no estar corriendo (¿scheduler caido?).")
        return 1

    print(f"[CRON][LAST_RUN] ultima corrida hace {horas:.1f}h (umbral {umbral}h).")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("[ERROR] Uso: cron_jobs.py start|end|skip|stale|coherencia|stock_gaps|"
              "catalogo_gap|abort|mark_step_failed|last_run ...", file=sys.stderr)
        return 2
    sub, args = sys.argv[1], sys.argv[2:]
    if sub == "start" and not args:
        return cmd_start()
    if sub == "end" and len(args) == 3:
        return cmd_end(*args)
    if sub == "skip" and len(args) == 1:
        return cmd_skip(*args)
    if sub == "stale" and len(args) <= 2:
        return cmd_stale(*args)
    if sub == "coherencia" and 1 <= len(args) <= 3:
        return cmd_coherencia(*args)
    if sub == "stock_gaps" and 1 <= len(args) <= 3:
        return cmd_stock_gaps(*args)
    if sub == "catalogo_gap" and not args:
        return cmd_catalogo_gap()
    if sub == "abort" and len(args) == 1:
        return cmd_abort(*args)
    if sub == "mark_step_failed" and len(args) == 2:
        return cmd_mark_step_failed(*args)
    if sub == "last_run" and len(args) <= 1:
        return cmd_last_run(*args)
    print(f"[ERROR] Subcomando/args invalidos: {sys.argv[1:]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
