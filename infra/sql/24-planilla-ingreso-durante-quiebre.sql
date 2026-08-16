USE evalutia;

-- Issue #145 -- pedido de Rodrigo, textual: "cuando habiendo quiebre ingresa
-- stock, pintar la celda o marcarla de forma diferencial para poder
-- entender que se trata de un mes en el cual hubo un ingreso de
-- importacion". Hoy un mes con quiebre se ve igual venga de donde venga:
-- el articulo se agoto y no repuso, o se quedo sin stock y entro una
-- importacion a mitad de mes -- son situaciones distintas y el cliente
-- las lee distinto (en la segunda, la venta baja no significa que el
-- articulo no venda).
--
-- Columna booleana simple: True solo cuando estado_mes = 'quiebre_parcial'
-- Y el stock diario del SKU paso de 0 a positivo en algun punto del mes
-- (ver detectar_ingreso_durante_mes() en run_calc_planilla.py). False en
-- cualquier otro caso -- no necesita NULL, siempre es computable.
SET @col := (
  SELECT COUNT(1) FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'planilla_ventas_calculada'
    AND column_name = 'ingreso_durante_quiebre'
);
SET @sql := IF(@col = 0,
  'ALTER TABLE planilla_ventas_calculada
     ADD COLUMN ingreso_durante_quiebre BOOLEAN NOT NULL DEFAULT FALSE AFTER venta_o_extrapolacion;',
  'SELECT 1;'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Issue #140: auto-registro para services/etl/apply_migrations.sh / docker-entrypoint-initdb.d.
INSERT IGNORE INTO schema_migrations (filename) VALUES ('24-planilla-ingreso-durante-quiebre.sql');
