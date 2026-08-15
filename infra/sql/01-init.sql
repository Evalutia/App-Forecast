-- Crea la base si no existe (aunque MYSQL_DATABASE ya la crea igual)
CREATE DATABASE IF NOT EXISTS evalutia;

-- Asegura que el usuario exista para cualquier host
CREATE USER IF NOT EXISTS 'evalutia'@'%' IDENTIFIED BY 'evalutia';

-- Da todos los permisos en la base
GRANT ALL PRIVILEGES ON evalutia.* TO 'evalutia'@'%';

FLUSH PRIVILEGES;

USE evalutia;

-- Issue #140: registro de que migraciones de infra/sql/ se aplicaron y
-- cuando. Se crea aca (archivo 01, primero en orden lexicografico) porque
-- tiene que existir ANTES de que cualquier otro archivo intente
-- auto-registrarse al final -- tanto en un volumen nuevo (docker-entrypoint-
-- initdb.d corre estos archivos en orden, sin ningun wrapper de por medio)
-- como via services/etl/apply_migrations.sh contra un entorno existente
-- (que ademas crea esta tabla defensivamente por su cuenta, por si este
-- archivo 01 nunca llego a correr con esta version en un entorno viejo).
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename   VARCHAR(255) NOT NULL,
  applied_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (filename)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO schema_migrations (filename) VALUES ('01-init.sql');
