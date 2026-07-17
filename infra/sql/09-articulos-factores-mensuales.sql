-- Issue #31: agregar 12 columnas de factores estacionales mensuales a articulos.
-- Para bases ya existentes (dev/prod), aplicar manualmente:
--   docker exec evalutia-mysql mysql -u evalutia -pevalutia evalutia \
--     -e "$(cat infra/sql/09-articulos-factores-mensuales.sql)"
-- En prod, aplicar 07 primero si aún no está aplicada.

ALTER TABLE articulos
  ADD COLUMN factor_mes_01 DECIMAL(5,3) NULL AFTER factor_estacional,
  ADD COLUMN factor_mes_02 DECIMAL(5,3) NULL AFTER factor_mes_01,
  ADD COLUMN factor_mes_03 DECIMAL(5,3) NULL AFTER factor_mes_02,
  ADD COLUMN factor_mes_04 DECIMAL(5,3) NULL AFTER factor_mes_03,
  ADD COLUMN factor_mes_05 DECIMAL(5,3) NULL AFTER factor_mes_04,
  ADD COLUMN factor_mes_06 DECIMAL(5,3) NULL AFTER factor_mes_05,
  ADD COLUMN factor_mes_07 DECIMAL(5,3) NULL AFTER factor_mes_06,
  ADD COLUMN factor_mes_08 DECIMAL(5,3) NULL AFTER factor_mes_07,
  ADD COLUMN factor_mes_09 DECIMAL(5,3) NULL AFTER factor_mes_08,
  ADD COLUMN factor_mes_10 DECIMAL(5,3) NULL AFTER factor_mes_09,
  ADD COLUMN factor_mes_11 DECIMAL(5,3) NULL AFTER factor_mes_10,
  ADD COLUMN factor_mes_12 DECIMAL(5,3) NULL AFTER factor_mes_11;
