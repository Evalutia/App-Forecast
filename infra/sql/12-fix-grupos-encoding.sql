USE evalutia;

-- Issue #56: 4 filas de grupos.descripcion quedaron con UTF-8 doblemente
-- codificado (mojibake). Confirmado que el archivo fuente (10-grupos.sql)
-- ya tenia el texto correctamente codificado en UTF-8 -- la corrupcion
-- ocurrio al aplicar el seed con un cliente mysql cuyo charset de sesion
-- por defecto es latin1 (character_set_client/connection/results), aunque
-- la base sea utf8mb4. SET NAMES fuerza el charset de la sesion para que
-- este mismo fix no repita el problema que esta corrigiendo.
SET NAMES utf8mb4;

UPDATE grupos SET descripcion = 'KIT SISTEMA CONTÍNUO' WHERE id = 28;
UPDATE grupos SET descripcion = 'PERIFÉRICOS' WHERE id = 50;
UPDATE grupos SET descripcion = 'AURICULAR INALÁMBRICO' WHERE id = 67;
UPDATE grupos SET descripcion = 'Modelo Econométrico' WHERE id = 201;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('12-fix-grupos-encoding.sql');
