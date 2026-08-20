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
resto -- la inmensa mayoria de las corridas -- el insert es aditivo: suma
membresias nuevas vistas esta semana, nunca borra las que no aparecieron.
Limitacion conocida y aceptada: una membresia que el cliente RETIRA de un
articulo en un grupo ya "viejo" no se detecta hasta que ese grupo vuelva a
hacer un pull completo -- mismo tipo de limitacion que ya tiene el resto de
este ETL incremental (no hay deteccion de bajas), no algo nuevo que este
script introduce.

Issue #168: el insert aditivo ya NO usa `INSERT IGNORE` a granel -- ese
IGNORE se tragaba por igual duplicados legitimos (esperado) y violaciones
de FK reales (un SKU en stage que nunca llego a existir en `articulos`).
Ahora es un insert fila por fila con `ON DUPLICATE KEY UPDATE` (ver
`finalize()`), que preserva el "no duplicar" pero deja pasar la excepcion
de una FK invalida para poder contarla y loguearla en vez de perderla en
silencio.

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


def finalize(conn, full_pull_grupos=()) -> tuple[int, int, int]:
    """
    Ejecuta el swap dentro de la transaccion ya abierta en `conn`. No hace
    commit ni rollback -- eso lo decide el caller (separado para poder
    testear el efecto antes de confirmar).

    full_pull_grupos: grupo_id de los grupos que esta corrida creawleo por
    completo (sin filtro de fecha). Solo esos se DELETE-an antes de
    reinsertar -- el resto es aditivo. Vacio -> no se borra nada, solo se
    agregan membresias nuevas.

    Issue #168 -- dos salvaguardas nuevas:
    1. Un grupo en `full_pull_grupos` sin NINGUNA fila en `articulo_grupo_stage`
       no se borra -- es la senal de que el pull realmente no trajo nada (WS
       fallido, o cualquier otra causa), no confiar ciegamente en que el
       caller haya excluido bien el grupo (defensa en profundidad, #167
       corrige el root cause del lado del caller pero esta guard es
       independiente de esa correccion).
    2. El volcado del stage ya no usa `INSERT IGNORE` a granel -- ese IGNORE
       se tragaba por igual duplicados legitimos (esperado, no pasa nada) y
       violaciones de FK reales (un SKU en stage que nunca llego a existir en
       `articulos`, ej. porque su propia insercion fallo). Ahora se inserta
       fila por fila con `ON DUPLICATE KEY UPDATE` (no-op en duplicados,
       pero NO silencia una violacion de FK como el IGNORE) -- una violacion
       de FK se cuenta y se loguea, sin abortar el resto del lote.

    Devuelve (n_membresias_insertadas, n_articulos_con_principal_actualizado,
    n_fk_violations).
    """
    full_pull_grupos = [int(g) for g in full_pull_grupos]

    with conn.cursor() as cur:
        grupos_a_borrar = []
        for g in full_pull_grupos:
            cur.execute("SELECT COUNT(*) FROM articulo_grupo_stage WHERE grupo_id = %s", (g,))
            if cur.fetchone()[0] > 0:
                grupos_a_borrar.append(g)
            else:
                print(
                    f"[WARN] grupo {g} en full_pull_grupos pero sin ninguna fila en "
                    "articulo_grupo_stage -- NO se borra su membresia existente (issue #168)"
                )

        if grupos_a_borrar:
            placeholders = ",".join(["%s"] * len(grupos_a_borrar))
            cur.execute(
                f"DELETE FROM articulo_grupo WHERE grupo_id IN ({placeholders})",
                grupos_a_borrar,
            )

        cur.execute("SELECT sku, grupo_id FROM articulo_grupo_stage")
        stage_rows = cur.fetchall()

        n_membresias = 0
        n_fk_violations = 0
        for sku, grupo_id in stage_rows:
            try:
                cur.execute(
                    "INSERT INTO articulo_grupo (sku, grupo_id) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE sku = sku",
                    (sku, grupo_id),
                )
                if cur.rowcount > 0:
                    n_membresias += 1
            except pymysql.err.IntegrityError as e:
                n_fk_violations += 1
                print(
                    f"[ERROR] membresia sku={sku} grupo_id={grupo_id} no se pudo insertar "
                    f"en articulo_grupo (issue #168, probable violacion de FK): {e}"
                )

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

    return n_membresias, n_articulos, n_fk_violations


def main() -> int:
    full_pull_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    full_pull_grupos = [g.strip() for g in full_pull_arg.split(",") if g.strip()]

    conn = db_connect()
    try:
        n_membresias, n_articulos, n_fk_violations = finalize(conn, full_pull_grupos)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] finalize_articulo_grupos abortado, sin cambios: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(
        f"[INFO] articulo_grupo actualizado: {n_membresias} membresias nuevas, "
        f"{n_articulos} articulos con grupo principal recalculado, "
        f"{n_fk_violations} violacion(es) de FK descartadas "
        f"(pull completo esta corrida: {full_pull_grupos or 'ninguno'})"
    )
    # Issue #168: violaciones de FK ya no quedan solo en el log de stdout --
    # exit code distinto de cero para que jobs_historial refleje que algo se
    # perdio, aunque el resto del volcado haya salido bien.
    if n_fk_violations:
        print(f"[ERROR] {n_fk_violations} membresia(s) no se pudieron insertar por violacion de FK")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
