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
  07-articulos-factor-estacional-estado.sql → ALTER TABLE articulos ADD factor_estacional + estado (issue #3)
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

---

### Filtros en `GET /api/planilla/ventas` — Issue #13 backend (sesión 2026-05-29)

| Decisión | Definición |
|----------|-----------|
| **Semántica de estadoMes** | Opción "al menos un mes": se devuelven SKUs que tienen **al menos una fila** con ese `estado_mes` en los 13 meses. No se filtran filas individuales — el array de 13 meses siempre viene completo. |
| **Dónde se aplican los filtros** | En la **primera query** (paginación de SKUs distintos), antes del `Skip/Take`. Garantiza que `totalSkus` y la página reflejen el mismo universo filtrado. |
| **Cardinalidad por filtro** | **Single value** — `marcaId`, `generoId` y `estadoMes` aceptan un único valor opcional cada uno. Los dropdowns del frontend son single-select. |
| **Validación de estadoMes** | El backend valida que el valor sea uno de `"normal"`, `"quiebre_parcial"` o `"sin_stock"`. Si no, retorna `400 Bad Request`. No se deja pasar un string arbitrario a la query. |
| **Firma de métodos** | Parámetros individuales en cada capa: `GetVentas(int page, int pageSize, uint? marcaId, uint? generoId, string? estadoMes)`. Sin objeto filtro — consistencia con el resto del codebase. |
| **IQueryable compartido** | Se construye una `IQueryable<string>` base (`skuQuery`) con todos los filtros aplicados, y se reutiliza tanto para `Count()` como para `OrderBy/Skip/Take`. Evita divergencia entre total y página. |
| **JOIN con articulos** | Los filtros de `marcaId`/`generoId` se aplican intersectando `skuQuery` con un subquery de `articulos` via `.Where(s => articulosQuery.Select(a => a.Sku).Contains(s))` — traducido por EF Core a `IN (SELECT sku FROM articulos WHERE ...)`. |

> **Nota:** El filtro `estadoMes` se aplica como `.Where(p => p.EstadoMes == estadoMes)` antes del `.Select(p => p.Sku).Distinct()`, lo que naturalmente implementa la semántica "al menos un mes". No requiere subquery adicional.

### `FiltrosPlanilla` — Issue #12 (sesión 2026-05-29)

| Decisión | Definición |
|----------|-----------|
| **Dónde se llama `usePlanillaFiltros`** | Dentro de `FiltrosPlanilla` — el componente es autocontenido. Solo emite los valores seleccionados hacia `PlanillaPage` vía callbacks. `PlanillaPage` no conoce las opciones de marcas/géneros. |
| **Aviso de artículos incompletos** | Texto inline dentro de la card de filtros: "⚠ X artículos sin marca · Y sin género". Solo visible cuando `sinMarca > 0` o `sinGenero > 0`. Desaparece si no hay incompletos. |
| **Estado de carga** | Dropdowns deshabilitados con texto "Cargando…" mientras `usePlanillaFiltros` está pendiente. No se mantienen los skeletons — los controles son visibles pero bloqueados. |

> **Nota:** Si `usePlanillaFiltros` falla, los dropdowns quedan deshabilitados sin mensaje de error crítico — el usuario puede igual navegar la tabla sin filtros. El aviso de incompletos no se muestra si el fetch falló.

### `PlanillaPage` — Issue #14 (sesión 2026-05-29)

| Decisión | Definición |
|----------|-----------|
| **Contenido de celda de mes** | `ventasCantidad` (número) + `estadoMes` como color de fondo suave. No se apilan múltiples valores en la celda. |
| **Scroll y sticky** | `overflow-x: auto` en `table-wrap`. Primera columna (SKU + Descripción) sticky con `position: sticky; left: 0`. |
| **Estado de filtros y paginación** | `useState` local en `PlanillaPage` — no se usa `useSearchParams`. Consistente con `StockAnalysisTable`. |
| **Columnas fijas** | SKU + Descripción (sticky) + Marca + Stock Mínimo. Género se omite — no aporta valor operacional en la tabla. |
| **Colores de estadoMes** | Fondos desaturados: verde suave para `normal`, amarillo suave para `quiebre_parcial`, rojo suave para `sin_stock`. Opacidad ~10–15% para no competir con el número. |

> **Nota:** El mes en el header se muestra como "Ene 25" (abreviado). Los colores deben funcionar sobre fondo blanco/claro del `card`. El componente de tabla se llama `PlanillaTable` y recibe los datos y handlers como props desde `PlanillaPage`.

---

### `07-articulos-factor-estacional-estado.sql` — Issue #3 (sesión 2026-06-06)

| Decisión | Definición |
|----------|-----------|
| **Formato `factor_estacional`** | `DECIMAL(5,3) NULL` — un único escalar = coeficiente del **mes actual**, recalculado cada noche por el ETL (issue #5) tomando el `MesXX` correspondiente del SOAP. No se guardan los 12 valores mensuales: el TODO en `05-planilla.sql` ya esperaba un escalar para `rotacion_diaria_real / NULLIF(a.factor_estacional, 0)`. |
| **Origen y semántica de `estado`** | `ENUM('activo','inactivo') NOT NULL DEFAULT 'activo'`. El SOAP **no** tiene un campo `Estado` — se deriva de la **presencia del SKU en el feed nocturno**: si un SKU deja de aparecer → `inactivo`; si reaparece → `activo`. Lo calcula el ETL (issue #5), no el usuario ni el backend. |
| **Visibilidad de `estado`** | Es **puramente informativo** — no debe usarse para ocultar artículos por default en ninguna vista (planilla, predicciones, listado de artículos). El usuario puede filtrar por `estado` si quiere, pero por defecto se muestran todos (activos e inactivos por igual). |
| **Alcance del issue** | Incluye script SQL **+** mapeo EF Core (`Articulo.cs` + `EvalutiaDbContext.cs`). No incluye DTOs ni endpoints — eso es "API surface", trabajo de otro issue. |
| **Mecánica de la migración** | Archivo numerado `infra/sql/07-articulos-factor-estacional-estado.sql` con `ALTER TABLE ... ADD COLUMN` estándar (MySQL 8 no soporta `IF NOT EXISTS` en `ADD COLUMN` — eso es extensión MariaDB). Es un script de una sola ejecución. Sirve de fuente de verdad del esquema para instalaciones nuevas. Para bases ya existentes (esta y prod) se aplica manualmente vía `docker exec evalutia-mysql mysql ... -e "ALTER TABLE ..."`. |
| **Índices** | `CREATE INDEX idx_articulos_estado ON articulos (estado)` — sigue el patrón existente de columnas categóricas filtrables (`familia_id`, `genero_id`, `barcode`). `factor_estacional` no se indexa: es un valor de cálculo, no un predicado de filtro. |

> **Nota para ETL/frontend:** `estado` no es fuente de verdad para "excluir productos descontinuados" de lógica crítica (predicciones, planilla) — es informativo. Si en el futuro se necesita excluir inactivos de algún cálculo, eso requiere una decisión explícita y separada, no inferirla silenciosamente de este campo.

### `run_extract_articulos.py` — Issues #2 y #5 (sesión 2026-06-07)

| Decisión | Definición |
|----------|-----------|
| **Fuente de `factor_estacional`** | Campos `Mes01`–`Mes12` dentro de cada `<Articulo>` en `ConsArticulosWeb` — mismo endpoint, sin llamada SOAP adicional. Issues #2 y #5 se resuelven en un único toque a `run_extract_articulos.py`. |
| **Mes a usar** | `datetime.now().month` sin parámetro — siempre el mes en que corre el ETL. En junio toma `Mes06`, en julio `Mes07`, etc. |
| **Valor 0 o campo ausente** | `factor_estacional = 0` → almacenar `NULL`. Campo `MesXX` no presente → `NULL`. La columna es `DECIMAL(5,3) NULL`. |
| **Mecánica de `estado`** | **Opción A:** al final del batch, `UPDATE articulos SET estado='inactivo' WHERE sku NOT IN (skus_vistos)`. Solo se ejecuta si `rows_ins > 0` — si el SOAP falló y no se procesó ningún artículo, se omite para no marcar todo como inactivo. |
| **Reactivación** | El `ON DUPLICATE KEY UPDATE` incluye `estado = 'activo'` — si un SKU reaparece en el feed después de estar inactivo, queda activo en la misma transacción, antes del `NOT IN`. |
| **Atomicidad** | Upserts + UPDATE estado en una sola transacción (`autocommit=False`, commit único al final). Si falla el UPDATE de estado, el commit no ocurre y los upserts se revierten. |

> **Nota:** El set de SKUs procesados se acumula en memoria durante el upsert loop y se pasa como `IN (...)` al UPDATE final. Para >10.000 SKUs considerar usar una tabla temporal, pero no es el caso actual.

### `run_calc_sugerencias.py` — Issue #15 (sesión 2026-06-07)

| Decisión | Definición |
|----------|-----------|
| **Qué es `rotacion_sugerida`** | Tendencia suavizada de rotación histórica reciente — **no** un forecast. Promedio ponderado de los últimos N meses `normal` de `rotacion_diaria_real` en `planilla_ventas_calculada`. Semántica: "a qué ritmo está rotando este SKU hoy". |
| **Filtro de meses** | Solo `estado_mes = 'normal'`. Meses con `quiebre_parcial` o `sin_stock` tienen rotación artificialmente suprimida y distorsionarían la tendencia hacia abajo. |
| **Mínimo de meses** | 3 meses `normal`. Si un SKU tiene menos → `rotacion_sugerida = NULL`, `fiabilidad_porcentaje = NULL`. |
| **Ventana** | Todos los meses `normal` disponibles, hasta 13 (ventana completa de `planilla_ventas_calculada`). No se limita a 6 — productos de tecnología tienen ciclos largos y 13 meses da más robustez. |
| **Pesos** | Lineales: mes más antiguo = peso 1, mes más reciente = peso N (donde N = cantidad de meses normales usados). |
| **`fiabilidad_porcentaje`** | Coeficiente de variación inverso: `max(0, (1 - std/mean) * 100)`. Mide estabilidad de la rotación. CV > 1 → fiabilidad 0. Rotación consistente → fiabilidad alta. No usar R² (penalizaría SKUs con rotación estable horizontal) ni % de meses con datos (mide calidad de datos, no del modelo). |
| **`modelo`** | `'weighted_avg_13m'` — nombre fijo en la columna `modelo` de `planilla_sugerencias`. |
| **Arquitectura** | Nuevo script `run_calc_sugerencias.py` + wrapper `run_calc_sugerencias.sh`. Invocado desde `job_etl_diario.kjb` después de `RUN CALC_PLANILLA`, antes de `TRUNCATE VENTAS_STAGE END`. |
| **Atomicidad** | Una sola transacción: calcular todos los SKUs en memoria → INSERT masivo con ON DUPLICATE KEY UPDATE → COMMIT. ROLLBACK en fallo → tabla conserva valores anteriores. |
| **Bloqueante** | No — fallo del script no aborta el ETL. Se loguea en `jobs_historial` con `subtipo = 'calc_sugerencias'`. |

> **Nota para frontend (#19):** `fiabilidad_porcentaje` debe mostrarse como badge de color en la columna ROT.S: verde (≥70), amarillo (40–69), rojo (<40). NULL = sin datos suficientes, mostrar "—". `rotacion_sugerida` NULL también muestra "—" sin crashear.

### `run_calc_sugerencias.py` (ampliación) — Issue #17 (sesión 2026-06-07)

| Decisión | Definición |
|----------|-----------|
| **Integración** | Dentro del mismo `run_calc_sugerencias.py`, misma pasada en memoria. `dias_hasta_quiebre` se calcula justo después de `rotacion_sugerida` para cada SKU, antes del INSERT. Sin script separado. |
| **`stock_actual`** | `MAX(fecha)` por SKU individual + `SUM(cantidad)` de todos los depósitos en esa fecha. Cada SKU usa su último dato disponible, independientemente de la fecha del último ETL. |
| **Stock negativo** | Se trata como `0` → `dias_hasta_quiebre = 0`. Es un artefacto de timing del ETL, no un estado real. No se guardan valores negativos. |
| **Fórmula** | `max(0, stock_actual) / rotacion_sugerida`. Si `rotacion_sugerida` es NULL o 0 → `NULL`. Si stock = 0 → `0`. Resultado en `DECIMAL(10,2)`. |

> **Nota para frontend (#20):** `dias_hasta_quiebre = 0` significa quiebre ya (mostrar badge rojo). `NULL` significa que no hay datos suficientes para calcular (mostrar "—"). Valor positivo = días estimados hasta quiebre con la rotación actual.

### `GET /api/planilla/sugerencias` — Issue #18 (sesión 2026-06-07)

| Decisión | Definición |
|----------|-----------|
| **Paginación** | Sin paginación — devuelve todos los SKUs en un solo array. La tabla es plana (una fila por SKU) y el volumen es manejable (~200 KB sin comprimir). El frontend la carga una vez e indexa por SKU con `Map<sku, SugerenciaDto>`. |
| **Shape del response** | Array plano de objetos: `[{ sku, rotacionSugerida, fiabilidadPorcentaje, diasHastaQuiebre }, ...]`. No objeto indexado por SKU — el indexado lo hace el frontend. |
| **Campo `modelo`** | Excluido del response. YAGNI — el frontend no lo necesita y actualmente solo hay un modelo. Si en el futuro hay múltiples modelos, es un cambio de schema primero. |
| **SKUs con NULLs** | Se incluyen en el response. `rotacionSugerida = null` significa menos de 3 meses normales — señal explícita para que el frontend muestre "—" en columna ROT.S. |
| **Autorización** | `[Authorize]` heredado de `PlanillaController` — sin restricción de rol. Tanto `administrador` como `duenoDeEmpresa` pueden acceder. |
| **Ubicación** | Nuevo método `[HttpGet("sugerencias")]` dentro del `PlanillaController` existente. Sin controller separado. |

> **Nota para frontend (#19, #20):** el frontend carga este endpoint al montar `PlanillaPage` (una sola vez), lo indexa por SKU, y une los valores a cada fila de la tabla de planilla client-side. No hacer un request por página de planilla.

### Columna ROT.S en `PlanillaTable` — Issue #19 (sesión 2026-06-07)

| Decisión | Definición |
|----------|-----------|
| **Dónde se fetcha** | En `PlanillaPage` — hook `usePlanillaSugerencias` al mismo nivel que los filtros. Se construye `Map<sku, sugerencia>` y se pasa como prop a `PlanillaTable`. Un solo fetch para toda la sesión, independiente de paginación y filtros. |
| **Formato de celda** | Dos elementos apilados (opción A): número de rotación arriba (`2.9710`), badge de fiabilidad abajo (`78%` con fondo de color). |
| **Posición en tabla** | Última columna, después de DDSTK. Es el "veredicto" del sistema tras el contexto histórico. |
| **`fiabilidad = null`** | Mostrar `—` con clase `sin-datos`, igual que Rot. DesEstac. y DDSTK. No usar badge gris. |
| **`staleTime`** | `5 * 60_000` (5 minutos) — igual que `usePlanillaFiltros`. Datos cambian solo con el ETL nocturno. |
| **Loading state** | Skeleton `skel-60` en cada celda de AE mientras el fetch de sugerencias está pendiente. Distingue "cargando" de "sin datos". |
| **Colores del badge** | Verde (`#16a34a` bg suave) ≥70% · Amarillo (`#ca8a04` bg suave) 40–69% · Rojo (`#dc2626` bg suave) <40% |

> **Nota:** `rotacionSugerida = null` también muestra `—` sin badge. El badge solo aparece cuando `rotacionSugerida` tiene valor (aunque `fiabilidad` podría ser 0 — en ese caso badge rojo). El Map de sugerencias se construye en `PlanillaPage` con `useMemo`.

### Columna QBK en `PlanillaTable` — Issue #20 (sesión 2026-06-07)

| Decisión | Definición |
|----------|-----------|
| **Fuente de datos** | `diasHastaQuiebre` ya está en `PlanillaSugerenciaDto` cargado en #19. No hay nuevo endpoint ni hook — reutiliza el mismo `Map<sku, sugerencia>` de `PlanillaPage`. |
| **Ubicación en tabla** | Columna nueva separada, inmediatamente después de AE (última columna). |
| **Formato de celda** | Badge simple (opción B): número redondeado a entero + "d". Ej: `15d`, `5d`, `0d`. No apilado vertical. |
| **Umbrales de color** | Rojo = 0 (quiebre ya) · Amarillo > 0 y ≤ 15d (urgencia alta) · Verde > 15d (OK). |
| **Texto en `= 0`** | `0d` — consistente con el formato numérico. El rojo comunica la urgencia. |
| **`null`** | `—` con clase `sin-datos`, igual que AE y DDSTK. |
| **Nombre de columna** | `QBK` — sigue el patrón de abreviaturas del proyecto (VTA, DDSTK, AE). Tooltip explica el significado. |
| **Loading state** | Skeleton `skel-60` igual que AE — reutiliza `sugerenciasLoading` ya disponible en `PlanillaTable`. |

> **Nota:** el umbral de 15 días es el lead time típico de reposición para productos de tecnología. Es arbitrario y documentado en el tooltip para que el cliente lo entienda.

### `DashboardPage.tsx` — Issue #22 (sesión 2026-06-10)

| Decisión | Definición |
|----------|-----------|
| **Causa raíz** | `DashboardPage` llamaba a `searchJobs()` (→ `GET /api/jobs`) sin condición de rol. El endpoint es admin-only, retorna 403 para `duenoDeEmpresa`, y el interceptor Axios mostraba el toast. |
| **Fix** | `enabled: isAdmin` en ambos `useQuery` de jobs. El bloque de estado ETL en la stats bar también se wrappea en `{isAdmin && ...}`. |
| **Scope** | Solo `DashboardPage.tsx`. No se tocó el interceptor Axios ni el `RequireAdmin` — ambos funcionaban correctamente. |
| **Visibilidad para duenoDeEmpresa** | El home muestra: bienvenida, "X módulos disponibles", "Acceso completo" (solo admin). Sin estado ETL para no-admins — no es info relevante para ellos. |

> **Nota:** Si en el futuro se agregan más `useQuery` en páginas accesibles a ambos roles que llamen a endpoints admin-only, aplicar el mismo patrón `enabled: isAdmin`. El interceptor NO se debe tocar para suprimir 403 globalmente — es una señal válida para acciones reales del usuario.

---

### Plan Fase 3 — Ajustes cliente v2 (sesión 2026-06-09)

| Issue | Capa | Título | Depende de | Estado |
|-------|------|--------|------------|--------|
| #22 | Frontend/Bug | Toast "Prohibido" para duenoDeEmpresa | — | Listo para arrancar |
| #23 | Frontend | Columnas Vta.Mes/Año en PlanillaTable | — | Listo para arrancar |
| #24 | ETL+DB | Estado artículo A/D desde SOAP | XML del cliente | **BLOQUEADO** |
| #25 | Backend | Exponer estado en GET /api/planilla/ventas | #24 | Bloqueado por #24 |
| #26 | Frontend | Columna Estado Artículo en PlanillaTable | #25 | Bloqueado por #25 |
| #27 | Python+DB | 3 niveles de quiebre por frecuencia de venta | — | Listo para arrancar |
| #28 | Frontend | Colores y cálculo por nivel de frecuencia | #27 | Bloqueado por #27 |
| #29 | Frontend | Fix exportPlanilla.ts (todas las columnas) | #23, #26, #28 | Bloqueado por deps |
| #30 | ML | Auditoría modelos de predicción | — | Separado del sprint |

**Decisiones clave de esta sesión:**

| Decisión | Definición |
|----------|-----------|
| **Estado Art. desde SOAP** | El SOAP expone solo `A` (activo) y `D` (discontinuo). `inactivo` sigue siendo derivado por ausencia en el feed — lógica ya existente de issue #3. |
| **`Rot. Manual`** | Columna presente en el CSV del cliente (override manual de rotación). Fuera de scope para esta fase. |
| **Issue #30** | Es auditoría/investigación, no feature. No bloquea ni es bloqueado por ningún otro issue. Si el audit da luz verde, se abre issue #31 para surfacear la fiabilidad en planilla. |
| **Umbrales de frecuencia (#27)** | Se definen al arrancar el issue, en conjunto con el cliente/equipo. No están hardcodeados aún. |

### `Rot. DesEstac.` — Issues #31 y #32 (sesión 2026-06-10)

| Decisión | Definición |
|----------|-----------|
| **Columnas afectadas** | Solo la columna resumen `Rot. DesEstac.`. Las 13 celdas mensuales siguen mostrando `rotacionDiariaReal` sin cambios. |
| **Fórmula Fase 2** | `avg(rotacionDiariaDesestacionalizada para meses normales, excluyendo mes de referencia)`. Si ningún mes tiene valor → `—`. |
| **Fuente del factor estacional** | SOAP provee `Mes01`–`Mes12` por SKU. Se almacenan como 12 columnas en `articulos` (`factor_mes_01`…`factor_mes_12`). Un factor por mes del año calendario. |
| **Cálculo en ETL** | `rotacion_diaria_desestacionalizada = rotacion_diaria_real / factor_mes_{MM}`. Si factor es NULL o 0, queda NULL. Se calcula en `run_calc_planilla.py` con preload dict de `articulos`. |
| **`factor_estacional`** | Se mantiene sin cambios — sigue almacenando el factor del mes actual (escalar, issue #3). Issue #31 agrega las 12 columnas nuevas sin tocar este campo. |
| **Lookup strategy en ETL** | Preload dict al inicio de `calcular_filas`: `SELECT sku, factor_mes_01…factor_mes_12 FROM articulos` → dict `factors[sku][1..12]`. Lookup O(1) por fila. Sin JOIN dinámico en SQL. |
| **C# modelo** | Sin cambios en `Articulo.cs` ni `EvalutiaDbContext.cs`. Las 12 columnas son ETL-internas. El backend lee `rotacion_diaria_desestacionalizada` de `planilla_ventas_calculada` (ya mapeado). |
| **Scope del cálculo ETL** | `rotacion_diaria_desestacionalizada` se calcula para toda fila donde `rotacion_diaria_real != NULL` (normal y quiebre_parcial). `sin_stock` queda NULL (ds==0 → rot_real==None). |
| **`calcRotDesEstac` (#32) — meses normales** | Usa `rotacionDiariaDesestacionalizada`. Si es NULL (factor no disponible), ese mes se omite del promedio — sin fallback a `rotacionDiariaReal`. |
| **`calcRotDesEstac` (#32) — meses quiebre_parcial** | Opción C: `rotacionAjustada * (rotacionDiariaDesestacionalizada / rotacionDiariaReal)`. Fallback a `rotacionAjustada` si `rotacionDiariaDesestacionalizada` es NULL. Omitir si `rotacionAjustada` es NULL. |
| **`calcRotDesEstac` (#32) — sin valores** | Si `vals.length === 0` → mostrar `—`. Sin fallback ni mezcla de valores desestacionalizados/no-desestacionalizados. |
| **Tooltip (#32)** | "Rotación diaria promedio corregida por estacionalidad.\nMeses normales: rotación real ÷ factor estacional del mes.\nMeses con quiebre: rotación ajustada por frecuencia × factor estacional.\nExcluye el mes de referencia." |
| **Migración** | `09-articulos-factores-mensuales.sql`: `ALTER TABLE articulos ADD COLUMN factor_mes_01 DECIMAL(5,3) NULL, …, ADD COLUMN factor_mes_12 DECIMAL(5,3) NULL`. |
| **Orden de implementación** | Primero Issue #31 (migración DB + ETL), luego Issue #32 (frontend). El cambio frontend no tiene efecto visible hasta que el ETL pueble el campo. |

> **Nota:** La migración `07-articulos-factor-estacional-estado.sql` (que agrega `factor_estacional` y `estado` a `articulos`) aún no está aplicada en producción. Para prod, aplicar `07` primero, luego `09`. En dev, solo `09` (07 ya aplicada). `run_extract_articulos.py` necesita actualizar INSERT + ON DUPLICATE KEY UPDATE con los 12 nuevos campos. El TODO en `run_calc_planilla.py` línea 216 se rellena con el preload dict.

### `Vta.Mes/Año` en PlanillaTable — Issue #23 (sesión 2026-06-10)

| Decisión | Definición |
|----------|-----------|
| **Columnas nuevas** | 13 columnas `Vta.Ene/25`…`Vta.Mes/Año` insertadas ANTES de las 13 columnas de rotación mensual. |
| **Datos** | `mes.ventasCantidad.toLocaleString('es-UY')` — entero, formato locale UY. |
| **Estilo** | Mismo `estadoMesBg(mes.estadoMes)` que la columna de rotación correspondiente. Mes de referencia con italic/opaco. |
| **Export en #23** | No se toca `exportPlanilla.ts` en este issue. El export completo se reescribe en Issue #29 cuando todas las columnas nuevas estén definidas. |

> **Nota:** Solo se modifica `PlanillaTable.tsx`. El `totalCols` pasa de `3 + n + 4` a `3 + n*2 + 4`.

### Frecuencia de quiebre — Issues #27 y #28 (sesión 2026-06-10)

| Decisión | Definición |
|----------|-----------|
| **Métrica de frecuencia** | Cantidad de meses con `ventas_cantidad > 0` en los 12 meses cerrados (excluye mes de referencia). `sin_stock` queda excluido naturalmente (0 ventas por definición). |
| **Umbrales** | Alta ≥ 9 meses · Media 4–8 meses · Baja ≤ 3 meses. Revisables con Daniel (economista del cliente) cuando esté disponible. |
| **DB schema** | Option B: mantener `estadoMes = quiebre_parcial` + agregar `frecuencia_nivel ENUM('alta','media','baja') NULL` y `rotacion_ajustada DECIMAL(10,4) NULL` a `planilla_ventas_calculada`. `frecuencia_nivel` es atributo del SKU (mismo valor en todas sus filas). |
| **Fórmulas por nivel** | Alta: `ventas / dias_con_stock` (igual que hoy) · Baja: `ventas / dias_naturales_mes` · Media: promedio de ambas. Se aplica SOLO en meses `quiebre_parcial`; meses `normal` y `sin_stock` no cambian. |
| **Rot. DesEstac. (Issue #28)** | Incluir meses `quiebre_parcial` usando `rotacion_ajustada` además de los meses `normal`. Actualmente solo usa meses normales. |
| **Colores frontend (#28)** | `quiebre_parcial + alta` → amarillo (igual que hoy) · `+ media` → naranja · `+ baja` → rojo. `sin_stock` → gris (sin cambio). Referencia visual: el cliente usa amarillo en su planilla para quiebre → amarillo = alta (comportamiento conocido), escalando a colores más fuertes para frecuencias menores. |
| **Valor en celda mensual (#28)** | Siempre `rotacionDiariaReal` — no se modifica. Solo cambia el color de fondo. `rotacionAjustada` se usa únicamente en `calcRotDesEstac`, no en la celda individual. |
| **`calcRotDesEstac` (#28)** | Incluye meses `quiebre_parcial` usando `rotacionAjustada` además de los meses `normal`. Fórmula: `AVG(rotacionDiariaReal para normal ∪ rotacionAjustada para quiebre_parcial)`, excluyendo mes de referencia. Si `rotacionAjustada` es null en un quiebre, ese mes se omite del promedio. |
| **Leyenda (#28)** | 3 ítems separados en lugar del único "Quiebre parcial": `Quiebre alta freq` (amarillo) · `Quiebre media freq` (naranja) · `Quiebre baja freq` (rojo). |
| **Indicador de nivel en fila (#28)** | Solo el color de celda — sin badge ni columna adicional de `frecuenciaNivel`. La leyenda explica el código de colores. |
| **Tooltips de celdas mensuales (#28)** | Actualizar a: `"Amarillo = quiebre alta freq · Naranja = quiebre media · Rojo = quiebre baja freq · Gris = sin stock"`. |

> **Nota:** `frecuencia_nivel` y `rotacion_ajustada` se calculan en `run_calc_planilla.py`. Primero se calcula el nivel por SKU (sobre todos los meses), luego se aplica la fórmula correspondiente a cada fila de quiebre. El cambio visual y de Rot. DesEstac. queda para Issue #28 (Frontend).

### `run_extract_articulos.py` + `08-articulos-estado-discontinuo.sql` — Issue #24 (sesión 2026-06-11)

| Decisión | Definición |
|----------|-----------|
| **Campo SOAP** | `<Inactivo>` con valores numéricos: `0`=activo, `1`=inactivo, `2`=discontinuo |
| **Mapping** | `get_estado()`: `"1"→inactivo`, `"2"→discontinuo`, cualquier otro valor (incluido ausente) → `"activo"` |
| **ENUM** | `ENUM('activo','inactivo','discontinuo')` — 'discontinuo' agregado al final para compatibilidad MySQL |
| **Lógica de ausencia eliminada** | El `UPDATE SET estado='inactivo' WHERE sku NOT IN (...)` fue removido. El SOAP es fuente de verdad: envía los 3 estados en el feed nocturno completo |
| **ON DUPLICATE KEY UPDATE** | `estado = VALUES(estado)` — ya no se hardcodea `'activo'` en el upsert |

> **Nota:** el feed nocturno trae TODOS los artículos (activos, inactivos y discontinuos) con su `<Inactivo>` seteado. No existe el caso de "ausencia implica inactivo" — si un artículo no aparece es un error del SOAP, no un cambio de estado.

### `PlanillaRepository` + `PlanillaService` + DTOs — Issue #25 (sesión 2026-06-11)

| Decisión | Definición |
|----------|-----------|
| **Ubicación en response** | `estadoArticulo` en `PlanillaVentasOutDto` (nivel SKU), no en `PlanillaMesOutDto`. El estado no varía por mes. |
| **Fallback LEFT JOIN** | Si un SKU no tiene fila en `articulos`, `estadoArticulo = "activo"`. |
| **Nombre del campo JSON** | `estadoArticulo` — distingue del `estadoMes` que ya existe en cada mes. |
| **Archivos modificados** | `IPlanillaRepository.cs`, `PlanillaRepository.cs`, `IPlanillaService.cs`, `PlanillaService.cs`, `PlanillaDtos.cs` |

> **Nota:** No se agregó filtro por `estadoArticulo` — el issue lo excluye explícitamente. Si se necesita en el futuro, el patrón a seguir es el mismo que `marcaId`/`generoId` (subquery en artículos).

---

### `PlanillaTable.tsx` + `exportPlanilla.ts` — Issue #26 (sesión 2026-06-11)

| Decisión | Definición |
|----------|-----------|
| **Visibilidad del badge** | Solo se renderiza badge para `inactivo` y `discontinuo`. Para `activo` la celda queda vacía — la ausencia de badge implica normalidad. |
| **Posición de columna** | Entre Género y VTA, tanto en la tabla como en el Excel export. Es metadata del artículo, no una métrica. |
| **Tratamiento de fila** | Sin opacidad ni fondo diferente. Solo el badge en la columna Estado; los números de la fila permanecen sin cambios. |
| **Filtro por estado** | Diferido. El #26 solo requiere mostrar el estado. Filtro = issue separado futuro. |
| **Excel export** | Sí, columna D (entre Género y VTA). Valor: string literal "activo" / "inactivo" / "discontinuo". |
| **CSS nuevo** | `planilla-badge--gris` para inactivo, `planilla-badge--naranja` para discontinuo. |

> **Nota:** El tipo `PlanillaVentasDto` en el frontend requiere `estadoArticulo?: string` (optional para compatibilidad con respuestas cacheadas antiguas).

---

### `exportPlanilla.ts` — Issue #29 (sesión 2026-06-11)

| Decisión | Definición |
|----------|-----------|
| **Sugerencias en el export** | Se pasan como parámetro `sugerencias: Map<string, PlanillaSugerenciaDto>` desde `PlanillaTable.handleExport`. No se hace fetch adicional — los datos ya están en caché de TanStack Query. |
| **Orden columnas mensuales** | Igual que la UI: todas las Vta.Mes juntas, luego todas las Rot.Mes. No alternado. |
| **Posición de VTA** | Al final, en el bloque de columnas resumen (después de las 26 columnas mensuales), como especifica el issue. |
| **Colores quiebre** | Tres colores distintos por `frecuenciaNivel`: alta → #FFCA28, media → #FFB74D, baja → #EF9A9A. Sin stock → #90A4AE. |
| **Columnas nuevas resumen** | ROT.S, Fiabilidad% y QBK con estilo summary (verde suave). Fiabilidad% con formato `0.0%`, QBK con `0.0 "días"`. |

> **Nota:** Tanto las celdas Vta mensual como Rot mensual reciben el mismo color de fondo por `estadoMes`/`frecuenciaNivel`.

---

### `Codigos Barras` en planilla — Issue #33 (sesión 2026-06-12)

| Decisión | Definición |
|----------|-----------|
| **Scope** | Solo `Codigos Barras`. `Rot. Manual` descartada permanentemente (no se implementará). |
| **Posición en tabla** | Columna scrollable, inmediatamente después de la sticky SKU/Desc, antes de Género. |
| **Valor vacío** | Muestra `—` igual que el resto de campos opcionales. No se oculta la columna si está vacía. |
| **Export Excel** | Incluida entre Descripción y Género. Campo vacío exporta como string vacío `""`. |
| **Fuente del dato** | Campo `Barcode` de `articulos` en DB, ya existente. Sin migración requerida. |

> **Nota:** Los gaps de `SIN STOCK`, `TOT STK` y `C/STK` del CSV del cliente son errores de fórmula Excel (`#NAME?`) que dependen de su propio sistema de stock. No son responsabilidad de Evalutia en esta fase.

---

### `webpage/index.html` — Auditoría responsive (sesión 2026-06-17)

| Decisión | Definición |
|----------|-----------|
| **Alcance** | Landing estática de presentación (`evalutia.net`), single-file HTML/CSS/JS sin framework. No confundir con el frontend React de la app (`app.evalutia.net`). |
| **Metodología** | Auditoría real con Playwright contra el sitio en vivo en 9 viewports (320px a 3840px/4K), no solo lectura de CSS. Script reusable en `playwright-verify/audit-responsive-evalutia.js`. |
| **Layout fluido** | Confirmado: cero overflow horizontal en los 9 tamaños probados gracias a grid fluido + `clamp()` tipográfico. Los dos breakpoints existentes (768px, 480px) son suficientes. |
| **Bug: flip-cards ilegibles en touch** | Las 6 tarjetas de "Características" dependían 100% de `:hover`, sin handler de `click`/`tap`. En cualquier celular/tablet el reverso (la explicación de cada feature) era inalcanzable. Fix: agregado `click` listener que togglea `.flipped`, conviviendo con el `:hover` de desktop y el `keydown` existente. |
| **Bug: modal de contacto sin scroll interno** | En viewports bajos (ej. 320×568) el modal medía más que el alto de pantalla y no tenía `overflow-y`, dejando el botón de cerrar fuera de la vista (`top:-33px`) y el submit parcialmente cortado. Fix: `.modal { max-height: calc(100svh - 48px); overflow-y:auto }`. |
| **Bug: logo roto en todos los dispositivos** | `<img src="assets/logo.png">` apuntaba a una carpeta `assets/` que no existe; el archivo real está en `webpage/logo.png` junto al HTML. 404 silencioso (oculto por `onerror`). Fix: corregida la ruta a `logo.png`. |
| **Mejora: sin navegación en mobile** | Por debajo de 768px los links de nav se ocultaban sin alternativa. Se agregó botón hamburguesa (`#nav-burger`) + dropdown (`#nav-mobile-menu`), visible solo `<=768px`. |
| **Verificación de regresión** | Re-corrida la auditoría completa post-fix: 0 overflow, 0 errores de consola, hover de desktop intacto, accesibilidad por teclado (`tabindex`/`aria-label`) intacta, breakpoint 767/768/769 sin solapamiento, sin overlap de nav en 320px. |

> **Nota:** Nada de esto requirió cambios en el backend, ETL ni en el frontend React de la app — es exclusivamente la landing estática. El script de auditoría queda versionado en `playwright-verify/audit-responsive-evalutia.js` para volver a correrlo cuando se quiera; las capturas de pantalla generadas son evidencia local, no se versionan.

---

### `run_calc_planilla.py` + `run_calc_sugerencias.py` — Issues #34, #35 (sesión 2026-06-17)

| Decisión | Definición |
|----------|-----------|
| **Causa raíz confirmada** | `clasificar_estado()` (línea 73-82) compara `dias_con_stock` contra `dias_naturales_mes` = total de días del mes calendario completo, incluso para el mes de referencia (en curso). A mitad de mes, `N/30` está casi siempre por debajo del 90% sin importar si el stock estuvo perfecto. Los meses cerrados no tienen el bug — validado contra producción (SKU I01088, jul-2025). |
| **Diseño elegido: NO agregar 4to valor a `estado_mes`** | `estado_mes` es `ENUM('normal','quiebre_parcial','sin_stock')` en `infra/sql/05-planilla.sql:24`, validado también por un `HashSet` hardcodeado en `PlanillaService.cs:9-10` y por el union type de `planilla.ts:10`. Agregar `'en_curso'` requeriría migración de schema + tocar 3 capas. Se descarta a favor de reusar `'normal'`. |
| **Regla para el mes de referencia** | En el loop de `calcular_filas()` (línea 216-240), call site único de `clasificar_estado()` (línea 237): si `(yr, mo) == mes_referencia` → `estado_mes = "normal"` si `dias_stock > 0`, sino `"sin_stock"`. Para todos los demás meses (cerrados), sin cambios — sigue llamando `clasificar_estado(ds, dn)` tal cual. |
| **Por qué se conserva `sin_stock` para el mes en curso** | Verificado: `dias_con_stock` se calcula con `COUNT(DISTINCT fecha)` sobre filas reales de `stock_diario` (líneas 169-190), acotado naturalmente por las fechas que de verdad existen en la tabla (no hay filas futuras). `dias_stock == 0` es un hecho ya consumado a cualquier día del mes, a diferencia del umbral del 90% que sí depende de cuántos días faltan transcurrir. Por eso se distingue: el 90% se bypasea, pero `sin_stock` se preserva. |
| **Impacto en frontend/export: ninguno** | `estadoMesBg()` (`PlanillaTable.tsx:12-20`) y `mesBgColor()` (`exportPlanilla.ts:18-26`) ya devuelven "sin color" para `'normal'` — no como fallback de un valor desconocido, sino como su rama explícita documentada. Al reusar `'normal'` en vez de inventar `'en_curso'`, cero cambios de código requeridos en frontend/export. |
| **Segundo consumidor afectado (mismo bug, no documentado en el pedido original)** | `run_calc_sugerencias.py:106-112` filtra `WHERE estado_mes = 'normal'` sin excluir el mes de referencia por `year`/`month`. Hoy funciona "por accidente" porque el mes en curso nunca es `'normal'` (el bug que se arregla). Una vez corregido el bug, este query empezaría a meter la rotación parcial del mes en curso al promedio de sugerencias de reposición — hay que excluirlo explícitamente ahí también. |
| **Cómo deriva cada script "cuál es el mes de referencia"** | `run_calc_planilla.py` y `run_calc_sugerencias.py` son procesos Python separados (invocados secuencialmente desde `job_etl_diario.kjb` vía wrappers `.sh` independientes, sin estado compartido en memoria). `run_calc_sugerencias.py` deriva el mes de referencia con `SELECT MAX(year), MAX(month) FROM planilla_ventas_calculada` en vez de recalcular con `dt.date.today()` — evita desincronización si el job corre a caballo de medianoche, y es consistente con el principio de anclar a datos reales en vez de la fecha del sistema. |
| **`ventana_meses()` parametrizable** | Se agrega un parámetro de fecha de referencia inyectable (default `dt.date.today()`) para poder testear cualquier día del mes (ej. día 1, día 17, día 28/30/31) sin esperar a que llegue. Va dentro del mismo issue del fix (#34) porque es lo mínimo necesario para escribir un test automatizado que lo verifique — separarlo dejaría el fix sin test reproducible. |
| **Backfill histórico: no se necesita** | `escribir_planilla()` (líneas 308-319) hace `DELETE FROM planilla_ventas_calculada` + `INSERT` completo de los 13 meses en una sola transacción cada corrida — no es upsert incremental. La próxima corrida normal del job (cron 3 AM o manual) recalcula todo desde cero con la lógica corregida. No hay estado histórico que sobreviva entre corridas. |
| **Umbral del 90% (`ESTADO_UMBRAL_NORMAL`)** | Se mantiene sin tocar en este fix. Ya estaba documentado como "arbitrario" en Issue #6 (`CONTEXTO.md` línea 266). La duda de si sigue siendo el correcto se separa en un issue de conversación con el cliente, sin código asociado. |
| **Caso I01088 jul-2025 (Excel cliente vs. sistema)** | Producción y entorno local coinciden entre sí, pero ambos difieren del Excel del cliente. No es un bug del sistema — se separa en un issue de comunicación con el cliente, sin cambios de código. |
| **Entorno local desincronizado** | Catálogo local incompleto (104 SKUs vs. cientos en producción) y datos topados en feb-2026. No es causado por este bug ni se corrige como parte de él, pero bloquea poder verificar el fix con datos completos — se separa en issue de infraestructura/sincronización. |

> **Nota:** El fix completo queda contenido a un único call site en `run_calc_planilla.py:237` (dentro del loop de `calcular_filas()`) más la exclusión equivalente en `run_calc_sugerencias.py`. Ningún archivo de frontend (`PlanillaTable.tsx`, `exportPlanilla.ts`) requiere cambios para este bug — confirmado, no asumido.

> **Gap detectado y cerrado:** la única validación contra producción hecha (SKU I01088, jul-2025) confirmó un caso **sin quiebre** — valida la clasificación `'normal'`, pero no prueba que un mes cerrado con `quiebre_parcial` real se pinte con el color correcto según `frecuenciaNivel`. Se agregó como criterio de aceptación a Issue #38: identificar al menos un SKU con `quiebre_parcial` real en un mes cerrado (post-sync) y confirmar visualmente el color correcto, antes de considerar el fix verificado end-to-end.

### `run_calc_planilla.py` — Implementación Issue #34 (sesión 2026-06-17)

| Decisión | Definición |
|----------|-----------|
| **Testing framework** | `pytest`, pero **solo como dependencia de desarrollo local** — no se agrega a `services/python-worker/requirements.txt` (el que instala el `Dockerfile` de `etl`) ni se corre en producción. Primer test real del repo; sienta el patrón para futuros scripts del ETL. |
| **Alcance del test** | Solo funciones puras en aislamiento: `ventana_meses(n, hoy=...)` y `clasificar_estado_mes(...)`. Sin mockear `pymysql` ni la conexión a MySQL — `calcular_filas()` no cambia de firma. |
| **`ventana_meses()`** | Gana parámetro opcional `hoy: dt.date \| None = None` (default `dt.date.today()` si no se pasa). Resto de la función sin cambios. |
| **Nueva función `clasificar_estado_mes()`** | Separada de `clasificar_estado()` (que queda intacta, sigue siendo "puro umbral"). Orquesta la excepción del mes de referencia: `"normal"` si `dias_stock > 0`, `"sin_stock"` si `dias_stock == 0`; para cualquier otro mes delega en `clasificar_estado()`. |
| **Call site del fix** | `calcular_filas()` línea 237: cambia `clasificar_estado(ds, dn)` por `clasificar_estado_mes(ds, dn, (yr, mo) == ultimo_mes)`, reusando la variable `ultimo_mes` ya existente (línea 137, = `meses[0]` = mes de referencia). |
| **Observabilidad** | `job_end()` detalle (jobs_historial) gana dos campos nuevos: `mes_referencia_normal` y `mes_referencia_sin_stock` — conteo de SKUs que cayeron en cada rama del override, para poder confirmar en producción que el fix se aplicó sin tener que consultar la tabla directamente. |
| **Ubicación de tests** | `services/etl/tests/test_run_calc_planilla.py` + `services/etl/tests/conftest.py` (3 líneas, agrega `services/etl/` a `sys.path` ya que `run_calc_planilla.py` es un script suelto, no un paquete). Sigue la convención de carpeta `tests/` ya esbozada (pero nunca usada) en `services/python-worker/tests/`. Deja lugar para los tests de #35 (`run_calc_sugerencias.py`) después. |
| **`run_calc_sugerencias.py` (Issue #35)** | No se toca en esta sesión — queda para su propio issue, con su propia exclusión del mes de referencia vía `SELECT MAX(year), MAX(month)` (ya decidido en la sesión anterior). |

> **Nota:** Ningún cambio de este issue toca `services/python-worker/requirements.txt`, el `Dockerfile` de `etl`, ni el `docker-compose.yml`. El test se corre localmente con `pip install pytest` + `pytest services/etl/tests/` desde el host, sin necesidad de Docker ni variables de entorno de MySQL (las funciones testeadas son puras, sin I/O).

### `run_calc_sugerencias.py` — Implementación Issue #35 (sesión 2026-06-17)

| Decisión | Definición |
|----------|-----------|
| **Implementado junto con #34** | Detectado un riesgo de ventana de deploy: `job_etl_diario.kjb` corre `CALC_PLANILLA` → `CALC_SUGERENCIAS` en la misma corrida nocturna. Si #34 se desplegaba solo, la primera noche ya contaminaba `rotacion_sugerida` con el mes en curso. Se implementó #35 en el mismo commit para no abrir esa ventana. |
| **Corrección sobre el diseño original** | La sesión anterior había propuesto `SELECT MAX(year), MAX(month)` para derivar el mes de referencia. Es **incorrecto**: si hubiera filas de dos años con distinto mes más alto, combina year y month de filas distintas. Se implementó con `SELECT year, month FROM planilla_ventas_calculada ORDER BY year DESC, month DESC LIMIT 1` — la combinación real más reciente. Con la ventana contigua de 13 meses no se manifestaría hoy, pero es la forma correcta. |
| **Nueva función `cargar_mes_referencia()`** | Devuelve `tuple[int,int] \| None` — `None` si la tabla está vacía (ej. antes de la primera corrida de `run_calc_planilla.py`), caso en el que `calcular_sugerencias()` no aplica ninguna exclusión. |
| **`calcular_sugerencias()`** | Gana parámetro `mes_referencia: tuple[int,int] \| None`. La query agrega `AND (year, month) != (%s, %s)` solo si `mes_referencia` no es `None`. |
| **Observabilidad** | `jobs_historial.detalle` gana `mes_referencia_excluido` (la tupla o `null`). |
| **Sin tests pytest para este issue** | A diferencia de #34, el cambio es casi enteramente construcción de query SQL — no hay lógica pura nueva que valga la pena aislar sin mockear `pymysql` (decisión ya tomada de no mockear DB en esta ronda). Se verifica con el checklist de integración/SQL manual, no con test unitario. |

> **Nota:** Único caller de `calcular_sugerencias()` es `main()`, ya actualizado. Sin otros consumidores en el repo.

### Umbral del 90% (`ESTADO_UMBRAL_NORMAL`) — Issue #36 (sesión 2026-06-17)

| Decisión | Definición |
|----------|-----------|
| **Se mantiene en 90%** | Sin cambios de código. `ESTADO_UMBRAL_NORMAL = 0.90` en `run_calc_planilla.py` queda igual. |
| **Naturaleza de la decisión** | **Provisoria, criterio interno/del consultor — no confirmada por el cliente.** Distinto de una validación real con el cliente. Si el cliente la cuestiona en el futuro, reabrir o crear issue nuevo puntual. |
| **Tooltip/leyenda en frontend** | Ya existe, no requirió trabajo nuevo. `PlanillaTable.tsx:143`, componente `Leyenda()`: `"Normal (≥90% días con stock)"`. Implementado como parte del Issue #11 (cerrado), antes de esta sesión — verificado en código, no asumido. |

> **Nota:** No confundir la numeración interna de `CONTEXTO.md` (issues #2–#33, anteriores a usar `gh issue create`) con los números reales de GitHub (#34 en adelante) — son el mismo proyecto pero "Issue #11" en este archivo y "issue #11" en GitHub coinciden numéricamente por coincidencia histórica, conviene verificar siempre contra `gh issue list` antes de asumir que algo sigue pendiente.

### Umbral del 90% → 100% — Issues #36/#37 reabiertos (sesión 2026-06-17, segunda parte)

| Decisión | Definición |
|----------|-----------|
| **Reabre y reemplaza la decisión anterior de #36** | "Mantener 90%" se cerró ese mismo día como decisión provisoria sin validar con cliente. Horas después, comparando el Excel real del cliente (`.xlsm`, vía `openpyxl`), se encontró evidencia dura que la contradice — ver siguiente fila. |
| **Metodología de verificación** | Se inspeccionó el `.xlsm` original del cliente (no el CSV exportado — pierde color de celda y comentarios) con `openpyxl`: 232 celdas con comentario "Dias de Quiebre N" en la hoja "Ventas", generadas automáticamente (comentario "SpreadsheetLight... a partir del documento importado", no es un Excel manual). |
| **Hallazgo: los números coinciden, el umbral no** | I01088 jul/25: 17 ventas ÷ 29 días con stock = 0.5862, idéntico a nuestra fórmula. La discrepancia original reportada (Excel cliente vs. sistema) **no era de cálculo** — nadie había comparado el color/clasificación, solo el valor de rotación. |
| **Criterio real del cliente: sin piso mínimo** | De las 232 celdas coloreadas como quiebre, el mínimo observado es **1 día de quiebre sobre 31** (96.8% de días con stock) — y se colorea igual. **0 casos** de "días de quiebre > 0" sin colorear. El cliente no usa 90%, usa: cualquier día sin stock = quiebre. |
| **Decisión: replicar el criterio del cliente** | `ESTADO_UMBRAL_NORMAL` cambia de `0.90` a `1.00` en `run_calc_planilla.py`. Con la fracción `dias_stock/dias_naturales >= 1.00`, equivale a `dias_stock == dias_naturales` — ningún cambio de lógica en `clasificar_estado()`, solo la constante. |
| **El sistema de 3 colores (alta/media/baja frecuencia) se mantiene** | El cliente solo usa amarillo para todo quiebre; nuestro sistema de Issues #27/#28 (amarillo/naranja/rojo según `frecuenciaNivel`) ya es una mejora sobre el de ellos. No se toca — coexiste con el nuevo umbral. |
| **`clasificar_estado_mes()` (fix de #34) no necesitó cambios** | Su rama para el mes de referencia (`"normal" if dias_stock > 0 else "sin_stock"`) nunca dependió de `ESTADO_UMBRAL_NORMAL` ni de `dias_naturales` — es agnóstica al valor del umbral por diseño. Verificado, no es casualidad. |
| **Efecto en cadena: `run_calc_sugerencias.py`** | Con el umbral más estricto, muchos menos meses califican como `'normal'`. Se amplió la query para incluir también `'quiebre_parcial'` (usando `rotacion_ajustada` en vez de `rotacion_diaria_real`), evitando que SKUs con algún quiebre puntual pierdan su `rotacion_sugerida` por debajo de `MIN_MESES_CON_DATOS` (renombrada de `MIN_MESES_NORMAL`). Verificado contra DB local: 82→83 SKUs elegibles (impacto chico en esta muestra por las limitaciones de #38; en producción con 13 meses reales el impacto esperado es mayor). |
| **Verificación en vivo del problema de #38** | Al correr contra datos locales reales, Feb/2026 (último mes con datos, por el hueco de sync de #38) pasó a mostrar `quiebre_parcial` en el 100% de los SKUs — porque el ETL local se cortó a mitad de mes y el sistema lo trata como "mes cerrado" (ya que el mes de referencia real, jun/2026, no tiene ningún dato). No es un bug del fix — es el síntoma exacto que #38 ya documentaba, ahora visible. |
| **Frontend** | Solo cambia el texto de la leyenda: `PlanillaTable.tsx:143`, de "Normal (≥90% días con stock)" a "Normal (100% días con stock)". Sin cambios de lógica de color — `estadoMesBg()`/`mesBgColor()` ya manejaban `'quiebre_parcial'`/`'sin_stock'` correctamente. |
| **Tests** | Casos actualizados a umbral 100%, incluyendo el caso real verificado (I01089 May/25: 1 día de quiebre sobre 31 → `quiebre_parcial`). 14/14 pasan. |

> **Nota para #37:** la conversación con el cliente cambia de enfoque — ya no es "avisarle de una discrepancia que tenemos que corregir", es "confirmarle que adoptamos su mismo criterio de quiebre (cualquier día sin stock cuenta) en vez del 90% que usábamos antes". Mostrarle el caso I01088 como demostración de que los números ya coincidían, y que el único cambio fue alinear el umbral visual.

> **Actualización post-implementación:** comparando el `.xlsm` real del cliente contra los datos YA cargados en local (no solo la fórmula), se encontró que para I01088 jul/25 los datos en sí difieren: cliente reporta 17 ventas / 29 días con stock, local tiene 16 ventas / 31 días con stock. La fórmula y el umbral ya están alineados, pero los **datos de base** no — y no se puede saber si es por el entorno local desincronizado (#38) o una diferencia real con producción, sin sincronizar primero. Esto eleva la prioridad de #38: ya no es "nice to have para verificar mejor", es el bloqueante real para cerrar #37 con certeza.

### Sincronización de entorno local — Issue #38 (sesión 2026-06-17, tercera parte)

| Decisión | Definición |
|----------|-----------|
| **Mecanismo: dump/restore, no re-correr el ETL** | El `WS_URL` en `.env` apunta al SOAP real de producción del cliente, no a un sandbox. Re-extraer todo desde `WS_START_DATE=2020-01-01` contra el webservice real generaría carga innecesaria y, peor, podría no coincidir exacto con lo que ya está calculado en `planilla_ventas_calculada` de producción — que es justamente contra lo que hay que comparar para #37. Dump/restore trae los mismos números que ya existen, sin recalcular nada. |
| **Acceso a producción** | El usuario no tiene acceso SSH/MySQL directo — hay que pedirlo a quien administre el hosting/firewall, habilitando la IP pública del usuario contra el puerto MySQL de producción. `docker-compose.yml:15-16` expone MySQL en el puerto `3307` (`ports: ["3307:3306"]`) sin restricción de IP en el archivo — la restricción real está a nivel de firewall/security group del hosting, no en Docker. |
| **Alcance del dump: 6 tablas, no la base completa** | `articulos`, `ventas_historicas`, `stock_diario`, `ventas_mensuales`, `planilla_ventas_calculada`, `planilla_sugerencias`. Se excluye `usuarios` (hashes de contraseñas reales — exposición innecesaria), `jobs_historial` y `predicciones` (no relevantes a la investigación de Planilla). |
| **FKs verificadas** | Solo `ventas_historicas`, `planilla_ventas_calculada` y `planilla_sugerencias` tienen FK a `articulos.sku`. `articulos` y `stock_diario` no tienen FKs salientes (`marca_id`/`genero_id` son columnas sin constraint) — las 6 tablas son autocontenidas, no se necesita traer tablas adicionales. Restore con `SET FOREIGN_KEY_CHECKS=0/1` alrededor para no depender del orden. |
| **Destino: pisar la base local directo** | No se crea un esquema/DB separado para comparación — el objetivo de #38 es que el entorno local *sea* equivalente a producción, no mantener dos copias. Los datos locales actuales son la misma salida del ETL pero incompleta, no hay nada curado a mano que preservar. |
| **Script reusable** | `scripts/sync_local_from_prod.sh` — corre `mysqldump` y el restore **dentro del contenedor `mysql` local** (no depende de tener cliente MySQL instalado en el host Windows). Variables de entorno `PROD_MYSQL_HOST/PORT/USER/PASSWORD/DB` requeridas, sin defaults para credenciales (fuerza a pasarlas explícitas, no quedan hardcodeadas en el repo). |
| **Flags de `mysqldump`** | `--single-transaction --quick --no-create-info --skip-triggers --no-tablespaces`. `--no-create-info` asume que el schema local ya coincide (mismas migraciones de `infra/sql/` aplicadas en ambos lados) — si no coincidiera, el restore fallaría por columnas faltantes, pero no es el caso esperado dado que ambos entornos corren desde el mismo repo. `--no-tablespaces` evita requerir privilegio `PROCESS` que el usuario de producción probablemente no tiene. |
| **Compatibilidad Windows/Git Bash** | El script exporta `MSYS_NO_PATHCONV=1` y `MSYS2_ARG_CONV_EXCL="*"` — sin esto, Git Bash traduce rutas estilo `/tmp/...` (destino del dump dentro del contenedor Linux) a rutas de Windows antes de pasarlas a `docker compose exec`, rompiendo el path. Encontrado y corregido durante el self-test. |
| **Self-test realizado** | Se corrió el script apuntando `PROD_MYSQL_*` a la propia base local (`127.0.0.1:3306` dentro del contenedor) como prueba de mecánica sin necesitar acceso real a producción todavía. Conteos antes/después idénticos (104 artículos, 927 filas de planilla) — confirma que dump+truncate+restore funcionan sin pérdida de datos. |

> **Nota:** el script todavía no se probó contra producción real — eso requiere que se resuelva el acceso de IP primero. Cuando se corra por primera vez contra prod real, validar especialmente el caso I01088 jul/25 contra el `.xlsm` del cliente para resolver la duda abierta de #37 (¿la diferencia de datos era del entorno local desincronizado, o existe también en producción?).

---

### `run_extract_sales_chunk.py/.sh` + backfill en producción — Issue #39 (sesión 2026-06-18)

| Decisión | Definición |
|----------|-----------|
| **Causa raíz (distinta de #34-#38)** | `stock_diario` se poblaba exclusivamente vía `ConsStockXml` — un endpoint de **snapshot** (stock actual, sin fecha real por registro) que `run_extract_stockxml.sh` estampa con `CHUNK_END` (la fecha de la ventana del loop) como si fuera la fecha real. `ConsStockVenta` (el endpoint que ya se usa para ventas) **también devuelve un campo `Stock` real por fecha**, pero se descartaba al hacer el merge — solo se copiaban `fecha, sku, cantidad, ts_carga, fuente`. Confirmado empíricamente comparando el Excel exportado de producción (174 celdas grises, 0 quiebre_parcial) contra el `.xlsm` del cliente (colores de quiebre parcial reales para SKUs con ventas). |
| **Fix: doble escritura en el script de ventas** | `run_extract_sales_chunk.py` agrega un segundo `INSERT ... ON DUPLICATE KEY UPDATE` hacia `stock_diario` usando el campo `Stock` ya presente en la respuesta de `ConsStockVenta`, condicionado a que `__FORCED_DEPOSITO` esté seteado (mismo patrón de loop por depósito que ya usa `run_extract_stockxml.sh`). `run_extract_sales_chunk.sh` exporta `__FORCED_DEPOSITO="${dep}"` antes de invocar el Python, igual que el script de stock. |
| **`ConsStockXml` no se elimina del job (Opción B, conservadora)** | Se mantiene como fallback en `job_etl_diario.kjb`. Como `RUN EXTRACT STOCKXML` corre **antes** de `RUN EXTRACT VENTAS` en el mismo hop sequence, y ambos upsertean a la misma clave única `(sku, fecha, deposito_id)`, el valor real de `ConsStockVenta` siempre sobreescribe al snapshot de `ConsStockXml` dentro de la misma corrida — sin necesidad de tocar/quitar el step viejo. |
| **Despliegue a VM — gotchas encontrados** | (1) Branch case-sensitive: `Develop` no `develop` — `git checkout develop` fallaba. (2) Tras `docker compose build etl`, el contenedor corriendo seguía con la imagen vieja (`grep` del código nuevo vacío) — `docker compose images` mostró `No such image` (referencia rota). Fix: `docker compose up -d --force-recreate etl`. |
| **Backfill histórico — por qué NO con `STEP_DAYS` simple** | `run_extract_stockxml.sh` sí soporta chunking por día vía `STEP_DAYS` (default 1) — sin overridearlo, recorre ~3650 días × 6 depósitos llamando a un endpoint que devuelve siempre la misma respuesta (snapshot), siendo pura pérdida de tiempo para un backfill histórico. `run_extract_sales_chunk.sh`, en cambio, **no tiene ningún chunking interno** — pasarle `FORCE_START=2016/FORCE_END=hoy` directo intentaría traer ~10 años en una sola llamada SOAP por depósito, con riesgo real de timeout/respuesta gigante. La receta documentada en el README (`STEP_DAYS=365`) solo resuelve el primer problema, no el segundo. |
| **Solución: chunking manual de 90 días por fuera del kjb** | Loop en bash (en el host, fuera de Pentaho) que invoca `run_extract_sales_chunk.sh` standalone (no el kjb completo) en ventanas de 90 días desde `03/10/2016` hasta hoy (~41 chunks). Validado primero con una ventana de prueba de 90 días (Ene-Mar/2020): 9.373 filas/depósito, 54 segundos, sin errores — extrapolado a ~35-40 min para el rango completo. Cada chunk escribe directo a `stock_diario` (vía el fix) y acumula en `ventas_historicas_stage`. |
| **Merge final manual** | Tras el loop, un único `INSERT ... ON DUPLICATE KEY UPDATE` de `ventas_historicas_stage` → `ventas_historicas` (la misma query que hace el step `MERGE STAGING -> VENTAS` del kjb, ejecutada a mano una sola vez al final en vez de repetirla 41 veces). |
| **Disparo de predict.py/calc_planilla/calc_sugerencias** | Se corrió el kjb completo una sola vez más, pero con `FORCE_START=FORCE_END=hoy` (ventana de 1 día) — la extracción se repite trivialmente rápido para hoy, y el job sigue su flujo normal hacia predict.py/calc_planilla/calc_sugerencias, que operan sobre **todo** el histórico ya cargado por el loop manual. Evita re-disparar la extracción de 10 años una segunda vez solo para llegar a los steps de cálculo. |
| **Backup previo (red de seguridad)** | `mysqldump --no-tablespaces` (el flag plano falla con "Access denied... PROCESS privilege" en MySQL 8 sin ese flag) de `stock_diario`, `ventas_historicas`, `planilla_ventas_calculada`, `ventas_mensuales` antes de tocar nada, guardado en `/opt/evalutia/backup_pre_fix_stock_<timestamp>.sql`. |
| **Gotcha de shell en la VM** | La sesión interactiva de AWS Session Manager corre como `sh`/`dash`, no `bash` — `[[ "$a" < "$b" ]]` con fechas ISO se interpretó como **redirección de archivo** (`<`/`>` siempre son redirección fuera de una `[[ ]]` real de bash), tirando `cannot open 2026-06-18: No such file`. Solución: comparar fechas convertidas a epoch (`date -d ... +%s`) con `[ ]` y `-le`/`-gt`, sin `<`/`>` ni `[[ ]]` — portable a cualquier shell POSIX. |
| **Validación post-fix** | `SELECT estado_mes, COUNT(*) FROM planilla_ventas_calculada GROUP BY estado_mes` → `normal=948, quiebre_parcial=89, sin_stock=302`. Antes del fix, `quiebre_parcial` era 0 en toda la tabla. Cierra el gap dejado abierto por la sesión de #34-#38 (que solo había validado un caso sin quiebre). |

> **Nota:** Este issue es independiente de #36/#37 (umbral 90%→100%) y de #38 (sync de entorno local) — aquellos asumían que `stock_diario` tenía datos históricos correctos y solo discutían el umbral de clasificación o la sincronización del entorno local; #39 corrige que los datos de base de `stock_diario` mismos eran incorrectos para fechas pasadas, independientemente del umbral usado. Con #39 resuelto en producción, vale la pena revisar si el caso I01088 jul/25 (la discrepancia de datos cliente-vs-sistema documentada en #37) se explica por este bug — ahora que `stock_diario` tiene datos reales por fecha, no snapshot.

---

### Incidente: `ventas_historicas` en cero en producción — Issue #39 ampliado (sesión 2026-06-18/19)

| Decisión | Definición |
|----------|-----------|
| **Qué pasó** | Al ejecutar el backfill histórico de #39 en producción, el merge `MERGE STAGING -> VENTAS (con snapshot)` del kjb (preexistente, sin relación con el fix de stock) dejó **toda la tabla `ventas_historicas` en `cantidad=0`** (365.238 filas, suma total 0). Se detectó porque el usuario comparó el export de producción contra el Excel del cliente y vio I01088 con `Vta=0` en los 12 meses, cuando el cliente reporta ventas reales todos los meses. |
| **Causa raíz** | `ventas_historicas` tiene clave única `(fecha, sku, fuente)` — **sin `deposito_id`**. El merge hace `INSERT...ON DUPLICATE KEY UPDATE cantidad=VALUES(cantidad)` fila por fila desde `ventas_historicas_stage`, que tiene **una fila por depósito** (6 depósitos × cada fecha+sku). Sin `GROUP BY`/`SUM`, cada depósito pisa el valor del anterior — el último depósito procesado en el loop (`S_DEPOSITOS=1,5,8,9,10,11`, el 11 al final) determina el valor final. Confirmado empíricamente: depósito 5 reportó `Venta=1` real para C00184/03-06-2025 mientras depósitos 1,8,9,10,11 reportaron `Venta=0` para el mismo SKU/fecha — el merge sin agregar dejaba 0. |
| **Por qué nunca se notó antes** | Con el cron incremental nocturno (ventana de ~7 días), el resultado dependía de qué depósito quedara "último" cada noche — a veces coincidía con el depósito de venta real por azar, dejando datos parcialmente correctos (de ahí los valores reales pero posiblemente ya incompletos en el backup). El backfill de #39, al procesar los 10 años con el mismo orden determinístico de depósitos en cada chunk, pisó sistemáticamente el 100% de la tabla con 0. |
| **Depósitos: confirmado con el usuario** | 1, 8, 9, 10, 11 son depósitos de logística/stock sin venta directa al público (reportan `Venta=0` consistentemente). Depósito 5 es el de venta real. Sumar `cantidad` across todos los depósitos es seguro — sumar ceros no infla nada. |
| **Fix aplicado** | `MERGE STAGING -> VENTAS (con snapshot)` en `job_etl_diario.kjb` (línea ~129): se agrega `GROUP BY DATE(s.fecha), TRIM(s.sku)` con `SUM(CAST(s.cantidad AS DECIMAL(12,3)))` en vez de seleccionar filas individuales sin agregar. `fuente` usa `MIN(s.fuente)` (todas las filas tienen la misma fuente en la práctica, MIN es solo para colapsar el grupo). Commit `af376b8`. |
| **Recuperación de datos** | Se restauró `ventas_historicas` desde el backup tomado *antes* del backfill (`mysqldump --no-tablespaces`, ver entrada anterior de #39) extrayendo solo esa tabla con `sed -n '/DROP TABLE.../,/UNLOCK TABLES/p'` del dump completo, para no perder el progreso de `stock_diario` (que no tenía este problema, al usar upsert real con `deposito_id` en su clave). |
| **Contaminación accidental del staging** | Las pruebas de diagnóstico (llamadas individuales por depósito, tests de ventana de un mes) insertaron filas extra en `ventas_historicas_stage` para fechas ya cubiertas (ene-mar 2020, primera semana y resto de jun/2025) — como el staging no dedupea (INSERT simple, no upsert), el merge con `SUM` las habría contado de más. Se resolvió truncando el staging y re-corriendo el backfill completo limpio, sin pruebas intercaladas. |
| **Interrupción por el cron nocturno** | El cron de Ofelia (3 AM, `TRUNCATE VENTAS_STAGE` como primer paso del job estándar) borró el staging de una corrida completa del backfill que quedó corriendo durante la noche, antes de poder mergearla manualmente. Lección: cuando se deja un backfill largo corriendo sin supervisión, conviene encadenar el merge en el mismo script (mismo proceso `nohup`) en vez de dejar un paso manual pendiente para "cuando vuelva", ya que el cron puede intervenir en el medio. |
| **Mecanismo para sobrevivir el cierre de sesión** | La sesión interactiva de AWS Session Manager mata los procesos hijos al desconectarse. Se usó `nohup bash -c '...' > log 2>&1 &` (sin `disown`, que no existe en `sh`/dash pero no es necesario — `nohup` ya alcanza) para que el backfill sobreviva el cierre de la terminal. |
| **Validación final** | I01088 jul/2025 post-fix: `ventas_cantidad=16, dias_con_stock=29, estado_mes=quiebre_parcial`. Cliente reporta 17 ventas / 29 días con stock — `dias_con_stock` coincide exactamente, `ventas_cantidad` a 1 unidad de diferencia (probable borde de fecha/zona horaria, no sistémico). Antes del fix completo, este mismo mes se calculaba `normal` con 30-31 días de stock. Distribución global sin cambios respecto al fix de stock (`normal=948, quiebre_parcial=89, sin_stock=302`, ya que esa clasificación depende de `stock_diario`, no de `ventas_historicas` — lo que cambió fue que las ventas dejaron de estar en cero). |

> **Nota:** Este merge sin agregación es un bug que pudo haber afectado la calidad de `ventas_historicas` desde que el sistema soporta múltiples depósitos, no algo introducido en esta sesión — el backfill de #39 simplemente lo expuso al 100% en vez de parcialmente. Vale la pena revisar si `ventas_mensuales` u otras tablas derivadas tienen agregaciones similares sin `GROUP BY` por las dudas, aunque no se encontró otro caso en esta sesión.

---

### Cierre de issues — sesión `/grill-me` (2026-06-19)

| Decisión | Definición |
|----------|-----------|
| **Issue #37 cerrado** | "[Cliente] Comunicar discrepancia SKU I01088" — la parte técnica se resolvió validando directo contra producción (no se esperó a #38): `dias_con_stock` coincide exacto (29=29), ventas a 1 unidad de diferencia (16 vs 17, aceptado como ruido no sistémico). La conversación real con el cliente queda fuera de GitHub, a cargo del usuario. |
| **Issue #39 cerrado** | "[QA] Verificar en producción el coloreado de quiebre" — es el issue que esta sesión completa resolvió: diagnóstico, fix de `stock_diario`, fix del merge sin agregación, backfill completo, validación SKU-por-SKU contra el Excel del cliente. |
| **Issue #40 creado** | Auditoría separada (no se hace en esta sesión) de si otras tablas/merges del ETL tienen el mismo patrón de falta de `GROUP BY` al colapsar datos multi-depósito hacia una tabla sin esa dimensión en su clave única. |
| **Issue #38 — baja de prioridad, no se cierra** | Ya no bloquea nada (su único bloqueo, #37, está resuelto). Se le quitó la label `blocker`. Sigue siendo útil para development futuro (testear sin tocar producción — justo el tipo de riesgo que se vivió hoy), pero sin urgencia. |
| **Issue #30 — sin tocar alcance, solo nota** | Se agregó comentario advirtiendo que cualquier RMSE/R² de modelos calculado *antes* de esta sesión no es comparable post-fix, porque el dataset de entrenamiento (`ventas_historicas`) cambió sustancialmente (de mayoría-cero a valores reales agregados). |

> **Nota:** Estado final de issues abiertos del proyecto tras esta sesión: solo #40, #38, #30 — ninguno bloqueante. #37 y #39 resueltos y cerrados con comentario de evidencia (queries SQL, comparación de Excel, logs de job) antes de cerrarse.

---

### `docs/Planilla_Reposicion_Guia_Cliente.docx` — Documentación para cliente (sesión 2026-06-20)

| Decisión | Definición |
|----------|-----------|
| **Audiencia** | Dueño de empresa, no técnico, pero con conocimiento de negocio retail (rotación, stock, lead time). Sin jerga estadística sin metáfora de negocio al lado. |
| **Flujo de revisión** | El documento primero lo revisa el padre del usuario (economista) antes de llegar al cliente. El padre sí entiende cálculos técnicos y quiere ver la lógica completa para poder auditarla. |
| **Estructura elegida** | Un solo documento (no documento + apéndice separado): cada concepto se explica primero en prosa simple y debajo se muestra la fórmula exacta, en el mismo flujo de lectura. |
| **Canal de referencia** | El cliente entra por la web app; el Excel exportado se menciona como opción pero no es el foco de las capturas/ejemplos. |
| **Fórmulas de rotación por frecuencia — confirmado** | Alta usa `ventas/días_con_stock` porque hay suficiente muestra real; baja usa `ventas/días_naturales_mes` para diluir el ruido de pocos días de venta real; media promedia ambas. Confirmado explícitamente con el usuario, no es solo inferencia del código. |
| **Umbrales de frecuencia (9 / 4–8 / 3 meses)** | Confirmado como **provisorios** — no validados aún con el economista del cliente (Daniel). Documentados como parámetro de negocio ajustable, no como regla fija, para no generar falsa precisión. |
| **Concepto "día con stock"** | Se incluye una nota breve explicando `stock_total_día > stock_mínimo` — es la base de todo el cálculo de quiebre y el cliente lo necesita para no confundirse con celdas de bajo stock que no cuentan como quiebre. |
| **Mes en curso** | Se explica proactivamente por qué nunca se pinta de quiebre a mitad de mes (el umbral del 100% se mediría contra el mes calendario completo, no los días ya transcurridos — daría falso positivo). |
| **Formato de salida** | Word (.docx), generado programáticamente con `python-docx` vía `docs/generar_doc_planilla.py` (no había `pandoc` ni LibreOffice disponibles en el entorno). Output: `docs/Planilla_Reposicion_Guia_Cliente.docx`. |

> **Nota:** El script `docs/generar_doc_planilla.py` regenera el `.docx` desde cero — no editar el `.docx` a mano si se va a volver a correr el script. Las decisiones de contenido (qué explicar, qué omitir, nivel de detalle) están en el script mismo como prosa; este registro es solo el resumen de las decisiones de diseño del documento, no su contenido completo.

---

### Ampliación a todos los grupos de productos — Issues #41-#47 (sesión 2026-06-23)

| Decisión | Definición |
|----------|-----------|
| **Terminología género vs grupo** | "Género" (campo ya existente, `genero_descripcion`) y "grupo" (PDF del cliente, ~70 categorías comerciales) son taxonomías distintas del ERP. Las planillas se separan por **grupo**; `genero_descripcion` queda como filtro secundario dentro de cada planilla, sin cambios — ya funciona. |
| **Catálogo `grupos` (tabla nueva)** | `id` (código del PDF), `descripcion`, `visible_planilla` (bool), `aplica_modelo_econometrico` (bool, `true` solo para 201). Seed único desde el PDF que mandó el cliente. |
| **Grupos 199 y 200** | Se cargan en la base igual que el resto (sin excepción en el ETL), pero con `visible_planilla = false` — no aparecen como filtro de planilla en la web. Decisión reversible con un `UPDATE`, sin redeploy. |
| **Cómo se taggea `grupo_id` por artículo** | No se confirmó que el SOAP de artículos devuelva el grupo en la respuesta (no se pudo verificar contra un payload real). En vez de depender de eso: se extrae un grupo a la vez (loop sobre los ~70 códigos del PDF) y se taggea cada inserción con el grupo pedido en el request — mismo patrón que ya usa `GROUPS="75 201"` en `run_etl_daily.sh`. |
| **Histórico de grupos nuevos** | Ventana fija: backfill único de "hoy − 2 años" hasta hoy, calculada una sola vez. Sin purga, sin rolling. De ahí en adelante el ETL incremental diario los trata igual que al grupo 201 (agrega desde `MAX(fecha)`, nunca borra). |
| **Modelos econométricos** | Siguen aplicando SOLO a SKUs con `grupos.aplica_modelo_econometrico = true` (hoy solo 201). El step `RUN PREDICT.PY` de `job_etl_diario.kjb:204-215` hoy NO pasa `--skus` ni `--top-n` a `predict.py`, así que toma TODO `ventas_historicas` sin filtro — hay que armar la lista desde `grupos` y pasarla con `--skus=...`. |
| **Orden de despliegue obligatorio** | El fix del worker (Issue #43) tiene que estar deployado y verificado **antes** de correr el backfill completo (Issue #44) en producción. Si se invierte el orden, el cron de las 3 AM de esa misma noche corre modelos econométricos sobre todos los SKUs nuevos de los 70 grupos. |
| **Rollout del backfill** | Corrida única, no por fases (decisión explícita del cliente, no recomendación). Salvaguardas acordadas: loop resumible por grupo (si falla a mitad, se puede continuar sin re-extraer lo ya hecho), corrida separada del cron diario de 3 AM, logging de éxito/fallo por grupo en `jobs_historial` (no un solo estado global para los 70 grupos). |
| **Filtro de planilla por grupo** | Se agrega como filtro nuevo en `PlanillaPage`, mismo patrón que `genero`/`marca` (ya existen y ya están probados en producción). El "~100 productos por planilla" mencionado por el cliente es una expectativa de tamaño, no un límite a forzar en código — no se implementa partición automática de grupos grandes. Si un grupo supera eso, el usuario combina filtros (grupo + género/marca) o pagina. |
| **Administración de la tabla `grupos`** | Sin endpoint/CRUD. Seed único vía script SQL + `UPDATE` manual a la base cuando haga falta tocar `visible_planilla` o `aplica_modelo_econometrico`. Es un catálogo que cambia muy rara vez (cuando el ERP agrega una categoría nueva). |
| **Deploy de esquema** | Script SQL nuevo numerado en `infra/sql/` (no hay migraciones EF Core en este repo — todo el esquema se mapea directo a SQL crudo), aplicado manualmente en prod igual que los cambios de esquema anteriores. |
| **`GET /api/planilla/filtros` (Issue #9) — ampliación dentro de #45** | Hoy devuelve TODOS los valores de género/marca del catálogo, sin acotar por grupo. Con 70 grupos, el dropdown de género pasa de ~22 a varios cientos de valores y permite combinaciones grupo+género que no existen. Se amplía para aceptar `grupoId` opcional y acotar género/marca a lo que existe dentro de ese grupo. No es issue nuevo, es alcance agregado a #45. |
| **Alcance explícito: solo planilla de reposición** | El cliente confirmó que este pedido es únicamente para la ventana de planilla de reposición. `/resultados` y el `DashboardPage` quedan **fuera de alcance** — van a seguir iterando sobre todos los artículos sin filtro de grupo, mezclando productos con y sin predicción econométrica. Es una decisión consciente, no un olvido; se revisita si el cliente lo pide o se nota como problema en producción. |

> **Nota:** Issue #43 (worker) bloquea el *momento de ejecución* de Issue #44 (backfill en prod), no su desarrollo — ambos se pueden codear en paralelo, pero #43 debe estar mergeado y verificado en prod antes de disparar #44. Numeración de issues continúa desde #41 porque #40 es el último real en GitHub (`gh issue list`), confirmado antes de asumir el próximo número (criterio ya documentado en la nota de la línea ~679 de este archivo).

---

### `10-grupos.sql` — Issue #41 (sesión 2026-06-23)

| Decisión | Definición |
|----------|-----------|
| **Seed real** | PDF del cliente adjuntado en la sesión (no estaba en el repo) — 66 grupos (códigos 5 a 92, más 199, 200, 201), texto preservado tal cual el PDF (sin normalizar mayúsculas/acentos), igual que el resto de columnas denormalizadas del esquema (`marca_nombre`, `genero_descripcion`, etc.). |
| **`articulos.grupo_id` con FK real** | A diferencia de `familia_id`/`genero_id`/`marca_id`/`seccion_id`/`temporada_id` (enteros sueltos sin `FOREIGN KEY` ni navegación EF Core, confirmado en `Articulo.cs`/`EvalutiaDbContext.cs`), `grupos` es el primer catálogo real del proyecto con FK (`fk_articulos_grupo`, `ON UPDATE CASCADE ON DELETE RESTRICT`, mismo patrón que `fk_ventas_articulo`). Justificación: `grupo_id` controla lógica de negocio crítica (`aplica_modelo_econometrico`) — un código huérfano no debe pasar desapercibido. |
| **Backfill de artículos existentes** | Incluido en el mismo script. `ADD COLUMN grupo_id INT UNSIGNED NOT NULL DEFAULT 201` aplica automáticamente 201 a los 104 artículos ya cargados (hoy el 100% son del único grupo procesado por el ETL hasta ahora). |
| **`DEFAULT 201` transitorio** | Tras el backfill, `ALTER TABLE articulos ALTER COLUMN grupo_id DROP DEFAULT` — verificado: un `INSERT` sin `grupo_id` falla (`ERROR 1364`). Evita que un bug futuro etiquete silenciosamente un artículo de otro grupo como 201. |
| **Mapeo EF Core** | Explícitamente **fuera de alcance** de este issue — solo el script SQL. `Grupo.cs`, `DbSet<Grupo>` y la propiedad `GrupoId` en `Articulo.cs` quedan para el primer issue que consuma la relación desde el backend (probablemente #45). |
| **Verificación** | Script aplicado y probado contra la base local: seed (66 filas), backfill (104/104 artículos en `grupo_id=201`), rechazo de FK inválida (`ERROR 1452`) y rechazo de insert sin `grupo_id` tras el `DROP DEFAULT`. |

> **Nota:** El archivo sigue el patrón de scripts de una sola ejecución (`07-articulos-factor-estacional-estado.sql`, `09-articulos-factores-mensuales.sql`) — se aplica manualmente en prod vía `docker exec evalutia-mysql mysql ...`. No requiere `IF NOT EXISTS` adicional porque `CREATE TABLE IF NOT EXISTS` ya cubre reintentos seguros para la tabla; los `ALTER TABLE` fallarían en una segunda corrida (limitación conocida de MySQL 8, ya documentada en el script 07).

---

### ETL ampliado a todos los grupos — Issue #42 (sesión 2026-06-23)

| Decisión | Definición |
|----------|-----------|
| **Bug bloqueante encontrado** | `run_extract_articulos.py` no incluye `grupo_id` en su `INSERT INTO articulos`. Como #41 dejó esa columna `NOT NULL` sin `DEFAULT`, el cron de esta misma noche iba a fallar en el primer upsert (`ERROR 1364`, ya reproducido contra la base local). Es el primer fix de #42, independiente del resto del diseño. |
| **`run_etl_daily.sh` es código muerto** | La cadena real de ejecución nocturna es `ofelia.ini` → `run_ofelia.sh` → `kitchen.sh job_etl_diario.kjb`, que llama **directo** a `run_extract_articulos.sh` / `run_extract_sales_chunk.sh` (sin loop por grupo). `run_etl_daily.sh` (el único script que sí loopea por grupo) no está conectado a nada — se **elimina** como parte de #42 en vez de resucitarlo. |
| **Dónde vive el loop por grupo** | Dentro de cada script (`run_extract_articulos.sh`, `run_extract_sales_chunk.sh`), mismo patrón que ya usa `run_extract_stockxml.sh` para iterar `S_DEPOSITOS` (`call_for_deposito()` + loop bash). Se agrega `call_for_grupo()` análogo. Necesario porque la estrategia de #41 ("taggear `grupo_id` con el valor pedido en el request") exige una llamada SOAP por grupo — un valor combinado tipo `IdGrupo=5,6,10` no permite saber a qué grupo perteneció cada fila devuelta. |
| **Fuente de la lista de grupos** | Se consulta `SELECT id FROM grupos` en runtime vía un helper nuevo `get_grupos.py` (pymysql, mismo patrón de conexión que los extractores existentes — el contenedor `etl` no tiene cliente `mysql` instalado). Evita una segunda fuente de verdad desincronizada de la tabla `grupos`. |
| **Override manual** | `get_grupos.py` respeta `GROUPS`/`GRUPOS` si vienen seteados explícitos en el environment (permite forzar un grupo puntual para debug o reproceso); si no están seteados, consulta la tabla. |
| **`run_ofelia.sh` y el kjb deben dejar de hardcodear el grupo** | `run_ofelia.sh` pasa hoy `-param:GRUPOS=201 -param:GROUPS=201` en cada corrida — si no se quita, el override siempre gana y la tabla `grupos` nunca se consulta en producción, dejando #42 sin efecto real. Se quita ese hardcode de `run_ofelia.sh` y se vacía el `default_value` de `GROUPS`/`GRUPOS` en `job_etl_diario.kjb`. |
| **`ConsStockXml` no necesita loop por grupo** | El parámetro `ID_GRUPO` está declarado en `run_extract_stockxml.sh` pero nunca se usa en el armado del request SOAP — confirmado que el WS no filtra por grupo ahí, ya trae stock de todos los artículos del ERP. Coherente con que `stock_diario` no tiene `grupo_id` ni FK a `articulos`. Sin cambios en ese script. |
| **Catálogo completo para grupos nuevos** | Los ~65 grupos nunca extraídos tienen artículos creados/modificados hace tiempo — una ventana incremental de "últimos 7 días" devolvería 0 filas para ellos, y sus SKUs nunca entrarían a `articulos`, rompiendo la FK de `ventas_historicas` cuando corra el backfill de ventas (#44). Se agrega como prerrequisito técnico de #42 (no es el backfill de ventas de 2 años, que sigue siendo #44). |
| **Detección de grupo nuevo: automática** | Antes de cada llamada, por grupo: `SELECT COUNT(*) FROM articulos WHERE grupo_id = G`. Si es `0` → `FechaDesde` muy vieja (pull completo). Si ya tiene artículos → ventana incremental normal. Resumible solo, sin paso manual: si la corrida de esta noche falla a mitad, la de la noche siguiente retoma los grupos que sigan en `0`. |
| **Manejo de fallos por grupo** | Continuar con el resto si un grupo falla (timeout, error del WS) — mismo patrón que el loop por depósito existente. Log por `stdout`/Pentaho, sin escritura nueva a `jobs_historial` (ningún script de extracción escribe ahí hoy; solo `calc_planilla`/`calc_sugerencias`). |
| **Volumen de llamadas SOAP** | El loop por grupo anidado en el loop por depósito sube las llamadas nocturnas de ventas de ~6 a ~396 (66 grupos × 6 depósitos), más 66 de artículos. Aceptado sin throttling — cron de 3 AM con margen horario, el WS ya soportó corridas de 41 chunks consecutivos sin problema (incidente de #39). Se ajusta con datos reales si aparecen timeouts en producción, no de antemano. |

> **Nota:** Este issue deja el sistema listo para que #43 (worker, filtra modelos econométricos a `grupos.aplica_modelo_econometrico=true`) y #44 (backfill histórico de ventas de 2 años) puedan ejecutarse sin romper la FK de `articulos`. El orden de despliegue sigue siendo: #41 → #42 → #43 (en prod) → #44.

> **Corrección post-mortem (sesión 2026-06-23, antes de #43):** la nota original de "#43 antes de #44" subestimaba el riesgo. `RUN PREDICT.PY` corre **todas las noches sin filtro**, no solo durante el backfill — en cuanto el cron real corra con #42 desplegado (sin el override `GROUPS=201`), la extracción incremental ya va a empezar a meter ventas de los grupos nuevos en `ventas_historicas`, y `predict.py` las va a tomar esa misma noche. El riesgo arranca en el momento en que **#42 corre de verdad en producción**, no en el momento en que se dispare #44. Mientras #43 no esté en prod, mantener `GROUPS=201` explícito en la invocación real del cron de la VM.

---

### `run_predict.sh` + `get_skus_modelo.py` — Issue #43 (sesión 2026-06-23)

| Decisión | Definición |
|----------|-----------|
| **Alcance** | 100% en `job_etl_diario.kjb` / scripts nuevos del lado del ETL. `predict.py` **no se toca** — ya soporta `--skus` (`parse_args` línea 49) y `load_series_by_sku_mysql` ya filtra por esa lista (mismo flag que usaba el notebook original). El bug está solo en que el kjb nunca lo pasaba. |
| **Extracción a wrapper** | El step `RUN PREDICT.PY` (hoy bloque inline en el XML del kjb con 11 argumentos hardcodeados) se reemplaza por una sola línea: `/app/services/etl/run_predict.sh`. Mismo patrón que `run_calc_planilla.sh`/`run_calc_sugerencias.sh` — necesario para poder testear la lógica nueva (construir la lista, manejar el caso vacío) de forma aislada con `docker exec`, como ya se hizo con `run_extract_articulos.sh` en #42. |
| **Helper de la query** | Nuevo `get_skus_modelo.py` (pymysql, mismo patrón que `get_grupos.py` de #42 — el contenedor `etl` ya tiene pymysql y de hecho ya tiene **todas** las dependencias de `predict.py` instaladas, porque hoy ya se invoca dentro del contenedor `etl`, no en `python-worker`). Query: `SELECT a.sku FROM articulos a JOIN grupos g ON g.id = a.grupo_id WHERE g.aplica_modelo_econometrico = TRUE`. Imprime SKUs separados por coma (formato que espera `--skus`, a diferencia del espacio que usa `get_grupos.py` para el loop bash). |
| **Override manual** | `get_skus_modelo.py` respeta `SKUS` si viene seteado en el environment (debug/reproceso puntual sin esperar la query real), igual que `GROUPS`/`GRUPOS` en `get_grupos.py`. Si no, corre la query. |
| **Lista vacía = abortar, no procesar todo** | `args.skus` es un string vacío `""` es *falsy* en Python — `only_skus = [...] if args.skus else None`, así que `--skus=""` equivale a no pasar nada, reintroduciendo silenciosamente el bug que #43 viene a cerrar. Si `get_skus_modelo.py` devuelve lista vacía, `run_predict.sh` aborta el step con `[ERROR]` visible en el log y **no invoca `predict.py`** esa noche. Preferible "no corrió nada" (se nota) a "corrió sobre todo el catálogo sin que nadie se entere". |
| **Lectura completa de `ventas_historicas` sin `WHERE`** | Hallazgo durante la sesión: `load_series_by_sku_mysql` (`ioworker/data.py:99-108`) hace `SELECT fecha, sku, SUM(cantidad) FROM ventas_historicas GROUP BY fecha, sku` sin filtro SQL, y recién filtra por `only_skus` **en memoria** con pandas. `--skus` evita entrenar modelos sobre SKUs de otros grupos (lo que pide el issue), pero no evita la lectura completa de la tabla. **No se toca en #43** — sin datos de cuánto pesa hoy (104 artículos), optimizar antes de medir es prematuro. Nota de seguimiento: revisar si el tiempo del job nocturno crece de forma notoria después del backfill de #44 (tabla mucho más grande). |
| **Verificación de no-regresión** | Hoy solo el grupo 201 tiene `aplica_modelo_econometrico=true` y es el único con artículos cargados (104). La lista que devuelva `get_skus_modelo.py` debe ser exactamente esos 104 SKUs — el comportamiento de `predict.py` no debería cambiar nada hoy, recién diverge cuando #42 traiga artículos de otros grupos. |
| **Observabilidad** | Sin trabajo adicional: `predict.py` ya registra `skus_procesados` en `jobs_historial.detalle` (línea ~470) independientemente de cómo se armó la lista — al pasar `--skus`, ese número va a reflejar el conteo restringido automáticamente. |

> **Nota:** Tras este issue, recién ahí queda seguro habilitar el cron real de la VM sin el override `GROUPS=201` (ver corrección de la nota de #42 arriba). Orden de despliegue: #41 → #42 (con `GROUPS=201` forzado en la VM) → #43 en prod y verificado → recién entonces sacar el override de #42 → #44.

---

### Despliegue a producción + verificación cron 3 AM — Issues #41+#42+#43 (sesión 2026-06-23/25)

| Verificación | Resultado |
|--------------|-----------|
| **Deploy VM** | `git merge --ff-only origin/Develop` (`c1260c1`), `10-grupos.sql` aplicado (66 grupos), `docker compose build etl` + `up -d --force-recreate etl`. Sin el override `GROUPS=201` quitado de antemano — el cron de esa misma noche ya corrió con el loop completo de #42 + filtro de #43 juntos (no hizo falta la ventana intermedia "solo #42 con override" descrita en la nota de #43, porque ambos llegaron a prod en el mismo deploy). |
| **Cron 3 AM 2026-06-25** | `job_etl_diario` completo, `failed: false`, 12m11s. Confirmado vía `docker logs evalutia-ofelia` (el output de `job-exec` de Ofelia queda en los logs del propio contenedor `ofelia`, **no** en `docker logs evalutia-etl` — gotcha nuevo para el próximo que verifique un cron). |
| **Extracción por grupo (#42)** | `grep -c "=== Grupo"` → 132 = 66 grupos × 2 scripts (`run_extract_articulos.sh` + `run_extract_sales_chunk.sh`). Cero líneas `FALLÓ`/`[ERROR]` reales (el único `ERROR` en el log es el `StdErr: Importing plotly failed` de Pentaho, ruido inofensivo ya visto en local). |
| **Catálogo resultante** | `articulos` pasó de 103 filas (todas `grupo_id=201`) a ~5500+ repartidas en ~60 `grupo_id` reales (5, 6, 10, 15… 92, 199, 200, 201). `grupo_id=201` quedó en 101 filas (vs. 103 antes — diferencia mínima, no investigada, no bloqueante). |
| **Filtro econométrico (#43)** | `SELECT a.grupo_id, COUNT(DISTINCT p.sku) FROM predicciones p JOIN articulos a ON a.sku=p.sku WHERE p.ts_generacion >= CURDATE() GROUP BY a.grupo_id` → **una sola fila, `grupo_id=201`, 76 SKUs**. Ningún SKU de los grupos nuevos recibió modelo econométrico — confirma que el fix de #43 funciona en producción, no solo en local. |
| **Columna real de fecha en `predicciones`** | Es `ts_generacion` (`DATE`), no `fecha_calculo` — confundible porque el nombre no sigue el patrón `ts_carga`/`fecha_inicio` del resto del esquema. Anotado para no volver a perder tiempo la próxima verificación. |

> **Nota:** Con esto, #41+#42+#43 quedan verificados de punta a punta en prod (no solo en local). El bloqueo de la nota de #43 para #44 (backfill histórico) está resuelto — #44 puede arrancar cuando se pida.

---

### `run_backfill_ventas.sh` — Issue #44 (sesión 2026-06-25)

| Decisión | Definición |
|----------|-----------|
| **Script nuevo, no reusar `run_extract_sales_chunk.sh` tal cual** | `services/etl/run_backfill_ventas.sh`, invocado manualmente (`docker compose exec etl /bin/bash /app/services/etl/run_backfill_ventas.sh`). No se cuelga de `job_etl_diario.kjb` ni de Ofelia — es 100% on-demand. Reusa el parser `run_extract_sales_chunk.py` para el insert, pero la orquestación bash es nueva porque el script actual asume "rango chico, una sola llamada SOAP" (sin chunking interno por fecha), incompatible con 2 años de una sola vez. |
| **Lista de grupos a procesar** | `SELECT id FROM grupos WHERE aplica_modelo_econometrico = FALSE` — excluye al 201 sin hardcodear el número, sin tocar `get_grupos.py` (que sigue usando el daily real intacto). |
| **Chunking de fecha** | Ventana de **30 días** por grupo×depósito (valor de partida, no hay precedente probado para rangos tan largos — el único precedente real, `CHUNK_DAYS=7`, era para un solo grupo). **Validar primero con una corrida piloto sobre un solo grupo chico** (`SELECT grupo_id, COUNT(*) FROM articulos GROUP BY grupo_id ORDER BY COUNT(*) ASC`) antes de lanzar los 65 grupos completos, para medir tiempo/payload real del WS con esa ventana y ajustar si hace falta. |
| **Rango de fechas fijo** | `FORCE_START`/`FORCE_END` ("hoy − 2 años" → "hoy") se calculan **una sola vez al arrancar el script**, no se recalculan por grupo — evita desalineamiento de ventana entre el primer y el último grupo procesado en una corrida de varias horas. `S_DEPOSITOS` reusa el mismo env var existente, sin cambios. |
| **Merge por grupo, inmediato** | Extract grupo G → `INSERT...ON DUPLICATE KEY UPDATE` solo las filas de ese grupo → `TRUNCATE ventas_historicas_stage` → siguiente grupo. **Corrección post-implementación:** el truncate-por-grupo no es necesario para la *corrección* del dato — se probó empíricamente que `cantidad = VALUES(cantidad)` reemplaza (no suma) y que, como cada SKU tiene un único `grupo_id` (FK), el `GROUP BY sku,fecha` del merge ya aísla los datos de cada grupo aunque el stage acumule varios sin truncar entre medio. La razón real es **performance**: sin el truncate, cada merge de grupo siguiente vuelve a escanear y re-agregar TODO el stage acumulado de los grupos ya procesados (no solo el suyo), haciendo cada iteración más lenta que la anterior a medida que avanza la corrida de los ~65 grupos. Se mantiene el truncate por esa razón, no por riesgo de duplicación. |
| **Resumibilidad** | Antes de procesar grupo G, chequear `jobs_historial` (`tipo_job='etl'`, `detalle.subtipo='backfill_ventas'`, `detalle.grupo_id=G`, `estado='exitoso'`) — si ya existe, saltear. Si la corrida falla a mitad, la siguiente retoma sin re-extraer los grupos ya completos. |
| **Manejo de fallos dentro de un grupo** | Igual que el patrón ya existente en el resto del ETL (`process_grupo` en `run_extract_sales_chunk.sh`): si un chunk/depósito falla, loguea `[WARN]` y sigue con el resto — no aborta el grupo. Se marca `fallido` en `jobs_historial` solo si hubo al menos un error, con el detalle de qué chunk/depósito específico falló (no un `fallido` genérico) para que el reintento por grupo completo tenga contexto. |
| **Exclusión mutua con el cron de las 3 AM** | Lock file (ej. `/app/data/backfill.lock`), creado al arrancar y borrado al terminar/fallar vía `trap`. `run_ofelia.sh` chequea el lock al inicio y aborta esa corrida del daily con mensaje claro en el log si existe, en vez de competir por `ventas_historicas_stage`. El mismo lock también previene dos corridas del propio backfill en simultáneo. |
| **Sin `predict.py`** | El backfill es estrictamente extracción + merge de ventas históricas. No dispara predicciones — `predict.py` ya filtra a `grupos.aplica_modelo_econometrico=true` (solo 201 hoy), así que correrlo por cada grupo nuevo sería un no-op costoso repetido 65 veces. Predicciones para SKUs de grupos nuevos quedan para otro issue (#47). |
| **`stock_diario` se backfillea como side-effect, a propósito** | `run_extract_sales_chunk.py` ya escribe `stock_diario` directo (sin stage) con cada respuesta de `ConsStockVenta`. El backfill de ventas automáticamente backfillea también el stock histórico de los grupos nuevos, sin código adicional — deseado: sin esto, `planilla_ventas_calculada` (#6) nacería con 2 años de `dias_con_stock=0` para esos grupos. |
| **Corrida piloto** | Mismo mecanismo de override que ya respeta `get_grupos.py` (env var `GROUPS`/`GRUPOS`) — sin flag nuevo. Como el script ya filtra por `aplica_modelo_econometrico=false`, si el piloto apuntara por error al 201 simplemente no haría nada. |

> **Nota:** Tras el backfill, `run_calc_planilla.py` (corre cada noche, TRUNCATE+INSERT completo) recalcula `planilla_ventas_calculada` automáticamente con el nuevo histórico en la corrida nocturna siguiente — no requiere disparo manual adicional. Predicciones para los grupos nuevos siguen bloqueadas hasta que se resuelva #47.

---

### Ejecución en producción + verificación — Issue #44 (sesión 2026-06-25/26)

| Verificación | Resultado |
|--------------|-----------|
| **Piloto previo** | Grupo 44 (1 SKU), 147s, sin errores — confirmó chunking/merge/lock/`jobs_historial` contra el WS real antes de lanzar los 65. |
| **Corrida completa** | Lanzada sin `GROUPS` override (los 65 grupos vía `grupos WHERE aplica_modelo_econometrico=FALSE`), con `nohup` por la `AWS Session Manager` (mata procesos hijos al desconectar, mismo gotcha que #39). Duración real ≈ 16-17hs — muy por encima de la estimación inicial de 2-4hs basada solo en el piloto (caso más liviano posible, 1 SKU); el tiempo por grupo escala fuerte con el volumen de SKUs/ventas de cada grupo, no con la cantidad de años. Grupos chicos (ej. 44) tardan ~2-3min; grupos grandes (ej. 200, el más pesado) tardaron 13.677s (~3.8hs) solos. |
| **Resultado primera pasada** | 63/65 `exitoso`, 2 `fallido` (grupos 15 y 24), cada uno con un único chunk/depósito puntual fallido por timeout del WS (`dep=5`, ventanas de fecha distintas) — no sistémico. |
| **Decisión: no acortar la ventana para acelerar** | Se evaluó achicar a "desde 2025" para los grupos restantes ante la demora, pero se descartó: la ventana de 2 años es decisión explícita del cliente (no parámetro técnico libre), y hubiera generado profundidad histórica inconsistente entre los grupos ya completos (2 años) y el resto (~1.5 años). Se dejó correr completo. |
| **Segunda pasada (retry)** | `GROUPS=15,24` — reprocesa el grupo completo desde cero (resumibilidad es por grupo, no por chunk, según diseño original). Ambos `exitoso` en el reintento (15: 2719s sin fallas; 24: 786s sin fallas) — confirma que los timeouts eran puntuales/transitorios, no reproducibles. |
| **Estado final** | 65/65 grupos con al menos un `exitoso` en `jobs_historial` (`COUNT(DISTINCT detalle->>'$.grupo_id')=65`). Los 2 registros `fallido` del primer intento quedan en el historial (no se borran), es esperado. |
| **Verificación de datos** | `ventas_historicas` total: 4.337.421 filas (incluye los 10 años de grupo 201 + los 2 años nuevos), rango global 2016-10-03 → 2026-06-26. Spot-check en grupos 15/24/200: 732 días distintos cada uno (731 esperados +1 por el desfasaje de un día entre la corrida original y el reintento al día siguiente — inofensivo, el merge es idempotente), rango 2024-06-25 → 2026-06-26, sin huecos. |
| **`stock_diario`** | Backfillado como side-effect en la misma corrida, sin trabajo adicional — confirmado funcionando ya en el piloto y heredado a la corrida completa. |

> **Nota:** Con esto, #44 queda resuelto en producción de punta a punta. Pendiente: #47 (predicciones para SKUs de grupos nuevos, hoy todavía sin modelo asignado) y la recalculación de `planilla_ventas_calculada` en el próximo cron nocturno (automática, sin disparo manual).

---

### Plan de trabajo — Migración a mTLS en Web Service SOAP (sesión 2026-06-25)

| Issue | Título | Tipo | Depende de |
|-------|--------|------|------------|
| #49 | Infra — almacenamiento/montaje de `cotech-prod.p12` + `ca.crt` en host AWS, volumen en `docker-compose.yml` (servicio `etl`) + `.gitignore` | infra | — |
| #50 | Config — variables de entorno mTLS en `.env` (rutas de cert + password), sin hardcodear el password en `run_ofelia.sh`; limpiar el `WS_URL` placeholder stale en `.env` | config | #49 |
| #51 | Código — declarar `CERT_PATH`/`CACERT_PATH`/`CERT_PASSWORD` como parámetros en `job_etl_diario.kjb`, pasarlos vía `-param` en `run_ofelia.sh` (incluyendo el switch de `WS_URL` a `https://`), y agregar `--cert/--cert-type/--cacert` en los 4 scripts curl (`run_extract_articulos.sh`, `run_extract_sales_chunk.sh`, `run_extract_stockxml.sh`, `run_backfill_ventas.sh`) | código | #49, #50 |
| #52 | Validación + corte — corrida manual coordinada con IT (Martín García, MG Soluciones IT) en horario de oficina, confirmar `200 OK`; recién ahí mergear/deployar a prod sin tocar el cron nocturno antes de pasar la prueba | proceso | #51 |
| #53 | Runbook — acceso de prueba desde terminal (PC/Mac, `cotech-dev.p12`) para el usuario y su socio, fuera del ETL automatizado | documentación | — |
| #54 | Plan de rollback operativo si el corte rompe el job nocturno | proceso | #52 |
| #55 (backlog) | Vigencia/rotación del certificado — sin fecha de vencimiento conocida todavía, solo anotado | monitoreo | — |

**Decisiones clave de esta sesión:**

| Decisión | Definición |
|----------|-----------|
| **Orden de ejecución** | Este plan arranca **después** de cerrar los issues en curso de la planilla — instrucción explícita del usuario, no se prioriza sobre eso. |
| **Wiring real de config (hallazgo)** | `WS_URL`/`MYSQL_*` no se leen de `.env` en runtime — llegan a los 4 scripts bash como parámetros declarados en `job_etl_diario.kjb`, inyectados por Pentaho al ejecutar cada entry `SHELL`, pasados explícitamente vía `-param` desde `run_ofelia.sh`. `CERT_PATH`/`CACERT_PATH`/`CERT_PASSWORD` deben seguir el mismo mecanismo de 3 puntos (kjb → run_ofelia.sh → script), no alcanza con solo `.env`. |
| **Seguridad del password del `.p12`** | `run_ofelia.sh` está trackeado en git y hoy hardcodea valores literales (`MYSQL_PASSWORD=evalutia`, `WS_URL=http://200.125.29.194:81`) directo en el comando. El password del cert **no** sigue ese patrón — va como `-param:CERT_PASSWORD=${CERT_PASSWORD}` expandido desde `.env` (gitignored), para no commitear el secreto real que entregó IT al historial de git. |
| **Scope Issue 2 — no se mezcla** | No se corrige el hardcodeo preexistente de `MYSQL_PASSWORD`/`WS_URL` en `run_ofelia.sh` como parte de este trabajo — es deuda técnica separada, decisión explícita del usuario para no inflar el diff de este cambio. |
| **Arquitectura Issue 3 — sin helper compartido** | Los 3 flags nuevos de curl (`--cert`/`--cert-type`/`--cacert`) se duplican en los 4 scripts, siguiendo el patrón de duplicación que ya existe hoy en el repo (no hay `common.sh` entre los scripts ETL). Se descarta crear un helper compartido — decisión explícita del usuario, consistente con no introducir abstracciones nuevas para 3 líneas. |
| **Issue "corte definitivo" no es código separado** | `ofelia.ini` confirma un solo job/contenedor (`evalutia-etl`), sin staging. El switch `http://` → `https://` **es** el mismo cambio del Issue 3 — no hay nada adicional que "cortar" en código. Se absorbe como gate de timing dentro del Issue 4: no mergear/deployar el cambio hasta que la corrida manual confirme `200 OK`. |
| **No existe "rollback a HTTP"** | El instructivo de IT confirma que el corte es del lado del servidor: a partir de la fecha de corte, el WS deja de aceptar HTTP sin importar qué hace nuestro script. El rollback real (Issue 6) es operativo, no de protocolo: pausar el cron / correr manual con `FORCE_START` al día siguiente si el mTLS falla — no mantener un fallback a `CURL_INSECURE`/HTTP, porque el servidor lo rechazaría igual. |
| **`.gitignore` con gap** | No excluye `*.p12`, `*.crt`, `*.pem` ni una carpeta de certs — se agrega en el Issue 1, para evitar commitear los certificados si se dejan en una carpeta del repo para montarlos como volumen. |
| **IPs de oficina, fuera del alcance del ETL** | IT optó por no fijar en el firewall las IPs dinámicas de la oficina del usuario (`186.50.179.252`) ni de su socio (`179.24.239.134`) — el acceso desde esas máquinas (solo pruebas manuales por terminal, Issue 5) queda cubierto únicamente por `cotech-dev.p12`, sin relación con el ETL en AWS (IP fija `3.150.104.146`, ya habilitada del lado de IT). |
| **Validación por IP, no por dominio** | El certificado del servidor de IT está emitido para `200.125.29.194` — usar esa IP exacta en la URL, no un nombre de dominio, en los 4 scripts y en cualquier prueba manual. |
| **Contacto de coordinación** | Martín García, MG Soluciones IT (+598 94 961 242) — referencia para coordinar la ventana de prueba del Issue 4. |

> **Nota de seguridad:** el mail con la contraseña real del `.p12` (compartida por IT) quedó en el historial de esta conversación de `/grill-me` — no se escribió en ningún archivo del repo ni se repite en este registro. Si este chat se exporta o se comparte, tratarlo como un secreto expuesto.

---

### Filtro de grupo en planilla de reposición + ampliación de `/api/planilla/filtros` — Issue #45 (sesión 2026-06-26)

| Decisión | Definición |
|----------|-----------|
| **Mapeo EF de `Grupo`** | Sin navigation property. `Articulo.GrupoId` queda como `uint` plano (mismo patrón que `MarcaId`/`GeneroId`), sin `HasOne/WithMany`. `Grupo.cs` se crea como entidad simple (`Id`, `Descripcion`, `VisiblePlanilla`, `AplicaModeloEconometrico`, `TsCarga`, `ActualizadoEn`) + `DbSet<Grupo>` en `EvalutiaDbContext`. El único precedente de navegación real en el repo (`Prediccion.Job`/`JobHistorial.Predicciones`) no se replica acá porque ningún código necesita `.Include(a => a.Grupo)`. |
| **Lista de grupos en el dropdown (`GetFiltros`)** | Mismo criterio que marca/género: cruzar contra SKUs presentes en `planilla_ventas_calculada`, más `WHERE g.visible_planilla = true`. Nunca se ofrece una opción que da resultado vacío. |
| **Scoping de marca/género por `grupoId` en `GetFiltros`** | El parámetro `grupoId` (opcional) acota las subqueries de marca y género a `WHERE a.grupo_id = grupoId` cuando viene seteado. |
| **Scoping de `articulosIncompletos` por `grupoId`** | El conteo de `sinMarca`/`sinGenero` también se acota a `grupo_id = grupoId` cuando viene seteado — si no, el aviso de datos incompletos pierde sentido al estar filtrando por grupo. |
| **Estado por defecto de `grupoId` sin seleccionar** | Sin preselección — la planilla sigue mostrando todos los grupos mezclados por defecto (igual que hoy), igual que la decisión ya tomada para `/resultados`/Dashboard. "Limpiar filtros" resetea `grupoId` a `undefined`, no a un valor por defecto. |
| **`visible_planilla = false` (grupos 199/200) no es un control de seguridad** | Es cosmético del dropdown, no se bloquea en el backend. `GET /api/planilla/ventas?grupoId=199` devuelve resultados igual si se pasa explícito — no hay dato sensible distinto entre grupos, y la nota original del issue ya describe `visible_planilla` como "reversible con un UPDATE, sin redeploy" (catálogo, no autorización). |
| **Interacción frontend: cambio de grupo limpia marca/género** | `handleFilterChange` en `PlanillaPage.tsx` limpia `marcaId`/`generoId` cuando cambia `grupoId`, para evitar combinaciones grupo+marca/género inválidas que ya no aparecen en el dropdown pero quedarían seleccionadas de un grupo anterior. `estadoMes` no se toca (independiente del catálogo). |
| **Orden del dropdown de grupo** | Alfabético por `descripcion`, igual que marca/género — no por `id` numérico del ERP. |
| **Sin columna "Grupo" en la tabla** | Alcance literal del issue: solo filtrar, no mostrar. No se toca `PlanillaSkuDto`/`PlanillaVentasOutDto`/`PlanillaTable.tsx`/`exportPlanilla.ts` para agregar `grupoNombre` por fila. Se revisita como issue aparte si el cliente lo pide al ver ~65 grupos mezclados sin esa referencia visual. |
| **`/api/planilla/sugerencias` no se toca** | Confirmado en código (`usePlanillaSugerencias()` sin params, `fetchPlanillaSugerencias()` sin query string) — devuelve todas las sugerencias sin filtro y el frontend las indexa en un `Map<sku, ...>` para lookup por fila ya renderizada. El filtro de grupo en `GetVentas` ya acota qué filas se muestran; las sugerencias de SKUs fuera de esa selección simplemente no se usan, sin necesidad de propagar `grupoId` a este endpoint. |

> **Nota:** Ningún flujo de este issue requiere tocar `predict.py`, `job_etl_diario.kjb` ni los scripts de ETL — es 100% backend (`PlanillaRepository`/`PlanillaService`/`PlanillaController` + `Grupo.cs`/`EvalutiaDbContext`) y frontend (`PlanillaPage`/`FiltrosPlanilla`/hooks/tipos de `planilla`). El script SQL de `grupos` y la FK ya están aplicados en prod desde #41.

---

### Selector de grupo en `PlanillaPage` — Issue #46 (sesión 2026-06-26)

| Decisión | Definición |
|----------|-----------|
| **Ya implementado por #45** | El alcance literal de #46 (dropdown de grupo, scoping de marca/género al elegir grupo, `exportPlanilla.ts` funcionando con el filtro aplicado) quedó cubierto en el mismo commit `d90e0ec` de #45 — no se agregó código nuevo en esta sesión. |
| **Referencia a Issue #12 en la descripción original, errónea** | El texto de #46 cita "mismo patrón UX que género/marca (Issue #12)", pero #12 es el coloreado de celdas por `estado_mes` (Q–AC), no tiene relación con dropdowns de filtro. Probable error de tipeo al redactar el issue (se quiso citar #9/#13). No se corrige el issue en GitHub, solo queda anotado acá. |
| **Coloreado de celdas (#12) para SKUs de grupos nuevos** | Confirmado en código que es génerico, sin gap: `estado_mes` y `frecuencia_nivel` se calculan en `run_calc_planilla.py` (líneas 270-317) por SKU individual, vía `INNER JOIN articulos` sin filtro de `grupo_id` — no dependen del modelo econométrico ni de ningún grupo en particular. El componente `estadoMesBg` (`PlanillaTable.tsx`) tampoco filtra por SKU/grupo. No se necesita código nuevo. |
| **Verificación pendiente, no bloqueante** | No se pudo verificar visualmente contra una SKU de un grupo nuevo porque localmente solo hay datos del grupo 201 (104 artículos). Se dejó como paso de checklist a correr contra producción, no como condición para cerrar el issue. |
| **Cierre del issue** | Se cierra #46 referenciando el commit `d90e0ec` de #45, sin esperar el resultado de la verificación en prod. |
| **Resultado de la verificación en prod (2026-06-26)** | `SELECT a.grupo_id, COUNT(*), SUM(estado_mes IS NULL), SUM(frecuencia_nivel IS NULL) FROM planilla_ventas_calculada p JOIN articulos a ... WHERE grupo_id NOT IN (199,200,201) GROUP BY grupo_id` → **0 nulls en ambas columnas en los 60 grupos nuevos con datos**, cientos de filas por grupo. Confirma que `run_calc_planilla.py` corrió sin excepciones por grupo tras el backfill de #44. Verificación visual en `app.evalutia.net` quedó como confirmatoria/opcional, no ejecutada — la combinación de código genérico (sin filtro de grupo en `estadoMesBg`) + datos sin nulls ya cierra el loop. |

> **Nota:** Acceso a producción es vía AWS Session Manager (sesión interactiva manual) — el asistente no tiene ese acceso, por lo que el paso de verificación en prod quedó con comandos exactos en el checklist para que lo corriera quien tiene acceso a la VM.

---

### Plan de verificación — Issue #47 (sesión 2026-06-26)

| Decisión | Definición |
|----------|-----------|
| **Mecanismo de ejecución** | Mismo patrón ya probado en #44/#46: el asistente prepara las queries SQL y comandos `docker compose exec`/curl exactos; el usuario los corre en la VM (AWS Session Manager) y pega el resultado para registrarlo acá. El asistente no tiene acceso directo a producción. |
| **Ítem 1 — filtro econométrico (solo grupo 201)** | Ampliado respecto al chequeo puntual de #43: no solo la corrida de esta noche, sino el historial completo de `predicciones` desde el deploy de #43 (2026-06-23) agrupado por `grupo_id` y por noche, para descartar que algún cron intermedio haya colado un grupo nuevo antes de que cerrara el backfill de #44 (2026-06-26). Más la confirmación puntual de la corrida de esta noche como cierre. |
| **Ítem 2 — filtro grupo/género/marca con datos reales** | Validación vía SQL + curl contra `GET /api/planilla/filtros?grupoId=X`, sobre 2-3 grupos representativos (uno chico, uno grande, uno con pocos género/marca distintos) — sin pasada visual en el navegador. El diseño de #45 ya está probado en código contra datos locales (104 artículos, un solo grupo real); esto valida los datos reales de prod (~5500 artículos en ~60 grupos) que no existían en ese entorno. |
| **Ítem 3 — performance del export** | Se prueba solo el grupo más pesado real en `planilla_ventas_calculada` (candidato: 200, el más pesado en el backfill de #44 por tiempo de extracción), filtrado por ese grupo — no el escenario sin filtro, que queda fuera del uso esperado (el cliente filtra antes de exportar, según la decisión de #45 de no forzar un límite de tamaño en código). Sin umbral numérico de tiempo: el criterio de "pasa" es que el `.xlsx` se descargue completo vía `exportPlanilla.ts` (todas las páginas), sin error de consola ni archivo truncado — no hay SLA de tiempo pedido por el cliente. |
| **Ítem 4 — grupos 199/200 ocultos del filtro** | Una sola query SQL sobre `articulos.grupo_id` + un curl a `GET /api/planilla/filtros` sin `grupoId`, sin verificación visual adicional en el dropdown — la lógica ya está probada en código desde #45 (`WHERE visible_planilla = true`); esto solo confirma que el dato en prod quedó poblado para 199/200 tras el backfill. |
| **Ítem 5 — `jobs_historial` del backfill #44** | Cerrado por referencia a la sesión de #44 (2026-06-25/26), sin query nueva — los 2 registros `fallido` reales (grupos 15 y 24) ya probaron en producción que el log identifica fallos individuales con detalle de chunk/depósito (no un estado genérico), evidencia ya documentada en este archivo. |
| **Protocolo ante hallazgos** | #47 es QA puro, sin alcance de código declarado. Si alguna verificación revela un bug real, se documenta acá y se abre un issue nuevo aparte (continuando la numeración real de GitHub) — no se arregla código dentro de esta sesión, mismo patrón que separó el fix de #43 del feature de #41/#42. |

> **Nota:** Issue #47 cierra el epic #41-#47 (ampliación a todos los grupos de productos). No bloquea ningún issue posterior conocido.

### Ejecución — Ítem 1, hallazgo real (sesión 2026-06-26)

| Verificación | Resultado |
|--------------|-----------|
| **Query histórica `predicciones` por noche/grupo desde 2026-06-23** | Dos filas: `2026-06-24, grupo_id=76, 2 skus` y `2026-06-25, grupo_id=201, 76 skus`. La noche del 25 ya sale limpia (coincide con lo documentado en la sesión de deploy de #41+#42+#43). |
| **Detalle de los 2 SKUs contaminados** | `I01497`/`I01512` (grupo 76, "FUENTE ATX ... ZUMAX"), modelo PROPHET, 4 filas cada uno, rango `ts_generacion` 2026-06-19 → 2026-06-24. Recibieron modelo econométrico varias noches antes de que el filtro de #43 quedara verificado limpio en prod. |
| **¿Sigue activo hoy?** | Sí — `MAX(ts_generacion)` para ambos SKUs sigue siendo 2026-06-24, nunca se sobreescribió porque dejaron de ser elegibles (`aplica_modelo_econometrico=false` para grupo 76). Si `/resultados`/Dashboard muestran la predicción más reciente por SKU sin filtrar por grupo, esos 2 productos exhiben hoy un pronóstico que nunca debió generarse. |
| **Acción tomada** | Issue nuevo [#57](https://github.com/Evalutia/App-Forecast/issues/57) — protocolo acordado para #47 (hallazgo real → issue aparte, sin tocar código en esta sesión). El alcance de la remediación (borrar filas, auditar rango más amplio, fallback en frontend) queda para una sesión de diseño dedicada a #57, no resuelto acá. |

### Hallazgo crítico — #45/#46 nunca se desplegaron a producción (sesión 2026-06-26)

| Verificación | Resultado |
|--------------|-----------|
| **Síntoma** | Ítem 2 de #47: `GET /api/planilla/filtros?grupoId=X` devolvió **el catálogo completo de marcas/géneros idéntico** para los grupos 200, 24 y 20, contradiciendo la SQL real (grupo 24 solo tiene 3 combinaciones género/marca, grupo 20 solo 1). |
| **Causa raíz** | No es un bug de código — `PlanillaRepository.cs:40-41`/`PlanillaService.cs`/`PlanillaController.cs:35-37` en el repo local aplican correctamente `WHERE a.GrupoId == grupoId`. El problema es que **el commit `d90e0ec` (#45) nunca llegó a producción**: `docker inspect evalutia-webapi` mostraba `Created: 2026-06-12`, `evalutia-webapp` mostraba `2026-06-15` — ambos 14-16 días *antes* de que el commit existiera (2026-06-26). #45/#46 se cerraron en GitHub basándose en verificación de código/diseño, sin el paso de deploy real (a diferencia de #41+#42+#43 y #44, que sí tienen su sesión de "Despliegue a producción" documentada). |
| **Acción tomada** | Deploy ejecutado en esta misma sesión, con confirmación explícita del usuario (no es deuda nueva, es completar un release que ya estaba aprobado): `cd /opt/evalutia && git merge --ff-only origin/Develop` (`841baaa → 1d80c9b`, fast-forward limpio, sin conflictos) → `sudo docker compose build webapi webapp` → `sudo docker compose up -d --force-recreate webapi webapp`. Ambos contenedores recreados a las 2026-06-26 20:41, healthy. |
| **Lección para próximos cierres de issue** | Cerrar un issue de backend/frontend en GitHub basándose en "el código ya está en Develop" no implica que esté en producción. A partir de ahora, cualquier issue que toque `apps/backend`/`apps/frontend` necesita su propia verificación de `docker inspect <container> --format='{{.Created}}'` contra la fecha del commit antes de cerrarse — mismo criterio que ya se aplicaba de hecho (sin estar escrito) para los cambios de ETL en #41-#44. |
| **Verificación post-deploy (ítem 2 de #47, repetida)** | `GET /api/planilla/filtros?grupoId=X` contra grupos 200/24/20 ya da resultados acotados que coinciden exactamente con la SQL real (ej. grupo 24 → géneros `BOTELLA TINTA CPT`/`INSUMOS DE RECARGA`/`TONER CPT`, marcas `ECOJET`/`GRAVITY Consumibles`/`{Sin Definir}`; grupo 20 → género `RECARGA DE TINTA`, marca `{Sin Definir}`). **Ítem 2 de #47: pasa.** |
| **Corrección de candidato para ítem 3 (performance export)** | El grupo 200 elegido originalmente como "más pesado" resultó ser `descripcion="Exportación Web"`, `visible_planilla=false` — uno de los dos grupos ocultos del dropdown (199/200), nunca seleccionable por un usuario real. Candidato correcto: grupo **50 — "PERIFÉRICOS"** (740 SKUs), el más pesado entre los `visible_planilla=true`. |
| **Ítem 3 — resultado** | Export de la planilla filtrada por grupo 50 descargado y abierto con `openpyxl`: 741 filas (1 header + 740 datos, coincide exacto con el conteo SQL), 13 columnas completas, sin truncar, archivo no corrupto. **Ítem 3 de #47: pasa.** |
| **Ítem 4 — resultado** | `grupos` 199 (`SIN VALOR PARA INVENTARIO`, 3 skus) y 200 (`Exportacion Web`, 2623 skus) confirmados en la base con `visible_planilla=0`. `GET /api/planilla/filtros` (post-deploy) devuelve ids `[5,6,10,...,92,201]` — ninguno de los dos aparece. **Ítem 4 de #47: pasa.** |

### Hallazgo adicional — `planilla_ventas_calculada` congelada una noche por el lock del backfill (sesión 2026-06-26)

Surgió al revisar por qué el export del grupo 50 (ítem 3) mostraba `Vta.Jun/26=0` en las 740 filas, cuando el baseline pre-rollout (grupo 201) tenía 71/103 filas con venta real en esa misma columna.

| Verificación | Resultado |
|--------------|-----------|
| **`ts_carga` de `planilla_ventas_calculada`** | Igual para grupo 50 y grupo 201: `2026-06-25 03:12` — toda la tabla (no solo grupos nuevos) quedó sin recalcular desde esa noche, un día completo de atraso para todos los grupos, incluido 201. |
| **`jobs_historial` (subtipo `calc_planilla`)** | Último `exitoso` es `id=82`, 2026-06-25 03:12, `skus_procesados=5535` pero `filas_insertadas=6771` (≪ 5535×13) — corrió ya con el catálogo completo de #42, pero antes de que el backfill de #44 completara para casi todos los grupos. **Sin ningún registro para 2026-06-26** — el cron de esa noche no llegó a ejecutar este paso. |
| **`jobs_historial` (subtipo `backfill_ventas`)** | El backfill del grupo 200 corrió de **2026-06-26 00:26 a 04:14** — atraviesa exactamente la ventana de las 3 AM del cron diario. El lock file de #44 (diseñado para evitar que backfill y cron compitan por `ventas_historicas_stage`) abortó el job diario completo esa noche, sin dejar registro `fallido` (el aborto ocurre antes de que cualquier script llegue a escribir en `jobs_historial`). |
| **Conclusión** | No es un bug — es el costo esperado de la salvaguarda de #44, ya documentada en su momento ("corrida separada del cron diario de 3 AM"). El backfill y sus reintentos (grupos 15/24) terminaron hoy a las 16:16, así que el cron de **2026-06-27 3 AM** debería correr limpio y recalcular `planilla_ventas_calculada` con el histórico completo de los 65 grupos nuevos — incluyendo `Rot. DesEstac.` solo si `articulos.factor_mes_XX` está poblado para esos SKUs (no verificado en esta sesión, pendiente revisar si sigue en `NULL` después del recálculo, ya que el factor estacional históricamente solo se calculó para el grupo 201 — issue #3). |
| **Pendiente de verificación** | Confirmar mañana (2026-06-27) que el cron corrió y que `planilla_ventas_calculada.ts_carga` para grupo 50 ya no muestra `2026-06-25`. Si sigue congelado, ahí sí corresponde abrir issue — señal de que el lock no se liberó o el cron tiene otro problema. |
| **Confirmación cruzada con export real de grupo 201** | Comparando los dos exports descargados el mismo día: grupo 201 (101 filas) tiene 13 columnas mensuales completas, `Vta.Jun/26≠0` en 71/101 (70%, igual que el baseline pre-rollout: 71/103), `Rot. DesEstac.` no nulo en 92/101 (91%), `QBK` no nulo en 81/101 (80%) — sano, sin cambios respecto al comportamiento histórico. Grupo 50 (740 filas) está en 0/740 en las cuatro métricas y solo tiene 1 columna mensual en vez de 13. Confirma que el síntoma está acotado a los grupos nuevos afectados por el timing del backfill — grupo 201 nunca dependió de él. |
| **Issue de seguimiento** | [#58](https://github.com/Evalutia/App-Forecast/issues/58) — verificación a correr el 2026-06-27: confirmar que `calc_planilla` corrió esa noche en `jobs_historial` y que `ts_carga`/meses de grupo 50 ya no muestran `2026-06-25`/1 mes. Incluye qué hacer si el cron vuelve a abortar (revisar si el lock de #44 quedó huérfano) en vez de asumir que se resuelve solo en otra noche más. |

### Cierre — Issue #47 (sesión 2026-06-26)

Los 5 ítems del alcance quedan resueltos: ítem 1 limpio desde el 2026-06-25 en adelante (contaminación previa documentada en issue [#57](https://github.com/Evalutia/App-Forecast/issues/57)); ítems 2, 3 y 4 pasan (ítem 2 requirió desplegar #45/#46, recién hecho en esta sesión); ítem 5 cerrado por referencia a la evidencia de #44. Hallazgo adicional (no en el alcance original, surgido del ítem 3): `planilla_ventas_calculada` quedó un día atrasada para todos los grupos por el lock del backfill — autoresoluble en el cron de 2026-06-27, con verificación pendiente. Issue #47 listo para cerrarse en GitHub, con esa verificación de seguimiento anotada.

---

### Remediación — Issue #57 (sesión 2026-06-26, continuación)

| Decisión | Definición |
|----------|-----------|
| **Auditoría completa, sin filtro de fecha** | `SELECT a.grupo_id, COUNT(DISTINCT p.sku), MIN(ts_generacion), MAX(ts_generacion) FROM predicciones p JOIN articulos a ON a.sku=p.sku WHERE a.grupo_id<>201 GROUP BY a.grupo_id` (toda la tabla, sin acotar a `ts_generacion >= 2026-06-23` como la auditoría original de #47) → resultado: **una sola fila, grupo 76, 2 SKUs, rango 2026-06-19 → 2026-06-24**. Cierra el punto 2 del issue ("¿auditar más?") con evidencia completa: no hay otra contaminación en ningún otro grupo ni en ninguna otra fecha, en toda la historia de `predicciones`. |
| **Impacto confirmado en código (antes de decidir borrar)** | `PrediccionRepository.GetUltimasBySku()` filtra por el último `job_id` de tipo `forecast` exitoso — **no** incluye estas filas (los jobs 63/78 no son el último job tras el fix de #43). Pero `ResultadosService.GetResumenGlobal()` (línea ~75-88) agrupa por `(Sku, Modelo)` **sin filtrar por job**, tomando la fila de mayor `ts_generacion` — sí incluye el R² de estos 2 SKUs en el promedio mostrado en Resultados. Y `GetStockAnalysis()` (línea 144-146) filtra `Predicciones` por `FechaPredicha >= today` **sin filtrar por job ni por grupo** — confirmado con datos reales que ambos SKUs tienen filas con `fecha_predicha` futura (2026-09-19/2026-09-24), por lo que su pronóstico Prophet contaminado se muestra hoy en la grilla de `/resultados`. |
| **Detalle exacto de las 8 filas afectadas** | `sku IN ('I01497','I01512')`, `job_id IN (63,78)`: <br>• I01497 — fecha_predicha 2026-06-19 (job 63, horiz.1, cant.529.61) / 2026-06-24 (job 78, horiz.1, cant.529.61) / 2026-09-19 (job 63, horiz.2, cant.494.69) / 2026-09-24 (job 78, horiz.2, cant.494.69), r2=0.6618 todas. <br>• I01512 — mismas 4 combinaciones job/horizonte/fecha, cant. 51.65/51.65/51.46/51.46, r2=0.9725 todas. |
| **Decisión: borrar las 8 filas, no preservarlas como histórico** | No son un hecho de negocio (como `ventas_historicas`) sino el *output* de un modelo que nunca debió ejecutarse — no tienen valor como registro histórico, la metodología en sí estaba mal. El rastro de auditoría completo (valores exactos arriba) ya queda preservado en este archivo y en el issue #57, sin necesidad de mantenerlas vivas en la tabla de producción donde siguen filtrándose a los dos cálculos de Resultados mencionados arriba. |

> **Nota:** no hace falta ningún resguardo de integridad referencial — `predicciones.job_id → jobs_historial.id` es la única FK relacionada y es la tabla padre (borrar de `predicciones`, el hijo, no afecta a `jobs_historial`).

| **Ejecución del borrado (confirmado)** | `DELETE FROM predicciones WHERE sku IN ('I01497','I01512')` ejecutado en prod — `ROW_COUNT()=8`, verificación posterior `SELECT COUNT(*) ... = 0`. Las 2 SKUs ya no tienen ninguna predicción contaminada en `ResultadosService.GetResumenGlobal()` ni en `GetStockAnalysis()`. |
| **Punto 3 del issue — fix defensivo, no solo limpieza de datos** | En vez de dejar el gap arquitectónico para que se repita silenciosamente la próxima vez que un SKU pierda elegibilidad, se agregó `GetSkusElegiblesModelo()` (helper privado, `apps/backend/WebApi/Services/Resultados/ResultadosService.cs`) — mismo criterio que `get_skus_modelo.py` de #43 (`articulos JOIN grupos WHERE aplica_modelo_econometrico=true`). Se aplica como filtro adicional en `GetResumenGlobal()` (R² promedio, línea ~75) y `GetStockAnalysis()` (`PronosticoProximoTrimestre`, línea ~145) — los dos puntos confirmados en código que leían `Predicciones` sin ningún filtro de elegibilidad. `UltimaPrediccion` (timestamp informativo de "cuándo corrió la última predicción del sistema") se deja sin filtrar a propósito — no es un valor analítico por SKU, es un indicador de salud del job. `PrediccionRepository.GetUltimasBySku()` no se tocó porque ya filtra por el último `job_id` exitoso, no necesitaba el fix. Build verificado (`dotnet build WebApi.sln`, 0 errores). |
| **Deploy del fix** | Commit `50bdb24` pusheado a Develop, mergeado en prod (`git merge --ff-only`), `docker compose build webapi` + `up -d --force-recreate webapi`, recreado 2026-06-26 21:16. |

### Hallazgo no relacionado durante el smoke test post-deploy — Issue [#59](https://github.com/Evalutia/App-Forecast/issues/59)

Al verificar que el deploy no rompió nada (`GET /api/resultados/resumen`), la request **no respondió ni siquiera con 120s de margen** (`curl -m 120` → timeout, exit 28). El log de `evalutia-webapi` confirma que no es la query SQL (completó en 5021ms) sino, casi seguro, el código C# posterior en `GetResumenGlobal()` (`ResultadosService.cs` líneas ~43-51 y ~61-72): `foreach (var sku in skuSet) { stockRows.Where(r => r.Sku == sku) ... }` — patrón O(n²) trivial con 104 artículos (antes del rollout de #41-44) pero potencialmente catastrófico con ~5500. **No relacionado con el fix de #57** (que es una query chica y separada al final del método) — es un problema preexistente recién expuesto porque nadie había pegado contra este endpoint con el catálogo completo hasta este smoke test. Registrado como issue aparte, no se investiga el fix en esta sesión.

---

### Remediación — Issue #59 (sesión 2026-06-26, continuación)

| Decisión | Definición |
|----------|-----------|
| **Confirmación de escala con datos reales** | `articulos.stock_minimo > 0` → **4874 SKUs**. `stock_diario` últimos 365 días → 12.1M filas crudas (multi-depósito), agrupadas en SQL a ~1.8M filas antes de llegar a C#. El loop original hacía `4874 × ~1.8M` comparaciones lineales, **dos veces** (stockout y ventas perdidas por separado) ≈ 17 mil millones de comparaciones — confirma la causa con números, no solo lectura de código. |
| **Confirmado: solo `GetResumenGlobal()` tiene el antipatrón** | `GetStockAnalysis()`, `GetTopVentasPerdidas()` y `GetStockoutDistribution()` ya agrupan `stockRows` con `GroupBy().ToDictionary()` antes de iterar (mismo archivo) — el punto 3 del issue queda confirmado sin necesidad de cambios ahí. |
| **Fix: agrupar + fusionar los 2 `foreach` en uno** | `stockRows` se agrupa una sola vez en `stockPorSku` (`Dictionary<string, List<...>>`, mismo patrón que los otros 3 métodos). Los dos loops separados (stockout y ventas perdidas, que recalculaban `diasConStock` cada uno) se fusionan en un solo `foreach` por SKU. Complejidad pasa de O(totalSkus × totalFilas) a O(totalFilas + totalSkus) — de ~17 mil millones a ~1.8 millones de operaciones. Build verificado (`dotnet build WebApi.sln`, 0 errores). |
| **Deploy** | Commit pusheado a Develop, mergeado a prod (`git merge --ff-only`), `docker compose build webapi` + `up -d --force-recreate webapi`. |
| **Pendiente, fuera de esta sesión** | Sin profiling formal del tiempo real de respuesta post-fix más allá de un smoke test — si vuelve a ser lento, hay que medir con detalle en vez de asumir que el fix alcanza. Tampoco se agregó health-check/alerta para detectar este tipo de degradación a futuro (quedó anotado en el issue original como punto 8, no resuelto en esta sesión). |

---

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
