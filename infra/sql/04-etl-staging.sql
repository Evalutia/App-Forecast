-- 1) Crear tabla STAGING clonando ventas_historicas
CREATE TABLE IF NOT EXISTS ventas_historicas_stage LIKE ventas_historicas;

-- 1.1) Remover la UNIQUE de staging si vino copiada por LIKE
SET @idx := (
  SELECT COUNT(1) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'ventas_historicas_stage'
    AND index_name = 'uq_ventas_fecha_sku_fuente'
);
SET @sql := IF(@idx > 0,
  'DROP INDEX uq_ventas_fecha_sku_fuente ON ventas_historicas_stage;',
  'SELECT 1;'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 2) Asegurar UNIQUE en predicciones para upsert por versión de modelo
SET @idx2 := (
  SELECT COUNT(1) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'predicciones'
    AND index_name = 'uq_pred_modelo_version_fecha'
);
SET @sql2 := IF(@idx2 = 0,
  'ALTER TABLE predicciones
     ADD UNIQUE KEY uq_pred_modelo_version_fecha (sku, modelo, version_modelo, fecha_predicha);',
  'SELECT 1;'
);
PREPARE stmt2 FROM @sql2; EXECUTE stmt2; DEALLOCATE PREPARE stmt2;
