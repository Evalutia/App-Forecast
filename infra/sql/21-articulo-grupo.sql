USE evalutia;

-- Issue #121: un articulo puede pertenecer a varios grupos comerciales del
-- ERP del cliente. Antes solo se guardaba el ultimo grupo que lo devolvia el
-- ETL (el de mayor id, por el orden de recorrido "de menor a mayor"), lo que
-- enterraba articulos que si venden bajo un catch-all (grupo 200, invisible
-- en el desplegable de filtros) -- 2.671 articulos en produccion (47,7% del
-- catalogo), el 100% de ellos con venta en los ultimos 12 meses. Ver
-- .claude/CONTEXTO.md y el comentario de diseño en el issue #121.
--
-- articulo_grupo guarda TODAS las membresias reales, reconstruidas por
-- completo en cada corrida del ETL (delete-and-reinsert). articulos.grupo_id
-- se conserva y pasa a significar "grupo principal" -- el de menor id entre
-- los grupos visible_planilla=true de esa membresia -- para no romper los
-- consumidores que hoy asumen un solo grupo por articulo (badge de la
-- planilla, exports). El filtro de la planilla pasa a consultar esta tabla.

CREATE TABLE IF NOT EXISTS articulo_grupo (
  sku       VARCHAR(128)  NOT NULL,
  grupo_id  INT UNSIGNED  NOT NULL,
  PRIMARY KEY (sku, grupo_id),
  CONSTRAINT fk_articulo_grupo_articulo FOREIGN KEY (sku)
    REFERENCES articulos(sku)
    ON UPDATE CASCADE
    ON DELETE RESTRICT,
  CONSTRAINT fk_articulo_grupo_grupo FOREIGN KEY (grupo_id)
    REFERENCES grupos(id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Issue #140: guardado via information_schema -- CREATE INDEX no es idempotente.
SET @idx := (
  SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE table_schema = DATABASE()
    AND table_name = 'articulo_grupo'
    AND index_name = 'idx_articulo_grupo_grupo_id'
);
SET @sql := IF(@idx = 0,
  'CREATE INDEX idx_articulo_grupo_grupo_id ON articulo_grupo (grupo_id);',
  'SELECT 1;'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Staging del crawl en curso (mismo patron que ventas_historicas_stage,
-- issue #42/#114): cada grupo del loop de run_extract_articulos.sh vuelca
-- aca sus pares (sku, grupo_id) a medida que va terminando. Se trunca al
-- empezar cada corrida y se vuelca a articulo_grupo (delete-and-reinsert)
-- solo si TODOS los grupos de la corrida respondieron sin error -- si
-- alguno fallo, queda con datos parciales para diagnostico y la corrida NO
-- toca articulo_grupo esa noche.
CREATE TABLE IF NOT EXISTS articulo_grupo_stage (
  sku       VARCHAR(128)  NOT NULL,
  grupo_id  INT UNSIGNED  NOT NULL,
  PRIMARY KEY (sku, grupo_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Seed inicial desde el grupo_id ("principal") que cada articulo ya tenia:
-- sin esto, articulo_grupo nace vacia y el filtro/desplegable de grupo de la
-- planilla (que a partir de este issue consultan SOLO esta tabla, sin caer
-- de vuelta a articulos.grupo_id) devolverian cero resultados hasta la
-- primera corrida completa del ETL con el codigo nuevo. Mismo criterio que
-- 10-grupos.sql/11-stock-resumen.sql: nunca dejar una tabla nueva vacia si
-- hay de donde derivar un valor inicial.
--
-- OJO -- este seed es solo la membresia que ya se conocia (una por
-- articulo), NO la multiple real que este issue existe para descubrir. Y a
-- diferencia de lo que decia una version anterior de este comentario, el
-- primer ETL run NO la completa solo: es_grupo_nuevo() en
-- run_extract_articulos.sh mira si el grupo YA tiene filas en
-- articulo_grupo -- como este seed le puso filas a practicamente todos los
-- grupos existentes, esos grupos van a verse "conocidos" y usar la ventana
-- incremental de 7 dias para siempre, sin volver a traer nunca el catalogo
-- completo. Hace falta UNA corrida manual con FORCE_FULL_PULL=1 (ver
-- run_extract_articulos.sh) despues de este deploy para que la membresia
-- multiple real se descubra -- no pasa sola.
INSERT IGNORE INTO articulo_grupo (sku, grupo_id)
  SELECT sku, grupo_id FROM articulos;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('21-articulo-grupo.sql');
