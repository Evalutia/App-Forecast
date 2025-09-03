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

CREATE TABLE IF NOT EXISTS ventas_historicas (
  id        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  fecha     DATE            NOT NULL,
  sku       VARCHAR(120)    NOT NULL,
  cantidad  INT UNSIGNED    NOT NULL,
  ts_carga  TIMESTAMP(6)    NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  fuente    VARCHAR(64)              NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_ventas_fecha_sku_fuente (fecha, sku, fuente),
  CONSTRAINT chk_ventas_cantidad CHECK (cantidad >= 0)
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
  PRIMARY KEY (id),
  CONSTRAINT chk_pred_cantidad CHECK (cantidad_predicha >= 0),
  CONSTRAINT chk_pred_horizonte CHECK (horizonte BETWEEN 1 AND 36)
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

ALTER TABLE predicciones
  ADD COLUMN job_id BIGINT UNSIGNED NULL,
  ADD CONSTRAINT fk_pred_job
    FOREIGN KEY (job_id) REFERENCES jobs_historial(id)
    ON DELETE SET NULL ON UPDATE RESTRICT;
