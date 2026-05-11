USE evalutia;

-- Tabla de ventana móvil de 12 meses pre-calculada por el ETL nocturno.
-- El ETL regenera esta tabla completa cada noche con TRUNCATE + INSERT dentro de una transacción.
CREATE TABLE IF NOT EXISTS planilla_ventas_calculada (
  sku                                VARCHAR(128)      NOT NULL,
  year                               SMALLINT UNSIGNED NOT NULL,
  month                              TINYINT UNSIGNED  NOT NULL,
  ventas_cantidad                    BIGINT UNSIGNED   NOT NULL DEFAULT 0,
  dias_con_stock                     SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  dias_naturales_mes                 TINYINT UNSIGNED  NOT NULL,

  -- ventas_cantidad / NULLIF(dias_con_stock, 0)
  rotacion_diaria_real               DECIMAL(10,4)     NULL,

  -- ventas_cantidad / dias_naturales_mes
  rotacion_diaria_bruta              DECIMAL(10,4)     NULL,

  -- TODO issue #2: poblar cuando factor_estacional esté disponible en articulos.
  -- Cálculo: rotacion_diaria_real / NULLIF(a.factor_estacional, 0)
  -- Requiere: issue #2 (acceso SOAP) → issue #3 (columna en articulos) → issue #5 (ETL extracción).
  rotacion_diaria_desestacionalizada DECIMAL(10,4)     NULL,

  estado_mes                         ENUM('normal','quiebre_parcial','sin_stock') NOT NULL,
  ts_carga                           TIMESTAMP(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

  PRIMARY KEY (sku, year, month),
  CONSTRAINT chk_planilla_month      CHECK (month BETWEEN 1 AND 12),
  CONSTRAINT chk_planilla_dias_nat   CHECK (dias_naturales_mes BETWEEN 28 AND 31),
  CONSTRAINT chk_planilla_dias_stock CHECK (dias_con_stock >= 0),
  CONSTRAINT fk_planilla_articulo    FOREIGN KEY (sku)
    REFERENCES articulos (sku)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- La PK compuesta (sku, year, month) cubre la query principal del backend.
-- Índice secundario para consultas por período (ej: todos los SKUs de un mes dado).
CREATE INDEX idx_planilla_ym ON planilla_ventas_calculada (year, month);
