USE evalutia;

-- Issue #3: agrega factor_estacional y estado a articulos.
--
-- factor_estacional: coeficiente del mes actual (escalar), recalculado cada noche
-- por el ETL (issue #5) tomando el MesXX correspondiente desde el SOAP (issue #2).
-- Usado por planilla: rotacion_diaria_real / NULLIF(a.factor_estacional, 0) (ver 05-planilla.sql).
--
-- estado: el SOAP no expone un campo Estado. Se deriva de la presencia del SKU
-- en el feed nocturno (lo calcula el ETL): si el SKU deja de aparecer -> inactivo,
-- si reaparece -> activo. Es puramente informativo: no debe usarse para ocultar
-- articulos por default en ninguna vista (planilla, predicciones, listados).

ALTER TABLE articulos
  ADD COLUMN factor_estacional DECIMAL(5,3) NULL AFTER stock_minimo,
  ADD COLUMN estado ENUM('activo','inactivo') NOT NULL DEFAULT 'activo' AFTER factor_estacional;

CREATE INDEX idx_articulos_estado ON articulos (estado);
