USE evalutia;

-- Issue #24: ampliar ENUM estado para incluir 'discontinuo'.
-- El campo <Inactivo> del SOAP es ahora la fuente de verdad:
--   0 -> activo, 1 -> inactivo, 2 -> discontinuo

ALTER TABLE articulos
  MODIFY COLUMN estado ENUM('activo','inactivo','discontinuo') NOT NULL DEFAULT 'activo';
