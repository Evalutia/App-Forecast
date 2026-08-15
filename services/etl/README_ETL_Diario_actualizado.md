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
ID_EMPRESA=1
S_DEPOSITOS=1,5,8,9,10,11
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

### `WS_URL` / `ID_EMPRESA` / `S_DEPOSITOS` — Issue #139

Estos tres valores manejan la conexión al web service SOAP del cliente y qué
depósitos entran en cada corrida. Hasta el #139 estaban **hardcodeados** en
el `-param:` de `kitchen.sh` dentro de `run_ofelia.sh` (el cron automático de
las 3 AM) — el único script que no seguía el patrón que ya usan
`run_backfill_ventas.sh` y `run_extract_sales_chunk.sh` (leerlos de env con
`: "${VAR:?missing}"`, sin default). Dos formas en que eso rompía en
silencio:

- Un depósito nuevo que el cliente abre queda afuera de la extracción sin que
  nada lo señale — la planilla sigue calculando, solo que sobre datos
  incompletos.
- Si el proveedor del web service cambia la IP, hay que editar el script **y
  reconstruir la imagen** para levantarlo de nuevo.

Ahora `run_ofelia.sh` los lee de entorno igual que los demás scripts, y
**falla rápido con un mensaje claro** (`WS_URL: missing`, etc.) si falta
alguno — antes de tocar el lock de backfill o invocar Pentaho — en vez de
dejar que `kitchen.sh` reciba un `-param:` vacío y falle mucho más adelante
con un error críptico de Pentaho.

**Dónde se cambian:** en el `.env` de la VM de producción (mismo archivo
donde ya viven `MYSQL_*` y `CERT_*`), agregando/editando las claves `WS_URL`,
`ID_EMPRESA` y `S_DEPOSITOS`.

**Qué hacer para que tome efecto:** el servicio `etl` en `docker-compose.yml`
usa `env_file: .env`, pero esas variables se leen **al crear el contenedor**,
no en cada `docker exec` — un `docker compose restart etl` reinicia el mismo
contenedor sin releer `.env`, así que no alcanza. Hace falta recrearlo (sin
rebuild de imagen, la imagen no cambió):

```bash
docker compose up -d etl
```

Esto reemplaza el contenedor `evalutia-etl` con el `.env` actualizado; el
cron de `ofelia` (`docker exec evalutia-etl /usr/local/bin/run_ofelia.sh`,
ver `ofelia.ini`) ve las variables nuevas en la próxima corrida sin tocar
código ni reconstruir nada.

---

### Migraciones de `infra/sql/` — Issue #140

`infra/sql/*.sql` **no se aplica solo** contra un volumen de MySQL que ya
existe — `docker-entrypoint-initdb.d` (donde `docker-compose.yml` monta
`infra/sql/`) solo corre en un volumen **recién creado y vacío**. En
producción, donde el volumen existe desde hace meses, un archivo `.sql`
nuevo se queda ahí sentado hasta que alguien se acuerde de correrlo a mano.
Ya pasó dos veces (migraciones de los issues #86 y #102, meses sin
aplicarse, descubiertas recién cuando un job fallaba a mitad de camino con
`"table doesn't exist"`).

**Registro:** la tabla `schema_migrations(filename, applied_at)` guarda qué
archivo se aplicó y cuándo. Se puede consultar directo:

```sql
SELECT filename, applied_at FROM schema_migrations ORDER BY applied_at;
```

**Agregar una migración nueva:**

1. Crear `infra/sql/NN-descripcion.sql` (el número siguiente al más alto que
   exista — hay números repetidos históricos, ej. dos archivos `08-*`, así
   que el número no es una clave única, solo una convención de orden).
2. Que las sentencias sean **idempotentes** (correr el archivo dos veces no
   debe romper) — `CREATE TABLE IF NOT EXISTS`, `INSERT IGNORE`/`ON DUPLICATE
   KEY UPDATE`, `MODIFY COLUMN` (naturalmente idempotente) son seguros
   directo. `CREATE INDEX` y `ALTER TABLE ... ADD COLUMN`/`ADD CONSTRAINT`
   **no lo son** en MySQL (a diferencia de Postgres/MariaDB, no existe un
   `IF NOT EXISTS` para eso) — hay que guardarlos con un chequeo previo
   contra `information_schema` (ver cualquier archivo de `infra/sql/` como
   plantilla, ej. `07-articulos-factor-estacional-estado.sql` o
   `15-planilla-frecuencia-tickets.sql`).
3. Terminar el archivo con la línea de auto-registro (se usa tanto en un
   volumen nuevo como en uno existente):
   ```sql
   INSERT IGNORE INTO schema_migrations (filename) VALUES ('NN-descripcion.sql');
   ```

**Aplicarla en un entorno existente** (local o producción, cada uno por
separado — no hay sync automático entre ellos):

```bash
docker compose exec etl bash /app/services/etl/apply_migrations.sh
```

Aplica **todas** las pendientes, en orden, y corta en la primera que falle
(no sigue con las siguientes). Detectar sin aplicar (lo que corre
`run_ofelia.sh` como pre-flight antes de cada corrida nocturna, y aborta con
un mensaje claro si hay algo pendiente en vez de dejar que un paso a mitad
del `.kjb` reviente más adelante):

```bash
docker compose exec etl bash /app/services/etl/apply_migrations.sh --check-only
```

Nunca aplica DDL sola — `--check-only` es de solo lectura, y el cron nunca
invoca el modo de aplicar. Correr la migración pendiente sigue siendo,
siempre, un paso manual.

Un volumen **recién creado** (dev nuevo, CI, una VM nueva) no necesita nada
de esto: `docker-entrypoint-initdb.d` ya corrió los archivos completos, y
cada uno se auto-registró al final — `schema_migrations` queda poblada
igual, sin pasar por `apply_migrations.sh`.

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
docker compose exec etl /bin/bash -lc "/opt/pentaho/data-integration/kitchen.sh -file=/app/services/etl/job_etl_diario.kjb -level=Basic -param:WS_URL=http://200.125.29.194:81 -param:DATE_FMT=dmy -param:ID_EMPRESA=1 -param:S_DEPOSITOS=1,5,8,9,10,11 -param:GRUPOS=201 -param:MYSQL_HOST=mysql -param:MYSQL_DB=evalutia -param:MYSQL_USER=evalutia -param:MYSQL_PASSWORD=evalutia -param:MYSQL_PORT=3306 -param:PREDICT_PERIODS=2 -param:PREDICT_RESAMPLE_RULE=QS -param:PREDICT_MODEL_SET=classic -param:PREDICT_VERSION=mvp-002 -param:FORCE_START=30/05/2023 -param:FORCE_END=30/05/2026"

docker compose exec etl /bin/bash -lc "STEP_DAYS=365 /opt/pentaho/data-integration/kitchen.sh -file=/app/services/etl/job_etl_diario.kjb -level=Basic -param:WS_URL=http://200.125.29.194:81 -param:DATE_FMT=dmy -param:ID_EMPRESA=1 -param:S_DEPOSITOS=1,5,8,9,10,11 -param:GRUPOS=201 -param:MYSQL_HOST=mysql -param:MYSQL_DB=evalutia -param:MYSQL_USER=evalutia -param:MYSQL_PASSWORD=evalutia -param:MYSQL_PORT=3306 -param:PREDICT_PERIODS=2 -param:PREDICT_RESAMPLE_RULE=QS -param:PREDICT_MODEL_SET=classic -param:PREDICT_VERSION=mvp-002 -param:FORCE_START=03/10/2016 -param:FORCE_END=25/02/2026"
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

## Recuperación de una noche perdida — Issue #133

`run_ofelia.sh` extrae con `FORCE_START=FORCE_END=ayer` (un solo día) para
`RUN EXTRACT STOCKXML` — necesario, porque `ConsStockXml` devuelve siempre
la foto de **hoy** sin importar la fecha pedida (`assert_ventana_no_peligrosa`
en `run_extract_stockxml.sh` rechaza cualquier rango de más de un día). Antes
del #133, ese mismo par de parámetros también forzaba a un solo día a
`RUN EXTRACT VENTAS` — así que si una noche el cron moría (backfill en
curso, contenedor caído, lo que sea), el día perdido **nunca se reponía
solo**: la corrida siguiente volvía a pedir únicamente "ayer".

A diferencia de stock, **ventas sí es recuperable** — el web service acepta
rangos históricos. Ahora `RUN EXTRACT VENTAS` recibe su propio par de
parámetros, `SALES_FORCE_START`/`SALES_FORCE_END`, calculados por
`run_ofelia.sh` como una ventana de **7 días terminando ayer** (no solo el
día de ayer). Cada corrida vuelve a pedir y fusionar esos 7 días — seguro
de repetir, el merge es `INSERT ... ON DUPLICATE KEY UPDATE` — así que una
noche perdida se repone sola en la corrida siguiente, sin intervención
manual, mientras el hueco tenga menos de una semana.

`FORCE_START`/`FORCE_END` (sin el prefijo `SALES_`) siguen existiendo tal
cual, sin tocar, y siguen siendo de un solo día — solo los usa
`RUN EXTRACT STOCKXML`.

**Huecos de stock, que no son recuperables:** `cron_jobs.py stock_gaps`
(nuevo, llamado desde `run_ofelia.sh` junto a `coherencia`) revisa los
últimos 7 días de `stock_diario` — misma ventana que la recuperación de
ventas — y deja registrado en `jobs_historial.detalle.stock_gaps` qué
fechas no tienen **ninguna** fila. Es puramente informativo (no bloqueante,
mismo criterio que `coherencia`): un hueco de stock no se puede rellenar,
así que lo único que corresponde es que quede visible en vez de
silencioso.

```sql
SELECT id, fecha_inicio, JSON_EXTRACT(detalle, '$.stock_gaps') AS stock_gaps
FROM jobs_historial
WHERE tipo_job = 'etl' AND JSON_EXTRACT(detalle, '$.stock_gaps.num_dias_sin_datos') > 0
ORDER BY id DESC LIMIT 10;
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
