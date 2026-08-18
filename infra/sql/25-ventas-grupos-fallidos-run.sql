-- Issue #157: registro efimero de que grupos de ConsStockVenta fallaron en
-- la extraccion de ventas de ESTA corrida, para que el paso "MERGE STAGING
-- -> VENTAS" de job_etl_diario.kjb pueda excluir solo esos grupos en vez de
-- saltear el merge entero (antes de este ticket, un solo grupo fallido
-- congelaba los ~66 -- ver .claude/CONTEXTO.md, seccion #157).
--
-- Efimero por diseño, igual que ventas_historicas_stage: se vacia al
-- arrancar cada corrida (run_extract_sales_chunk.sh, no un paso propio del
-- .kjb -- ver grupos_fallidos_run.py). No es un historico de fallos, es el
-- estado de "esta noche" nada mas.
CREATE TABLE IF NOT EXISTS ventas_grupos_fallidos_run (
  grupo_id INT NOT NULL,
  PRIMARY KEY (grupo_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('25-ventas-grupos-fallidos-run.sql');
