USE evalutia;

-- Issue #102: agrega el valor 'eval_elegibilidad' al ENUM de
-- jobs_historial.tipo_job, para poder registrar la corrida mensual de
-- medicion (dry-run) de eval_walkforward.py + apply_elegibilidad.py como
-- un tipo de job propio, distinto de 'forecast' (predict.py nocturno).
--
-- MODIFY COLUMN sobre un ENUM no es idempotente por si solo (a diferencia
-- de ADD COLUMN/INDEX, que si lo son via los chequeos de information_schema
-- ya usados en 04-etl-staging.sql/14-ventas-cantidad-signed.sql) -- se sigue
-- el mismo patron defensivo del resto de infra/sql/: chequear
-- information_schema.COLUMNS.COLUMN_TYPE (el string completo del ENUM)
-- antes de alterar, para que re-correr esta migracion no dependa de que
-- MySQL tolere en silencio un ALTER repetido.

SET @tipo_actual := (
  SELECT COLUMN_TYPE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'jobs_historial'
    AND COLUMN_NAME = 'tipo_job'
);
SET @sql := IF(@tipo_actual NOT LIKE '%eval_elegibilidad%',
  "ALTER TABLE jobs_historial MODIFY COLUMN tipo_job ENUM('etl','forecast','backfill','export','eval_elegibilidad') NOT NULL;",
  'SELECT 1;'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
