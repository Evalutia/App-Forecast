USE evalutia;

-- Issue #27: agrega clasificación de frecuencia de quiebre a planilla_ventas_calculada.
--
-- frecuencia_nivel: nivel del SKU según cuántos meses cerrados tuvo ventas > 0.
--   alta  : >= 9 meses con ventas (quiebre puntual, formula normal)
--   media : 4-8 meses con ventas (promedio de formula normal y formula baja)
--   baja  : <= 3 meses con ventas (demanda real por mes, no dias_con_stock)
--
-- rotacion_ajustada: rotación calculada con la fórmula correspondiente al nivel.
--   Solo se puebla en meses con estado_mes = 'quiebre_parcial'.
--   Meses 'normal' y 'sin_stock' quedan NULL (usan rotacion_diaria_real).

ALTER TABLE planilla_ventas_calculada
  ADD COLUMN frecuencia_nivel ENUM('alta','media','baja') NULL AFTER estado_mes,
  ADD COLUMN rotacion_ajustada DECIMAL(10,4) NULL AFTER frecuencia_nivel;
