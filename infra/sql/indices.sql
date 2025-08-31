USE evalutia;

-- Consultas típicas por SKU + rango de fechas
CREATE INDEX idx_ventas_sku_fecha ON ventas_historicas (sku, fecha);
CREATE INDEX idx_ventas_fecha      ON ventas_historicas (fecha);

-- Predicciones: buscar la última predicción por SKU/fecha
CREATE INDEX idx_pred_sku_fecha           ON predicciones (sku, fecha_predicha);
CREATE INDEX idx_pred_sku_fecha_ts        ON predicciones (sku, fecha_predicha, ts_generacion);
-- Filtrar por modelo/version (dashboards comparativos)
CREATE INDEX idx_pred_modelo_version      ON predicciones (modelo, version_modelo);
CREATE INDEX idx_pred_sku_modelo_version  ON predicciones (sku, modelo, version_modelo);

-- Jobs: listados por tipo / estado recientes
CREATE INDEX idx_jobs_tipo_inicio   ON jobs_historial (tipo_job, fecha_inicio);
CREATE INDEX idx_jobs_estado_inicio ON jobs_historial (estado,   fecha_inicio);
