USE evalutia;

CREATE INDEX idx_ventas_sku_fecha ON ventas_historicas (sku, fecha);
CREATE INDEX idx_ventas_fecha      ON ventas_historicas (fecha);

CREATE INDEX idx_pred_sku_fecha           ON predicciones (sku, fecha_predicha);
CREATE INDEX idx_pred_sku_fecha_ts        ON predicciones (sku, fecha_predicha, ts_generacion);

CREATE INDEX idx_pred_modelo_version      ON predicciones (modelo, version_modelo);
CREATE INDEX idx_pred_sku_modelo_version  ON predicciones (sku, modelo, version_modelo);

CREATE INDEX idx_jobs_tipo_inicio   ON jobs_historial (tipo_job, fecha_inicio);
CREATE INDEX idx_jobs_estado_inicio ON jobs_historial (estado,   fecha_inicio);

CREATE INDEX idx_articulos_family ON articulos (familia_id);
CREATE INDEX idx_articulos_genre  ON articulos (genero_id);
CREATE INDEX idx_articulos_barcode ON articulos (barcode);

CREATE INDEX idx_stock_sku_fecha ON stock_diario (sku, fecha);
CREATE INDEX idx_stock_fecha     ON stock_diario (fecha);
CREATE INDEX idx_stock_sku_fecha_deposito ON stock_diario (sku, fecha, deposito_id);

CREATE INDEX idx_ventasmens_sku_ym ON ventas_mensuales (sku, year, month);
CREATE INDEX idx_ventasmens_year_month ON ventas_mensuales (year, month);

CREATE INDEX idx_ventas_historicas_sku_ts ON ventas_historicas (sku, ts_carga);
CREATE INDEX idx_articulos_ts_carga ON articulos (ts_carga);
