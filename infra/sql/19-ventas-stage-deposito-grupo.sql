USE evalutia;

-- Issue #114: ventas_historicas_stage no tenia clave unica -- el diseno
-- original en 04-etl-staging.sql le saca a proposito la UNIQUE que hereda
-- de ventas_historicas via LIKE, porque queria que el INSERT plano
-- acumulara una fila por deposito para que el merge las sumara (fix de
-- #39). Con el loop por grupo de #42 (66 grupos x deposito), un articulo
-- que pertenece a varios grupos vuelve en varias respuestas del WS -> una
-- fila de mas por cada grupo que lo devuelve -> el SUM del merge
-- multiplica la venta por la cantidad de grupos. Esta migracion revierte
-- esa decision de diseno a proposito: agrega deposito_id (participa en la
-- clave, hace la ingesta idempotente por deposito) y grupo_id (solo
-- trazabilidad, fuera de la clave -- la fila se pisa, no se duplica,
-- cuando el mismo articulo/fecha/deposito vuelve por otro grupo).
--
-- deposito_id es NOT NULL DEFAULT '' (no NULL): MySQL no colisiona NULL
-- contra NULL en una UNIQUE, asi que un deposito_id nulo reabriria el
-- mismo bug por otra puerta si alguna vez S_DEPOSITOS viniera vacio. El
-- script de ingesta normaliza el sentinel de __FORCED_DEPOSITO vacio al
-- mismo ''.
--
-- stock_diario.deposito_id ya tiene este mismo landmine (VARCHAR(64) NULL
-- en su propia UNIQUE) -- no se toca aca: esa tabla tiene datos reales en
-- produccion, cambiar el tipo de columna ahi es una migracion de mas
-- riesgo que la de un staging que se trunca cada noche. Queda para #122.

SET @col_dep := (
  SELECT COUNT(1) FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'ventas_historicas_stage'
    AND column_name = 'deposito_id'
);
SET @sql1 := IF(@col_dep = 0,
  "ALTER TABLE ventas_historicas_stage ADD COLUMN deposito_id VARCHAR(64) NOT NULL DEFAULT '' AFTER stock;",
  'SELECT 1;'
);
PREPARE stmt1 FROM @sql1; EXECUTE stmt1; DEALLOCATE PREPARE stmt1;

SET @col_grp := (
  SELECT COUNT(1) FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'ventas_historicas_stage'
    AND column_name = 'grupo_id'
);
SET @sql2 := IF(@col_grp = 0,
  'ALTER TABLE ventas_historicas_stage ADD COLUMN grupo_id INT UNSIGNED NULL AFTER deposito_id;',
  'SELECT 1;'
);
PREPARE stmt2 FROM @sql2; EXECUTE stmt2; DEALLOCATE PREPARE stmt2;

SET @idx_dep := (
  SELECT COUNT(1) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'ventas_historicas_stage'
    AND index_name = 'uq_ventas_stage_fecha_sku_deposito'
);
SET @sql3 := IF(@idx_dep = 0,
  'ALTER TABLE ventas_historicas_stage ADD UNIQUE KEY uq_ventas_stage_fecha_sku_deposito (fecha, sku, deposito_id);',
  'SELECT 1;'
);
PREPARE stmt3 FROM @sql3; EXECUTE stmt3; DEALLOCATE PREPARE stmt3;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('19-ventas-stage-deposito-grupo.sql');
