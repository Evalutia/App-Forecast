-- Crea la base si no existe (aunque MYSQL_DATABASE ya la crea igual)
CREATE DATABASE IF NOT EXISTS evalutia;

-- Asegura que el usuario exista para cualquier host
CREATE USER IF NOT EXISTS 'evalutia'@'%' IDENTIFIED BY 'evalutia';

-- Da todos los permisos en la base
GRANT ALL PRIVILEGES ON evalutia.* TO 'evalutia'@'%';

FLUSH PRIVILEGES;
