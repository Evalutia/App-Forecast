USE evalutia;

-- Issue #62: columnas de frecuencia de venta por tickets en
-- planilla_ventas_calculada. Ver .claude/CONTEXTO.md, sesion 2026-07-14.
--
-- Sistema DISTINTO de frecuencia_nivel/rotacion_ajustada (issue #27,
-- 08-planilla-frecuencia-quiebre.sql): ese clasifica el SKU a nivel ANUAL
-- (meses con ventas en los 12 meses) para elegir la formula de rotacion en
-- meses de quiebre. Este clasifica cada MES individual por cantidad de
-- tickets (dias con venta ese mes) para elegir el blending
-- Historico/Promedio/Real -- ambos sistemas coexisten (decision ya tomada
-- en #65, no se reemplaza el significado de frecuencia_nivel).
--
-- Nombres deliberadamente distintos (tickets_mes, valor_historico,
-- valor_ajustado, criterio_frecuencia) para no confundir los dos sistemas.
--
-- "Ticket" = un dia del mes con al menos una fila de venta en
-- ventas_historicas (positiva o negativa), definicion cerrada con el
-- cliente en #61. "Historico" = promedio mensual de unidades vendidas del
-- SKU en los ultimos 12 meses (o de los meses disponibles si el SKU tiene
-- menos antiguedad).
--
-- ALTER TABLE ADD COLUMN no es idempotente (falla si la columna ya existe)
-- -- se guarda con chequeo previo via information_schema, mismo patron ya
-- usado en 04-etl-staging.sql, dado el incidente real de comando repetido
-- que ya tuvimos en las migraciones de #71/#80 esta misma sesion.

SET @col := (
  SELECT COUNT(1) FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'planilla_ventas_calculada'
    AND column_name = 'tickets_mes'
);
SET @sql := IF(@col = 0,
  'ALTER TABLE planilla_ventas_calculada
     ADD COLUMN tickets_mes         TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER rotacion_ajustada,
     ADD COLUMN valor_historico     DECIMAL(10,2)    NULL     AFTER tickets_mes,
     ADD COLUMN valor_ajustado      DECIMAL(10,2)    NULL     AFTER valor_historico,
     ADD COLUMN criterio_frecuencia ENUM(''historico'',''promedio'',''real_extrapolado'') NULL AFTER valor_ajustado;',
  'SELECT 1;'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
