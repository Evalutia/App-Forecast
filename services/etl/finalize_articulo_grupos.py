#!/usr/bin/env python3
"""
finalize_articulo_grupos.py - Issue #121: vuelca a la tabla real
articulo_grupo lo que este run acumulo en articulo_grupo_stage (cada llamada
de run_extract_articulos.py agrega ahi sus pares sku/grupo), y recalcula
articulos.grupo_id ("grupo principal") a partir de esa membresia.

Se invoca UNA sola vez, al final del loop de run_extract_articulos.sh, y
SOLO si los ~65 grupos de la corrida respondieron sin error (ver
lib_articulo_grupo_decision.sh) -- si alguno fallo, el caller no debe
invocar este script.

IMPORTANTE -- por que el DELETE es ACOTADO, no de toda la tabla:
la llamada SOAP de cada grupo es incremental (FechaDesde = ultimos 7 dias)
salvo la PRIMERA vez que se procesa ese grupo (es_grupo_nuevo en el .sh),
que trae el catalogo completo sin filtro de fecha. O sea que en una corrida
normal, articulo_grupo_stage NO contiene la membresia completa de los
grupos ya conocidos -- solo los articulos que cambiaron esta semana. Un
delete-and-reinsert de TODA la tabla en cada corrida (version anterior de
este script) borraba silenciosamente, noche a noche, la membresia real de
todo articulo que no hubiera cambiado en los ultimos 7 dias -- practicamente
todo el catalogo a los pocos dias del deploy.

El fix: el caller pasa la lista de grupos que efectivamente hicieron pull
COMPLETO esta corrida (`full_pull_grupos`, generalmente vacia salvo la
primera corrida o un grupo nuevo). Solo esos grupos tienen su membresia
reemplazada por completo (ahi si el stage refleja el 100% real). Para el
resto -- la inmensa mayoria de las corridas -- el insert es aditivo
(INSERT IGNORE): suma membresias nuevas vistas esta semana, nunca borra las
que no aparecieron. Limitacion conocida y aceptada: una membresia que el
cliente RETIRA de un articulo en un grupo ya "viejo" no se detecta hasta
que ese grupo vuelva a hacer un pull completo -- mismo tipo de limitacion
que ya tiene el resto de este ETL incremental (no hay deteccion de bajas),
no algo nuevo que este script introduce.

grupo principal = el de menor id entre los grupos visible_planilla=TRUE de
la membresia del articulo (para no volver a caer en un catch-all como 199/200
via un simple MIN sin ese filtro); si el articulo no tiene NINGUN grupo
visible entre sus membresias, se usa el de menor id sin ese filtro (nunca se
deja grupo_id sin valor -- la columna es NOT NULL con FK a grupos). Se
recalcula sobre TODA articulo_grupo en cada corrida, sin importar el alcance
del delete de arriba -- una membresia agregada de forma incremental puede
cambiar cual es el principal de un articulo.

Todo en una sola transaccion real: DELETE FROM (no TRUNCATE, que en MySQL
hace commit implicito y romperia el todo-o-nada) para poder revertir si algo
falla a mitad de camino.
"""

import os
import sys

import pymysql


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


def finalize(conn, full_pull_grupos=()) -> tuple[int, int]:
    """
    Ejecuta el swap dentro de la transaccion ya abierta en `conn`. No hace
    commit ni rollback -- eso lo decide el caller (separado para poder
    testear el efecto antes de confirmar).

    full_pull_grupos: grupo_id de los grupos que esta corrida creawleo por
    completo (sin filtro de fecha). Solo esos se DELETE-an antes de
    reinsertar -- el resto es aditivo. Vacio -> no se borra nada, solo se
    agregan membresias nuevas.

    Devuelve (n_membresias_insertadas, n_articulos_con_principal_actualizado).
    """
    full_pull_grupos = [int(g) for g in full_pull_grupos]

    with conn.cursor() as cur:
        if full_pull_grupos:
            placeholders = ",".join(["%s"] * len(full_pull_grupos))
            cur.execute(
                f"DELETE FROM articulo_grupo WHERE grupo_id IN ({placeholders})",
                full_pull_grupos,
            )

        cur.execute(
            "INSERT IGNORE INTO articulo_grupo (sku, grupo_id) "
            "SELECT sku, grupo_id FROM articulo_grupo_stage"
        )
        n_membresias = cur.rowcount

        cur.execute(
            """
            UPDATE articulos a
            JOIN (
              SELECT ag.sku,
                     COALESCE(
                       MIN(CASE WHEN g.visible_planilla THEN ag.grupo_id END),
                       MIN(ag.grupo_id)
                     ) AS grupo_principal
              FROM articulo_grupo ag
              JOIN grupos g ON g.id = ag.grupo_id
              GROUP BY ag.sku
            ) p ON p.sku = a.sku
            SET a.grupo_id = p.grupo_principal
            WHERE a.grupo_id <> p.grupo_principal
            """
        )
        n_articulos = cur.rowcount

        # DELETE, no TRUNCATE: TRUNCATE es DDL y hace commit implicito en
        # MySQL, lo que romperia el "todo o nada" de esta transaccion (si
        # esta linea fallara, el DELETE/INSERT/UPDATE de arriba ya habrian
        # quedado confirmados para siempre pese al rollback de mas abajo).
        cur.execute("DELETE FROM articulo_grupo_stage")

    return n_membresias, n_articulos


def main() -> int:
    full_pull_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    full_pull_grupos = [g.strip() for g in full_pull_arg.split(",") if g.strip()]

    conn = db_connect()
    try:
        n_membresias, n_articulos = finalize(conn, full_pull_grupos)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] finalize_articulo_grupos abortado, sin cambios: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(
        f"[INFO] articulo_grupo actualizado: {n_membresias} membresias nuevas, "
        f"{n_articulos} articulos con grupo principal recalculado "
        f"(pull completo esta corrida: {full_pull_grupos or 'ninguno'})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
