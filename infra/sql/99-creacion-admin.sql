USE evalutia;

-- Issue #140: a diferencia del resto de infra/sql/, este archivo no era
-- idempotente (INSERT simple sin IGNORE/ON DUPLICATE) -- correrlo dos veces
-- rompia con "Duplicate entry" contra uq_usuarios_correo. INSERT IGNORE lo
-- deja seguro de re-correr, requisito para que el bootstrap uniforme de
-- apply_migrations.sh (correr cualquier archivo pendiente sin casos
-- especiales) sea seguro tambien para este archivo.
INSERT IGNORE INTO usuarios (correo, hash_password, rol)
VALUES ('admin@evalutia.com', '$2b$11$6WJXyYf7x0p00/Z2ituT6uXArHM83W1G7ojDUon4/b.Ma.URWyxAi', 'administrador');

INSERT IGNORE INTO usuarios (correo, hash_password, rol)
VALUES ('rodrigo@ecologictech.com.uy', '$2b$11$F99tqmuD3GmMSI77FBGIWOH54Db79CWSwrbDc2SykvWyd4manzs3K', 'duenoDeEmpresa');

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('99-creacion-admin.sql');
