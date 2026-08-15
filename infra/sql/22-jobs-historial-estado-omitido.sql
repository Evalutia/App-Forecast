USE evalutia;

-- Issue #132: agrega 'omitido' al ENUM de jobs_historial.estado.
--
-- Una noche salteada por el lock de backfill (cron_jobs.py `skip`) se
-- guardaba como estado='exitoso' -- indistinguible de una corrida real y
-- buena. Paso de verdad: 29, 30 y 31/07/2026, tres noches seguidas sin ETL,
-- las tres contadas como exitosas. Ni 'exitoso' ni 'fallido' describen bien
-- un skip intencional: no corrio nada que pudiera fallar, pero tampoco es
-- una corrida real -- de ahi el valor nuevo, en vez de forzar uno de los dos
-- existentes.
--
-- MODIFY COLUMN sobre un ENUM no es idempotente por si solo -- se sigue el
-- mismo patron defensivo que 18-jobs-historial-eval-elegibilidad.sql:
-- chequear information_schema.COLUMNS.COLUMN_TYPE (el string completo del
-- ENUM) antes de alterar, para que re-correr esta migracion no dependa de
-- que MySQL tolere en silencio un ALTER repetido.

SET @tipo_actual := (
  SELECT COLUMN_TYPE FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'jobs_historial'
    AND COLUMN_NAME = 'estado'
);
SET @sql := IF(@tipo_actual NOT LIKE '%omitido%',
  "ALTER TABLE jobs_historial MODIFY COLUMN estado ENUM('en_cola','ejecutando','exitoso','fallido','omitido') NOT NULL;",
  'SELECT 1;'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('22-jobs-historial-estado-omitido.sql');
