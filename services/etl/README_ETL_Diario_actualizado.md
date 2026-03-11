# ETL Diario de Ventas — `services/etl/`

Este directorio contiene el **job ETL diario** que ejecuta Pentaho (Kettle) dentro del contenedor `etl` y recalcula predicciones con Python.

---

## ¿Qué hace el job? (flujo de punta a punta)

1) **TRUNCATE de staging**  
   Limpia `ventas_historicas_stage` al **inicio** (y también al final) para que cada corrida sea limpia e idempotente.

2) **Extracción desde SOAP en “chunks”**  
   Se consulta el WebService `…/VsWebProduccion/SwNadWeb.asmx` (`ConsStockVenta`) en **ventanas de días** controladas por `${CHUNK_DAYS}`.  
   - Para cada chunk de fechas (`CHUNK_START`→`CHUNK_END`) se arma el request con `ID_EMPRESA`, `WS_ID_GRUPO` y `S_DEPOSITOS` (si aplica).  
   - La respuesta SOAP se parsea a JSON y se **inserta** en `ventas_historicas_stage` con columnas (`fecha`, `sku`, `cantidad`, `stock`, `fuente`).

3) **MERGE (upsert) de staging a histórico**  
   Con un `INSERT … ON DUPLICATE KEY UPDATE` se combina `ventas_historicas_stage` → `ventas_historicas` sobre la **clave única** `(fecha, sku, fuente)`.

4) **Predicciones**  
   Se ejecuta `predict.py` con `--periods`, `--model-set` y `--version`. Persiste en `predicciones` con **UNIQUE** `(sku, modelo, version_modelo, fecha_predicha)` para que:  
   - **Mis­ma versión** reemplace (idempotente).  
   - **Versión nueva** conviva (snapshot histórico de modelos).

5) **TRUNCATE de staging (fin)**  
   Se vuelve a limpiar `ventas_historicas_stage` para dejar la tabla lista para la próxima corrida.

> Motor: **Pentaho CE (Kitchen)** + **Python (statsmodels/XGB/RF)**. Corre diariamente en Docker (servicio `etl`) vía **cron** dentro del contenedor.

---

## ¿Cada cuánto corre? (schedule)

- Corre **1 vez por día** por **cron** dentro del contenedor `etl`.  
- La hora se controla con la variable de entorno `PREDICT_SCHEDULE_HOUR` (o `CRON_SPEC` si tu entrypoint usa un cron spec completo).  
- Podés **forzar una ejecucion manual** en cualquier momento con los comandos de la sección _“Ejecución y pruebas”_.

---

## ¿Cuántas ventas hacia atrás toma en cada corrida?

- Por defecto, cada corrida toma **desde la última fecha cargada + 1 día** en `ventas_historicas` **hasta hoy** (inclusive).  
- La ventana se parte en chunks de `${CHUNK_DAYS}` días (`7` por defecto) para no saturar el WS.  
- Si la tabla está vacía, el arranque usa `${WS_START_DATE}` como fecha inicial.  
- Podés **anular la ventana automática** con `-param:FORCE_START=dd/MM/yyyy` y `-param:FORCE_END=dd/MM/yyyy` para hacer **backfills** o reprocesos controlados.

> Ejemplo típico: si corre a diario y ayer ya quedó cargado, la nueva corrida solo extrae **el día de hoy** (o hasta hoy si hubo atrasos).

---

## Archivos clave

- **`job_etl_diario.kjb` (Job maestro)**  
  - TRUNCATE `ventas_historicas_stage` (inicio)  
  - `tr_get_last_date.ktr` → obtiene `${LAST_LOADED_DATE}`  
  - `tr_generate_chunks.ktr` → genera (`CHUNK_START`, `CHUNK_END`) hasta hoy en ventanas de `${CHUNK_DAYS}`  
  - `tr_extract_sales_chunk.ktr` (por cada chunk)  
  - MERGE SQL: staging → `ventas_historicas`  
  - Ejecuta `predict.py` (`--periods`, `--model-set`, `--version`)  
  - TRUNCATE `ventas_historicas_stage` (fin)

- **`tr_extract_sales_chunk.ktr` (por chunk)**  
  - POST SOAP a `${WS_URL}` con fechas + `WS_ID_GRUPO` (+ `ID_EMPRESA`, `S_DEPOSITOS`)  
  - Parseo JSON → filas (`sku`, `fecha`, `cantidad`, `stock`, `fuente`)  
  - Inserción en `ventas_historicas_stage`

- **`tr_get_last_date.ktr`**  
  - `SELECT IFNULL(MAX(fecha), STR_TO_DATE('${WS_START_DATE}','%Y-%m-%d') - INTERVAL 1 DAY) AS last_date FROM ventas_historicas;`  
  - Settea `${LAST_LOADED_DATE}` (`yyyy-MM-dd`).

- **`tr_generate_chunks.ktr`**  
  - Desde `${LAST_LOADED_DATE}+1` hasta **hoy**, en tramos de `${CHUNK_DAYS}` días (emite filas con `CHUNK_START/END`).

- **`Dockerfile`**  
  - Imagen Ubuntu 22.04 + **Java 11** + **Pentaho PDI 9.4** + **Python 3.10**.  
  - Instala dependencias de `services/python-worker/requirements.txt`.  
  - Prepara `cron` y logs.

- **`cron-etl` / `entrypoint.sh`**  
  - Programa Kitchen según `PREDICT_SCHEDULE_HOUR` o `CRON_SPEC`.  
  - Logs en `/app/data/etl_job.log` dentro del contenedor.

> **SQL asociado** (ejemplo en `infra/sql/04-etl-staging.sql`):  
> - `CREATE TABLE IF NOT EXISTS ventas_historicas_stage LIKE ventas_historicas;`  
> - `ALTER TABLE ventas_historicas_stage DROP KEY uq_ventas_fecha_sku_fuente;`  
> - `ALTER TABLE predicciones ADD UNIQUE KEY uq_pred_modelo_version_fecha (sku, modelo, version_modelo, fecha_predicha);` *(si faltara)*

---

## Variables de entorno (`.env`)

```dotenv
# SOAP
WS_URL=https://cliente.com/VsWebProduccion/SwNadWeb.asmx
WS_USER=
WS_PASS=
WS_ID_GRUPO=201
S_DEPOSITOS=1,5
WS_TIMEOUT_MS=30000
WS_SOURCE_NAME=grupo201

# ETL
CHUNK_DAYS=7
WS_START_DATE=2020-01-01

# Predicción
PREDICT_PERIODS=6
PREDICT_MODEL_SET=classic
PREDICT_VERSION=mvp-001
PREDICT_SCHEDULE_HOUR=3   # (o usar CRON_SPEC="0 3 * * *")

# MySQL
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DB=evalutia
MYSQL_USER=evalutia
MYSQL_PASSWORD=evalutia
MYSQL_ROOT_PASSWORD=change-me
TZ=UTC
```

> Estas variables se inyectan al contenedor `etl` vía `env_file: .env` en `docker-compose.yml`.

---

## Docker Compose (servicio `etl` resumido)

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
---

## Ejecución y pruebas

### 1) Build y levantar
```bash
# Build de la imagen ETL
docker compose build etl

# Levantar el servicio (cron queda corriendo adentro)
docker compose up -d etl
```

### 2) Correr **ya** (independiente del cron)
```bash
# Windows PowerShell (comillas dobles)
docker compose exec etl /opt/pentaho/data-integration/kitchen.sh `
  "-file=/app/services/etl/job_etl_diario.kjb" -level=Detailed
```

### 3) Corrida **incremental** (simula la diaria por defecto)
```bash
docker compose exec etl /opt/pentaho/data-integration/kitchen.sh \
  -file=/app/services/etl/job_etl_diario.kjb -level=Basic
```

### 4) **Backfill completo** desde una fecha fija
```bash
# Linux/macOS
docker compose run --rm etl /opt/pentaho/data-integration/kitchen.sh \
  -file=/app/services/etl/job_etl_diario.kjb \
  -param:WS_START_DATE=2020-01-01 \
  -level=Detailed
```

### 5) **Backfill de 2 años** (ejemplo exacto probado)
**Windows PowerShell (exacto que usamos):**
```powershell
docker compose exec etl /bin/bash -lc "/opt/pentaho/data-integration/kitchen.sh -file=/app/services/etl/job_etl_diario.kjb -level=Basic -param:WS_URL=http://200.125.29.194:81 -param:DATE_FMT=dmy -param:ID_EMPRESA=1 -param:S_DEPOSITOS=1,5 -param:GRUPOS=201 -param:MYSQL_HOST=mysql -param:MYSQL_DB=evalutia -param:MYSQL_USER=evalutia -param:MYSQL_PASSWORD=evalutia -param:MYSQL_PORT=3306 -param:PREDICT_PERIODS=2 -param:PREDICT_RESAMPLE_RULE=QS -param:PREDICT_MODEL_SET=classic -param:PREDICT_VERSION=mvp-002 -param:FORCE_START=25/02/2026 -param:FORCE_END=11/03/2026"

docker compose exec etl /bin/bash -lc "STEP_DAYS=365 /opt/pentaho/data-integration/kitchen.sh -file=/app/services/etl/job_etl_diario.kjb -level=Basic -param:WS_URL=http://200.125.29.194:81 -param:DATE_FMT=dmy -param:ID_EMPRESA=1 -param:S_DEPOSITOS=1,5 -param:GRUPOS=201 -param:MYSQL_HOST=mysql -param:MYSQL_DB=evalutia -param:MYSQL_USER=evalutia -param:MYSQL_PASSWORD=evalutia -param:MYSQL_PORT=3306 -param:PREDICT_PERIODS=2 -param:PREDICT_RESAMPLE_RULE=QS -param:PREDICT_MODEL_SET=classic -param:PREDICT_VERSION=mvp-002 -param:FORCE_START=03/10/2016 -param:FORCE_END=25/02/2026"
```

**Backfill de 2 años relativo (PowerShell):**
```powershell
$start=(Get-Date).AddYears(-2).ToString('dd/MM/yyyy')
$end=(Get-Date).ToString('dd/MM/yyyy')
docker compose exec etl /opt/pentaho/data-integration/kitchen.sh `
  "-file=/app/services/etl/job_etl_diario.kjb" -level=Basic `
  "-param:FORCE_START=$start" "-param:FORCE_END=$end"
```

**Backfill de 2 años relativo (bash):**
```bash
START=$(date -d '2 years ago' +%d/%m/%Y); END=$(date +%d/%m/%Y)
docker compose exec etl /opt/pentaho/data-integration/kitchen.sh \
  -file=/app/services/etl/job_etl_diario.kjb -level=Basic \
  -param:FORCE_START="${START}" -param:FORCE_END="${END}"
```

### 6) Solo **predicciones** (adhoc, por si falla el paso Python)
```bash
docker compose exec python-worker python /app/services/python-worker/predict.py \
  --input-source mysql --mysql-host mysql --mysql-port 3306 \
  --mysql-db evalutia --mysql-user evalutia --mysql-pass evalutia \
  --periods 6 --model-set classic --version mvp-001
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

## SQL de verificación rápida

**Staging cargado:**
```sql
SELECT COUNT(*) FROM ventas_historicas_stage;
```

**Rango y cantidad en histórico:**
```sql
SELECT MIN(fecha) min_f, MAX(fecha) max_f, COUNT(*) filas FROM ventas_historicas;
```

**Último día cargado:**
```sql
SELECT MAX(fecha) FROM ventas_historicas;
```

**Duplicados (no debería haber por UNIQUE (fecha, sku, fuente)):**
```sql
SELECT fecha, sku, fuente, COUNT(*) c
FROM ventas_historicas
GROUP BY 1,2,3
HAVING c > 1;
```

**Predicciones (última generación por modelo):**
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

## Notas y buenas prácticas

- `CHUNK_DAYS`: si el WS es lento, usá 7–15 días para balancear llamadas/tiempo.  
- `PREDICT_VERSION`: fija (p.ej. `mvp-001`) para **reemplazar** diariamente; cambia de valor para **conservar** snapshots.  
- TZ y fechas: la conexión MySQL en PDI usa `UTC` para evitar corrimientos.  
- Idempotencia: staging limpio + upsert + UNIQUE de predicciones garantizan corridas repetibles.  
- Permisos MySQL mínimos (si hiciera falta recrearlos):
  ```sql
  GRANT SELECT, INSERT, UPDATE ON evalutia.ventas_historicas TO 'evalutia'@'%';
  GRANT SELECT, INSERT, UPDATE, DELETE, DROP ON evalutia.ventas_historicas_stage TO 'evalutia'@'%';
  GRANT SELECT, INSERT, UPDATE, DELETE ON evalutia.predicciones TO 'evalutia'@'%';
  FLUSH PRIVILEGES;
  ```

---

**Contacto / Soporte**  
Ante cualquier warning de `statsmodels` (p.ej. `ConvergenceWarning`) el job puede finalizar OK; revisar las métricas `rmse/r2` y, si hace falta, reintentar el paso de predicción con el comando de la sección correspondiente.
