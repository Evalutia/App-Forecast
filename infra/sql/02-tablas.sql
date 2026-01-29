USE evalutia;

CREATE TABLE IF NOT EXISTS usuarios (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  correo         VARCHAR(254)    NOT NULL,
  hash_password  VARCHAR(255)    NOT NULL,
  rol            ENUM('administrador','duenoDeEmpresa') NOT NULL,
  creado_en      TIMESTAMP(6)    NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  actualizado_en TIMESTAMP(6)             NULL ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_usuarios_correo (correo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS articulos (
  sku                       VARCHAR(120)    NOT NULL,
  barcode                   VARCHAR(64)             NULL,
  descripcion               VARCHAR(512)           NULL,
  familia_id                INT UNSIGNED           NULL,
  familia_nombre            VARCHAR(255)           NULL,
  genero_id                 INT UNSIGNED           NULL,
  genero_descripcion        VARCHAR(255)           NULL,
  stock_minimo              INT UNSIGNED    NOT NULL DEFAULT 0,
  frecuencia_mensual        TINYINT UNSIGNED       NULL,
  fuente                    VARCHAR(64)            NULL,
  ts_carga                  TIMESTAMP(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  actualizado_en            TIMESTAMP(6)           NULL ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS ventas_historicas (
  id        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  fecha     DATE            NOT NULL,
  sku       VARCHAR(120)    NOT NULL,
  cantidad  INT UNSIGNED    NOT NULL,
  ts_carga  TIMESTAMP(6)    NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  fuente    VARCHAR(64)              NULL,
  barcode                 VARCHAR(64)            NULL,
  descripcion_articulo    VARCHAR(512)           NULL,
  familia_id              INT UNSIGNED           NULL,
  familia_nombre          VARCHAR(255)           NULL,
  genero_id               INT UNSIGNED           NULL,
  genero_descripcion      VARCHAR(255)           NULL,
  stock_minimo            INT UNSIGNED    NOT NULL DEFAULT 0,
  frecuencia_mensual      TINYINT UNSIGNED       NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_ventas_fecha_sku_fuente (fecha, sku, fuente),
  CONSTRAINT chk_ventas_cantidad CHECK (cantidad >= 0),
  CONSTRAINT fk_ventas_articulo FOREIGN KEY (sku)
    REFERENCES articulos(sku)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS jobs_historial (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  tipo_job     ENUM('etl','forecast','backfill','export') NOT NULL,
  estado       ENUM('en_cola','ejecutando','exitoso','fallido') NOT NULL,
  fecha_inicio TIMESTAMP(6)    NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  fecha_fin    TIMESTAMP(6)             NULL,
  detalle      JSON                     NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS predicciones (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  sku                VARCHAR(120)    NOT NULL,
  fecha_predicha     DATE            NOT NULL,
  cantidad_predicha  DECIMAL(18,2)   NOT NULL,
  modelo             VARCHAR(64)     NOT NULL,
  version_modelo     VARCHAR(32)     NOT NULL,
  horizonte          TINYINT UNSIGNED NOT NULL,
  rmse               DOUBLE            NULL,
  r2                 DOUBLE            NULL,
  ts_generacion      DATE    NOT NULL,
  job_id             BIGINT UNSIGNED NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_pred_sku_modelo_version_horiz (sku, modelo, version_modelo, horizonte),
  CONSTRAINT chk_pred_cantidad CHECK (cantidad_predicha >= 0),
  CONSTRAINT chk_pred_horizonte CHECK (horizonte BETWEEN 1 AND 36),
  CONSTRAINT fk_pred_job FOREIGN KEY (job_id)
    REFERENCES jobs_historial(id)
    ON DELETE SET NULL
    ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS stock_diario (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  sku            VARCHAR(120)    NOT NULL,
  fecha          DATE            NOT NULL,
  cantidad       INT UNSIGNED    NOT NULL DEFAULT 0,
  deposito_id    VARCHAR(64)             NULL,
  fuente         VARCHAR(64)            NULL,
  ts_carga       TIMESTAMP(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_stock_sku_fecha_deposito (sku, fecha, deposito_id),
  CONSTRAINT chk_stock_cantidad CHECK (cantidad >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS ventas_mensuales (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  sku              VARCHAR(120)    NOT NULL,
  year             SMALLINT UNSIGNED NOT NULL,
  month            TINYINT UNSIGNED NOT NULL,
  ventas_cantidad  BIGINT UNSIGNED NOT NULL DEFAULT 0,
  dias_con_stock   SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  fuente           ENUM('ws','calculado') NOT NULL DEFAULT 'calculado',
  ts_carga         TIMESTAMP(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  actualizado_en   TIMESTAMP(6)           NULL ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_ventasmens_sku_ym (sku, year, month),
  CONSTRAINT chk_ventasmens_month CHECK (month BETWEEN 1 AND 12),
  CONSTRAINT chk_ventasmens_dias CHECK (dias_con_stock >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE OR REPLACE VIEW resumen_producto_365 AS
SELECT
  vh.sku,
  COALESCE(SUM(vh.cantidad), 0) AS ventas_365,
  COALESCE(MAX(vm.dias_con_stock_365), 0) AS dias_con_stock_365,
  CASE
    WHEN COALESCE(MAX(vm.dias_con_stock_365), 0) = 0 THEN NULL
    ELSE ROUND(SUM(vh.cantidad) / MAX(vm.dias_con_stock_365), 4)
  END AS ventas_por_dia_stock_365
FROM ventas_historicas vh
LEFT JOIN (
  SELECT
    sku,
    SUM(dias_con_stock) AS dias_con_stock_365
  FROM ventas_mensuales
  WHERE DATE(CONCAT(year,'-',LPAD(month,2,'0'),'-01')) >= DATE_SUB(CURDATE(), INTERVAL 365 DAY)
  GROUP BY sku
) vm ON vm.sku = vh.sku
WHERE vh.fecha >= DATE_SUB(CURDATE(), INTERVAL 365 DAY)
GROUP BY vh.sku;