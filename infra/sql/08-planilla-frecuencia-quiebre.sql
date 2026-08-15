USE evalutia;

-- Issue #27: agrega clasificación de frecuencia de quiebre a planilla_ventas_calculada.
--
-- frecuencia_nivel: nivel del SKU según cuántos meses cerrados tuvo ventas > 0.
--   alta  : >= 9 meses con ventas (quiebre puntual, formula normal)
--   media : 4-8 meses con ventas (promedio de formula normal y formula baja)
--   baja  : <= 3 meses con ventas (demanda real por mes, no dias_con_stock)
--
-- rotacion_ajustada: rotación calculada con la fórmula correspondiente al nivel.
--   Solo se puebla en meses con estado_mes = 'quiebre_parcial'.
--   Meses 'normal' y 'sin_stock' quedan NULL (usan rotacion_diaria_real).

-- Issue #140: ALTER TABLE ADD COLUMN no es idempotente -- mismo chequeo
-- previo via information_schema del resto de infra/sql/.
SET @col := (
  SELECT COUNT(1) FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'planilla_ventas_calculada'
    AND column_name = 'frecuencia_nivel'
);
SET @sql := IF(@col = 0,
  "ALTER TABLE planilla_ventas_calculada
     ADD COLUMN frecuencia_nivel ENUM('alta','media','baja') NULL AFTER estado_mes,
     ADD COLUMN rotacion_ajustada DECIMAL(10,4) NULL AFTER frecuencia_nivel;",
  'SELECT 1;'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('08-planilla-frecuencia-quiebre.sql');
