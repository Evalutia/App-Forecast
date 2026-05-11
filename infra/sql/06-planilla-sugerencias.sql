USE evalutia;

-- Tabla de sugerencias ML por SKU. Una fila por SKU.
-- El ML worker hace INSERT ... ON DUPLICATE KEY UPDATE: SKUs nuevos se agregan,
-- existentes se actualizan, y los que fallen en un ciclo conservan su valor anterior.
CREATE TABLE IF NOT EXISTS planilla_sugerencias (
  sku                    VARCHAR(128)   NOT NULL,
  rotacion_sugerida      DECIMAL(10,4)          NULL,
  fiabilidad_porcentaje  DECIMAL(5,2)           NULL,  -- 0.00 a 100.00
  modelo                 VARCHAR(64)            NULL,
  -- TODO issue #17: poblar cuando el modelo de prediccion de quiebre este listo.
  -- Calculo: stock_actual / NULLIF(rotacion_sugerida, 0)
  dias_hasta_quiebre     DECIMAL(10,2)          NULL,
  ts_generacion          TIMESTAMP(6)           NULL,
  ts_carga               TIMESTAMP(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  actualizado_en         TIMESTAMP(6)           NULL ON UPDATE CURRENT_TIMESTAMP(6),

  PRIMARY KEY (sku),
  CONSTRAINT chk_sugerencias_fiabilidad CHECK (fiabilidad_porcentaje BETWEEN 0 AND 100),
  CONSTRAINT chk_sugerencias_rotacion   CHECK (rotacion_sugerida >= 0),
  CONSTRAINT chk_sugerencias_dias       CHECK (dias_hasta_quiebre >= 0),
  CONSTRAINT fk_sugerencias_articulo    FOREIGN KEY (sku)
    REFERENCES articulos (sku)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
