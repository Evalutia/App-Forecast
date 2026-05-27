# Contexto del Proyecto: Evalutia Portal

> Última actualización: mayo 2026  
> Rama principal: `main` | Rama activa al momento del relevamiento: `feature/planilla-estacionalidad`

---

## ¿Qué es este proyecto?

**Evalutia Portal** es una plataforma de forecasting para gestión de inventario. Extrae datos de ventas y stock desde un webservice SOAP externo, los almacena en MySQL, genera predicciones con modelos de ML, y los expone mediante un dashboard web.

---

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Frontend | React 19 + TypeScript 5.8 + Vite 7 + Tailwind CSS 4 + React Router 7 + React Query 5 |
| Backend | ASP.NET Core 8 + EF Core + Pomelo MySQL + JWT Bearer + Swagger |
| Base de datos | MySQL 8.0 |
| ETL | Pentaho PDI 9.4 (Kitchen/kjb) + Python 3.10 + SOAP |
| ML / Predicciones | Statsmodels (SARIMA/ETS), scikit-learn (RF), XGBoost, Prophet, ensemble por inverse-RMSE |
| Orquestación | Docker Compose, Ofelia (cron scheduler), Redis |
| Proxy | Caddy (reverse proxy + TLS) |

---

## URLs locales

| Servicio | URL |
|----------|-----|
| Frontend (Vite dev) | http://localhost:5173 |
| WebAPI (Swagger) | http://localhost:8080/swagger |
| Adminer (MySQL UI) | http://localhost:8081 |

---

## Estructura de carpetas

```
App-Forecast/
├── apps/
│   ├── frontend/          # React/Vite SPA
│   └── backend/           # ASP.NET Core 8 (C#)
│       └── WebApi/
│           ├── WebApi/        # Controllers, Program.cs, Filters
│           ├── DataAccess/    # Repositories (Dapper/EF Core)
│           ├── Models/        # Entidades + Validators
│           └── Services/      # Lógica de negocio
├── services/
│   ├── etl/               # Pentaho PDI + scripts Python de extracción
│   └── python-worker/     # CLI predict.py + módulos ML
├── infra/
│   └── sql/               # Migraciones SQL (01 al 99)
├── caddy/                 # Caddyfile (proxy reverso)
├── docs/                  # Documentación técnica
├── ofelia.ini             # Configuración cron de Ofelia
├── docker-compose.yml
└── .env                   # Variables de entorno (no versionar valores sensibles)
```

---

## Servicios Docker (docker-compose.yml)

| Servicio | Imagen / Build | Función |
|----------|---------------|---------|
| `mysql` | mysql:8.0 | Base de datos principal, volumen `mysql_data` |
| `adminer` | adminer | UI web para MySQL |
| `redis` | redis:7-alpine | Cache / sesiones |
| `webapi` | apps/backend/Dockerfile | API REST C# en puerto 8080 |
| `python-worker` | services/python-worker/Dockerfile | Predicciones ML |
| `etl` | services/etl/Dockerfile | Extracción SOAP + Pentaho |
| `ofelia` | mcuadros/ofelia:latest | Scheduler de jobs (cron Docker) |
| `webapp` | apps/frontend/Dockerfile | Frontend React en puerto 5173 |
| `caddy` | caddy/ | Proxy reverso HTTP/HTTPS |

**Red:** `evalutia_net` (externa, compartida entre todos los servicios)

### ⚠️ Workaround Apple Silicon (M1/M2/M3)
El servicio `etl` tiene `platform: linux/amd64` para forzar emulación x86 vía Rosetta.  
Rosetta debe estar activado en Docker Desktop → Settings → General → "Use Rosetta for x86/amd64 emulation on Apple Silicon".  
La variable `JAVA_TOOL_OPTIONS=-XX:+UseSerialGC` en `.env` evita el crash del G1 GC de Java bajo emulación.  
Estos cambios en `docker-compose.yml` están marcados con `git update-index --skip-worktree` para no pushearlos.

---

## Base de Datos (MySQL)

### Tablas principales

| Tabla | Descripción |
|-------|-------------|
| `usuarios` | Usuarios del sistema. Roles: `administrador`, `duenoDeEmpresa` |
| `articulos` | Catálogo de productos (sku PK, familia, stock_minimo, etc.) |
| `ventas_historicas` | Ventas diarias por SKU. UNIQUE(fecha, sku, fuente) |
| `jobs_historial` | Registro de ejecuciones ETL/forecast. Estados: en_cola, ejecutando, exitoso, fallido |
| `predicciones` | Resultados del ML. UNIQUE(sku, modelo, version_modelo, horizonte) |
| `stock_diario` | Stock por SKU y depósito. UNIQUE(sku, fecha, deposito_id) |
| `ventas_mensuales` | Aggregado mensual por SKU. UNIQUE(sku, year, month) |
| `planilla_ventas_calculada` | Tabla de rotación (issue #4). PK(sku, year, month) |
| `planilla_sugerencias` | Sugerencias de reposición por SKU (issue #16). PK(sku) |

### Tablas de staging (ETL)
- `ventas_historicas_stage` — staging temporal, se trunca post-merge
- `stock_diario_stage` — ídem para stock

### Migraciones SQL (orden)
```
infra/sql/
  01-init.sql              → CREATE DATABASE
  02-tablas.sql            → Tablas principales
  03-indices.sql           → Índices compuestos
  04-etl-staging.sql       → Tablas staging
  05-planilla.sql          → planilla_ventas_calculada (issue #4)
  06-planilla-sugerencias.sql → planilla_sugerencias (issue #16)
  99-creacion-admin.sql    → Usuario admin inicial
```

---

## Backend (ASP.NET Core 8)

### Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/auth/login` | Login, retorna JWT |
| GET | `/api/auth/me` | Usuario autenticado |
| GET/POST/PUT/DELETE | `/api/usuarios` | CRUD de usuarios |
| GET | `/api/predicciones` | Predicciones (paginado, filtros: sku, modelo, fechas) |
| GET | `/api/predicciones/ultimas` | Últimas predicciones por SKU |
| GET | `/api/predicciones/jobs/{jobId}` | Predicciones de un job |
| GET | `/api/ventas` | Ventas históricas (con agregación por período) |
| GET | `/api/ventas/distinct-skus` | Lista de SKUs disponibles |
| GET | `/api/ventas/top-skus` | Top 20 SKUs |
| GET | `/api/ventasmensuales` | Ventas mensuales |
| GET | `/api/articulos` | Catálogo de artículos |
| GET | `/api/stockdiario` | Stock diario |
| GET | `/api/resultados` | Análisis de stock |
| GET | `/api/jobs` | Historial de jobs |
| GET | `/api/jobs/{id}` | Detalle de un job |

### Autenticación
- JWT Bearer, claims: userId, correo, rol
- Roles: `administrador` (acceso total), `duenoDeEmpresa` (lectura)
- Config: `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_SECRET` (en .env)

### Estructura interna
- Patrón: Controller → Service → Repository (DataAccess)
- ORM: Entity Framework Core + Pomelo MySQL
- Validación: Validators en capa Models
- Error handling global: ExceptionFilter

---

## Frontend (React)

### Rutas

| Ruta | Componente | Acceso |
|------|-----------|--------|
| `/login` | LoginPage | Público |
| `/` o `/home` | Dashboard | Autenticado |
| `/predicciones` | PrediccionesPage | Autenticado |
| `/articulos` | ArticulosPage | Autenticado |
| `/ventas-mensuales` | VentasMensualesPage | Autenticado |
| `/stock-diario` | StockDiarioPage | Autenticado |
| `/resultados` | ResultadosPage | Autenticado |
| `/planilla` | PlanillaPage | Autenticado |
| `/usuarios` | UsersPage | Solo admin |
| `/ventas` | VentasPage | Solo admin |
| `/jobs` | JobsPage | Solo admin |
| `/jobs/:id` | JobDetailPage | Solo admin |

### Features principales

- **auth**: Login, JWT storage en localStorage, logout automático en 401
- **predictions**: Tabla + gráficos Chart.js (ProjectedSalesChart, ModelPerformanceChart), export Excel
- **sales**: Filtros por fecha/SKU, tablas de ventas y agregadas
- **jobs**: Historial de ejecuciones, badges de estado, link a predicciones
- **users**: CRUD de usuarios con modales (solo admin)
- **resultados**: Análisis ABC, stock-out, ventas perdidas + gráficos
- **planilla**: Tabla de reposición (en desarrollo, issue #10)

### Stack de estado
- React Query (`@tanstack/react-query`) para fetching/cache
- `sonner` para toasts
- Axios con interceptores (auth header, error handling, logout en 401)
- `react-hook-form` + `zod` para formularios

---

## ETL (Pentaho + Python)

### Flujo del job diario (`job_etl_diario.kjb`)
1. TRUNCATE `ventas_historicas_stage`
2. Extracción SOAP en chunks de `CHUNK_DAYS` días (desde `WS_START_DATE` o `FORCE_START`)
3. MERGE a `ventas_historicas` (`INSERT ... ON DUPLICATE KEY UPDATE`)
4. Ejecuta `predict.py` (predicciones ML)
5. TRUNCATE staging (limpieza)

### Cómo ejecutar el ETL manualmente
```bash
docker compose exec -e JAVA_TOOL_OPTIONS="-XX:+UseSerialGC" etl /bin/bash -lc \
  "/opt/pentaho/data-integration/kitchen.sh \
  -file=/app/services/etl/job_etl_diario.kjb \
  -level=Basic \
  -param:WS_URL=http://<HOST> \
  -param:DATE_FMT=dmy \
  -param:ID_EMPRESA=1 \
  -param:S_DEPOSITOS=1,5 \
  -param:GRUPOS=201 \
  -param:MYSQL_HOST=mysql \
  -param:MYSQL_DB=evalutia \
  -param:MYSQL_USER=evalutia \
  -param:MYSQL_PASSWORD=evalutia \
  -param:MYSQL_PORT=3306 \
  -param:PREDICT_PERIODS=2 \
  -param:PREDICT_RESAMPLE_RULE=QS \
  -param:PREDICT_MODEL_SET=classic \
  -param:PREDICT_VERSION=mvp-002 \
  -param:FORCE_START=DD/MM/YYYY \
  -param:FORCE_END=DD/MM/YYYY"
```

### Python Worker (predict.py)
- Modelos: SARIMA, ETS, RandomForest, XGBoost, Prophet
- Ensemble: combinación por inverse-RMSE
- Holdout para evaluar RMSE/R²
- Upsert en `predicciones`, registro en `jobs_historial`

---

## Variables de entorno (.env) — Keys

```
PROJECT_NAME, ENV
WEBAPP_PORT, WEBAPI_PORT, ADMINER_PORT
MYSQL_HOST, MYSQL_PORT, MYSQL_DB, MYSQL_USER, MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD
JWT_ISSUER, JWT_AUDIENCE, JWT_SECRET
REDIS_HOST, REDIS_PORT
ASPNETCORE_ENVIRONMENT, CORS_ORIGINS
VITE_API_BASE_URL
TZ
WS_URL, WS_USER, WS_PASS, WS_ID_GRUPO, WS_TIMEOUT_MS, WS_SOURCE_NAME
JAVA_TOOL_OPTIONS=-XX:+UseSerialGC   ← workaround Apple Silicon
CHUNK_DAYS, WS_START_DATE
PREDICT_PERIODS, PREDICT_MODEL_SET, PREDICT_VERSION, PREDICT_SCHEDULE_HOUR
```

---

## Decisiones de diseño (registradas en sesiones /grill-me)

### `run_calc_planilla.py` — Issue #6 (sesión 2026-05-26)

| Decisión | Definición |
|----------|-----------|
| **Fuente de datos** | `ventas_historicas` + `stock_diario`, GROUP BY mes. No usar `ventas_mensuales`. |
| **Ventana temporal** | 13 meses: mes actual + 12 anteriores completos (TRUNCATE + INSERT completo cada noche) |
| **dias_con_stock** | Días donde `SUM(stock de todos los depósitos) > stock_minimo` del artículo (JOIN con `articulos`) |
| **Depósitos** | Se suman todos los depósitos (sin filtrar por `S_DEPOSITOS`) |
| **estado_mes** | `sin_stock` = 0 días con stock · `quiebre_parcial` = >0 pero <90% de días naturales · `normal` = ≥90% |
| **Umbral 90%** | ⚠️ Arbitrario — documentar en UI y en este archivo. El cliente puede pedir cambiarlo. |
| **SKUs huérfanos** | INNER JOIN con `articulos` — se omiten silenciosamente, se loguea la cantidad al final |
| **jobs_historial** | `tipo_job = 'etl'`, `detalle.subtipo = 'calc_planilla'` + métricas (skus_procesados, meses_calculados, skus_omitidos, duracion_seg) |
| **Atomicidad** | Una transacción: BEGIN → TRUNCATE → INSERT masivo → COMMIT. ROLLBACK si falla → tabla queda con datos anteriores intactos |
| **Error handling** | Si falla → ROLLBACK + registrar `estado = 'fallido'` en `jobs_historial` con el error en `detalle` |

> **Nota para el frontend (#11):** mostrar el umbral del 90% visible en la UI de la planilla (ej. tooltip o leyenda) para que el cliente entienda la clasificación de `estado_mes` y pueda solicitar ajustarlo.

---

### `run_calc_planilla.sh` + `job_etl_diario.kjb` — Issue #7 (sesión 2026-05-27)

| Decisión | Definición |
|----------|-----------|
| **Bloqueante** | No — fallo del cálculo de planilla no aborta el ETL. Se loguea y continúa. |
| **Integración** | No se embebe en `run_etl_daily.sh` (correría antes del merge). Se crea `run_calc_planilla.sh` como wrapper independiente invocado desde el KJB. |
| **Posición en KJB** | Después de `RUN PREDICT.PY`, antes de `TRUNCATE VENTAS_STAGE END`. Hop `unconditional` para garantizar no-bloqueo. |
| **Flujo final KJB** | `CALC_UPSERT_VENTAS_MENSUALES` → `RUN PREDICT.PY` → `RUN CALC_PLANILLA` → `TRUNCATE VENTAS_STAGE END` |

> **Nota:** `run_calc_planilla.sh` pasa las mismas variables MySQL que ya tiene el KJB. No requiere parámetros adicionales.

### `GET /api/planilla/ventas` — Issue #8 (sesión 2026-05-27)

| Decisión | Definición |
|----------|-----------|
| **Formato respuesta** | Wide — una fila por SKU con array `meses[]` de 13 elementos. No tall. |
| **Paginación** | `PagedResultDto<T>` paginado por SKU (igual que el resto de endpoints). `pageSize` default 50. |
| **Campos de artículo** | `descripcion`, `marca_nombre`, `genero_descripcion`, `stock_minimo` |
| **Autorización** | `[Authorize]` sin restricción de rol — acceden `administrador` y `duenoDeEmpresa` |
| **Patrón implementación** | Completo: Controller → Service → Repository con interfaces (igual que `VentasController`) |

> **Nota:** El pivot tall→wide se hace en memoria en el Repository (GroupBy por SKU tras traer los datos del page). El endpoint acepta `page` y `pageSize` como query params. Los filtros (marca, genero, estado_mes) se agregan cuando se implemente el issue #13.

---

### `GET /api/planilla/filtros` — Issue #9 (sesión 2026-05-27)

| Decisión | Definición |
|----------|-----------|
| **DTO simétrico** | Tanto marcas como géneros usan `{ id, nombre }` — aunque en DB el género se llama `genero_descripcion`. La asimetría de la DB no se filtra al contrato de la API. |
| **NULLs excluidos** | Artículos con `marca_id IS NULL` o `genero_id IS NULL` se omiten de las listas. Son un problema de calidad de datos del SOAP. |
| **articulosIncompletos** | El response incluye `{ sinMarca: N, sinGenero: N }` — conteo de SKUs en planilla con campos nulos. Visibilidad directa sin necesidad de revisar logs. |
| **Deduplicación** | `GROUP BY marca_id + MAX(marca_nombre)` (idem para géneros). Evita duplicados si el SOAP envía inconsistencias de nombre para el mismo ID. |
| **Caché** | Sin caché por ahora. La query es simple y los datos cambian solo con el ETL nocturno. |
| **Arquitectura** | Las tres queries (marcas, géneros, incompletos) van en el repositorio. El servicio solo mapea al DTO de salida. |
| **Ordenamiento** | Alfabético por `nombre` para ambas listas. |

> **Nota para el frontend (#12):** los dropdowns de filtro deben poblar sus opciones llamando a este endpoint al montar la página de planilla. Si `articulosIncompletos.sinMarca > 0` o `sinGenero > 0`, mostrar un aviso discreto al usuario (ej. tooltip o badge) para que el cliente sepa que hay artículos con datos incompletos en el SOAP.

## Issues conocidos / TODOs en código

| Issue | Ubicación | Descripción |
|-------|-----------|-------------|
| #2 | articulos | Acceso a `factor_estacional` vía SOAP |
| #3 | articulos | Columna `factor_estacional` en tabla articulos |
| #4 | planilla | Poblar `planilla_ventas_calculada` |
| #5 | ETL | Extracción de factor estacional |
| #10 | frontend | Sección Planilla con ruta `/planilla` |
| #16 | DB | Tabla `planilla_sugerencias` |
| #17 | planilla_sugerencias | Campo `dias_hasta_quiebre` (requiere modelo de quiebre) |

### TODOs SQL explícitos
```sql
-- infra/sql/05-planilla.sql:
-- TODO issue #2: poblar rotacion_diaria_desestacionalizada cuando factor_estacional esté disponible.
-- Cálculo: rotacion_diaria_real / NULLIF(a.factor_estacional, 0)
-- Requiere: issue #2 → issue #3 → issue #5

-- infra/sql/06-planilla-sugerencias.sql:
-- TODO issue #17: poblar dias_hasta_quiebre cuando modelo de predicción de quiebre esté listo.
-- Cálculo: stock_actual / NULLIF(rotacion_sugerida, 0)
```

---

## Cómo levantar el proyecto

### Con Docker (modo normal)
```bash
docker compose build
docker compose up -d
```

### Frontend en modo desarrollo local (sin Docker)
```bash
# Requiere Node 20+
cd apps/frontend
nvm use 20        # si usás nvm
npm install
npm run dev       # http://localhost:5173
```

> **Nota Node version:** el proyecto requiere Node ≥20. Con Node 18 el install de dependencias puede trabarse.  
> Si se traba: `rm -rf node_modules && npm install`

---

## Documentación adicional

| Archivo | Contenido |
|---------|-----------|
| `docs/arquitectura-mysql.md` | Diseño de BD, relaciones, índices, patrones de consulta |
| `docs/script-de-prediccion.md` | Detalles de predict.py, modelos ML, ensemble |
| `services/etl/README_ETL_Diario_actualizado.md` | Flujo ETL completo, variables, backfills |
