USE evalutia;

-- Issue #80: permite ventas netas negativas (notas de credito) en el
-- pipeline. Ver .claude/CONTEXTO.md, sesion 2026-07-13 (#79) para el
-- hallazgo completo. Rodrigo confirmo que el SOAP devuelve netos negativos
-- ocasionalmente (devoluciones que superan la venta del dia) -- hoy se
-- pierden: clamp explicito en el ETL + columnas UNSIGNED/CHECK aca abajo.
--
-- Solo ventas_historicas tiene un CHECK nombrado (chk_ventas_cantidad)
-- ademas del tipo UNSIGNED; las otras 4 tablas dependen solo del tipo.
-- DROP CHECK sobre una constraint que ya no existe falla (a diferencia de
-- MODIFY COLUMN, que es idempotente por si solo) -- se guarda con chequeo
-- previo, mismo patron que 04-etl-staging.sql, dado el incidente real de
-- comando repetido que ya tuvimos en la migracion de #71 (esta misma sesion).
--
-- No se toca: predicciones.cantidad_predicha (CHECK >=0 correcto, un
-- pronostico futuro no debe ser negativo) ni stock_diario/planilla_sugerencias
-- (stock fisico, concepto distinto, ya normalizado a 0 en run_calc_sugerencias.py).
-- Sin CHECK de reemplazo: el rango natural de INT/BIGINT ya alcanza, un
-- limite arbitrario seria un numero inventado sin caso real que lo justifique.

SET @chk := (
  SELECT COUNT(1) FROM information_schema.table_constraints
  WHERE table_schema = DATABASE()
    AND table_name = 'ventas_historicas'
    AND constraint_name = 'chk_ventas_cantidad'
);
SET @sql := IF(@chk > 0,
  'ALTER TABLE ventas_historicas DROP CHECK chk_ventas_cantidad;',
  'SELECT 1;'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

ALTER TABLE ventas_historicas         MODIFY COLUMN cantidad INT NOT NULL;
ALTER TABLE ventas_historicas_stage   MODIFY COLUMN cantidad INT NOT NULL;
ALTER TABLE ventas_mensuales          MODIFY COLUMN ventas_cantidad BIGINT NOT NULL DEFAULT 0;
ALTER TABLE planilla_ventas_calculada MODIFY COLUMN ventas_cantidad BIGINT NOT NULL DEFAULT 0;
ALTER TABLE stock_resumen_365         MODIFY COLUMN ventas_365 BIGINT NOT NULL DEFAULT 0;
