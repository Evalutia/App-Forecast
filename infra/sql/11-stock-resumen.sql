USE evalutia;

-- Issue #59/#60: resumen precalculado por SKU sobre los últimos 365 días de
-- stock_diario, regenerado completo por el ETL nocturno (DELETE + INSERT en una
-- transacción, mismo patrón que planilla_ventas_calculada).
--
-- Reemplaza la agregación en vivo de stock_diario (25M+ filas) que hacían
-- GetResumenGlobal/GetStockAnalysis/GetTopVentasPerdidas/GetStockoutDistribution
-- en ResultadosService.cs — con la VM de producción sin RAM suficiente (issue #60)
-- esa agregación tardaba minutos por request HTTP. El costo se paga una sola vez
-- por noche en vez de en cada request.
--
-- Guarda solo conteos crudos, no tasas/categorías derivadas: las 4 funciones
-- consumidoras usan fórmulas y umbrales distintos entre sí sobre estos mismos
-- números (ver sesión /grill-me de #60, 2026-07-10) — cada una sigue aplicando
-- su propia fórmula, solo cambia el origen de los datos crudos.
--
-- Cubre TODOS los SKUs de articulos, no solo stock_minimo > 0: GetStockAnalysis()
-- no filtra por ese umbral, a diferencia de las otras 3 funciones.
CREATE TABLE IF NOT EXISTS stock_resumen_365 (
  sku             VARCHAR(128)      NOT NULL,
  dias_con_stock  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  dias_sin_stock  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  total_dias      SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  ventas_365      BIGINT UNSIGNED   NOT NULL DEFAULT 0,
  ts_carga        TIMESTAMP(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

  PRIMARY KEY (sku),
  CONSTRAINT chk_stockresumen_dias CHECK (dias_con_stock + dias_sin_stock = total_dias),
  CONSTRAINT fk_stockresumen_articulo FOREIGN KEY (sku)
    REFERENCES articulos (sku)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('11-stock-resumen.sql');
