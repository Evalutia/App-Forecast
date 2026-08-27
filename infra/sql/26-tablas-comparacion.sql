-- Issue #186: almacen de comparacion aislado para re-extraer ventas/stock
-- con el codigo actual sin tocar produccion (ventas_historicas/stock_diario).
-- Mismo esquema exacto que las tablas de produccion que espejan -- asi
-- run_backfill_ventas.sh puede escribir en cualquiera de los dos juegos sin
-- ninguna diferencia de tipo/indice/constraint que distorsione la
-- comparacion (la diferencia tiene que ser de datos, no de estructura).
--
-- Nota para quien retome esto (encontrado por /code-review post-implement,
-- verificado y descartado): los tipos de abajo NO salen de leer
-- 02-tablas.sql/04-etl-staging.sql/14-ventas-cantidad-signed.sql de forma
-- aislada -- eso lleva a conclusiones erroneas (ej. "stock deberia ser INT"
-- por el ALTER legacy de 04-etl-staging.sql:39, que nunca se aplica porque
-- 02-tablas.sql ya crea la columna como DECIMAL(18,4); o "falta un CHECK en
-- cantidad" por el chk_ventas_cantidad de 02-tablas.sql:50, que
-- 14-ventas-cantidad-signed.sql dropea). Salen de `SHOW CREATE TABLE` contra
-- la DB real (unico lugar donde se ve el efecto acumulado de todas las
-- migraciones aplicadas) -- si el esquema de produccion cambia, re-consultar
-- ahi, no releer los .sql de a uno.
--
-- Temporal por diseño (#186, criterio de aceptacion): existen para el ciclo
-- del diagnostico de #186/#187/#188, no indefinidamente. Se dropean a mano
-- cuando #188 (el informe final) cierra:
--   DROP TABLE IF EXISTS stock_diario_comparacion;
--   DROP TABLE IF EXISTS ventas_historicas_comparacion;
--   DROP TABLE IF EXISTS ventas_historicas_stage_comparacion;
-- (stock antes que ventas: sin FK entre ellas, pero mantiene el mismo orden
-- que usa un DROP de las tablas reales si alguna vez hiciera falta).

CREATE TABLE IF NOT EXISTS ventas_historicas_stage_comparacion (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `fecha` date NOT NULL,
  `sku` varchar(128) NOT NULL,
  `cantidad` int NOT NULL,
  `stock` decimal(18,4) DEFAULT NULL,
  `deposito_id` varchar(64) NOT NULL DEFAULT '',
  `grupo_id` int unsigned DEFAULT NULL,
  `fuente` varchar(64) DEFAULT NULL,
  `ts_carga` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ventas_stage_comp_fecha_sku_deposito` (`fecha`,`sku`,`deposito_id`),
  KEY `idx_vhs_comp_sku_fecha` (`sku`,`fecha`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS ventas_historicas_comparacion (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `fecha` date NOT NULL,
  `sku` varchar(128) NOT NULL,
  `cantidad` int NOT NULL,
  `ts_carga` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `fuente` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ventas_comp_fecha_sku_fuente` (`fecha`,`sku`,`fuente`),
  KEY `idx_ventas_comp_sku_fecha` (`sku`,`fecha`),
  KEY `idx_ventas_comp_fecha` (`fecha`),
  CONSTRAINT `fk_ventas_comp_articulo` FOREIGN KEY (`sku`) REFERENCES `articulos` (`sku`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS stock_diario_comparacion (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `sku` varchar(128) NOT NULL,
  `fecha` date NOT NULL,
  `cantidad` int unsigned NOT NULL DEFAULT '0',
  `deposito_id` varchar(64) NOT NULL DEFAULT '',
  `fuente` varchar(64) DEFAULT NULL,
  `ts_carga` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_stock_comp_sku_fecha_deposito` (`sku`,`fecha`,`deposito_id`),
  KEY `idx_stock_comp_sku_fecha` (`sku`,`fecha`),
  KEY `idx_stock_comp_fecha` (`fecha`),
  CONSTRAINT `chk_stock_comp_cantidad` CHECK ((`cantidad` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('26-tablas-comparacion.sql');
