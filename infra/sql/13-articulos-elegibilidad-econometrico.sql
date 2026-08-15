USE evalutia;

-- Issue #71: migra la elegibilidad de modelo econometrico de nivel-grupo
-- (grupos.aplica_modelo_econometrico) a nivel-SKU individual, con las
-- metricas de r2_test/estabilidad del walk-forward (criterio cerrado en #70).
--
-- Tabla nueva y separada de articulos: estos campos son resultado del
-- pipeline de ML (recalculados por #72/#73), no datos del ERP -- se evita
-- que el upsert masivo de run_extract_articulos.py tenga que excluirlos
-- a mano.
--
-- grupos.aplica_modelo_econometrico NO se elimina (columna muerta, sin
-- DROP) -- rollback trivial si algo falla, sin restaurar backup. Limpieza
-- como issue de deuda tecnica aparte, una vez #72/#73 esten validados.

CREATE TABLE IF NOT EXISTS articulos_elegibilidad_econometrico (
  sku              VARCHAR(128)      NOT NULL,
  elegible         BOOLEAN           NOT NULL DEFAULT FALSE,
  r2_test          DOUBLE                NULL,
  estable          BOOLEAN               NULL,  -- NULL = no evaluable (<2 folds)
  n_folds          TINYINT UNSIGNED      NULL,
  meses_historia   SMALLINT UNSIGNED     NULL,
  evaluado_en      TIMESTAMP(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (sku),
  KEY idx_elegibilidad_elegible (elegible),
  CONSTRAINT fk_elegibilidad_articulo FOREIGN KEY (sku)
    REFERENCES articulos(sku)
    ON UPDATE CASCADE
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Seed de continuidad: los SKUs que hoy ya reciben modelo econometrico via
-- grupos.aplica_modelo_econometrico quedan marcados elegible=TRUE, sin
-- metricas todavia (las calculan #72/#73). Cero cambio de comportamiento
-- real para get_skus_modelo.py hasta que esas metricas se recalculen.
-- INSERT IGNORE: re-ejecutar este script no falla por PK duplicada.
INSERT IGNORE INTO articulos_elegibilidad_econometrico (sku, elegible)
SELECT a.sku, TRUE
FROM articulos a
JOIN grupos g ON g.id = a.grupo_id
WHERE g.aplica_modelo_econometrico = TRUE;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('13-articulos-elegibilidad-econometrico.sql');
