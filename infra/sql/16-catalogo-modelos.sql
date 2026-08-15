USE evalutia;

-- Issue #84: catalogo historico de estimaciones de modelo (RF/XGB/PROPHET)
-- por SKU, para comparar performance y decidir arquitectura de seleccion
-- de modelos (#87/#88) -- distinto del criterio puntual de elegibilidad
-- econometrica de #70/#73 (articulos_elegibilidad_econometrico).
--
-- Acumula historico (una fila por re-estimacion, sin upsert) -- a
-- diferencia de articulos_elegibilidad_econometrico, que si hace upsert
-- sobre una fila por SKU. Decisiones tomadas en sesion de /grill-me +
-- /code-review 2026-07-15 (ver CONTEXTO.md):
--   - rmse_test agregada (no estaba en el alcance original del issue):
--     #89 aplica el criterio de seleccion via r2_test/rmse_test real.
--   - fecha_estimacion es TIMESTAMP(6), no DATE ni DATETIME: distingue
--     corridas del mismo dia (incluso el mismo segundo) para el analisis
--     de evolucion de performance de #87, mismo patron que evaluado_en/
--     ts_carga en el resto del repo.
--   - version_modelo agregada: mismo concepto que ya usa `predicciones`,
--     para poder filtrar corridas de una version de codigo especifica.
--   - indice compuesto (sku, modelo, fecha_estimacion) sin UNIQUE: cubre
--     historial ordenado y "ultima fila por modelo", pero no es upsert.
--   - n_arboles/profundidad_max son columnas GENERADAS desde el JSON de
--     hiperparametros (no se escriben aparte) -- code review encontro que
--     como columnas propias duplicaban el JSON sin garantia de consistencia;
--     derivarlas via GENERATED ALWAYS AS deja una sola fuente de verdad y
--     de paso quedan NULL para PROPHET automaticamente (su JSON no tiene
--     esas claves).
--   - CHECK fecha_primera_obs <= fecha_ultima_obs y CHECK n_obs_train +
--     n_obs_test <= n_obs_total: code review encontro que el resto del
--     repo si tiene CHECK para invariantes de dominio analogas
--     (chk_pred_cantidad, chk_stockresumen_dias) y esta tabla no tenia
--     ninguna.
--   - FK con ON DELETE RESTRICT, no CASCADE: esta es una tabla de
--     historial acumulativo (a diferencia de articulos_elegibilidad_
--     econometrico, que es upsert de estado actual) -- RESTRICT tiene
--     costo cero si articulos nunca borra de verdad (como asume el
--     diseno original), pero evita perder historial irrecuperable si
--     alguna vez se viola esa premisa.
--   - Sin politica de retencion por ahora -- se revisa una vez que #87 de
--     una idea real de volumen.

CREATE TABLE IF NOT EXISTS catalogo_modelos (
  id                 BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
  sku                VARCHAR(128)     NOT NULL,
  modelo             VARCHAR(64)      NOT NULL,
  version_modelo     VARCHAR(32)      NOT NULL,
  fecha_estimacion   TIMESTAMP(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  freq               VARCHAR(8)       NOT NULL,
  fecha_primera_obs  DATE             NOT NULL,
  fecha_ultima_obs   DATE             NOT NULL,
  n_obs_total        SMALLINT UNSIGNED NOT NULL,
  n_obs_train        SMALLINT UNSIGNED NOT NULL,
  n_obs_test         SMALLINT UNSIGNED NOT NULL,
  r2_train           DOUBLE               NULL,
  r2_test            DOUBLE               NULL,
  rmse_train         DOUBLE               NULL,
  rmse_test          DOUBLE               NULL,
  mae_train          DOUBLE               NULL,
  mae_test           DOUBLE               NULL,
  n_folds            TINYINT UNSIGNED     NULL,
  estable            BOOLEAN              NULL,  -- NULL = no evaluable (<2 folds)
  hiperparametros    JSON                 NULL,
  features           JSON                 NULL,
  n_arboles SMALLINT UNSIGNED
    GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(hiperparametros, '$.n_estimators')) + 0) STORED,  -- NULL para PROPHET (su JSON no tiene n_estimators)
  profundidad_max TINYINT UNSIGNED
    GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(hiperparametros, '$.max_depth')) + 0) STORED,  -- NULL para PROPHET (su JSON no tiene max_depth)
  PRIMARY KEY (id),
  KEY idx_catalogo_sku_modelo_fecha (sku, modelo, fecha_estimacion),
  CONSTRAINT chk_catalogo_fechas_obs CHECK (fecha_primera_obs <= fecha_ultima_obs),
  CONSTRAINT chk_catalogo_n_obs CHECK (n_obs_train + n_obs_test <= n_obs_total),
  CONSTRAINT fk_catalogo_articulo FOREIGN KEY (sku)
    REFERENCES articulos(sku)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('16-catalogo-modelos.sql');
