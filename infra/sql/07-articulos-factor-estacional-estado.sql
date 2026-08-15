USE evalutia;

-- Issue #3: agrega factor_estacional y estado a articulos.
--
-- factor_estacional: coeficiente del mes actual (escalar), recalculado cada noche
-- por el ETL (issue #5) tomando el MesXX correspondiente desde el SOAP (issue #2).
-- Usado por planilla: rotacion_diaria_real / NULLIF(a.factor_estacional, 0) (ver 05-planilla.sql).
--
-- estado: el SOAP no expone un campo Estado. Se deriva de la presencia del SKU
-- en el feed nocturno (lo calcula el ETL): si el SKU deja de aparecer -> inactivo,
-- si reaparece -> activo. Es puramente informativo: no debe usarse para ocultar
-- articulos por default en ninguna vista (planilla, predicciones, listados).

-- Issue #140: ALTER TABLE ADD COLUMN / CREATE INDEX no son idempotentes
-- (fallan si la columna/indice ya existen) -- mismo patron de chequeo previo
-- via information_schema ya usado en 04-etl-staging.sql/15-planilla-frecuencia-tickets.sql.
SET @col := (
  SELECT COUNT(1) FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'articulos'
    AND column_name = 'factor_estacional'
);
SET @sql := IF(@col = 0,
  "ALTER TABLE articulos
     ADD COLUMN factor_estacional DECIMAL(5,3) NULL AFTER stock_minimo,
     ADD COLUMN estado ENUM('activo','inactivo') NOT NULL DEFAULT 'activo' AFTER factor_estacional;",
  'SELECT 1;'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx := (
  SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE table_schema = DATABASE()
    AND table_name = 'articulos'
    AND index_name = 'idx_articulos_estado'
);
SET @sql2 := IF(@idx = 0,
  'CREATE INDEX idx_articulos_estado ON articulos (estado);',
  'SELECT 1;'
);
PREPARE stmt2 FROM @sql2; EXECUTE stmt2; DEALLOCATE PREPARE stmt2;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('07-articulos-factor-estacional-estado.sql');
