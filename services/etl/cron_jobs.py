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
      Cierra la fila: 'exitoso' si exit_code == 0, 'fallido' si no.

  skip <motivo>
      Registra una noche salteada (ej. lock de backfill) como fila
      terminal con detalle.resultado='omitido'. No es una corrida real:
      queda distinguible de un 'exitoso' de verdad.

  stale [umbral_dias]
      Imprime cuantos dias de atraso tiene el dato de ventas
      (CURDATE() - MAX(fecha) de ventas_historicas) y sale con codigo 1
      si supera el umbral (default 2). Read-only.

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
"""

import datetime as dt
import json
import os
import sys

import pymysql

SUBTIPO = "cron_diario"
UMBRAL_ATRASO_DIAS = 2  # el cron extrae "ayer": 1 dia de atraso es lo normal
TOLERANCIA_RATIO = 0.1  # ratio venta/caida fuera de [0.9, 1.1] cuenta como anomalo


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
    detalle = {
        "subtipo": SUBTIPO,
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
        detalle["posible_oom"] = True
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs_historial SET estado = %s, fecha_fin = NOW(6), detalle = %s "
                "WHERE id = %s",
                ("exitoso" if codigo == 0 else "fallido",
                 json.dumps(detalle, ensure_ascii=False), job_id),
            )
        conn.commit()
    finally:
        conn.close()
    return 0


def cmd_skip(motivo: str) -> int:
    # 'exitoso' porque saltear es el comportamiento correcto y esperado (no es
    # una falla); detalle.resultado='omitido' lo distingue de una corrida real.
    # No se inventa un estado 'omitido': jobs_historial.estado es un ENUM
    # cerrado ('en_cola','ejecutando','exitoso','fallido') y agregarle un valor
    # exigiria migracion + aplicarla a mano en produccion (los volumenes ya
    # creados no re-ejecutan docker-entrypoint-initdb.d).
    conn = db_connect()
    try:
        print(_insert(
            conn, "exitoso",
            {"subtipo": SUBTIPO, "resultado": "omitido", "motivo": motivo},
            terminal=True,
        ))
    finally:
        conn.close()
    return 0


def cmd_stale(umbral_dias: str = str(UMBRAL_ATRASO_DIAS)) -> int:
    """
    Atraso medido sobre el DATO, no sobre el bookkeeping: una noche salteada
    o un job que muere antes del merge dejan el dato viejo igual, y eso es lo
    que ve el cliente en la planilla.
    """
    umbral = int(umbral_dias)
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATEDIFF(CURDATE(), MAX(fecha)) FROM ventas_historicas")
            atraso = cur.fetchone()[0]
    finally:
        conn.close()

    if atraso is None:
        print("[CRON] Sin datos en ventas_historicas -- no se puede medir atraso.")
        return 1

    atraso = int(atraso)
    if atraso > umbral:
        print(f"[CRON][ATRASO] ventas_historicas tiene {atraso} dias de atraso "
              f"(umbral {umbral}). La planilla que ve el cliente esta desactualizada.")
        return 1

    print(f"[CRON] Atraso de ventas_historicas: {atraso} dia(s) (umbral {umbral}).")
    return 0


def _calcular_coherencia(conn, fecha_desde: str, fecha_hasta: str) -> dict:
    """
    Para cada sku-dia con venta en [fecha_desde, fecha_hasta] donde el stock
    bajo de un dia para el otro, compara venta contra caida de stock. Query
    de referencia: issue #115 / diagnostico #114. Alcance honesto: detecta
    duplicacion o perdida de venta contrastada contra el stock -- no valida
    que el stock mismo este bien.

    stock_diario se consulta desde un dia antes de fecha_desde porque cada
    fila de venta necesita el stock del dia anterior (sp) ademas del propio
    (sh).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT v.cantidad AS venta, (sp.st - sh.st) AS caida
            FROM ventas_historicas v
            JOIN (
                SELECT sku, fecha, SUM(cantidad) AS st
                FROM stock_diario
                WHERE fecha BETWEEN DATE_SUB(%(desde)s, INTERVAL 1 DAY) AND %(hasta)s
                GROUP BY sku, fecha
            ) sh ON sh.sku = v.sku AND sh.fecha = v.fecha
            JOIN (
                SELECT sku, fecha, SUM(cantidad) AS st
                FROM stock_diario
                WHERE fecha BETWEEN DATE_SUB(%(desde)s, INTERVAL 1 DAY) AND %(hasta)s
                GROUP BY sku, fecha
            ) sp ON sp.sku = v.sku AND sp.fecha = DATE_SUB(v.fecha, INTERVAL 1 DAY)
            WHERE v.fecha BETWEEN %(desde)s AND %(hasta)s
              AND v.cantidad > 0
              AND (sp.st - sh.st) > 0
            """,
            {"desde": fecha_desde, "hasta": fecha_hasta},
        )
        filas = cur.fetchall()

    total = len(filas)
    anomalos = sum(
        1 for venta, caida in filas
        if abs((float(venta) / float(caida)) - 1.0) > TOLERANCIA_RATIO
    )
    pct = round(100.0 * anomalos / total, 2) if total else None

    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "num_observaciones": total,
        "num_anomalos": anomalos,
        "pct_anomalo": pct,
    }


def cmd_coherencia(job_id: str, fecha_desde: str = None, fecha_hasta: str = None) -> int:
    """
    No bloqueante (#115): un chequeo caido -- DB abajo, tabla renombrada, lo
    que sea -- se loguea y jamas propaga una excepcion. El costo de un falso
    positivo frenando el pipeline es peor que un dia de demora en detectar
    (la leccion de #111/#114).
    """
    if fecha_desde is None:
        fecha_desde = fecha_hasta = (dt.date.today() - dt.timedelta(days=1)).isoformat()
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
              f"(ningun sku con caida de stock en el rango).")
        return 0

    print(f"[CRON][COHERENCIA] {fecha_desde}..{fecha_hasta}: "
          f"{resultado['pct_anomalo']}% anomalo "
          f"({resultado['num_anomalos']}/{resultado['num_observaciones']} filas, "
          f"ratio venta/caida fuera de [{1 - TOLERANCIA_RATIO:.1f}, {1 + TOLERANCIA_RATIO:.1f}]).")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("[ERROR] Uso: cron_jobs.py start|end|skip|stale|coherencia ...", file=sys.stderr)
        return 2
    sub, args = sys.argv[1], sys.argv[2:]
    if sub == "start" and not args:
        return cmd_start()
    if sub == "end" and len(args) == 3:
        return cmd_end(*args)
    if sub == "skip" and len(args) == 1:
        return cmd_skip(*args)
    if sub == "stale" and len(args) <= 1:
        return cmd_stale(*args)
    if sub == "coherencia" and 1 <= len(args) <= 3:
        return cmd_coherencia(*args)
    print(f"[ERROR] Subcomando/args invalidos: {sys.argv[1:]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
