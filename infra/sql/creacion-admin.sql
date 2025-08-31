USE evalutia;

-- Admin inicial (reemplazar hash por uno real generado con bcrypt/argon2 desde la WebAPI)
INSERT INTO usuarios (correo, hash_password, rol)
VALUES ('admin@evalutia.local', '$2b$12$REEMPLAZAR_CON_HASH_BCRYPT', 'administrador');

/* Ejemplos de datos mínimos (opcional)
INSERT INTO ventas_historicas (fecha, sku, cantidad, fuente)
VALUES 
  ('2025-06-01', 'SKU-001', 12, 'demo'),
  ('2025-06-02', 'SKU-001', 10, 'demo'),
  ('2025-06-02', 'SKU-002',  8, 'demo');

INSERT INTO jobs_historial (tipo_job, estado, detalle)
VALUES ('forecast', 'exitoso', JSON_OBJECT('run_id','demo-1','skus_procesados',2));
*/
