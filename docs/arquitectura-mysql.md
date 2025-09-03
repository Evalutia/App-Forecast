# Arquitectura MySQL – Evalutia (Portal de Predicción)

## Objetivo
Persistir:
- **Ventas históricas** para entrenamiento y monitoreo.
- **Predicciones** por SKU/fecha con metadatos (modelo, versión, horizonte, métricas).
- **Usuarios** del portal (autenticación y roles).
- **Jobs/Logs** para trazabilidad operativa (ETL, forecast, backfill).

## Tablas y relaciones
- `ventas_historicas`: hecho transaccional diario. Unique `(fecha, sku, fuente)`.
- `predicciones`: salidas por modelo/versión; timestamp de generación; índices para obtener la última por SKU/fecha.
- `usuarios`: autenticación (hash) y autorización (rol).
- `jobs_historial`: auditoría de procesos (estado, tiempos, detalle JSON).
- Relación **opcional**: `predicciones.job_id → jobs_historial.id`.

## Decisiones de tipos
- Fechas `DATE`, auditoría `TIMESTAMP(6)`.
- Predicciones `DECIMAL(18,4)`; ventas `INT UNSIGNED`.
- Campos de texto dimensionados para SKUs largos (`VARCHAR(120)`).

## Índices
- `ventas_historicas (sku, fecha)` y `(fecha)`.
- `predicciones (sku, fecha_predicha, ts_generacion)`, `(modelo, version_modelo)`.
- `jobs_historial (tipo_job, fecha_inicio)` y `(estado, fecha_inicio)`.

## Patrones de consulta
- Última predicción por SKU/fecha:
  ```sql
  SELECT p.*
  FROM predicciones p
  WHERE p.sku = ? AND p.fecha_predicha BETWEEN ? AND ?
  QUALIFY ROW_NUMBER() OVER (PARTITION BY p.sku, p.fecha_predicha ORDER BY p.ts_generacion DESC) = 1;

## Operación

- ETL escribe `ventas_historicas` (idempotencia apoyada por UNIQUE).

- Worker de Python lee ventas, genera predicciones, registra `jobs_historial`.

- WebAPI expone endpoints; nunca exponer credenciales ni hashes.

## Escalabilidad (futuro)

- Particionamiento por rango en `ventas_historicas/predicciones` (mensual o anual).

- Materialized views (o tablas de snapshot) con “última predicción” por SKU/mes.

- Retención de logs y predicciones antiguas (policy por meses).

- Replica read-only para BI/analytics si fuese necesario.

## Seguridad

- Usuario MySQL dedicado (`evalutia`) con permisos acotados.

- Hash de contraseñas con `bcrypt` o `argon2` desde la WebAPI.

## Cómo ejecutarlo con Docker Compose

### 1 Base + tablas
docker compose exec mysql sh -lc "mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" < /sql/00_create_database.sql"
docker compose exec mysql sh -lc "mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" < /sql/01_tables.sql"

### 2 Índices
docker compose exec mysql sh -lc "mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" < /sql/02_indexes.sql"

### 3 Seed (opcional)
docker compose exec mysql sh -lc "mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" < /sql/03_seed.sql"

### 4 Grants (opcional)
docker compose exec mysql sh -lc "mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" < /sql/99_grants_example.sql"
