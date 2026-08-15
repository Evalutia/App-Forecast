USE evalutia;

-- Issue #122 (dejado pendiente a proposito en 19-ventas-stage-deposito-grupo.sql,
-- ver ese comentario): stock_diario.deposito_id es VARCHAR(64) NULL, y la
-- UNIQUE uq_stock_sku_fecha_deposito (sku, fecha, deposito_id) no protege
-- contra duplicados cuando deposito_id llega vacio -- MySQL no colisiona
-- NULL contra NULL en una UNIQUE. Dos filas (mismo sku, misma fecha, las dos
-- con deposito_id=NULL) pasan la clave sin problema, y cualquier query que
-- sume stock_diario por (sku, fecha) a traves de depositos (ej.
-- CALC_UPSERT_VENTAS_MENSUALES en job_etl_diario.kjb, o dias_con_stock en
-- run_calc_planilla.py) cuenta esa fila dos veces.
--
-- Mismo fix que ya se aplico a ventas_historicas_stage en la migracion 19:
-- NOT NULL DEFAULT '' en vez de NULL, para que la UNIQUE existente empiece
-- a proteger de verdad. A diferencia de esa tabla (staging, se trunca cada
-- noche), stock_diario tiene datos reales en produccion -- por eso el
-- backfill explicito de las filas NULL existentes ANTES de aplicar la
-- restriccion, no solo el ALTER.

-- Pre-chequeo (hallazgo de /code-review, #122): si YA existe mas de una fila
-- NULL por (sku, fecha) -- exactamente el agujero que esta migracion cierra --
-- el UPDATE de abajo choca consigo mismo contra uq_stock_sku_fecha_deposito
-- al poner el mismo '' en las dos, con un "Duplicate entry" generico que no
-- explica nada. Se cuenta ANTES de tocar nada; local confirma 0 grupos asi
-- hoy, pero produccion es un ambiente distinto y no hay garantia. Si hay
-- duplicados, tanto el backfill como el ALTER quedan como no-op (decidir que
-- fila conservar por grupo es una decision de datos, no algo para resolver
-- en silencio aca) y el SELECT de abajo lo deja explicito en el output.
SET @dup_groups := (
  SELECT COUNT(*) FROM (
    SELECT sku, fecha
    FROM stock_diario
    WHERE deposito_id IS NULL
    GROUP BY sku, fecha
    HAVING COUNT(*) > 1
  ) dups
);

SELECT
  CASE WHEN @dup_groups > 0
    THEN CONCAT('ATENCION: ', @dup_groups, ' grupos (sku,fecha) tienen mas de una fila con deposito_id NULL en stock_diario. Migracion 20 NO aplicada -- resolver los duplicados a mano antes de reintentar (ver comentario en infra/sql/20-stock-diario-deposito-not-null.sql).')
    ELSE 'OK: sin duplicados NULL detectados, migracion 20 procede.'
  END AS estado_migracion_20;

-- Backfill: filas NULL existentes pasan al mismo sentinel '' que va a usar
-- la ingesta de ahora en mas. No-op si @dup_groups > 0 (ver pre-chequeo) o
-- si ya no quedan NULLs.
SET @sql0 := IF(@dup_groups = 0,
  "UPDATE stock_diario SET deposito_id = '' WHERE deposito_id IS NULL;",
  'SELECT 1;'
);
PREPARE stmt0 FROM @sql0; EXECUTE stmt0; DEALLOCATE PREPARE stmt0;

SET @col_type := (
  SELECT IS_NULLABLE FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'stock_diario'
    AND column_name = 'deposito_id'
);
SET @sql1 := IF(@col_type = 'YES' AND @dup_groups = 0,
  "ALTER TABLE stock_diario MODIFY COLUMN deposito_id VARCHAR(64) NOT NULL DEFAULT '';",
  'SELECT 1;'
);
PREPARE stmt1 FROM @sql1; EXECUTE stmt1; DEALLOCATE PREPARE stmt1;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('20-stock-diario-deposito-not-null.sql');
