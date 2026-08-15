USE evalutia;

-- Issue #137: "V/E" (venta real del mes, o su extrapolacion si hubo
-- quiebre) se recalculaba en el browser reimplementando en TypeScript la
-- formula de extrapolacion_mes() -- mientras VAj, en la columna de al lado,
-- se lee persistida. Las dos solo coincidian si el ETL habia vuelto a
-- correr despues del ultimo cambio de formula (#129 dejo una ventana real
-- de una hora en produccion con el mismo articulo mostrando VAj=465,00 y
-- V/E=29,52 en la misma fila).
--
-- El ETL ya calculaba este valor como paso intermedio antes de mezclarlo en
-- VAj (ver run_calc_planilla.py, valor_ajustado_y_criterio) -- solo faltaba
-- guardarlo bajo su propia columna. Con los dos escritos por la misma
-- funcion en la misma corrida, la desincronizacion queda estructuralmente
-- imposible, no solo detectada.
SET @col := (
  SELECT COUNT(1) FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'planilla_ventas_calculada'
    AND column_name = 'venta_o_extrapolacion'
);
SET @sql := IF(@col = 0,
  'ALTER TABLE planilla_ventas_calculada
     ADD COLUMN venta_o_extrapolacion DECIMAL(10,2) NULL AFTER criterio_frecuencia;',
  'SELECT 1;'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('23-planilla-venta-o-extrapolacion.sql');
