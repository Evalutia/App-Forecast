USE evalutia;

-- Issue #67: tabla generica clave-valor para parametros de negocio editables
-- por el administrador sin pasar por el equipo de desarrollo. Arranca con
-- los 2 umbrales de tickets (#61/#63) -- ESTADO_UMBRAL_NORMAL y
-- FREQ_ALTA_MIN/FREQ_BAJA_MAX quedan como constantes Python por ahora,
-- nadie los pidio todavia, pero la tabla los banca sin migrar de nuevo.
--
-- actualizado_por (FK a usuarios) ademas de actualizado_en: es un valor de
-- negocio critico que afecta lo que ve el cliente en la Planilla, vale la
-- pena poder decir "lo cambio Fulano el martes" si algo sale raro.
--
-- Decision de sesion /grill-me 2026-07-17: no se le pregunta al cliente si
-- quiere esto -- se construye, se le muestra hecho, se ajusta despues.

CREATE TABLE IF NOT EXISTS configuracion_sistema (
  clave           VARCHAR(64)      NOT NULL,
  valor           VARCHAR(255)     NOT NULL,
  descripcion     VARCHAR(255)         NULL,
  actualizado_en  TIMESTAMP(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  actualizado_por BIGINT UNSIGNED      NULL,
  PRIMARY KEY (clave),
  CONSTRAINT fk_configuracion_usuario FOREIGN KEY (actualizado_por)
    REFERENCES usuarios(id)
    ON UPDATE CASCADE
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Seed con los valores actuales (TICKETS_BAJO_MAX=2, TICKETS_ALTO_MIN=5 en
-- run_calc_planilla.py) -- cero cambio de comportamiento hasta que un admin
-- edite algo activamente. INSERT IGNORE: re-ejecutar este script no falla
-- por PK duplicada.
INSERT IGNORE INTO configuracion_sistema (clave, valor, descripcion, actualizado_por) VALUES
  ('tickets_bajo_max', '2', 'Umbral de tickets (dias con venta en el mes) bajo -- <= este valor usa Historico en el blending de frecuencia de venta', NULL),
  ('tickets_alto_min', '5', 'Umbral de tickets (dias con venta en el mes) alto -- >= este valor usa Venta Real/Extrapolacion en el blending de frecuencia de venta', NULL);

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('17-configuracion-sistema.sql');
