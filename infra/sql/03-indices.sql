USE evalutia;

-- Issue #140: CREATE INDEX plano no es idempotente en MySQL -- a diferencia
-- de Postgres/MariaDB, MySQL 8 no soporta "CREATE INDEX ... IF NOT EXISTS"
-- ni "ALTER TABLE ... ADD INDEX IF NOT EXISTS" (verificado contra la version
-- real, 8.0.45: las dos formas tiran ERROR 1064, error de sintaxis). Cada
-- indice se guarda contra information_schema.STATISTICS antes de crearse,
-- mismo patron de SQL dinamico que ya usa infra/sql/20-stock-diario-deposito-not-null.sql.
-- Encontrado corriendo este archivo por segunda vez con
-- services/etl/apply_migrations.sh (issue #140): "ERROR 1061 Duplicate key name".

DELIMITER $$
DROP PROCEDURE IF EXISTS _crear_indice_si_falta $$
CREATE PROCEDURE _crear_indice_si_falta(
  IN p_tabla VARCHAR(64),
  IN p_indice VARCHAR(64),
  IN p_definicion_columnas VARCHAR(255)
)
BEGIN
  DECLARE v_existe INT;
  SELECT COUNT(*) INTO v_existe
    FROM information_schema.STATISTICS
   WHERE table_schema = DATABASE()
     AND table_name = p_tabla
     AND index_name = p_indice;
  IF v_existe = 0 THEN
    SET @sql := CONCAT('CREATE INDEX ', p_indice, ' ON ', p_tabla, ' ', p_definicion_columnas);
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
  END IF;
END $$
DELIMITER ;

CALL _crear_indice_si_falta('ventas_historicas', 'idx_ventas_sku_fecha', '(sku, fecha)');
CALL _crear_indice_si_falta('ventas_historicas', 'idx_ventas_fecha', '(fecha)');

CALL _crear_indice_si_falta('predicciones', 'idx_pred_sku_fecha', '(sku, fecha_predicha)');
CALL _crear_indice_si_falta('predicciones', 'idx_pred_sku_fecha_ts', '(sku, fecha_predicha, ts_generacion)');

CALL _crear_indice_si_falta('predicciones', 'idx_pred_modelo_version', '(modelo, version_modelo)');
CALL _crear_indice_si_falta('predicciones', 'idx_pred_sku_modelo_version', '(sku, modelo, version_modelo)');

CALL _crear_indice_si_falta('jobs_historial', 'idx_jobs_tipo_inicio', '(tipo_job, fecha_inicio)');
CALL _crear_indice_si_falta('jobs_historial', 'idx_jobs_estado_inicio', '(estado, fecha_inicio)');

CALL _crear_indice_si_falta('articulos', 'idx_articulos_family', '(familia_id)');
CALL _crear_indice_si_falta('articulos', 'idx_articulos_genre', '(genero_id)');
CALL _crear_indice_si_falta('articulos', 'idx_articulos_barcode', '(barcode)');

CALL _crear_indice_si_falta('stock_diario', 'idx_stock_sku_fecha', '(sku, fecha)');
CALL _crear_indice_si_falta('stock_diario', 'idx_stock_fecha', '(fecha)');
CALL _crear_indice_si_falta('stock_diario', 'idx_stock_sku_fecha_deposito', '(sku, fecha, deposito_id)');

CALL _crear_indice_si_falta('ventas_mensuales', 'idx_ventasmens_sku_ym', '(sku, year, month)');
CALL _crear_indice_si_falta('ventas_mensuales', 'idx_ventasmens_year_month', '(year, month)');

CALL _crear_indice_si_falta('ventas_historicas', 'idx_ventas_historicas_sku_ts', '(sku, ts_carga)');
CALL _crear_indice_si_falta('articulos', 'idx_articulos_ts_carga', '(ts_carga)');

DROP PROCEDURE IF EXISTS _crear_indice_si_falta;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('03-indices.sql');
