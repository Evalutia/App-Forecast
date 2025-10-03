# ETL Diario de Ventas (Pentaho) — `services/etl/`

Este directorio contiene el **job ETL diario** que:
1) Extrae ventas desde el **WebService SOAP** (`/VsWebProduccion/SwNadWeb.asmx`) en **chunks** cortos por fecha.  
2) Carga a **staging** (`ventas_historicas_stage`) y luego hace **upsert** en `ventas_historicas` (histórico sin borrar).  
3) Ejecuta **`predict.py`** para recalcular **predicciones** con versionado (misma versión = reemplaza; versión nueva = convive).  
4) Registra logs/estado (ver `jobs_historial` y logs del contenedor).

> Motor: **Pentaho CE (Kettle)** + **Python**. Corre diariamente en Docker (servicio `etl`) vía **cron**.

---

## Estructura de archivos

- **`job_etl_diario.kjb`**  
  *Job maestro*. Orquesta todo el flujo:  
  - Trunca `ventas_historicas_stage` (inicio).  
  - Llama a `tr_get_last_date.ktr` → obtiene `${LAST_LOADED_DATE}`.  
  - Llama a `tr_generate_chunks.ktr` → emite pares (`CHUNK_START`, `CHUNK_END`) hasta **hoy** en ventanas `${CHUNK_DAYS}`.  
  - Por cada chunk: ejecuta `tr_extract_sales_chunk.ktr`.  
  - Ejecuta SQL **MERGE** (upsert) de *staging* → `ventas_historicas`.  
  - Lanza `predict.py` con `--periods`, `--model-set`, `--version`.  
  - Trunca `ventas_historicas_stage` (fin).

- **`tr_extract_sales_chunk.ktr`**  
  *Transformación por chunk*.  
  - **POST SOAP** a `${WS_URL}` con `CHUNK_START`, `CHUNK_END`, `${WS_ID_GRUPO}`.  
  - Extrae el **JSON** del SOAP, parsea a filas (`sku`, `fecha`, `cantidad`).  
  - Valida nulos/tipos, agrega `fuente=${WS_SOURCE_NAME}` y **inserta** en `ventas_historicas_stage`.

- **`tr_get_last_date.ktr`**  
  - `SELECT IFNULL(MAX(fecha), STR_TO_DATE('${START_DATE_PARAM}','%Y-%m-%d') - INTERVAL 1 DAY) AS last_date FROM ventas_historicas;`  
  - Setea `${LAST_LOADED_DATE}` en formato `yyyy-MM-dd`.

- **`tr_generate_chunks.ktr`**  
  - Desde `${LAST_DATE}+1` hasta **hoy**, genera ventanas de `${CHUNK_DAYS}` días.  
  - Devuelve filas (`CHUNK_START`, `CHUNK_END`) al job (usado con `execute_each_row=Y`).

- **`Dockerfile`**  
  - Imagen Ubuntu + **Java 11** + **Pentaho PDI CE** + **Python**.  
  - Copia el monorepo en `/app` e instala `services/python-worker/requirements.txt`.  
  - Registra `cron-etl` y ejecuta `cron -f`.

- **`cron-etl`**  
  - Programa el job diario con **Kitchen** a la hora `${PREDICT_SCHEDULE_HOUR}`.  
  - Logs en `/app/data/etl_job.log`.

> **SQL asociado (en `infra/sql/04-etl-staging.sql`):**  
> - `CREATE TABLE IF NOT EXISTS ventas_historicas_stage LIKE ventas_historicas;`  
> - `ALTER TABLE ventas_historicas_stage DROP KEY uq_ventas_fecha_sku_fuente;`  
> - `ALTER TABLE predicciones ADD UNIQUE KEY uq_pred_modelo_version_fecha (sku, modelo, version_modelo, fecha_predicha);` *(si faltara)*

---

## Variables de entorno requeridas (`.env`)

```dotenv
# SOAP
WS_URL=https://cliente.com/VsWebProduccion/SwNadWeb.asmx
WS_USER=
WS_PASS=
WS_ID_GRUPO=201
WS_TIMEOUT_MS=30000
WS_SOURCE_NAME=grupo201

# ETL
CHUNK_DAYS=7
WS_START_DATE=2020-01-01

# Predicción
PREDICT_PERIODS=6
PREDICT_MODEL_SET=full
PREDICT_VERSION=v1.0.0
PREDICT_SCHEDULE_HOUR=3   # Hora diaria (cron del contenedor etl)

# MySQL (ya existentes en el repo)
# MYSQL_HOST=mysql
# MYSQL_PORT=3306
# MYSQL_DB=evalutia
# MYSQL_USER=...
# MYSQL_PASSWORD=...
# MYSQL_ROOT_PASSWORD=...
# TZ=America/Montevideo
```

> Estas variables se inyectan al contenedor **etl** via `env_file: .env` (docker-compose).  
> Pentaho y `predict.py` leen `${MYSQL_*}`, `${WS_*}`, `${PREDICT_*}` directamente.

---

## Docker Compose (resumen del servicio `etl`)

```yaml
etl:
  build:
    context: .
    dockerfile: ./services/etl/Dockerfile
  container_name: evalutia-etl
  env_file:
    - .env
  environment:
    TZ: ${TZ}
  depends_on:
    mysql:
      condition: service_healthy
  networks:
    - evalutia_net
  restart: unless-stopped
```

> No expone puertos (no necesita proxy). Solo hace salidas HTTP (SOAP) y conecta a MySQL.

---

## Ejecución y pruebas

### 1) Build/levantar
```bash
# Build de la imagen ETL
docker compose build etl

# Levantar (se queda corriendo cron adentro)
docker compose up -d etl
```

### 2) Correr **ya mismo** (independiente de la hora del cron)
```bash
# Ejecutar el job manualmente dentro del contenedor
docker compose exec etl /opt/pentaho/data-integration/kitchen.sh   -file=/app/services/etl/job_etl_diario.kjb -level=Detailed
```

### 3) **Backfill** completo (desde una fecha inicial)
> Ajustá `WS_START_DATE` en `.env` o pasalo como parámetro:
```bash
docker compose run --rm etl /opt/pentaho/data-integration/kitchen.sh   -file=/app/services/etl/job_etl_diario.kjb   -param:WS_START_DATE=2020-01-01   -level=Detailed
```

### 4) **Incremental** manual (simular corrida diaria)
```bash
docker compose exec etl /opt/pentaho/data-integration/kitchen.sh   -file=/app/services/etl/job_etl_diario.kjb
```

### 5) Solo **predicciones** (adhoc / servicio python-worker)
```bash
docker compose exec python-worker python /app/services/python-worker/predict.py   --input-source=mysql --periods 6 --model-set full --version v1.0.0
```

---

## Logs y monitoreo

- **Logs del contenedor ETL (cron + kitchen + predict.py):**
```bash
docker compose logs -f etl
# o dentro del contenedor:
docker compose exec etl tail -f /app/data/etl_job.log
```

- **Verificar cron cargado:**
```bash
docker compose exec etl crontab -l
```

---

## Sanity checks (SQL útiles)

**¿Hay datos en staging?**
```sql
SELECT COUNT(*) FROM ventas_historicas_stage;
```

**Rango en `ventas_historicas`:**
```sql
SELECT MIN(fecha) AS min_f, MAX(fecha) AS max_f, COUNT(*) AS filas FROM ventas_historicas;
```

**Duplicados (no debería haber por UNIQUE (fecha, sku, fuente)):**
```sql
SELECT fecha, sku, fuente, COUNT(*) c
FROM ventas_historicas
GROUP BY 1,2,3
HAVING c > 1;
```

**Último día cargado:**
```sql
SELECT MAX(fecha) FROM ventas_historicas;
```

**Predicciones por SKU (última versión):**
```sql
SELECT p.*
FROM predicciones p
JOIN (
  SELECT sku, modelo, MAX(ts_generacion) ts
  FROM predicciones
  GROUP BY sku, modelo
) t ON p.sku=t.sku AND p.modelo=t.modelo AND p.ts_generacion=t.ts
ORDER BY p.sku, p.modelo, p.fecha_predicha;
```

---

## Idempotencia y errores

- **Idempotencia:**  
  - *staging* se trunca al inicio/fin.  
  - Upsert a `ventas_historicas` con `ON DUPLICATE KEY UPDATE`.  
  - `predicciones` tiene **UNIQUE** `(sku, modelo, version_modelo, fecha_predicha)` → misma versión **reemplaza**, versión nueva **convive**.

- **Timeouts/WS caído:**  
  - Configurar `WS_TIMEOUT_MS`.  
  - Reintentar manualmente: volver a ejecutar el job (incremental).  
  - Si falla `predict.py`, re-ejecutar solo predicciones (comando arriba).

---

## Mantenimiento

- **Limpiar versiones antiguas de predicciones (opcional):**
```sql
DELETE FROM predicciones
WHERE ts_generacion < DATE_SUB(CURDATE(), INTERVAL 6 MONTH);
```

- **Backups MySQL (ejemplo host script):**
```bash
DATE=$(date +%Y%m%d_%H%M%S)
docker exec evalutia-mysql sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" evalutia' > "./backups/evalutia_$DATE.sql"
# Mantener 30 días
find ./backups -type f -name "evalutia_*.sql" -mtime +30 -delete
```

- **Restore:**
```bash
docker cp backups/evalutia_YYYYMMDD_HHMMSS.sql evalutia-mysql:/tmp/restore.sql
docker compose exec mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" evalutia < /tmp/restore.sql'
```

---

## Notas finales

- Los `.ktr/.kjb` usan rutas **relativas** (`${Internal.Entry.Current.Directory}`), por eso deben convivir acá dentro de `services/etl/`.  
- No se requiere **proxy reverso**: el ETL no expone puertos; solo hace **salidas** HTTP (SOAP) y conexiones a MySQL.  
- Ajustá `${CHUNK_DAYS}` si el WS demora mucho (p.ej. 7–15 días funciona bien).  
- Configurá `${PREDICT_VERSION}`: fija (p.ej. `v1`) para reemplazar a diario; cambia el valor para conservar “snapshots” de predicciones.
