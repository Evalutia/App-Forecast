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

### El fix de código no resolvió el síntoma — causa real es infraestructura (sesión 2026-06-26, continuación)

Smoke test post-deploy del fix: `GET /api/resultados/resumen` siguió sin responder, ahora con timeouts de hasta 300s. Investigación encontró la causa de fondo:

| Verificación | Resultado |
|--------------|-----------|
| **Logs del contenedor durante el timeout** | `MySqlException: The Command Timeout expired before the operation completed` (`CommandTimeout=30`). `Program.cs:47` tiene `EnableRetryOnFailure(3)` — EF Core reintenta hasta 3 veces una query que ya viene fallando por timeout, multiplicando el tiempo total. |
| **`EXPLAIN` de la query de `stock_diario`** | `type: index` (no `range`) — escanea **25.99M filas** (toda la tabla), porque MySQL elige el orden del índice `idx_stock_sku_fecha` para satisfacer el `GROUP BY sku, fecha` en vez de filtrar primero por fecha. Hay índices de sobra (`idx_stock_fecha`, `idx_stock_sku_fecha`, etc.) — no es falta de índices. |
| **Prueba con `FORCE INDEX (idx_stock_fecha)`** | Cambia el plan a `type: range`, **13M filas** (acotado a los últimos 365 días, como se esperaba) — mejor plan, pero la query **igual tardó ~5 minutos** en ejecutar. `SHOW FULL PROCESSLIST` confirmó que no hay contención (ninguna otra query corriendo en simultáneo). |
| **Causa real: la VM no tiene memoria para el volumen de datos actual** | `free -h`: 1.9 GiB RAM total, 84 MiB libres, **1.0 GiB de swap en uso activo**. MySQL: `innodb_buffer_pool_size=128MB` (ínfimo para una tabla de 24.75M filas) y `tmp_table_size`/`max_heap_table_size=16MB` (el `GROUP BY` de esta query produce ~2M filas, excede ese límite y se convierte en tabla temporal en disco). Esta configuración estaba bien para el catálogo original (104 artículos) pero quedó obsoleta tras el rollout de #41-44 (~5500 artículos, 24.75M filas en `stock_diario`). |
| **Conclusión** | El fix de C# de esta sesión (agrupar en `Dictionary`) es una mejora real y se mantiene desplegado — elimina trabajo innecesario en la app. Pero **no alcanza por sí solo**: el cuello de botella real es de infraestructura (RAM + configuración de MySQL), no de código de aplicación ni de índices de base de datos. |
| **Acción tomada** | Issue nuevo [#60](https://github.com/Evalutia/App-Forecast/issues/60) (CRÍTICO) para la decisión de infraestructura (subir RAM de la VM, ajustar `innodb_buffer_pool_size`/`tmp_table_size`, o evaluar si la solución de fondo de #59 —precalcular en vez de agregar en cada request— alcanza sin upgrade). #59 queda **abierto**, no se cierra — el síntoma reportado (timeout) no está resuelto, solo mitigado parcialmente por el fix de C#. |

---

### Re-diagnóstico y plan de resolución — Issue #60 (sesión 2026-07-10)

Sesión `/grill-me` para confirmar si el hallazgo de #60 seguía vigente dos semanas después, y decidir cómo avanzar.

| Verificación | Resultado |
|--------------|-----------|
| **RAM/swap de la VM (`free -h`)** | 1.9 GiB total, **76 MiB libres**, **747 MiB de swap en uso** — prácticamente igual que el snapshot original (84 MiB libres / 1.0 GiB swap). Sin cambios en dos semanas. |
| **Config MySQL** | `innodb_buffer_pool_size=128MB`, `tmp_table_size`/`max_heap_table_size=16MB` — idéntico al original, nadie la tocó. |
| **Tamaño de `stock_diario`** | Creció de 24.75M a **25.19M filas** (+1.8%, consistente con el ETL nocturno). 1.79 GB datos + 4.51 GB índices = 6.3 GB, ~50x el buffer pool disponible. |
| **Reproducción de la query real de `GetResumenGlobal()`** (`GROUP BY sku, fecha` sobre 365 días, sin `FORCE INDEX`, sin otra query corriendo en paralelo — `SHOW FULL PROCESSLIST` limpio) | **7 min 50 seg**, 2,020,378 filas agrupadas. Peor que el ~5 min del test con `FORCE INDEX` documentado en la sesión original. **Confirmado: el problema sigue 100% vigente, no mejoró.** |

| Decisión | Definición |
|----------|-----------|
| **Camino elegido: atacar el patrón de agregación en vivo antes que subir infraestructura** | En vez de upsizear la instancia AWS (costo recurrente + ventana de downtime), se prioriza implementar la solución de fondo ya prevista en #59: precalcular un resumen de `stock_diario` una vez por noche vía el ETL, en vez de agregar 25M filas en cada request HTTP. Subir RAM queda pospuesto condicionalmente — se retoma solo si, tras desplegar y verificar este fix, algún otro punto de la app (ETL, otro endpoint) sigue degradado por el swap/buffer pool chico. |
| **Alcance: las 4 funciones de `ResultadosService.cs`, no solo `GetResumenGlobal()`** | `GetStockAnalysis()`, `GetTopVentasPerdidas()` y `GetStockoutDistribution()` tienen el mismo patrón exacto (`GroupBy` de `stock_diario` por sku+fecha en 365 días sobre el catálogo completo) y nunca fueron probadas con el catálogo de ~5500 SKUs — podrían estar igual de rotas sin que nadie lo haya notado todavía (línea "Impacto" de #59 ya lo anticipaba). Se migran las 4 en la misma pasada. |
| **Diseño: rollup final por SKU, sin tabla intermedia día-por-día** | Ninguna de las 4 funciones necesita el detalle diario después de agregarlo — solo derivan `diasConStock`/`diasSinStock` por SKU. Tabla nueva `stock_resumen_365` (una fila por SKU, ~5500 filas en vez de ~2M): `sku` (PK, FK a `articulos`), `dias_con_stock`, `dias_sin_stock`, `total_dias`, `ventas_365`, `ventas_perdidas_365`, `stockout_rate`, `categoria`, `fecha_calculo`. No incluye `pronostico`/`sugerencia_compra` (vienen de `predicciones`, tabla chica sin este problema — no mezclar dos problemas distintos en una tabla). Si en el futuro hace falta el detalle día-por-día para otro caso de uso (ej. gráfico de evolución de stock), `StockDiarioRepository.GetDailySumBySkuAndMonth()` ya cubre consultas puntuales por SKU (barato, usa índice) — no hace falta precalcular algo que hoy no se usa. |
| **Implementación: script Python hermano de `run_calc_planilla.py`** | Mismo patrón ya probado (`services/etl/run_calc_planilla.py` → `planilla_ventas_calculada`), orquestado desde el mismo `job_etl_diario.kjb` (Pentaho), mismo cron de Ofelia (3 AM). Evita tener un segundo scheduler paralelo en el backend .NET compitiendo por la misma tabla. Tabla creada vía script SQL numerado (`infra/sql/11-stock-resumen.sql`), siguiendo el patrón existente (no EF Core Migrations — este proyecto no las usa). |
| **Orden de rollout** | (1) aplicar `infra/sql/11-stock-resumen.sql` (tabla vacía) → (2) correr el script Python manualmente una vez contra prod para poblarla (mismo patrón que el backfill de #44) → (3) verificar `SELECT COUNT(*) FROM stock_resumen_365` (~5500 filas esperadas) → (4) recién ahí deployar el código del backend que lee de la tabla. Mismo orden de 3 pasos que ya se usó en el deploy de grupos (`10-grupos.sql` → backfill → código) — evita que el código nuevo lea una tabla vacía y muestre todo en cero durante horas. |
| **Estado de los issues** | #59 sigue **abierto** hasta desplegar y verificar el fix (mismo tipo de smoke test que destapó el problema: `curl` real a `/api/resultados/resumen` con catálogo completo, midiendo tiempo). #60 sigue **abierto pero re-priorizado** — de "bloqueante crítico" a "seguimiento condicional", con nota de que el diagnóstico se re-verificó hoy (7:50 min, peor que el dato original) y que se decidió no subir RAM todavía a favor de resolver el patrón de agregación en vivo primero. |

> **Nota para quien retome esto:** el precálculo nocturno asume que `stock_minimo` (usado para clasificar días con/sin stock) es el valor *actual* del artículo al momento del recálculo, igual que el comportamiento hoy en vivo — no hay versionado histórico de ese umbral. Si el ETL de una noche falla o se salta (lock de backfill, ver `run_ofelia.sh`), `stock_resumen_365` simplemente no se actualiza esa noche y sigue sirviendo el dato del día anterior — mismo criterio de staleness que ya tiene el resto de la app (ETL nocturno como única fuente de actualización).

---

### Implementación — Issue #59/#60 (sesión 2026-07-10, continuación)

Código escrito y verificado localmente (`dotnet build WebApi.sln` → 0 errores; `pytest services/etl/tests/` → 18/18 OK, incluye 4 tests nuevos). **No desplegado a producción todavía** — falta correr el rollout en la VM.

| Archivo | Contenido |
|---|---|
| `infra/sql/11-stock-resumen.sql` | `CREATE TABLE stock_resumen_365` — PK `sku` VARCHAR(128), `dias_con_stock`/`dias_sin_stock`/`total_dias`/`ventas_365` crudos (sin tasas/categorías derivadas), FK a `articulos(sku)` igual que `planilla_ventas_calculada`. |
| `apps/backend/WebApi/Models/StockResumen365.cs` + `EvalutiaDbContext.cs` | Entity + `DbSet<StockResumen365>`, mapeo mirror de `PlanillaVentasCalculada`. |
| `apps/backend/WebApi/Services/Resultados/ResultadosService.cs` | Las 4 funciones (`GetResumenGlobal`, `GetStockAnalysis`, `GetTopVentasPerdidas`, `GetStockoutDistribution`) reescritas para leer `_db.StockResumen365` (~5500 filas) en vez de agregar `_db.StockDiario` en vivo (25M+ filas). Cada una conserva **exactamente** su propia fórmula/umbral original (confirmado que las 4 no son idénticas entre sí — ver corrección de diseño de la sesión anterior). `GetStockAnalysis` sigue sin filtrar por `stock_minimo > 0` (cubre todo `articulos`, como antes). |
| `services/etl/run_calc_stock_resumen.py` | Calcula el resumen: 1 query SQL con `LEFT JOIN` desde `articulos` (cubre todos los SKUs) agregando `stock_diario` por sku+fecha con `CASE WHEN total > stock_minimo`, + 1 query de `ventas_historicas` agrupada por sku. Combina ambas en Python (`combinar()`, función pura, testeada sin DB). Escribe con `DELETE + INSERT` en una transacción (no `TRUNCATE` — mismo criterio que `run_calc_planilla.py`, rollbackeable). Registra inicio/fin en `jobs_historial` (`tipo_job='etl'`, `detalle.subtipo='calc_stock_resumen'`). |
| `services/etl/run_calc_stock_resumen.sh` | Wrapper no bloqueante (siempre `exit 0`), mirror de `run_calc_planilla.sh`. |
| `services/etl/tests/test_run_calc_stock_resumen.py` | 4 tests de `combinar()`: SKU sin ventas, SKU sin filas de stock_diario, cálculo de `dias_sin_stock`, ventas de SKU huérfano ignoradas. |
| `services/etl/job_etl_diario.kjb` | Nuevo step `RUN CALC_STOCK_RESUMEN` enganchado entre `RUN CALC_SUGERENCIAS` y `TRUNCATE VENTAS_STAGE END` (mismo lugar que los otros steps de cálculo derivado). |

**Pendiente — rollout en producción**, en este orden exacto (acordado en la sesión anterior):
1. Aplicar `infra/sql/11-stock-resumen.sql` en la VM (`docker exec -i evalutia-mysql mysql -u root -p evalutia < infra/sql/11-stock-resumen.sql`, o vía `docker compose exec`).
2. `docker compose build etl` (el Dockerfile hace `COPY . /app` — el script nuevo no existe en el contenedor hasta rebuildear la imagen) + correr manualmente `run_calc_stock_resumen.sh` una vez contra prod para poblar la tabla antes de que el código nuevo la lea (mismo patrón que el backfill de #44).
3. Verificar `SELECT COUNT(*) FROM stock_resumen_365` (~5500 filas esperadas, todo `articulos`).
4. Recién ahí: `docker compose build webapi` + `up -d --force-recreate webapi`.
5. Smoke test: `curl` real a `/api/resultados/resumen`, `/api/resultados/stock-analysis`, `/api/resultados/charts/top-ventas-perdidas`, `/api/resultados/charts/stockout-distribution` — confirmar que responden en milisegundos y no en minutos.

---

### Plan de trabajo — Mail del cliente "Frecuencia de venta + Modelo econométrico" (sesión 2026-07-12)

Origen: mail del cliente con dos pedidos independientes. **Parte A** (frecuencia de venta por tickets para desestacionalizar) e **Parte B** (ampliar modelo econométrico más allá del grupo 201). Se dividieron en issues con estimación en horas ($25/h) para presupuestar.

#### Parte A — Frecuencia de venta por tickets

| Decisión | Definición |
|----------|-----------|
| **"Histórico" y "Tickets" no estaban definidos por el cliente — repregunta enviada 2026-07-13** | Se decidió **no asumir por conveniencia técnica** (aunque `rotacion_sugerida` de `run_calc_sugerencias.py` era candidato natural para "Histórico", no se dio por sentado) y se mandó la pregunta a Rodrigo. **Respuesta recibida (2026-07-13):** "Histórico" = promedio mensual de unidades vendidas del SKU en los últimos 12 meses (o de los meses disponibles si el SKU tiene menos antigüedad) — **confirmado, sin ambigüedad, no usa `rotacion_sugerida`** (era un candidato, no lo que el cliente pidió; es un promedio simple, no ponderado por meses "normales"). "Ticket" = cada documento de venta (devoluciones contado y notas de crédito restan; múltiples unidades del mismo SKU en un mismo documento = 1 ticket) — **bloqueado**: verificado contra el código que esa granularidad de documento/transacción no existe hoy en ningún punto de la cadena (`ventas_historicas` solo agrega cantidad total por `fecha+sku+fuente`; el extractor SOAP `run_extract_sales_chunk.py` no pide ni recibe identificador de documento; `fuente` identifica el endpoint SOAP de origen, no un tipo de movimiento). Se mandó repregunta a Rodrigo: si el sistema de origen (POS/ERP) puede exponer el detalle por documento, o si acepta como aproximación "día distinto con venta" (calculable hoy, sin poder descontar devoluciones/NC por separado). **#61 sigue abierto** hasta tener la definición de "Ticket" confirmada — "Histórico" ya se puede implementar. |
| **Colores: se reusa el mecanismo, no el significado** | El nuevo criterio de tickets se muestra con color de fondo (mismo mecanismo visual que `estado_mes`/`frecuencia_nivel`), pero **no reemplaza** el significado del color de quiebre ya validado contra el Excel del cliente (issues #36-#39). Conviven como señales separadas. |
| **Sin columnas numéricas nuevas en la planilla principal** | La planilla solo muestra la señal de color. El detalle completo (tickets, Histórico, VentaReal/Extrapolación, valor final aplicado) va únicamente en la tabla exportable, que es donde el cliente pidió verlo con números — evita agregar un tercer bloque de 13 columnas a una tabla que ya tiene scroll horizontal con 2 bloques. |
| **Umbrales (≤2, 3-4, ≥5) como constantes ajustables por código** | Mismo patrón que `FREQ_ALTA_MIN`/`FREQ_BAJA_MAX` en `run_calc_planilla.py` — no UI de configuración ahora (el cliente pidió esto para "un futuro", no ahora). Si más adelante pide tocarlo él mismo sin pasar por nosotros, es un issue nuevo aparte. |

**Issues:**

| # | Issue | Horas |
|---|-------|-------|
| #61 | Mail de dudas al cliente + cierre de definición (Histórico, Tickets) — bloqueante, arranca el resto de la Parte A | 2–3 |
| #62 | Migración SQL: columnas nuevas en `planilla_ventas_calculada` (tickets, histórico, venta ajustada, criterio aplicado) | 1–2 |
| #63 | ETL: cálculo de tickets/histórico/extrapolación y fórmula de blending (6 casos: 3 niveles × stock-completo/quiebre) en `run_calc_planilla.py` | 6–9 |
| #64 | Verificación: casos de ejemplo del mail del cliente + validación SKU real contra su Excel (mismo tipo de QA que #36-#39) | 4–6 |
| #65 | Frontend: indicador de color en `PlanillaTable.tsx` reusando la paleta de 3 niveles existente, sin pisar `estadoMesBg` | 4–6 |
| #66 | Export: columnas nuevas en la tabla exportable (`exportPlanilla.ts`) | 1–2 |
| #67 | *(Fuera de alcance ahora — futuro)* UI de configuración de umbrales, si el cliente la pide más adelante | — |

**Subtotal Parte A: ≈18–28 h**

#### Parte B — Modelo econométrico más allá del grupo 201 (plan anidado)

| Decisión | Definición |
|----------|-----------|
| **Hallazgo: el R²/RMSE de producción es in-sample, no holdout** | `fit_rf_insample`/`fit_xgb_insample`/`fit_prophet_insample` (`ml/models.py`) entrenan con todos los datos disponibles y evalúan sobre esos mismos datos — no mide generalización, mide memorización. Confirma la sospecha del usuario de que los modelos "pueden no estar bien" sin haberlo verificado nunca con holdout real. |
| **`ml/eval_models.py` (intento previo de evaluación con holdout) está roto** | Llama a `fit_xgb_with_holdout_multi`, función que ya no existe en `ml/models.py` (solo quedan las variantes in-sample). Coincide con un issue que el usuario había arrancado y dejado a mitad de camino. |
| **No existe un modelo "econométrico" como técnica separada** | Lo que el proyecto llama "modelo econométrico" es el ensemble clásico (RF+XGB+Prophet, `--model-set=classic`) aplicado hoy solo a SKUs del grupo 201 vía `grupos.aplica_modelo_econometrico`. No hay SARIMAX/ETS conectado en el pipeline real pese a figurar en el stack tecnológico. |
| **Secuencia: diagnóstico acotado antes de rediseño** | B0 es deliberadamente chico (arreglar el holdout roto + correr sobre 201 + medir el gap `r2_train` vs `r2_test`) antes de comprometerse a un rediseño completo de metodología (walk-forward validation, etc.). Si el gap es chico, se ahorra ese trabajo; si es grande, se abre un issue de rediseño con evidencia concreta, no a ciegas. |
| **Se factura al cliente, con framing transparente** | No es "deuda técnica interna random" — es un prerrequisito directo de lo que el cliente pidió explícitamente ("usar R² para evaluar la calidad"). Sin arreglar el holdout, ese pedido no se puede cumplir honestamente. |
| **Criterio de elegibilidad: comparativo, no absoluto** | Un SKU pasa a modelo econométrico si su R²/RMSE en holdout es **mejor** que el del ensemble que ya le asignarían — no un umbral fijo en el vacío. Cumple el pedido del cliente de aplicarlo "solo donde realmente me sea útil". |
| **Elegibilidad por SKU individual, no por grupo** | Requiere migrar el esquema (`grupos.aplica_modelo_econometrico` → nivel SKU) porque dentro de un mismo grupo puede haber SKUs con buen ajuste econométrico y otros sin ninguno. |

**Issues:**

| # | Issue | Horas |
|---|-------|-------|
| #68 | B0.1 — Reconstruir la función de holdout faltante en `ml/models.py` para que `eval_models.py` corra | 3–5 |
| #69 | B0.2 — Correr `eval_models.py` sobre el grupo 201 actual, medir gap train/test, documentar hallazgos | 2–4 |
| #70 | B1 — Definir criterio de elegibilidad comparativo (R² test econométrico vs ensemble) + mínimo de meses con datos | 1–2 |
| #71 | B2 — Migrar esquema de elegibilidad de nivel-grupo a nivel-SKU | 3–5 |
| #72 | B3 — Extender evaluación holdout a todos los candidatos (no solo grupo 201) + persistir R²/RMSE comparativo | 6–9 |
| #73 | B4 — Aplicar criterio y marcar SKUs elegibles | 3–4 |
| #74 | B5 — Medir y resolver impacto de performance del job nocturno con el volumen ampliado (~5500 SKUs candidatos vs 104 hoy) | 3–6 |
| #75 | B6 — Backfill de predicciones para SKUs recién elegibles + validación en producción (mismo patrón que #43-#46) | 6–10 |

**Subtotal Parte B: ≈27–45 h** (B0 = #68+#69, ≈5–9 h, da la info real antes de comprometer el resto)

**Total combinado (costo técnico estimado): ≈45–73 h → US$1.125–US$1.825 a $25/h.**

> **Decisión de precio (no técnica):** Nico decidió cobrarle a Rodrigo **USD 600 fijo** por este paquete completo (Parte A + Parte B + "el matcher"), muy por debajo del costo técnico estimado — no por error de cálculo sino como decisión deliberada de relación con el cliente (ver [[project_rodrigo_pricing_agreement]]: acuerdo previo de mantener accesibles los cambios sobre el portal existente, más el valor de aprendizaje/relación de este cliente para el equipo). El orden de prioridad de entrega dentro de ese precio, si el tiempo se estira, es el mismo del plan de arriba: Parte A completa primero, después diagnóstico B0 (#68-#69), y B1-B6 según tiempo disponible.

---

### `ml/models.py` — Issue #77 (sesión 2026-07-12)

| Decisión | Definición |
|----------|-----------|
| **Restauración verbatim, sin corregir el desalineamiento de `trend`** | `_build_lag_month_trend` se restaura tal cual existía antes del borrado accidental (commit `1209bfd^`). Se detectó que la feature `trend` tiene un salto de `lags` posiciones entre el rango visto en entrenamiento (`0..len(train)-lags-1`, calculado post-`dropna()`) y el usado al pronosticar (`len(tr)+i`, sobre la serie sin recortar) — para RF/XGB esto no rompe nada, pero satura la feature de tendencia en todo el horizonte de forecast. No se corrige ahora: es un problema de calidad de modelado preexistente al bug de #77, no parte de su alcance ("restaurar lo borrado", no "mejorar el feature engineering"). Queda como hallazgo para #76 (auditoría de calibración/casos borde del ensemble). |
| **No se restaura `_build_lag_month_trend_rich`** | Se borró en el mismo commit, pero no tiene ningún call-site vigente (pertenecía al ensemble de 14 variantes ya abandonado, mismo hallazgo de #68). Restaurarla sería código muerto. |
| **Impacto en producción — validar antes de dejarlo al cron** | Desde 2025-12-04 todas las predicciones con `--model-set classic/tree` quedaron en Prophet por descarte (RF/XGB rotos). Al deployar el fix, el próximo job de las 3 AM va a volver a comparar los 3 modelos de verdad por RMSE — es esperable que varios SKUs cambien de "mejor modelo" de un día para otro. Se corre `predict.py` manualmente contra producción (o un dump reciente) primero, se compara contra lo ya persistido, y si el movimiento es grande se avisa al cliente antes de que lo note solo en el dashboard. |
| **Sin backfill de predicciones históricas** | Las predicciones ya persistidas desde diciembre (con Prophet por descarte) no se reprocesan como parte de #77. El fix aplica solo hacia adelante. Si el negocio pide backfillear, es un issue nuevo siguiendo el patrón ya usado en #43-#46 — no una decisión implícita de este fix. |
| **Logging dentro de los `except Exception` de `ml/models.py`** | Se agrega `log.exception(...)` (nuevo `logging.getLogger(__name__)`, el archivo no tenía logger) dentro de los bloques `except` de `fit_rf_insample`, `fit_xgb_insample` y `fit_prophet_insample` — sin cambiar el `return None` de fallback. Esto es lo que permitió que el `NameError` de `_build_lag_month_trend` quedara invisible 7 meses; el logging no arregla el patrón de raíz pero deja rastro la próxima vez. |

> **Nota:** el mismo patrón de `except Exception: return None` sigue existiendo en las nuevas `fit_*_with_holdout` de #68 — quedan sin el logging agregado acá porque #77 se acotó a los 3 `*_insample` que ya tenían el bug real. Si se decide extenderlo, es continuación natural pero no se asumió sin pedirlo.

**Verificado en vivo (DB local, no el servidor de producción real):**
- Sintético: `fit_rf_with_holdout`/`fit_xgb_with_holdout` pasan de devolver `None` siempre a producir `HoldoutResult` real.
- `python -m ml.eval_models` con `EVAL_ONLY_SKUS=C00375`: ahora aparecen RF y XGB en el resumen además de PROPHET (antes solo PROPHET). El `mean_gap` de RF (0.85) y XGB (0.30) muestra overfitting real — justo lo que #69 va a medir en profundidad sobre el grupo 201.
- `predict.py --model-set classic --skus C00375 --version test-77-verify` (fila de prueba, borrada después de verificar): el mejor modelo para este SKU pasó de PROPHET (RMSE in-sample 544) a **XGB** (RMSE in-sample 343). El valor pronosticado cambió entre ~15% y ~26% respecto a lo persistido con `mvp-002`. Confirma que el impacto en producción es real y significativo — antes de deployar, corresponde repetir esta comparación sobre el conjunto completo de SKUs del `--model-set` vigente en producción (no solo este SKU) y decidir si se avisa al cliente antes de que el cron de las 3 AM lo aplique solo.

---

### `ml/eval_models.py` + `ml/models.py` — Issue #69 (sesión 2026-07-12)

| Decisión | Definición |
|----------|-----------|
| **Fuente de SKUs del grupo 201** | Se reusa `services/etl/get_skus_modelo.py` (ya existente, patrón del issue #43: `articulos JOIN grupos WHERE aplica_modelo_econometrico = TRUE`) para alimentar `EVAL_ONLY_SKUS`, en vez de hardcodear `grupo_id=201`. Si mañana se agrega un segundo grupo econométrico, el diagnóstico lo sigue automáticamente. |
| **Reporte con distribución, no solo promedio** | `eval_models.py` solo imprimía la media del `gap` por modelo — insuficiente para "distribución" que pide el criterio de aceptación. Se agregan percentiles (min/p25/mediana/p75/max) del `gap` y `mae_rel` por modelo, y se vuelca el detalle completo por SKU a CSV vía env var opcional `EVAL_OUTPUT_CSV` (si no se setea, no escribe nada — comportamiento actual intacto). |
| **Criterio de aceptación del gap (dos niveles, sobre `r2_test`, no sobre el gap crudo)** | **Aceptable:** mediana de `r2_test` ≥ 0.3 en el grupo **y** <25% de SKUs con `r2_test < 0`. **Rediseño necesario:** mediana de `r2_test` negativa/cercana a 0, o >40% de SKUs con `r2_test < 0`. **Zona gris:** entre esos rangos, se documenta y se decide con el cliente, no solo técnicamente. Se usa `r2_test` (no el gap `r2_train - r2_test`) porque un gap chico con `r2_train` bajo no es "generalización" — es que el modelo nunca ajustó nada. |
| **Simulación de la selección real de producción** | Además del desglose por modelo (RF/XGB/PROPHET por separado), se agrega una vista por SKU que replica la selección de `predict.py` (menor RMSE in-sample entre los 3) y reporta el `r2_test` del modelo *elegido* — porque "modelo econométrico" (como quedó definido en #68) es el ensemble completo con selección por SKU, no el promedio de cada modelo aislado. Esto es lo que el cliente realmente ve. |
| **Cambio de código requerido** | `HoldoutResult` (en `ml/models.py`) no propagaba `rmse_train` (solo `r2_train`/`r2_test`/`mae_train`/`mae_test`) — se le agrega el campo, poblado desde `base.rmse` de la `*_insample` correspondiente, para poder replicar el criterio de selección real (que es por RMSE, no por R²). |
| **Hallazgo durante la corrida real — guardrail agregado a `fit_rf_with_holdout`/`fit_xgb_with_holdout`** | Al correr sobre las 104 SKUs reales, 10 crasheaban (`ValueError: Input contains NaN` / `Found array with 0 sample(s)`): tienen solo 5 trimestres de historia total, y al aplicarles el holdout de 4 trimestres el `train` queda con 1 solo punto — insuficiente para construir ni un lag. El logging de #77 los atrapaba y logueaba, pero de forma ruidosa. Se agregó `if len(train) < 2: return None` en ambas funciones (antes de llamar a `fit_rf_insample`/`fit_xgb_insample`), igual patrón que ya usa Prophet con su propio mínimo. Mismo resultado final (esos 10 SKUs quedan excluidos igual, cobertura sin cambios: 85/104), pero sin traceback. |

**Resultado del diagnóstico (grupo 201, 104 SKUs, corrido contra DB local — no el servidor de producción real):**

| Modelo | n_skus | mean_r2_test | mediana gap | p75 gap |
|--------|--------|--------------|--------------|---------|
| PROPHET | 53 | 0.379 | 0.360 | 0.635 |
| RF | 85 | 0.098 | 0.773 | 1.000 |
| XGB | 85 | 0.157 | 0.882 | 1.000 |

**Simulación de selección real de producción (menor RMSE in-sample por SKU):** PROPHET gana en 40 SKUs, RF en 33, XGB en 12. Mediana de `r2_test` del modelo elegido: **0.0623**. % de SKUs con `r2_test < 0`: **0.0%**.

**Veredicto: ZONA GRIS.** No cumple el criterio de "aceptable" (mediana r2_test 0.06, muy por debajo del umbral 0.3) pero tampoco el de "rediseño necesario" (0% de SKUs peor que la media, muy por debajo del umbral 40%). Lectura: el modelo econométrico casi nunca es *peor* que predecir el promedio, pero rara vez explica una porción sustancial de la varianza real fuera de muestra — generaliza "sin romperse" pero con poca capacidad predictiva real. Cobertura parcial: PROPHET solo cubrió 53/104 SKUs (su propio mínimo de 8 trimestres de historia), RF/XGB cubrieron 85/104.

**Decisión tomada (sesión siguiente, mismo día):** rediseñar la metodología a walk-forward **antes** de #70-#75, no después. Razón técnica: con `years_test=1` en trimestral, el holdout usa solo 4 puntos de test por SKU — un `r2_test` calculado sobre 4 puntos es una estimación muy ruidosa (puede saltar de 0 a 1 con variaciones chicas). Gran parte del "zona gris" puede ser ruido de medición, no necesariamente mala calidad real del modelo. Construir #70-#72 (criterio de elegibilidad + extensión a ~5500 SKUs candidatos) sobre una métrica ruidosa arriesga decisiones de elegibilidad que son básicamente aleatorias, con el costo de #75 (backfill, 6-10h) para deshacerlas después. Ver plan de rediseño en la subsección siguiente.

---

### Plan de rediseño — walk-forward validation (sesión 2026-07-12)

Ejecuta la parte "Estabilidad" de #30 (auditoría original: "correr el modelo con distintas ventanas temporales — ver si RMSE/R2 son consistentes o volátiles según el SKU"), que #68/#69 no cubrían (ellos solo hicieron el "overfitting check" train vs. holdout de #30).

| Decisión | Definición |
|----------|-----------|
| **Ventana de entrenamiento: expanding, no rolling** | Crece con toda la historia disponible en cada fold, igual que entrena `predict.py` hoy en producción (con toda la historia). Así el walk-forward mide lo mismo que el sistema real hace, no un escenario artificial con ventana recortada. |
| **Horizonte de test por fold: 2 trimestres** | Igual a `forecast_periods` de producción — el error medido es directamente comparable a lo que el cliente ve. |
| **Número de folds: adaptativo por SKU, tope de 5** | Se calculan cuántos orígenes de test caben en la historia disponible, repartidos parejo a lo largo de toda la historia utilizable (no siempre los últimos períodos) — tope de 5 folds para acotar el costo de cómputo (hasta 5x más fits por SKU/modelo que el holdout simple). |
| **`min_train=2` (solo anti-crash), sin corte duro de calidad — corregido tras verificar contra datos reales** | Se había propuesto `min_train=10` (lags+2) pensando que evitaba fits degenerados, pero matemáticamente eso solo garantiza 2 filas reales de entrenamiento (no evita degeneración, y el crash ya está resuelto genéricamente desde #69 con `len(train)>=2`, válido para cualquier `lags`). Verificado contra los 98 SKUs con historia local del grupo 201: con `min_train=10` se excluía el **46%** (45/98, peor que el 85/104 de #69) sin ganancia real de calidad — no existe un umbral que resuelva la tensión calidad-vs-cobertura por sí solo. Se usa `min_train=2` (mismo guardrail de #69, máxima cobertura) y en cambio se reporta **`n_train_rows`** (filas reales de entrenamiento tras construir los lags) por fold como señal de confianza transparente — un SKU con muy poca historia muestra folds de 1-2 filas reales, lo cual naturalmente lo marca "volátil" en la métrica de estabilidad sin necesidad de un corte arbitrario. La decisión de mínimo de historia para elegibilidad queda para #70, con evidencia real. |
| **SKUs sin historia ni para 1 fold** (`N < min_train+horizon` = 4 trimestres) | Quedan fuera del reporte — mismo caso ya cubierto por el guardrail de #69. |
| **Reporte de estabilidad, no solo precisión** | Por SKU se reporta **mediana e IQR** (más robusto que media/desvío frente a folds degenerados) de `r2_test` entre folds — responde directamente lo que #30 pedía. Umbral para "volátil": `std(r2_test entre folds) ≥ 0.2` cuando hay ≥2 folds; con 1 solo fold no se puede evaluar estabilidad (se marca explícitamente, no se fuerza un valor). |
| **Ubicación del código** | Nuevo `walk_forward_split(...)` en `ml/evaluate.py` (generaliza `holdout_split`, no la reemplaza — `holdout_split` sigue existiendo). Nuevas `fit_rf_with_walkforward`/`fit_xgb_with_walkforward`/`fit_prophet_with_walkforward` en `ml/models.py`, reusando internamente `fit_*_insample` por fold (no se duplica lógica de features/entrenamiento). Las `fit_*_with_holdout` de #68 no se tocan ni se eliminan. |
| **Script nuevo, no se extiende `eval_models.py`** | `ml/eval_walkforward.py` — el shape de datos es distinto (por SKU: n_folds/mediana-IQR/n_train_rows/estable) al de `eval_models.py` (por sku+modelo, un solo split). Mezclar ambos con branching complicaba sin necesidad; `eval_models.py` queda intacto como diagnóstico rápido de #69. |
| **Hallazgo adicional (informativo para #70, no bloquea)** | `TEST-SKU-001` está tageado en el grupo 201 (`aplica_modelo_econometrico=1`) pero sin historia en `ventas_historicas` — parece un SKU de prueba mal cargado en el catálogo real. Limpieza de catálogo aparte, no se toca en #78. |
| **Desglose en issues** | 2 unidades de trabajo, no más: (A) issue nuevo — implementar walk-forward + volver a correr el diagnóstico sobre el grupo 201, reemplazando el veredicto "zona gris" de #69. (B) editar el issue #70 existente (todavía no arrancado) para que su criterio de elegibilidad consuma métricas de walk-forward en vez de holdout simple — no se duplica como issue nuevo. |
| **Estimación y numeración** | Issue A entra al roadmap como **B0.3** (continuación de B0 = #68+#69), 6-10h. #70 (B1) no suma horas nuevas — se reformula su alcance, la tarea de definir el criterio en sí no es más compleja. |
| **Corrección durante la implementación: `horizon=2` rompía `r2_test`** | Se había elegido `horizon=2` (igual a `forecast_periods` de producción) para el tamaño de la ventana de test por fold. Con exactamente 2 puntos, `r2_score` (correlación de Pearson al cuadrado, la implementación de este proyecto) es **matemáticamente casi siempre 1.0 o 0.0** — una recta siempre pasa por 2 puntos, dando correlación ±1 sin importar la magnitud del error; solo colapsa a 0.0 si la predicción es constante. Verificado: la primera corrida dio `mediana r2_test = 1.0000` para PROPHET, un resultado imposible de creer que reveló el problema. Se corrigió a `horizon=4` (mismo tamaño de ventana que usó #69 originalmente, con grados de libertad reales para que la correlación varíe) — el RMSE/MAE no tienen este problema (son válidos a cualquier n), solo `r2_test` lo requiere. |

**Resultado del diagnóstico final (grupo 201, walk-forward con `horizon=4`, DB local):**

| Modelo | Cobertura | median r2_test | % estable | % volátil | % solo 1 fold |
|--------|-----------|-----------------|-----------|-----------|----------------|
| PROPHET | 53/98 | 0.332 | 45% | 43% | 11% |
| RF | 85/98 | 0.000 | 80% | 12% | 8% |
| XGB | 85/98 | 0.000 | 71% | 21% | 8% |

**Simulación de selección real de producción:** PROPHET gana en 50 SKUs, RF en 33, XGB en 2. Mediana `r2_test` (walk-forward) del modelo elegido: **0.0659** (vs. 0.0623 de #69 con un solo split — prácticamente idéntico). **29.4%** de los SKUs elegidos son "volátiles" entre folds. **15.3%** solo tuvo 1 fold evaluable (historia insuficiente para medir estabilidad).

**Veredicto: ZONA GRIS confirmado.** El hallazgo más importante no es el número (casi no cambió), es la **confianza**: el walk-forward confirma que el "zona gris" de #69 **no era ruido de un solo split de 4 puntos** — es un resultado estable y reproducible a través de múltiples ventanas de evaluación. Y agrega información nueva que #69 no podía dar: casi 3 de cada 10 SKUs elegidos por producción tienen una calidad de ajuste que varía fuertemente según qué período se use para medirla (volátiles), y 1 de cada 6 no tiene ni siquiera suficiente historia para saberlo. Esta evidencia (no un número inventado) es la que alimenta #70 para definir el mínimo de historia y el criterio de estabilidad de elegibilidad.

---

### Plan de deploy a producción — Issue #59/#60 (sesión 2026-07-13)

El fix de código (`stock_resumen_365`, commit `1adafb3`) ya está commiteado y verificado localmente (104 SKUs). Falta confirmar que resuelve el timeout a escala real de producción (~5500 SKUs, 25M filas). Nico tiene acceso para correr comandos en la VM de AWS — el deploy lo ejecuta él, con esta secuencia acordada:

| Decisión | Definición |
|----------|-----------|
| **Acceso** | Claude no tiene acceso directo al servidor de producción. Nico ejecuta los comandos en la VM de AWS; Claude los prepara con checkpoints de verificación entre paso y paso. |
| **Orden de operaciones (estricto, no saltear pasos)** | (1) Migración SQL (`CREATE TABLE IF NOT EXISTS`, no toca tablas existentes) → (2) Correr `run_calc_stock_resumen.py` manualmente una vez → (3) **Checkpoint duro**: verificar que la tabla tiene ~5500 filas (o el conteo real del catálogo de producción) antes de seguir → (4) Recién ahí desplegar la imagen nueva de `webapi` → (5) Smoke test de los 4 endpoints de `/api/resultados`. Razón: si el código nuevo se despliega antes de que la tabla tenga datos, el endpoint no crashea pero devuelve todo en cero/vacío — parece que "funciona" pero miente, peor que el timeout actual que al menos es visiblemente un error. |
| **Rollback: tag de la imagen actual antes de reconstruir** | `docker tag evalutia-webapi:latest evalutia-webapi:pre-stock-resumen` antes de tocar nada — permite volver atrás en segundos sin rebuildear si algo sale mal. La migración SQL no necesita rollback propio (tabla nueva, no toca datos existentes); en el peor caso alcanza con volver la imagen de `webapi` atrás y la tabla queda sin usarse. |
| **Backup de la DB antes de tocar nada** | `mysqldump` completo (o al menos de las tablas relevantes si el dump completo con 25M filas es muy pesado) antes de empezar — no porque se espere que esta migración puntual rompa algo, sino porque es la primera vez que se toca este servidor en esta conversación y no hay un backup reciente confirmado como punto de partida. |
| **Timing: evitar la ventana de las 3 AM del cron de Ofelia** | El cron corre `job_etl_diario.kjb` (que ahora incluye `RUN CALC_STOCK_RESUMEN`) todas las noches a las 3 AM Montevideo. Deployar cerca de esa hora arriesga que el ETL manual y el del cron corran en simultáneo sobre la misma tabla (no corrompe datos — el `DELETE+INSERT` es atómico — pero puede confundir el smoke test). Deploy autorizado siempre que falte más de ~1 hora para las 3 AM. No hay razón de negocio para esperar "horario de bajo tráfico": `/resultados` ya está roto ahora mismo, no le sirve a nadie en su estado actual. |
| **Fuera de alcance de este deploy** | El cambio de `docker-compose.yml` (puerto de `webapp`, `WEBAPP_PORT`→`80`) que quedó deliberadamente fuera del commit `1adafb3` no se toca ni se despliega en esta sesión — es un ajuste no relacionado. |

> **Nota:** este plan resuelve la mitad de código de #59. La otra mitad — si el precálculo alcanza sin necesidad del upgrade de RAM de #60 — solo se puede confirmar después del smoke test contra el volumen real.

**Deploy ejecutado y verificado (2026-07-13, mismo día):**

| Paso | Resultado |
|------|-----------|
| Push a `origin/Develop` | 4 commits (`f7d3ebf..1adafb3`), incluye el fix + todo el hilo de ML de #68-#78 — no se habían pusheado hasta esta sesión. |
| Backup | `mysqldump` completo, 2.6 GB, cerró limpio (`-- Dump completed on 2026-07-13 18:06:22`). |
| Tag de rollback | `evalutia-webapi:pre-stock-resumen` y `evalutia-etl:pre-stock-resumen` — el segundo no tomó en el primer intento (se pisó con la repetición de comandos en la terminal), detectado y corregido antes de seguir. |
| `git merge --ff-only origin/Develop` en `/opt/evalutia` | Fast-forward limpio, `1adafb3` en `HEAD`. |
| Migración SQL | Tabla creada, 6 columnas confirmadas con `DESCRIBE`. |
| Rebuild + recreate `etl` | **Gap real detectado durante el deploy:** el primer `docker compose up -d --force-recreate etl` no se aplicó (interrumpido por un Ctrl+C accidental en la terminal) — el contenedor seguía siendo el de "hace 2 semanas" a pesar de que la imagen sí se había reconstruido. Se detectó comparando el `CREATED` de `docker compose ps` contra la hora real, y se corrigió recreándolo de nuevo. **Lección para el próximo deploy: siempre verificar `CREATED` de `docker compose ps`, no asumir que el `up --force-recreate` surtió efecto solo porque no tiró error.** |
| Cálculo manual (`run_calc_stock_resumen.sh`) | **5550 SKUs procesados en 574.25s (~9.6 min)** — dentro del rango estimado (7-8 min de la query de `stock_diario` sola, medido en la sesión de #60 del 2026-07-10, más overhead). |
| Checkpoint duro | `SELECT COUNT(*) FROM stock_resumen_365` = **5550**, coincide exactamente con el log del ETL. |
| Rebuild + recreate `webapi` | Mismo patrón de verificación con `CREATED` — confirmado recreado (no repitió el problema del `etl`). |
| Smoke test contra producción real | Los 4 endpoints de `/api/resultados`, con JWT real (`admin@evalutia.com`): `resumen` 200/0.51s, `stock-analysis` 200/0.52s, `top-ventas-perdidas` 200/0.12s, `stockout-distribution` 200/0.17s. **Antes: timeout de 120-300s.** |

**Resultado: #59 cerrado** (la condición de cierre — "la solución de fondo alcanza sin el upgrade de RAM" — se cumplió). **#60 no se cierra** — la causa raíz (RAM/swap/buffer pool de la VM) sigue igual, solo se evitó que este endpoint puntual la sufriera; queda como seguimiento condicional si otro proceso empieza a degradarse por el mismo motivo.

---

### `job_etl_diario.kjb` (CALC_UPSERT_VENTAS_MENSUALES) — Issue #40 (sesión 2026-07-13)

| Decisión | Definición |
|----------|-----------|
| **Fix mínimo inline en el `.kjb`, no migrar a Python** | El bug es una sola query (subquery `d` de `CALC_UPSERT_VENTAS_MENSUALES`, líneas 182-189): comparaba `stock_diario.cantidad` fila por fila (una fila por depósito) contra `stock_minimo`, sin sumar los depósitos primero — un SKU con depósito A=8 + B=8 (mínimo 10) contaba como "sin stock" cuando el combinado (16) sí superaba el mínimo. Se corrige agregando un nivel de subquery (`SUM(cantidad) GROUP BY sku, fecha` antes de comparar), mismo patrón que ya usa `run_calc_planilla.py`. No se migra a un script Python nuevo — sería un refactor mucho mayor no pedido por el issue. |
| **Re-verificación del radio de impacto encontró un segundo lugar sospechoso, descartado tras revisar el código real** | Un research agent señaló `StockService.CalculateDaysWithStockForMonth` (vía `AdminService.RecalcForSku`, endpoint de recálculo manual) como posible segunda instancia del bug, por estructura similar. Verificado el código real: usa `StockDiarioRepository.GetDailySumBySkuAndMonth`, que sí hace `GroupBy(Fecha).Sum(Cantidad)` antes de comparar — **no tiene el bug**. Único consumidor confirmado de `ventas_mensuales.dias_con_stock`: `VentasMensualesPage.tsx:124` (vía `GET /api/VentasMensuales`). No afecta `ResultadosService.cs` (usa `stock_resumen_365`, tabla distinta) ni `planilla_ventas_calculada` (usa su propio cálculo en `run_calc_planilla.py`, ya correcto). |
| **Sin backfill necesario** | La query no tiene ventana de fechas — recalcula el historial completo (`UNION` de `ventas_historicas` + `stock_diario`, sin `WHERE` de fecha) con `INSERT...ON DUPLICATE KEY UPDATE` cada vez que corre. Una sola ejecución corrige retroactivamente todo el historial, a diferencia del fix de planilla (#4) que sí necesitó backfill por su ventana fija de 13 meses. |
| **Verificación: caso real, no sintético** | Se encontró en la DB local un SKU real (`I00990`, oct-2016) con stock repartido en depósitos 1 y 5 (2+2 unidades, `stock_minimo=2`) que exhibe el bug en su forma más extrema: la query vieja da **0 días con stock** ese mes (ningún depósito individual supera el mínimo, así que la subquery no devuelve fila y el `COALESCE` cae a 0); la corregida da **29**. Se corrió la query completa corregida contra la DB local: `ventas_mensuales` pasó de `dias_con_stock=0` a `29` para ese sku/mes, y las 11639 filas de la tabla se recalcularon en una sola pasada (confirma que no hace falta backfill aparte). |
| **Oráculo de verificación usado: el endpoint de recálculo manual, no un test nuevo** | En vez de escribir tests desde cero para una query SQL cruda embebida en XML de Pentaho (sin cobertura de tests hoy), se usó como referencia la lógica ya correcta de `StockService`/`AdminService.RecalcForSku` — ambos caminos calculan lo mismo (agregar depósitos antes de comparar), confirmando el fix por equivalencia de lógica en vez de por test automatizado nuevo. |
| **Riesgo de performance identificado y medido: la query nueva agrega una pasada extra sobre `stock_diario` sin ventana de fechas** | A diferencia de `stock_resumen_365` (acotada a 365 días), esta query recalcula el historial completo cada noche por diseño (ver fila "Sin backfill necesario") — el fix agrega un `GROUP BY sku, fecha` intermedio sobre **todo** `stock_diario` antes de agrupar por mes. Medido localmente (686K filas): query vieja 1.8s, nueva 2.7s (~50% más lenta). En producción (`stock_diario` con 25M+ filas, VM con RAM ajustada y `tmp_table_size=16MB` documentados en #60) el resultado intermedio podría desbordar a disco, mismo patrón que causó el timeout de #59. **Decisión:** desplegar igual — es un job batch nocturno sin timeout duro (a diferencia de un request HTTP), y ya se probó que este tipo de agregación sobre `stock_diario` tarda minutos pero termina (`CALC_STOCK_RESUMEN` tardó 574s en prod). Si se dispara demasiado, se ataca como issue nuevo con datos reales. |
| **Plan de monitoreo corregido: no sirve mirar `jobs_historial`** | Se planteó inicialmente monitorear la duración en `jobs_historial`, pero se verificó que `CALC_UPSERT_VENTAS_MENSUALES` es una entrada SQL cruda dentro del `.kjb` — no hace su propio insert en `jobs_historial` (a diferencia de `run_calc_planilla.py`/`run_calc_stock_resumen.py`, que sí registran su propio job vía Python). Solo se podría ver la duración agregada de todo el job nocturno, señal demasiado ruidosa para aislar el impacto de este cambio puntual. **Corrección:** al desplegar, correr la query manualmente contra producción envuelta en `time` (mismo patrón usado para medirla localmente) para obtener una medición aislada y limpia, en vez de inferirla del job completo. |

**Deploy ejecutado y verificado en producción (2026-07-13, mismo día):**

| Paso | Resultado |
|------|-----------|
| Push a `origin/Develop` | `1adafb3..27b179d`. |
| Backup extra de solo `ventas_mensuales` | 15 MB, rápido (tabla de agregados mensuales, no 25M filas como `stock_diario`). |
| Tag de rollback | `evalutia-etl:pre-ventas-mensuales-fix` (nombre nuevo, no pisa el tag `pre-stock-resumen` de la sesión anterior del mismo día). |
| `git merge --ff-only origin/Develop` en `/opt/evalutia` | Fast-forward limpio, `27b179d` en `HEAD`. |
| Rebuild + recreate `etl` | Confirmado con `CREATED: 33 segundos` (se repitió el chequeo aprendido en el deploy de #59 — esta vez sin el problema del Ctrl+C). |
| Query corregida corrida manualmente, medida con `time` | **10 minutos 5 segundos** — mismo orden de magnitud que `CALC_STOCK_RESUMEN` (9.6 min), consistente con el riesgo de performance anticipado. Terminó sin error. |
| Verificación — conteo total | `SELECT COUNT(*) FROM ventas_mensuales` = **153404** filas (vs. 11639 en local — consistente con la escala de producción). |
| Verificación — caso real afectado en producción | Se encontraron 3 SKUs reales con el patrón del bug (`I00932`, `I00963`, `I01491`). Para `I00963`/nov-2020: `dias_con_stock=3`, `actualizado_en` coincide exactamente con el momento de la corrida — confirma que la fila se recalculó con la query corregida, no que quedó con un valor viejo por casualidad. |

**Resultado: fix desplegado y verificado en producción.** El riesgo de performance identificado se confirmó (10 min, no segundos) pero dentro de lo tolerable para un job batch nocturno sin timeout duro — no rompió nada, terminó limpio.

---

### Intento de sincronizar entorno local con producción — Issue #38 (sesión 2026-07-13, pausado)

| Decisión | Definición |
|----------|-----------|
| **Alcance: dump parcial, no completo** | Excluir `usuarios` (hashes de contraseñas reales), `jobs_historial` y `predicciones` — mismo criterio que un dump parcial usado en una sesión anterior. El objetivo es testear ETL/planilla con volumen y catálogo reales, no replicar el sistema de auth de producción localmente. Igual incluye `ventas_historicas` y `stock_diario` (las tablas grandes), así que no es un archivo chico. |
| **Dump nuevo, no reusar el backup de hoy** | El `mysqldump` completo de 2.6GB tomado esta mañana (antes del deploy de #59) quedó desactualizado por los dos deploys de hoy mismo (`stock_resumen_365` poblada, fix de `ventas_mensuales` de #40) — sincronizar con un dump viejo de horas atrás derrotaría el propósito del issue. |
| **Bloqueador real encontrado: no hay mecanismo de transferencia disponible sin instalar herramientas nuevas** | El acceso a la VM es por AWS Session Manager vía navegador (no SSH directo, no AWS CLI local). Verificado en la VM: `sshd` corre (con `ec2-instance-connect.conf`), pero `aws` CLI **no está instalado**. Sin AWS CLI en ningún lado, ni el camino de S3 (subir desde la VM, bajar desde la consola web) ni el port-forwarding de SSM son viables sin un setup de infraestructura real (instalar awscli + crear bucket S3 + permisos IAM, o habilitar SSH con una key y armar `scp`). |
| **Decisión: pausado, no se invierte el setup hoy** | El issue ya estaba marcado sin urgencia — no vale la pena el trabajo de infra (que además excede el alcance original de "sincronizar datos") solo para sacarlo de encima hoy. Queda documentado el camino técnico mapeado (S3+awscli, o SSH+EC2 Instance Connect) para cuando alguien lo retome con tiempo dedicado. |
| **Hallazgo aparte, no relacionado (informativo, no se tocó)** | El log de `sshd` mostró intentos de fuerza bruta activos (usuarios `root`, `dd`, IP externa) — sugiere que el puerto 22 podría estar expuesto públicamente en el security group. No se investigó ni se tocó; vale la pena revisarlo en algún momento como tema de seguridad aparte. |

---

### `infra/sql/12-fix-grupos-encoding.sql` — Issue #56 (sesión 2026-07-13)

| Decisión | Definición |
|----------|-----------|
| **Causa raíz confirmada con evidencia de bytes, no solo hipótesis** | Se verificaron los bytes crudos (`xxd`) de `infra/sql/10-grupos.sql` (el seed original) para las 4 filas afectadas: el archivo fuente **ya tenía el texto correctamente codificado en UTF-8** (`C38D`=Í, `C389`=É, `C381`=Á, `C3A9`=é, todos de 2 bytes, válidos). La corrupción no está en el archivo — ocurrió al aplicar el seed. Confirmado en vivo: el cliente `mysql` tiene `character_set_client`/`connection`/`results` = `latin1` por default (aunque `character_set_database`=`utf8mb4`) — el mecanismo exacto de la doble codificación. |
| **Fix: script SQL numerado (`12-fix-grupos-encoding.sql`), no un `UPDATE` suelto** | Mismo criterio que el resto de `infra/sql/` — todo cambio de base queda como archivo versionado, aunque sea solo datos y no schema, para que sobreviva a un rebuild completo del entorno desde `01` a `12`. No se re-corre el seed completo de `10-grupos.sql` (reintroduciría el mismo bug si se aplica con la misma conexión mal configurada). |
| **`SET NAMES utf8mb4;` embebido en el archivo, no un flag del comando** | Para que el propio fix no repita el bug que está corrigiendo, sin depender de que quien lo aplique se acuerde de `--default-character-set=utf8mb4` en el comando. Viaja con el archivo. |
| **Error propio detectado y corregido antes de aplicar nada: "Económetrico" → "Econométrico"** | Al transcribir el valor esperado de la fila 201 se escribió mal la posición de la tilde. Verificado byte por byte contra el hex del archivo fuente (`c3a9` cae justo después de "Econom", antes de "trico") — la palabra correcta es "Econométrico" (mismo término usado en todo el sistema: `aplica_modelo_econometrico`, "modelo econométrico"), no "Económetrico". Se verificaron los 4 valores del archivo de fix byte por byte contra el seed original antes de aplicar. |
| **Radio de impacto reverificado** | Único consumidor confirmado de `grupos.descripcion`: `PlanillaRepository.GetFiltros()` (dropdown de filtro de grupo, #45) — que además hace `OrderBy(g => g.Descripcion)`, así que estas 4 filas también estaban mal ordenadas alfabéticamente hasta ahora (efecto secundario menor, se corrige solo con el fix). `ResultadosService.cs` también usa `_db.Grupos` pero solo filtra por `AplicaModeloEconometrico`, no lee `Descripcion` — confirma la afirmación del issue de que ningún otro lugar expone el campo. |
| **Verificado localmente** | Aplicado contra la DB local: las 4 filas pasan de `HEX` con patrón `C383C2XX` (doble-encoding) a `C38D`/`C389`/`C381`/`C3A9` (encoding simple correcto). |
| **Pendiente antes del deploy a producción** | Correr el mismo scan (`HEX(col) LIKE '%C383%'`) contra `articulos` en producción real (el scan local dio 0 filas afectadas, pero el local no está sincronizado con producción — no es representativo, ver #38) para cerrar la segunda parte del alcance del issue ("revisar otras columnas"). |
| **Scan de `articulos` en producción: dos falsos positivos metodológicos descartados antes de confiar en el resultado** | **Intento 1** (`HEX(col) LIKE '%C383%'`, mismo método usado para `grupos`): dio 15 filas en `descripcion` y 9 en `comentario` — revisadas a mano, ninguna tenía mojibake visible. Causa: `LIKE` sobre una cadena hexadecimal puede matchear una subcadena que **cruza el límite entre dos bytes** (ej. `"L8410"` → hex `...4C 38 34...` contiene la subcadena `"C383"` sin que exista un byte real `0xC3` seguido de `0x83`). **Intento 2** (`descripcion LIKE '%Ã%'`, buscando el carácter literal): dio números absurdos (5025/5025 en `descripcion`, 54/66 en `grupos` cuando se sabía que eran 4). Causa: la collation default `utf8mb4_0900_ai_ci` es *accent-insensitive* — `LIKE '%Ã%'` matchea cualquier variante acentuada de "A" (á, à, â, ä...), no el carácter exacto. **Fix metodológico:** `LIKE '%Ã%' COLLATE utf8mb4_bin` (comparación binaria exacta sobre el string ya decodificado, sin el riesgo de alineación de bytes del HEX). Con este método: `grupos.descripcion` = **4** (coincide exactamente con el conteo ya verificado byte a byte) y **todas las columnas de `articulos` = 0**. Confirma que el problema está acotado a las 4 filas de `grupos`, no hay nada más que arreglar. |

**Deploy ejecutado y verificado en producción (2026-07-13, mismo día):**

| Paso | Resultado |
|------|-----------|
| Push + merge en `/opt/evalutia` | Fast-forward limpio, `41cc34b` en `HEAD`. Sin rebuild de contenedores — es un `UPDATE` puro, no toca código de `webapi`/`etl`. |
| Snapshot pre-fix | Confirmado: producción tenía el mismo patrón `C383C2XX` que local antes del fix, en las 4 filas (28, 50, 67, 201). |
| Aplicación | `12-fix-grupos-encoding.sql` corrido contra producción — sin error. |
| Verificación post-fix | Las 4 filas con `HEX` limpio (`C38D`/`C389`/`C381`/`C3A9`) y texto legible correcto. |

**Resultado: fix desplegado y verificado en producción, issue #56 completamente cerrado** (incluyendo la parte de "revisar otras columnas", con el scan corregido dando 0 en `articulos`).

---

### Plan de verificación — Issue #58 (sesión 2026-07-13)

| Decisión | Definición |
|----------|-----------|
| **La fecha específica del issue (2026-06-27) ya no es lo relevante** | Pasaron ~17 corridas nocturnas desde entonces. La pregunta real hoy no es "¿corrió bien esa noche puntual?" sino "¿está sano `planilla_ventas_calculada` *ahora*". Se abandona la verificación por fecha específica de `jobs_historial` a favor de chequear el estado actual directamente. |
| **Chequeo combinado, no dos pasadas separadas** | `MAX(ts_carga)` reciente por grupo ya implica que el job viene corriendo bien las últimas noches — solo si algo sigue viejo/en cero vale la pena bucear en `jobs_historial` noche por noche para encontrar cuándo volvió a fallar. |
| **Query amplia sobre toda la tabla, no solo el grupo 50 de ejemplo** | El hallazgo original decía que el congelamiento afectaba "a toda la tabla, no solo a los grupos nuevos". Chequear solo el grupo 50 confirmaría ese caso puntual pero no descartaría que otro de los 65 grupos nuevos haya quedado atascado por una razón distinta. Query: `GROUP BY grupo_id HAVING MAX(ts_carga) vieja OR meses < 10` sobre todos los grupos. |
| **Se corre contra producción, no contra local** | El catálogo local (~104 SKUs, solo grupo 201) no tiene los grupos nuevos (ej. grupo 50, 740 SKUs) — esta verificación no es posible localmente, confirmado por los hallazgos de #38. |

**Resultado (verificado contra producción, 2026-07-13):**
- Query amplia (todos los grupos, `HAVING ts_carga vieja OR meses < 10`): **0 filas** — ningún grupo rezagado.
- Grupo 50 (el ejemplo del issue original): `ultima_carga = 2026-07-13 03:34:09` (anoche), **13 meses** completos, 744 SKUs.

**Conclusión: #58 se resolvió solo con el paso del tiempo** — la hipótesis del propio issue ("debería autoresolverse sin intervención") era correcta. No hizo falta ningún cambio de código ni de datos.

---

### Almacenamiento y montaje de certificados mTLS — Issue #49 (sesión 2026-07-13)

| Decisión | Definición |
|----------|-----------|
| **Excepción a la regla de secuencia acordada** | La sesión del 2026-06-25 había definido que el plan de mTLS arranca "después de cerrar los issues en curso de la planilla" — #61-67 (Parte A) siguen técnicamente abiertos (pausados esperando la respuesta de Rodrigo sobre "Ticket", sin fecha). Se decide hacer una excepción explícita: avanzar con #49 mientras Parte A está bloqueada externamente, en vez de quedar sin avanzar nada a la espera. |
| **Archivos reales ya disponibles** | Encontrados en `Descargas/infra cliente/` del usuario: `ca.crt`, `cotech-dev.p12`, `cotech-prod.p12` + 2 PDFs de instructivo de IT. Verificado (`openssl x509`, solo el `.crt` público, no se tocaron los `.p12`): CA emitida por "MG Soluciones IT" (coincide con el contacto ya documentado, Martín García), válida 2026-06-16 a 2036-06-13. |
| **Transferencia: base64 por terminal, no SSH/S3** | Los archivos son chicos (~2-4KB cada uno) — a diferencia del intento de sincronizar la DB completa en #38 (multi-GB, requería SSH+EC2 Instance Connect o S3), acá alcanza con codificar en base64 y pegar el texto por la sesión de Session Manager, decodificando del otro lado con `base64 -d`. Sin instalar herramientas nuevas ni tocar el security group. |
| **Alcance: solo `cotech-prod.p12` + `ca.crt`, no `cotech-dev.p12`** | `cotech-dev.p12` es para pruebas manuales desde PC/Mac por terminal — alcance de #53 (runbook), ni siquiera necesita estar en la VM. Subirlo ahora mezclaría el alcance de dos issues sin necesidad; se sube con el mismo mecanismo cuando se aborde #53. |
| **Ruta en el host: `/opt/certs-ws/`** | Hermano de `/opt/evalutia` (el repo desplegado), fuera del control de git. Permisos `700` en la carpeta, `600` en los archivos. Se prefiere sobre `~/certs-ws/` (home de `ssm-user`) porque los volúmenes de Docker Compose son más predecibles con rutas absolutas fuera de `$HOME`, y no depende de qué usuario esté logueado en la VM. |
| **Mount en `docker-compose.yml`** | `volumes: - /opt/certs-ws:/certs:ro` en el servicio `etl`. Solo lectura — ni el ETL ni nada dentro del contenedor necesita escribir ahí. `/certs` del lado del contenedor es la convención de ruta que va a usar `#51` para `CERT_PATH=/certs/cotech-prod.p12` / `CACERT_PATH=/certs/ca.crt` — se deja definida ahora para que ese issue no tenga que redecidir nada. |
| **`.gitignore`** | Se agregan `*.p12`, `*.crt`, `*.pem` — no porque los certs reales vivan en el repo (viven en `/opt/certs-ws`, fuera de git), sino como red de seguridad defensiva si alguna vez alguien copia certs dentro del directorio del repo por costumbre/error, tal como pedía el alcance original del issue. |
| **Manejo de la contraseña del `.p12`** | No se lee el PDF de instructivo ni se extrae la contraseña en esta sesión — #49 es solo almacenamiento/montaje, no requiere la contraseña todavía (eso es uso en tiempo de ejecución, alcance de `#50`/`#51`). Mismo criterio de la sesión anterior: la contraseña no se escribe en ningún archivo del repo. |

**Deploy ejecutado y verificado en producción (2026-07-13, mismo día):**

| Paso | Resultado |
|------|-----------|
| Transferencia por base64 | **Lección real de esta sesión:** pegar el base64 en una sola línea larga (5860 caracteres) o en un solo bloque de 78 líneas cortas **falló dos veces** en la terminal de Session Manager (una vez con `base64: invalid input`, otra con el paste duplicándose a mitad de camino) — el navegador/terminal tiene un límite práctico de tamaño de paste confiable. **Solución que funcionó:** partir el base64 en 4 chunks de ~20 líneas cada uno (`split -l 20`), cargarlos de a uno con `cat >>` (append), verificando `wc -l` después de cada chunk antes de seguir al siguiente. Para transferencias futuras de archivos chicos por este mismo canal, usar chunks de ~20-25 líneas desde el principio, no intentar el archivo completo de una. |
| `ca.crt` transferido | 1935 bytes — coincide exacto con el original. `openssl x509` confirma el mismo certificado (CA de MG Soluciones IT, válido a 2036) tanto local como en la VM. |
| `cotech-prod.p12` transferido | 4394 bytes — coincide exacto con el original (tras descartar un primer intento corrupto de 3071 bytes). |
| Permisos | `/opt/certs-ws` en `700`, ambos archivos en `600`, propietario `root`. |
| `git merge --ff-only origin/Develop` | Fast-forward limpio, `7da23e1` en `HEAD` — confirma que el cambio pendiente de puerto de `webapp` (`WEBAPP_PORT`→`80`) es una modificación local de la máquina de Nico, no algo que exista en el working tree de la VM (el merge no tuvo conflictos). |
| Recreate `etl` | Solo `docker compose up -d --force-recreate` — **sin rebuild**, porque el cambio es únicamente de `docker-compose.yml` (el volumen), no del código dentro de la imagen. Confirmado `CREATED: 30 segundos`. |
| Verificación del mount | `docker compose exec etl ls -la /certs` — ambos archivos visibles dentro del contenedor, mismos tamaños y permisos que en el host. |

**Resultado: Issue #49 completamente implementado, desplegado y verificado.** Los certificados ya están disponibles para que `#50`/`#51` los consuman (`CERT_PATH=/certs/cotech-prod.p12`, `CACERT_PATH=/certs/ca.crt`).

---

### Variables de entorno mTLS sin hardcodear el password — Issue #50 (sesión 2026-07-13)

| Decisión | Definición |
|----------|-----------|
| **No hace falta que el usuario repita la contraseña del `.p12`** | Se encontró ya cargada en el `.env` local (`CERT_PASSWORD`, de una sesión anterior) al revisar la estructura del archivo — no se le pidió repetirla. Para minimizar cuánto aparece en el historial del chat, el valor real de producción se escribe directo en la VM con un comando que usa un placeholder (`CERT_PASSWORD=<REEMPLAZAR>`), sin que el usuario lo pegue de vuelta en la conversación para confirmar. |
| **`.env` local ya tenía `CERT_PATH`/`CACERT_PATH` apuntando a una ruta de Windows con `cotech-dev.p12`** | Es un experimento previo sin terminar (ruta de host de Windows, no tiene sentido para el contenedor Linux de producción) — no se toca como parte de este issue, fuera de alcance. |
| **`CERT_PATH`/`CACERT_PATH` en producción apuntan a `/certs/...` (ruta del contenedor), no a `/opt/certs-ws/...` (ruta del host)** | `.env` es cargado como `env_file` para el servicio `etl` — sus valores los ve un proceso *dentro* del contenedor, donde el mount de #49 expone los certs en `/certs`. Poner la ruta del host sería un error silencioso (el archivo no existiría desde la perspectiva del contenedor). |
| **Limpieza de `WS_URL` en ambos `.env` (local y producción)** | Confirmado que los 4 scripts `run_extract_*.sh`/`run_backfill_ventas.sh` sí requieren `WS_URL` (`: "${WS_URL:?missing}"`), pero **no la leen del `.env`** — llega como parámetro del `.kjb`, y `run_ofelia.sh` la hardcodea (`http://200.125.29.194:81`), ignorando el `.env` por completo. No se borra la variable (los scripts la necesitan si se corren manualmente) — se corrige el placeholder viejo (`https://cliente.com/...`, nunca real) por el valor real ya hardcodeado, con un comentario explicando que el cron nocturno no la usa. |
| **`CERT_PATH`/`CACERT_PATH`/`CERT_PASSWORD` se agregan a `run_ofelia.sh` ahora, aunque queden inertes hasta `#51`** | Verificado en `job_etl_diario.kjb`: no declara ningún parámetro `CERT_*` todavía (es alcance de `#51`). Pentaho Kitchen tolera parámetros `-param` no declarados sin fallar — pasarlos ahora es inofensivo y deja `#51` con menos trabajo (solo declarar los parámetros en el `.kjb` y usarlos, sin tocar `run_ofelia.sh` de nuevo). Se usa `${CERT_PATH:-}` (con default vacío) para no romper `set -u` si la variable no está seteada en algún entorno. |

**Deploy ejecutado y verificado en producción (2026-07-13, mismo día):**

| Paso | Resultado |
|------|-----------|
| Hallazgo al revisar el `.env` de producción antes de tocarlo | A diferencia del local, producción **no tenía ninguna sección de SOAP/ETL** (ni `WS_URL` stale ni nada) — consistente con que `run_ofelia.sh` hardcodea todo y no lee `.env` en el path automatizado. No hizo falta limpiar ningún placeholder ahí, solo agregar las 3 variables nuevas. |
| `git merge --ff-only origin/Develop` | Fast-forward limpio, `0743a22` en `HEAD`. |
| Variables agregadas a `.env` de producción | `CERT_PATH=/certs/cotech-prod.p12`, `CACERT_PATH=/certs/ca.crt` agregadas con un comando visible; `CERT_PASSWORD` agregada con un placeholder (`<REEMPLAZAR...>`) y reemplazada por el usuario mismo con `sed` en un comando aparte — el valor real no se pidió de vuelta en el chat para confirmar (aunque el usuario lo pegó espontáneamente una vez; no es información nueva, ya estaba en el `.env` local visto antes en la sesión). |
| Recreate `etl` | Solo `up -d --force-recreate` (sin rebuild, es config vía `env_file`, no código). Confirmado `CREATED: 32 segundos`. |
| Verificación sin exponer el secreto | `printenv CERT_PATH`/`CACERT_PATH` dentro del contenedor confirmaron los valores correctos. Para `CERT_PASSWORD` se verificó presencia y longitud (`${#CERT_PASSWORD}` = 12, coincide con la contraseña real) sin imprimir el valor. |

**Resultado: Issue #50 completamente implementado y desplegado.** Las 3 variables ya están disponibles en el contenedor `etl` para que `#51` las declare en `job_etl_diario.kjb` y las use en las llamadas SOAP.

---

### `job_etl_diario.kjb` + `run_ofelia.sh` + 4 scripts curl — Issue #51 (sesión 2026-07-13)

| Decisión | Definición |
|----------|-----------|
| **Flags de curl obligatorios, sin fallback a HTTP** | `--cert-type P12 --cert "${CERT_PATH}:${CERT_PASSWORD}" --cacert "${CACERT_PATH}"` se agregan incondicionalmente en los 4 scripts (`run_extract_articulos.sh`, `run_backfill_ventas.sh`, `run_extract_sales_chunk.sh`, `run_extract_stockxml.sh`), con guards `: "${CERT_PATH:?missing}"` etc. al inicio. Ningún camino sigue permitiendo HTTP sin certificado. |
| **Sintaxis exacta según IT** | Se verificó contra `instructivo-cliente-mtls.pdf` de MG Soluciones IT (Martín García): usan `--cert su-nombre.p12:LA_CONTRASEÑA` con la contraseña embebida tras `:`, no `--pass` por separado. Se corrigió una recomendación inicial propia (`--pass`) para igualar exactamente el ejemplo documentado por IT. |
| **`WS_URL` pasa a `https://`** | `run_ofelia.sh`: `-param:WS_URL=https://200.125.29.194:81` (puerto 81 sin cambios, confirmado en el instructivo — el corte es solo de protocolo, no de puerto). |
| **`job_etl_diario.kjb` declara los 3 parámetros nuevos** | `CERT_PATH`, `CACERT_PATH`, `CERT_PASSWORD` — se exponen a las entradas `SHELL` como variables de entorno automáticamente (mismo mecanismo confirmado empíricamente para `WS_URL`/`MYSQL_*`, sin plumbing adicional). |
| **No deployar a producción todavía** | Se comitea y pushea el código (`7af0867`), pero el `docker compose up -d --force-recreate etl` en producción queda explícitamente pendiente hasta que `#52` (coordinación con IT) confirme el 200 OK con mTLS real. Producción sigue corriendo con `WS_URL=http://...` hoy, sin riesgo. |

**Validación en vivo (2026-07-13), antes de comitear:**

| Prueba | Resultado |
|--------|-----------|
| curl mTLS desde la máquina local de Nico | `curl: (28) Connection timed out` — no es error de certificado, es timeout de conexión TCP. Causa: IT solo tiene whitelisteada la IP fija de la VM de producción (`3.150.104.146`), no las IPs dinámicas de oficina (decisión ya documentada en la sesión de `#49`). |
| curl mTLS desde el contenedor `etl` en la VM (IP whitelisteada), usando `CERT_PATH`/`CACERT_PATH`/`CERT_PASSWORD` ya cargados por `#49`/`#50` | TCP conecta, pero TLS falla: `error:0A00010B:SSL routines::wrong version number`. Esto indica que el servidor todavía responde con bytes no-TLS, no que el certificado esté mal. |
| curl HTTP plano (sin cert) al mismo endpoint desde la VM | `HTTP_STATUS:200` — el servidor de IT **todavía sirve HTTP sin cifrar**. Confirma que el corte a mTLS anunciado en el instructivo ("a partir de la fecha de corte que se les comunicará") **aún no ocurrió del lado de IT**. |
| **Conclusión** | El código, la sintaxis de curl, el cert, la URL y el puerto están correctos y listos. El bloqueo restante es 100% del lado de IT (fecha de corte pendiente) — no hay nada más para corregir en el código de `#51`. |

> **Nota para `#52`:** cuando IT confirme la fecha de corte, repetir la prueba de curl mTLS desde la VM (`sudo docker compose exec etl bash -c 'curl -v --cert-type P12 --cert "${CERT_PATH}:${CERT_PASSWORD}" --cacert "${CACERT_PATH}" "https://200.125.29.194:81/VsWebProduccion/SwNadWeb.asmx"'`) — si responde WSDL/HTML, recién ahí se hace `docker compose up -d --force-recreate etl` en producción para activar el `WS_URL=https://...` ya comiteado.

---

### Runbook (#53) y plan de rollback (#54) — sesión de grill-me pausada (2026-07-13)

| Decisión | Definición |
|----------|-----------|
| **Hallazgo que contradice el plan original de junio** | La sesión de `/grill-me` del 2026-06-25 (ver sección "Plan de trabajo — Migración a mTLS") había anotado que *"IT optó por no fijar en el firewall las IPs dinámicas de la oficina... el acceso queda cubierto únicamente por el certificado"*. La prueba real de hoy (ver sesión de `#51` arriba) usó exactamente ese escenario — `curl` con `cotech-dev.p12` desde la máquina de oficina de Nico (IP dinámica, no whitelisteada) — y dio **timeout de conexión TCP**, no un rechazo de certificado. Esto pone en duda esa premisa: el firewall de IT podría estar bloqueando por IP también para el certificado de prueba, no solo para el de producción. |
| **No confirmado todavía si aplica también a la oficina del socio** | Solo se probó desde la IP de Nico. La IP del socio (`179.24.239.134`, según el plan de junio) no se probó — sigue siendo una incógnita separada. |
| **El mail ya enviado a Martín no cubre esta pregunta** | El mail enviado hoy (sesión de `#51`/`#52`) solo pregunta por la fecha de corte — no menciona la duda sobre si las IPs de oficina (de Nico y su socio) van a estar habilitadas para el certificado `cotech-dev.p12`. Queda pendiente decidir si se manda como pregunta de seguimiento o se espera la respuesta del mail actual primero. |
| **Decisión: pausar #53 y #54 hasta la respuesta de Martín** | El usuario decidió no redactar ninguno de los dos documentos todavía — se prefiere esperar la confirmación real de IT antes de invertir tiempo en documentar un flujo que podría no funcionar tal como está planteado. Se descartó la alternativa (redactar igual con un aviso de riesgo marcado) que se había recomendado. |

> **Nota:** `#54` ya tenía una dependencia declarada desde el plan original (`Depende de: #52`). Lo nuevo de esta sesión es que `#53` (que decía "Depende de: —") en la práctica también quedó bloqueado por la misma incertidumbre de IT, aunque no estaba declarado así en el issue.

---

### Criterio de elegibilidad para modelo econométrico — Issue #70 (sesión 2026-07-13)

| Decisión | Definición |
|----------|-----------|
| **Ambigüedad resuelta: no hay "ensemble" contra el cual comparar** | El texto original de `#70` pedía comparar el R²/RMSE walk-forward del modelo econométrico "vs. el ensemble que hoy se le asignaría a ese SKU". Verificado en código (`run_predict.sh` + `get_skus_modelo.py`): `predict.py` corre una sola vez por noche, filtrado a los SKUs de `grupos.aplica_modelo_econometrico = TRUE` (hoy solo grupo 201, ~104 SKUs); si esa lista da vacía, `run_predict.sh` aborta sin correr nada. Los ~5400 SKUs restantes **no reciben ninguna predicción hoy** — no existe un "ensemble" corriendo para ellos contra el cual comparar. Además, `#68` ya había establecido que "modelo econométrico" y "ensemble" son el mismo código (RF+XGB+Prophet), no dos cosas distintas. |
| **Elegibilidad = criterio absoluto sobre métricas propias, no comparativo** | Se decide qué SKUs *nuevos* merecen empezar a recibir predicción evaluando solo las métricas walk-forward de ese SKU (sin rival contra el cual medirse). Construir un modelo baseline nuevo para poder comparar quedó descartado — está fuera del alcance/estimación de `#70` (1-2h) y del acuerdo de precio fijo con Rodrigo (ver [[project_rodrigo_pricing_agreement]]); el cliente nunca pidió un baseline, pidió usar R² para saber cuándo confiar en el econométrico. |
| **Mínimo de historia: 24 meses (8 trimestres)** | No es un número nuevo — coincide exactamente con el mínimo que `fit_prophet_insample` (`ml/models.py:415`) ya exige para poder correr (`min_needed = 8` en frecuencia trimestral, comentario original: "al igual que el notebook: 8 trimestres"). Verificado con `walk_forward_split`: 8 trimestres de historia producen **3 folds** evaluables (no solo 2), dando mejor señal de estabilidad que el piso mínimo técnico. Se descartó agregar un umbral de meses inventado aparte — este ya es el que efectivamente usa el sistema. |
| **Métrica y umbral** | `r2_test` (walk-forward) del modelo que ganaría por menor RMSE in-sample en ese SKU — la misma lógica de selección que ya usa `predict.py` en producción. Umbral: **`r2_test ≥ 0`** (el modelo generaliza mejor que predecir la media). Se descartó el umbral de 0.3 usado en `#69` para juzgar la salud general del grupo — ese umbral es para el diagnóstico agregado, no para elegibilidad por SKU individual: aplicado literalmente dejaría fuera al grupo 201 actual (mediana real de `r2_test` del modelo seleccionado: 0.0659), que el cliente ya usa y acepta. |
| **Estabilidad como descalificador duro, no solo aviso** | Un SKU clasificado "volátil" en `#78` (`std(r2_test) ≥ 0.2` entre folds, con ≥2 folds) queda **no elegible** aunque su `r2_test` mediano pase el umbral — un número que salta fuerte según qué trimestre se mida no es una señal confiable para el cliente. |
| **SKUs con solo 1 fold evaluable** | No se puede medir estabilidad con un solo fold — se tratan como **no elegibles por ahora** (no como "elegibles sin verificar"), consistente con que `#70` pide incorporar estabilidad como factor de decisión, no solo el promedio. En la práctica esto ya queda cubierto por el piso de 24 meses (8 trimestres → 3 folds), así que no debería ser un caso frecuente entre los SKUs que sí cumplen el mínimo de historia. |
| **`r2_test ≥ 0` es un umbral débil a propósito — riesgo detectado y mitigado, no ignorado** | Con `horizon=4` (4 puntos de test por fold), el error estándar de una correlación estimada es ~1 (`1/√(n-3)` con n=4) — un `r2_test` de 0.2-0.4 puede aparecer por puro ruido estadístico. El umbral `≥0` casi no filtra nada por sí solo; el filtro real de calidad lo hace la regla de estabilidad (folds consistentes entre sí), no la magnitud del R². Se mantiene igual (no se sube el umbral) porque la alternativa para estos SKUs hoy es **cero predicción** — pasar a tener una, aunque con señal débil, sigue siendo una mejora, siempre que no se le oculte al cliente qué tan débil es esa señal (ver punto siguiente). |
| **Transparencia: el `r2_test` real se expone al cliente, no solo un flag binario "elegible"** | Decisión explícita del usuario: no alcanza con que un SKU "pase" el gate de elegibilidad — el valor real de `r2_test` debe llegar a la UI/export junto con la predicción, para que el cliente distinga un SKU con `r2_test=0.35` de uno con `r2_test=0.02` (ambos "elegibles" bajo el gate binario). Esto conecta directo con la motivación original de `#30`: *"el cliente solicita un modelo econométrico que muestre la fiabilidad de los datos para saber cuándo tomarlo en cuenta"* — el gate decide si hay predicción; el número real es lo que le permite al cliente decidir cuánto confiar en ella. `#71` ya contempla persistir "las métricas de R²/RMSE del holdout" a nivel SKU en su alcance original — este punto confirma que ese dato no es solo para uso interno/diagnóstico, tiene que ser visible para el cliente (alcance de UI queda para el issue de frontend correspondiente, no de `#70`/`#71`). |

> **Nota para `#71`/`#72`/`#73`:** el criterio completo a implementar es: **historia ≥ 24 meses** Y **`r2_test` (walk-forward, modelo ganador por RMSE) ≥ 0** Y **no volátil** (`std(r2_test) < 0.2` entre folds). Los tres deben cumplirse — no es un score ponderado ni umbrales alternativos. `n_train_rows` (señal de confianza de `#78`) queda como dato informativo en el reporte, no como cuarto criterio duro. Además, el `r2_test` persistido por SKU (`#71`) debe quedar accesible para mostrarse al cliente, no solo para uso técnico interno — probablemente amerita un issue de frontend aparte para decidir dónde/cómo mostrarlo (ej. planilla, tooltip, columna de export).

---

### Migración de elegibilidad a nivel-SKU — Issue #71 (sesión 2026-07-13)

| Decisión | Definición |
|----------|-----------|
| **Tabla nueva dedicada, no columnas en `articulos`** | `articulos_elegibilidad_econometrico` (PK `sku`, FK a `articulos`). Los campos (elegible, `r2_test`, estable, folds, fecha de evaluación) son resultado del pipeline de ML, no datos del ERP — separarlos de `articulos` mantiene la línea clara entre "lo que dice el SOAP" y "lo que calculamos nosotros", y evita que `run_extract_articulos.py` (que hace upsert masivo con lista explícita de columnas) tenga que acordarse de excluirlos. |
| **Riesgo de rollout detectado y mitigado: seed obligatorio en la misma migración** | `get_skus_modelo.py` migra a leer de la tabla nueva; si esa tabla queda vacía al momento del deploy (porque `#72`/`#73`, que recién van a poblarla con la evaluación completa, corren *después* de `#71` en el roadmap), `run_predict.sh` aborta sin correr nada — no solo no se agregan SKUs nuevos, se **pierde la predicción de los 104 SKUs que ya funcionan hoy en producción**. Se decide sembrar la tabla nueva, como parte del mismo script SQL de `#71`, con los SKUs actuales de `grupos.aplica_modelo_econometrico = TRUE` marcados `elegible = TRUE` (mismo patrón que el backfill de `grupo_id` en `10-grupos.sql`, vía `INSERT ... SELECT`, no lista hardcodeada). Cero cambio de comportamiento real hasta que `#72`/`#73` recalculen con el criterio completo. |
| **`grupos.aplica_modelo_econometrico` no se elimina** | Se deja como columna muerta, sin `DROP COLUMN` ni cambios en `10-grupos.sql`. Es la operación más difícil de deshacer del lote — si algo falla con la tabla nueva en producción, la columna vieja queda de referencia/rollback trivial sin restaurar backup. Limpieza como issue de deuda técnica aparte, una vez `#72`/`#73` estén validados en producción. |
| **Esquema exacto** | `sku PK/FK`, `elegible BOOLEAN NOT NULL DEFAULT FALSE`, `r2_test DOUBLE NULL`, `estable BOOLEAN NULL` (NULL = no evaluable, <2 folds), `n_folds TINYINT UNSIGNED NULL`, `meses_historia SMALLINT UNSIGNED NULL`, `evaluado_en TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)`. `ON DELETE CASCADE` en la FK (consistente con que `articulos` prácticamente nunca borra filas, usa el enum `estado` en su lugar). |
| **Archivo de migración** | Próximo número disponible en `infra/sql/`: `13-articulos-elegibilidad-econometrico.sql` (el 12 ya lo usó `#56` para el fix de encoding de grupos). |

> **Nota:** `#71` es deliberadamente acotado a schema + wiring de `get_skus_modelo.py` + seed de continuidad — la evaluación real sobre los ~5400 SKUs candidatos y la aplicación del criterio completo de `#70` quedan para `#72`/`#73`, que van a hacer `UPDATE`/`INSERT ... ON DUPLICATE KEY UPDATE` sobre esta misma tabla con los resultados reales del walk-forward.

**Falla real encontrada y corregida antes de commitear:** el `CREATE INDEX` separado (fuera del `CREATE TABLE IF NOT EXISTS`) no es idempotente en MySQL — reventaba con `Duplicate key name` al re-ejecutar el script. Se movió el índice adentro del `CREATE TABLE` (como `KEY` inline) para que todo el archivo sea seguro de re-correr, dado el patrón ya visto en esta sesión de comandos de deploy repetidos por error (Ctrl+C, reintentos). Verificado localmente: 2 corridas seguidas, silenciosas, sin duplicar filas.

**Deploy ejecutado y verificado en producción (2026-07-13, mismo día):**

| Paso | Resultado |
|------|-----------|
| `git merge --ff-only origin/Develop` | Fast-forward `0743a22..1000185` — trajo también los commits de `#51` (mTLS), todavía no activados. |
| **Riesgo detectado a tiempo:** rebuild/recreate de `etl` activaría `#51` de forma prematura | `get_skus_modelo.py` queda horneado en la imagen de `etl` (`COPY . /app` en el `Dockerfile`) — un rebuild para activar `#71` también activaría `WS_URL=https://...` de `#51`, todavía gateado por `#52` (IT no cortó a mTLS). Se decide aplicar **solo la migración SQL** ahora (segura, no toca código en ejecución) y posponer el rebuild/recreate de `etl` hasta que `#52` confirme el corte — momento en el que `#51` y `#71` se activan juntos en el mismo rebuild. |
| Migración SQL aplicada | Sin errores. |
| Checkpoint duro | `deberia_haber` (query real contra `grupos`) = **101**, `quedo_sembrado` (tabla nueva) = **101** — coinciden exactamente. (Producción tiene 101 SKUs en grupo 201 hoy, no 104 como el dump local usado para probar — la migración se adapta al dato real vía `INSERT...SELECT`, no una lista fija.) |
| Estado actual | Migración aplicada y verificada; contenedor `etl` **sin recrear todavía** — sigue leyendo de `grupos` (código viejo), cero cambio de comportamiento. Pendiente: rebuild/recreate conjunto de `#51`+`#71` cuando `#52` lo habilite. |

---

### Hallazgo: ventas negativas (notas de crédito) se pierden en todo el pipeline — Issue #79 (sesión 2026-07-13)

Rodrigo respondió por mail la pregunta bloqueante de `#61` ("Histórico" ya había sido aceptado antes; "Ticket" quedó definido ahora): *"la info que reciben ustedes si tienen las notas de crédito, son las ventas negativas que aparecen de vez en cuando... si pueden obtener la cantidad de días de un mes que hubo ventas (sean negativas o positivas), tengo todos los datos que necesito... para mí es mejor cerrarlo por día."*

| Decisión | Definición |
|----------|-----------|
| **"Ticket" queda definido** | Un día del mes con al menos una fila de venta en `ventas_historicas` (positiva o negativa) — contado por día, no por transacción individual. Decisión explícita del cliente, no interpretación nuestra. |
| **Bloqueo real encontrado antes de poder implementar `#61`** | El sistema hoy **descarta el signo de las ventas negativas antes de guardarlas** — `run_extract_sales_chunk.py` tiene `clamp_nonneg_int()` que hace `max(0, n)`, y 5 tablas (`ventas_historicas`, `ventas_historicas_stage`, `ventas_mensuales`, `planilla_ventas_calculada`, `stock_resumen_365`) son `UNSIGNED`/`CHECK >= 0`. Un día con solo una nota de crédito (sin venta positiva ese día) queda indistinguible de un día sin ninguna venta — para todo el histórico, no solo de ahora en más (afecta tanto la carga diaria como el backfill, mismo script). |
| **Auditoría completa: 15-18 archivos en 4 capas interdependientes** | Esquema (3 SQL) + ETL (6 archivos, incluye `job_etl_diario.kjb` — el paso real que persiste en producción, no solo el script de staging) + ML (`ml/models.py`: `fit_prophet_insample` descarta filas de **entrenamiento** con `y<0`, sesgando el modelo — no es solo un problema de tipos) + Backend (6 archivos). Ninguna capa se puede tocar sola: migrar el esquema sin arreglar el backend primero generaría corrupción silenciosa. |
| **Hallazgo más peligroso de la auditoría** | `VentaRepository.cs` hace `(uint)g.Sum(x => x.Cantidad)` — en C#, castear un negativo a `uint` sin `checked` no tira excepción, da wraparound (`-5` → `4294967291`). Hoy está "dormido" (cantidad nunca es negativa en la DB), pero se activa en cuanto se migre el esquema si no se arregla en el mismo esfuerzo — corrompería datos mostrados al cliente sin ningún error visible. |
| **Estructura en GitHub: issue paraguas + 4 issues por capa** (decisión explícita del usuario, prefirió granular sobre un solo issue grande) | `#79` (paraguas, documenta el hallazgo completo) → `#80` [DB][ETL] esquema+pipeline (raíz, sin dependencias) → `#81` [ML] Prophet + heurísticas de primera venta (depende de `#80`) → `#82` [Backend] tipos signed + fix del cast wraparound + rediseño de `GetAbcClassification` (depende de `#80`) → `#83` [Frontend] UX de valores negativos, baja prioridad (depende de `#82`). |
| **`#61` no se cierra** | La definición de "Ticket" queda registrada y aceptada (comentario en el issue), pero `#61` queda bloqueado por `#79` hasta que el pipeline pueda preservar el signo real. `#62`-`#67` (que dependen de `#61`) heredan el mismo bloqueo. |

> **Nota:** `stock_diario`/`planilla_sugerencias` (stock físico) y `predicciones.cantidad_predicha` (pronóstico futuro) **no se tocan** — son conceptos distintos de "venta neta histórica" y sus `CHECK >= 0` son correctos (no tiene sentido un stock o un pronóstico futuro negativo).

---

### Diseño del fix de esquema+ETL — Issue #80 (sesión 2026-07-13)

| Decisión | Definición |
|----------|-----------|
| **Alcance acotado: integridad de datos, no rediseño de negocio** | `#80` se limita a preservar el signo real de principio a fin sin romper nada (esquema + tipos + agregados numéricamente correctos). El rediseño de la lógica de "Ticket"/frecuencia (`meses_con_ventas`, `frecuencia_nivel` en `run_calc_planilla.py`) queda 100% para `#63` — no se toca en `#80`. Verificado que esto no genera un vacío: el clamp ocurre a nivel de fila diaria antes de cualquier agregación, así que corregirlo no cambia el resultado de la clasificación `vq > 0` existente (un mes cuya única venta fue una devolución da `0` hoy y daría un negativo con el fix — ambos casos fallan `> 0` igual). El efecto real es que los totales (`ventas_mensuales`, gráficos) pasan a ser netos reales en vez de brutos-con-clamp-silencioso. |
| **Backfill histórico: fuera del alcance de `#80`, coordinado con `#63`/`#64`** | El clamp ocurre al insertar cada fila — todo el histórico ya guardado en `ventas_historicas` tiene el signo perdido para siempre; la única forma de recuperarlo es re-pedirle esos días al SOAP y re-correr `run_backfill_ventas.sh` con el fix aplicado. No se mete en el criterio de aceptación de `#80` (ya es grande: 15-18 archivos, 4 capas) — se agenda como parte de `#64` (QA de frecuencia contra datos reales), que de todos modos necesita datos reales para validar la fórmula. |
| **Tipo de columna: `INT` signed, sin `CHECK` de reemplazo** | Se descarta poner un límite arbitrario (ej. `BETWEEN -999999 AND 999999`) — sería un número inventado sin caso real que lo justifique. El rango natural de `INT` (±2.147 mil millones) ya es más que suficiente; un valor corrupto real del SOAP se ataja en el manejo de errores del ETL, no con un CHECK en la tabla. |
| **Migración idempotente con patrón defensivo** | La migración toca 5 tablas con `DROP CHECK` + `MODIFY COLUMN`. `DROP CHECK` sobre una constraint que ya no existe falla (a diferencia de `MODIFY COLUMN`, que sí es seguro de repetir) — se usa el mismo patrón ya existente en `04-etl-staging.sql` (chequear `information_schema` + SQL dinámico antes de alterar), dado el incidente real de comando repetido que ya tuvimos hoy mismo en `#71`. |
| **Verificado: sin filtros de signo ocultos en `job_etl_diario.kjb`** | Los pasos `MERGE STAGING -> VENTAS` y `CALC_UPSERT_VENTAS_MENSUALES` son `SUM(...)` planos, sin `WHERE cantidad > 0` ni filtro similar — con el esquema signed funcionan sin tocar una sola línea de SQL del `.kjb`, el problema es 100% de tipos. |

> **Nota:** `services/etl/run_extract_sales_chunk.py` necesita una función nueva (no reusar `clamp_nonneg_int`) para `cantidad` — el uso existente de esa función sobre `stock` (líneas ~122-124, 137 del mismo archivo) debe seguir clampeado a 0 sin cambios, es un concepto distinto (inventario físico, no venta neta).

**Corrección encontrada en la revisión final (antes de commitear):** solo `ventas_historicas` tiene un `CHECK` nombrado (`chk_ventas_cantidad`), verificado directo contra `information_schema.check_constraints` — las otras 4 tablas dependen solo del tipo `UNSIGNED`, sin `CHECK` propio. El patrón defensivo de `DROP CHECK` aplica a una sola tabla, no a las 5; las otras 4 solo necesitan `MODIFY COLUMN` (ya idempotente por sí solo). Esto simplificó la migración final respecto a la versión inicial documentada arriba.

**Implementado y verificado en DB local (2026-07-13, mismo día):**

| Paso | Resultado |
|------|-----------|
| `infra/sql/14-ventas-cantidad-signed.sql` | Aplicada 2 veces seguidas — segunda corrida silenciosa (toma la rama `SELECT 1` para el `DROP CHECK`), sin error. |
| Tipos resultantes (las 5 tablas) | Confirmado `signed` (sin `unsigned`) vía `information_schema.columns`. |
| `run_extract_sales_chunk.py`: `clamp_signed_int` nueva, usada solo para `cantidad` | `stock` (líneas 133, 146) confirmado sin tocar — sigue en `clamp_nonneg_int`. |
| Prueba sintética end-to-end (SKU `TEST-NEG-80`, neto `-5`) | Insertado en `ventas_historicas_stage` → simulado el paso MERGE del `.kjb` → `-5` llegó intacto a `ventas_historicas` → simulado `CALC_UPSERT_VENTAS_MENSUALES` → `-5` llegó intacto a `ventas_mensuales`. Sin error, sin rollback. Datos de prueba borrados después de verificar. |
| Commit y push | `d6d0ce9` — solo los 2 archivos de código + `CONTEXTO.md`, `docker-compose.yml` (cambio no relacionado de `WEBAPP_PORT`) queda fuera, mismo patrón que `#51`/`#71`. |
| **Deploy a producción: decidido no tocar todavía** | Mismo acoplamiento que `#71`: el rebuild/recreate de `etl` (necesario porque el script queda horneado en la imagen) activaría también `#51` (mTLS), gateado por `#52`. A diferencia de `#71`, acá el usuario decidió **no aplicar ni siquiera la migración SQL sola** en producción por ahora — `#80` queda pusheado pero sin ningún cambio en la VM, abierto en GitHub. |

---

### Extender evaluación holdout a todo el catálogo — Issue #72 (sesión 2026-07-13)

| Decisión | Definición |
|----------|-----------|
| **Hallazgo: "extender a todos los candidatos" ya está resuelto estructuralmente** | `ml/eval_walkforward.py` + `load_series_by_sku_mysql` no filtran por grupo — sin `EVAL_ONLY_SKUS` seteado, ya evalúan **todo** `ventas_historicas`. Lo que realmente falta es la persistencia (hoy solo imprime/CSV) y dos cálculos nuevos. |
| **`#72` persiste solo métricas crudas, no `elegible`** | Escribe `r2_test`/`estable`/`n_folds`/`meses_historia` en `articulos_elegibilidad_econometrico` (tabla de `#71`) — la columna `elegible` no se toca acá. `#73` ("Aplicar criterio y marcar SKUs") es quien calcula y escribe el flag final para todo el catálogo, incluyendo recalcular los 101 SKUs de grupo 201 que hoy están `elegible=TRUE` por el seed provisorio de `#71`. Separa "medir" de "decidir", consistente con los nombres de los issues. |
| **`meses_historia` = span calendario, cálculo nuevo** | `(fecha_max - fecha_min)` en meses + 1, por SKU, contra `ventas_historicas` — no existía en el script (que solo tenía `n_train_rows_mean/min`, un concepto distinto: filas reales de entrenamiento por fold, no historia total). Es la métrica que realmente limita a Prophet (necesita que la serie resampleada tenga ≥8 trimestres de longitud). |
| **Se persiste el modelo *ganador* por SKU, no los 3 por separado ni un promedio** | Reusa la lógica ya existente en el script (`winners = valid.loc[valid.groupby("sku")["rmse_train_median"].idxmin()]`) — el modelo que ganaría por menor RMSE in-sample, misma selección real de `predict.py`. Coincide exactamente con la definición del criterio de `#70` ("el modelo que ganaría por RMSE en ese SKU"). |
| **Ejecución real contra producción, vía VM** | La DB local solo tiene los ~104 SKUs de grupo 201 sincronizados (`#38`, todavía sin resolver) — no el catálogo completo (~5500 SKUs). Correr contra local no evaluaría "todos los candidatos" de verdad. Se corre contra producción: de solo lectura sobre `ventas_historicas` + `INSERT/UPDATE` acotado a la tabla de `#71`, bajo riesgo, no bloqueado por `#38`. |
| **Commits incrementales + corrida en background (`nohup`), no una transacción gigante** | A diferencia del patrón de `run_calc_stock_resumen.py` (una sola transacción con `executemany`, aceptable ahí porque tardó ~9.6 min con una simple suma SQL), acá el volumen de trabajo es mucho mayor (RF+XGB+Prophet × hasta 5 folds × ~5500 SKUs) y puede tardar horas — commits por SKU/lote evitan perder todo el progreso si se corta, y `nohup` evita que la terminal de Session Manager (ya mostró fragilidad esta sesión) mate la corrida si se desconecta. Naturalmente reanudable vía `INSERT ... ON DUPLICATE KEY UPDATE`. |

> **Nota:** el tiempo real de ejecución medido en esta corrida es insumo directo de `#74` (medir impacto de performance del job nocturno con volumen ampliado) — no hace falta medirlo aparte.

---

### Plan de trabajo para el corte mTLS del viernes 18/07 (sesión 2026-07-13)

Martín García (MG Soluciones IT) confirmó por mail: curl del lado de ellos listo, propuso fecha de corte y un procedimiento de 3 pasos. Se le contestó confirmando `curl 7.81.0`/OpenSSL 3.0.2 (verificado localmente contra la misma imagen base de `etl`), que no hay otros sistemas propios que consuman el WS, y se aceptó **viernes 18/07, 9-12hs**.

| Decisión | Definición |
|----------|-----------|
| **No se crea un issue nuevo — se actualiza `#52`** | El alcance de `#52` ya coincidía casi punto por punto con el procedimiento de Martín. Se le agrega la fecha concreta y el paso nuevo que no tenía: probar **primero sin certificado** y confirmar que rechaza (`tlsv13 alert certificate required`) — prueba más fuerte que solo confirmar `200 OK` con certificado, valida que el servidor realmente exige mTLS. |
| **`#53` sigue pausado** | El mail de Martín no resuelve la pregunta que lo bloqueaba (si las IPs dinámicas de oficina de Nico/socio van a estar habilitadas para `cotech-dev.p12`) — es un tema distinto del corte de producción del viernes, sigue sin info nueva. |
| **`#54` se redacta ahora** | Antes era hipotético; ahora hay info concreta: Martín confirmó que el rollback de su lado es inmediato y sin impacto ("vuelve a HTTP plano"), y el rollback de nuestro lado es trivial — simplemente no mergear/deployar el cambio de `WS_URL` a `https://`, seguimos en `http://` sin ningún riesgo. |
| **Migración SQL de `#80` se aplica en producción antes del viernes, desacoplada del corte** | Si el viernes se recrea `etl` con el código de `#80` pero sin la migración aplicada, `run_extract_sales_chunk.py` intentaría insertar negativos en una columna todavía `UNSIGNED` — no rompe el job (el `try/except` ya existente descarta la fila y sigue) pero vuelve silenciosamente al comportamiento viejo (pierde el signo) hasta que se aplique. Aplicarla antes evita esa sorpresa durante la ventana acotada del viernes (9-12hs) — es de bajo riesgo, ya verificada localmente (idempotente, sin errores), y no depende en nada del corte mTLS. |

**Plan resultante (orden de ejecución):**
1. Aplicar migración de `#80` en producción (cualquier momento antes del viernes, independiente de todo lo demás).
2. Viernes 18/07, 9-12hs, coordinado en vivo con Martín: correr los 3 pasos de `#52` (rechazo sin cert → `200 OK` con cert → corrida manual del job).
3. Si los 3 pasos pasan: `docker compose build etl` + `up -d --force-recreate etl` — activa `#51` (mTLS/`WS_URL=https`) + `#71` (elegibilidad SKU, ya migrado) + `#80` (ventas negativas, ya migrado) juntos en la misma imagen.
4. Si algo falla: no se hace el rebuild/recreate — se sigue en `http://` sin impacto, tal como confirmó Martín de su lado.
5. Verificar el primer cron nocturno real post-corte (esa misma noche, 3 AM) antes de dar por cerrado `#51`/`#52`.

**`#54` redactado (comentario en el issue, 2026-07-13):** aclarado que el plan aplica *después* del corte definitivo, no al día de la prueba en sí (eso es trivialmente seguro, ya cubierto por `#52` — si falla, simplemente no se deploya). Procedimiento: el cron falla atómico sin corromper nada → diagnosticar vía `docker compose logs etl` → resolver (cert vencido, `.env` mal seteado, o coordinar con Martín si es de su lado) → recuperar con `FORCE_START`/`FORCE_END` (mismo mecanismo de `#44`) → confirmar `exitoso` en `jobs_historial`. Sin fallback a HTTP, sería código muerto.

---

### Retomado: sincronizar entorno local con producción — Issue #38 (sesión 2026-07-13)

Motivación actual (más amplia que el alcance original del issue, que era puntual a #34/#35): el usuario quiere poder desarrollar y debuggear localmente con datos reales de producción, usando la VM únicamente para deployar cambios ya validados — no depender de la VM para cada lectura/prueba.

| Decisión | Definición |
|----------|-----------|
| **Transporte: S3, no túnel SSM** | Subir el dump desde la VM a un bucket S3 con `aws s3 cp`, bajarlo en local igual. Se descarta `aws ssm start-session --document-name AWS-StartPortForwardingSession` (túnel directo a MySQL de la VM) por menor privilegio: la credencial de S3 solo puede tocar un bucket puntual (`s3:GetObject`/`PutObject`), el túnel SSM requeriría `ssm:StartSession` sobre la instancia — una puerta de acceso de red mucho más amplia. Además el volumen (~2.6 GB, visto en el backup de `#59`/`#60`) es más robusto de mover por S3 que sostenido en un túnel en vivo. |
| **`usuarios` se excluye del dump** | Contiene credenciales reales de usuarios del cliente (contraseñas hasheadas + correos reales) — no aporta nada a lo que se busca validar (Planilla, predicciones, elegibilidad) y expondría datos de usuarios reales en una máquina de desarrollo sin necesidad. El entorno local sigue usando el admin local ya seedeado por `99-creacion-admin.sql`. Se sincroniza el resto completo: `articulos`, `ventas_historicas`, `ventas_mensuales`, `stock_diario`, `grupos`, `articulos_elegibilidad_econometrico`, `predicciones`, `jobs_historial`. |
| **Proceso documentado y repetible, no un dump puntual** | Dado que el objetivo es trabajar localmente de forma continua (no una vez y listo), se arma un script de cada lado (dump+upload en la VM, download+import en local) en vez de un procedimiento ad-hoc que haya que re-derivar cada vez que la producción avance. |
| **Credencial AWS en `~/.aws/credentials`, perfil dedicado (ej. `evalutia-sync`)** | No en el `.env` del proyecto — es una credencial de la máquina, no del repo; separarla evita mezclarla con los secretos que ya viven en `.env` (DB, JWT, certs mTLS). Cualquier comando la usa con `--profile evalutia-sync`. |
| **La cuenta de AWS la administra otra persona, pero el usuario tiene acceso a ella (falta el código MFA)** | No hace falta un pedido externo formal (como con Martín/IT) — el usuario puede crear el bucket S3 y el usuario IAM él mismo en la consola, una vez que consiga el código MFA de quien lo tiene. No se sabía si ya existe un bucket reusable — se asume que hay que crear uno nuevo dedicado. |

> **Nota:** el rol de la VM (EC2) para poder subir a ese mismo bucket también hay que confirmarlo/configurarlo — si la instancia ya tiene un IAM role adjunto, alcanza con agregarle permiso al bucket nuevo; si no, hay que decidir entre adjuntarle un role o usar una access key también ahí. Queda como paso siguiente, no resuelto en esta sesión.

**Hallazgo durante la implementación:** ya existía `scripts/sync_local_from_prod.sh` de una sesión anterior (2026-06-17), con un diseño **distinto** al decidido hoy — asumía conexión directa desde el PC al MySQL de producción (`PROD_MYSQL_HOST`/etc.), whitelisteando la IP del usuario en el security group. Se comparó con el diseño de hoy (S3) y se decidió mantener S3 — más seguro (nunca expone el puerto de MySQL a internet, ni siquiera acotado a una IP, que además es dinámica). El script viejo se sobrescribió con el nuevo diseño.

**Implementado (2026-07-13), pendiente de probarse — bloqueado en acceso a AWS:**
- `scripts/prod_dump_to_s3.sh` (nuevo, corre en la VM): `mysqldump` de 11 tablas (`articulos`, `grupos`, `ventas_historicas`, `ventas_mensuales`, `stock_diario`, `stock_resumen_365`, `articulos_elegibilidad_econometrico`, `predicciones`, `jobs_historial`, `planilla_ventas_calculada`, `planilla_sugerencias` — sin `usuarios` ni tablas `*_stage`), comprime y sube a `s3://BUCKET/latest.sql.gz`.
- `scripts/sync_local_from_prod.sh` (reescrito, corre en local): baja el dump de S3, trunca las mismas 11 tablas localmente y restaura. Sintaxis verificada (`bash -n`), no probado end-to-end todavía (falta el bucket + credenciales).
- Política IAM (para el usuario `evalutia-sync`, acotada a un bucket): `s3:ListBucket` sobre el bucket + `s3:GetObject`/`PutObject`/`DeleteObject` sobre su contenido. El mismo usuario/credencial se pensaba reusar en la VM (evita crear un segundo usuario para un bucket de un solo propósito).

**Bloqueado:** el socio de Nico administra la cuenta de AWS y todavía no le pasó el acceso (MFA) — no se pudo crear el bucket/usuario IAM ni probar el flujo completo. Se sigue usando el relevo por la VM (Session Manager) para todo lo que necesite producción mientras tanto, sin que esto bloquee el resto del backlog.

---

### Backend: soportar cantidad negativa sin corromper agregados — Issue #82 (sesión 2026-07-13)

| Decisión | Definición |
|----------|-----------|
| **Hallazgo antes de grillar: `StockResumen365.Ventas365` ya es `long`** | No tiene el problema de tipos que suponía la auditoría original — el riesgo real está concentrado en `VentaHistorica.Cantidad` (`uint`), `VentaAgregada.TotalCantidad` (`uint`) y los campos `ulong` de `VentaSkuResumen`. |
| **Filtros `v.Cantidad > 0` en `VentasService.cs` se eliminan** | `TopSkusByVentas` y `GetSkuResumen` (al menos 6 lugares) filtraban filas antes de sumar — inofensivo cuando `Cantidad` era siempre ≥0, pero post-`#80` esto excluiría las devoluciones de la suma, mostrando bruto en vez de neto real. Se saca el filtro, se suman todas las filas (positivas y negativas) — es exactamente lo que pidió el cliente en `#61`/`#79`. |
| **`GetAbcClassification` (`ResultadosService.cs`): rediseño del algoritmo de Pareto** | Hoy `granTotal` incluye todos los totales (incluso negativos), lo que puede hacer que el acumulado supere el 100% antes de terminar de recorrer la lista, rompiendo la clasificación A/B/C de todos los SKUs subsiguientes. Se recalcula `granTotal` solo con la suma de SKUs de `Total > 0` (el "pastel" real de ventas positivas); los SKUs con `Total <= 0` se clasifican automáticamente como "C" (reusa la categoría existente, no inventa una nueva) sin participar del acumulado — siguen apareciendo en la lista por transparencia, solo no afectan el corte 80/95% de los demás. |
| **Migración de tipos** | `VentaHistorica.Cantidad`: `uint`→`int` (fila individual). `VentaAgregada.TotalCantidad`: `uint`→`long` (suma agregada). `VentaSkuResumen` (`MinimoVentasTrimestral`, `MaximoVentasTrimestral`, `VentasUltimoTrimestre`, `VentasUltimoAnioCalendario`): `ulong`→`long`. Todos los casts `(uint)`/`(ulong)` en `VentaRepository.cs`/`VentasService.cs` pasan a `(long)`, **sin** los `Math.Max(0, ...)` que hoy clampean negativos a 0 antes de mostrar (eso es justo lo que hay que sacar). |
| **Verificación: cero regresión + caso sintético negativo** | Contra la DB local (ya tiene el esquema signed de `#80`): (1) los datos actuales (solo positivos) deben dar exactamente el mismo resultado que antes, (2) un SKU sintético con neto negativo real (mismo patrón usado para probar `#80`) confirma que `GetAbcClassification` no rompe el acumulado y que los totales reflejan el neto, no el bruto. |

**Hallazgos adicionales durante la implementación (revisión final antes de codear):**
- `VentaAgregadaOutDto` (`VentasDtos.cs`) tenía su propio `uint TotalCantidad` separado del modelo interno — sin corregirlo, el código no compilaba tras cambiar `VentaAgregada.TotalCantidad` a `long`.
- `VentasMensuales.VentasCantidad` (`ulong`) también mapea a `ventas_mensuales.ventas_cantidad`, migrada por `#80`. Evaluación inicial ("código muerto") fue **incorrecta** — `VentasMensualesController.Get()` sí consulta `_db.VentasMensuales` directo (bypasea el repositorio) y expone el valor en `GET /api/ventasmensuales`, un endpoint real. Corregido `VentasMensualesOutDto`, `IVentasMensualesRepository`/`VentasMensualesRepository.Upsert`, `IStockService`/`StockService.UpsertVentasMensualesCalculated` (todos ulong→long).
- Confirmado que `StockDiario.Cantidad`/`StockDiarioRepository` (`uint`, stock físico) y `UsuarioService.Id` (`ulong`, PK de usuario) son conceptos no relacionados — no se tocan.

**Implementado y verificado (2026-07-14):**

| Paso | Resultado |
|------|-----------|
| `dotnet build` | 0 errores (warnings preexistentes no relacionados) |
| Rebuild + recreate `webapi` local | Confirmado (`CREATED` reciente) |
| Cero regresión | `GET /api/resultados/charts/abc` antes/después/tras limpieza: `21A/27B/55C/103 items` idéntico en los 3 momentos |
| Caso sintético (SKU `TEST-NEG-82`, ventas `+50`/`-80`, neto `-30`) | `ventasTotal: -30` y `ventasUltimoAnioCalendario: -30` (neto real, sin clamp ni wraparound); clasificado `"C"`; `porcentajeAcumulado` nunca supera 100% en toda la lista; ranking correcto (último lugar, 104/104). Datos de prueba borrados después. |
| Commit y push | `2eef51f..HEAD` — `docker-compose.yml` (no relacionado) y los 2 scripts de `#38` (sin probar, bloqueados por acceso a AWS) quedan fuera. |
| **Deploy a producción** | Pendiente — bloqueado por falta de acceso a la VM (socio administra la cuenta de AWS, sin MFA todavía). A diferencia de `#51`/`#71`/`#80`, `#82` no tiene acoplamiento con el corte mTLS (`webapi` es un servicio distinto de `etl`) — se puede desplegar independientemente en cuanto haya acceso a la VM. |

---

### ML: corregir descarte de negativos en Prophet + heurísticas de historia — Issue #81 (sesión 2026-07-14)

| Decisión | Definición |
|----------|-----------|
| **Sacar el filtro `df_prop['y'] >= 0]` en `fit_prophet_insample`** | No es solo un fix de sesgo de entrenamiento — es un **crash latente**: `ml/models.py:464` construye `holdout = pd.Series(insample['yhat'].values, index=tr.index)` usando el índice completo (`tr.index`) pero valores de predecir sobre `df_prop` (filtrado, potencialmente más corto). Con negativos reales (post-`#80`), esas longitudes no coinciden y `pd.Series` tira `ValueError`. Sacar el filtro basta — sin él, `df_prop` y `tr` siempre tienen la misma longitud, no hace falta un chequeo de longitud aparte (sería validar contra un estado que ya no puede ocurrir). |
| **Confirmado: `_sanitize_forecast`/`np.maximum(y_fc, 0.0)` solo tocan el forecast futuro** | Verificado en código — `_sanitize_forecast` (definida y usada una sola vez en `predict.py:120,388`) se aplica solo a `r.forecast`, nunca a `tr`/`train`. No hace falta cambiar nada ahí. |
| **Asimetría entre las dos heurísticas de corte de historia** | **"Primera venta efectiva"** (`ensure_monthly_series:106`, `ioworker/data.py`, `cantidad > 0`): se documenta como **correcta tal cual**, no se cambia — una devolución sin venta previa es un dato raro (probablemente un ajuste de stock inicial mal cargado), no debería contar como "acá empezó a venderse esto" (mismo criterio ya aplicado en `#82` para `VentasService.cs:150`). Confirmado el mismo patrón triplicado sin cambios necesarios: `predict.py:106`, `ioworker/data.py:63` (loader CSV) y `:131` (loader MySQL). **"Última venta"** (`predict.py:291,313`, `last_sale = train_full[train_full > 0].last_valid_index()`): **sí se corrige** — si el período más reciente es neto negativo, esta heurística saltaba hacia atrás al último período positivo, corriendo mal la ventana de pronóstico (re-prediciendo un período que ya tiene dato real, o desplazando el horizonte sin que nadie lo pida). Pasa a usar el último período con cualquier dato, sin filtrar por signo. |

**Implementado y verificado (2026-07-14):**

| Paso | Resultado |
|------|-----------|
| Sintaxis (`py_compile`) | OK en `ml/models.py` y `predict.py` |
| Rebuild + recreate `python-worker` local | Confirmado (`CREATED` reciente) |
| Prophet entrena con negativo real (llamada directa a `fit_prophet_insample`, serie sintética de 10 trimestres con uno de neto -20) | `RESULTADO OK`, sin `ValueError`; `holdout_pred` en el trimestre negativo da `-16.6` (aprendió el dato real, no lo ignoró); forecast futuro sigue clampeado a valores positivos (`[12.57, 1.82]`) — confirma que el clamp sigue aplicando solo al output, no al entrenamiento. |
| "Última venta" — comparación directa viejo vs. nuevo con serie sintética (último trimestre neto -15) | Viejo: saltaba a `2025-01` (último positivo). Nuevo: usa `2025-04` (el período real, sin importar signo) — confirma que el fix evita re-predecir un período que ya tiene dato real. |
| Commit y push | `docker-compose.yml` (no relacionado) y los 2 scripts de `#38` (sin probar, bloqueados por acceso a AWS) quedan fuera. |
| **Deploy a producción** | Pendiente — bloqueado por falta de acceso a la VM (`#38`). `python-worker` no tiene acoplamiento con el corte mTLS (`etl` es un servicio distinto) — se puede desplegar independientemente en cuanto haya acceso. |

---

### Frontend: revisión UX de valores negativos — Issue #83 (sesión 2026-07-14), cerrado sin código

Revisados los 4 archivos identificados: `TablaVentas.tsx`, `PlanillaTable.tsx`, `AbcChart.tsx`, `VentasTrendChart.tsx`.

| Decisión | Definición |
|----------|-----------|
| **Sin riesgo de crash en ningún lugar** | TypeScript usa `number` en todos los tipos de venta; `.toLocaleString()` (usado en `PlanillaTable.tsx` y `AbcChart.tsx`) maneja negativos sin problema, con signo y separadores de miles. |
| **`PlanillaTable.tsx`: coloreado ya es independiente del signo** | `estadoMesBg` colorea celdas según `estado_mes`/`frecuencia_nivel` (clasificación de negocio calculada en el ETL), no según el signo crudo de `ventasCantidad` — no hay conflicto que resolver. |
| **`AbcChart.tsx`: el donut usa conteo de SKUs, no totales** | El donut/leyenda principal grafica `cantidadA/B/C` (conteos, siempre positivos) — un SKU de total negativo no lo afecta visualmente. Solo aparece el valor crudo en la tabla expandible de detalle, ya formateado correctamente. |
| **`VentasTrendChart.tsx`: `beginAtZero: true` no recorta negativos** | Chart.js extiende el rango del eje hacia abajo si hay datos negativos reales — no hay pérdida visual de datos. |
| **Cierre sin cambios de código** | Un signo negativo es una convención universalmente entendida — agregar color/ícono especial sería decoración sin necesidad real. Coincide con el propio issue ("con o sin cambio visual") y con el patrón ya usado en la sesión (no agregar tratamiento más allá de lo que hace falta). |

**Revisión ampliada (antes de cerrar, "revisa todo" final):** se encontraron 9 archivos más no cubiertos por el grill original (`TablaVentasAgregadas.tsx`, `TopSkusVentasTable.tsx`, `DatosExtra.tsx`, `ProjectedSalesChart.tsx`, `VentasMensualesPage.tsx`, `exportPlanilla.ts`, y los tipos asociados). Todos confirmados seguros:
- `formatNumber`/`formatPronostico` (`format.ts`) y `fmtPct` (`DatosExtra.tsx`): verificado que `Math.abs()` solo decide el formato (con/sin comas), nunca se aplica al valor mostrado — un negativo se muestra con su signo real, sin "robo de signo".
- `ProjectedSalesChart.tsx` ya tiene un checkbox existente (`startFromZero`) que le da al usuario control sobre si el eje Y arranca en cero o se autoescala — sin pérdida de datos negativos en ningún caso.
- El resto (`TablaVentasAgregadas.tsx`, `TopSkusVentasTable.tsx`, `VentasMensualesPage.tsx`, `exportPlanilla.ts`) renderiza el valor crudo sin ningún tratamiento que pueda perder el signo.

---

### Migración SQL: columnas de frecuencia de venta por tickets — Issue #62 (sesión 2026-07-14)

| Decisión | Definición |
|----------|-----------|
| **Hallazgo: ya existe un sistema de "frecuencia" distinto (`#27`)** | `frecuencia_nivel` (alta/media/baja) + `rotacion_ajustada` (`08-planilla-frecuencia-quiebre.sql`) clasifican el SKU a nivel **anual** (meses con ventas en los 12 meses) para elegir la fórmula de rotación en meses de quiebre. El nuevo sistema (`#61-67`) clasifica **cada mes individual** por cantidad de tickets (días con venta ese mes) para elegir el blending Histórico/Promedio/Real — concepto distinto, ya decidido que coexisten (confirmado en el propio `#65`: "no reemplaza el significado del color de quiebre ya validado — ambas señales conviven"). |
| **Nombres sin colisión** | `tickets_mes`, `valor_historico`, `valor_ajustado`, `criterio_frecuencia` — deliberadamente distintos de `frecuencia_nivel`/`rotacion_ajustada` para que nadie confunda los dos sistemas al leer el código o una query suelta dentro de un año. |
| **Esquema exacto** | `tickets_mes TINYINT UNSIGNED NOT NULL DEFAULT 0` (siempre calculable, 0-31 días, nunca falta). `valor_historico`/`valor_ajustado DECIMAL(10,2) NULL`, `criterio_frecuencia ENUM('historico','promedio','real_extrapolado') NULL` — nulos permitidos para un SKU sin ningún mes previo de historia (0 meses disponibles, promedio indefinido). Agregadas después de `rotacion_ajustada`, mismo patrón `ALTER TABLE` de `#27`. |
| **Fuera de alcance de `#62`** | El modelo C# (`PlanillaVentasCalculada.cs`) no se toca en esta migración — es puro schema, el consumo backend/frontend llega con `#63`/`#65`/`#66` cuando la lógica de cálculo exista. |
| **Migración idempotente con patrón defensivo** | `ALTER TABLE ADD COLUMN` no es idempotente (falla si la columna ya existe) — se guarda con chequeo previo vía `information_schema`, mismo patrón de `04-etl-staging.sql`, dado el incidente real de comando repetido que ya tuvimos en las migraciones de `#71`/`#80` esta misma sesión. Archivo: `infra/sql/15-planilla-frecuencia-tickets.sql`. |

**Implementado y verificado en DB local (2026-07-14):**

| Paso | Resultado |
|------|-----------|
| Migración aplicada 2 veces seguidas | Segunda corrida silenciosa, sin error — idempotente confirmado |
| Esquema resultante | Las 4 columnas nuevas quedan justo después de `rotacion_ajustada`, tipos y nulabilidad exactos como se diseñó |

---

### Fórmula de blending — Issue #63 (sesión 2026-07-14)

**Mail original de Rodrigo recuperado** (no estaba preservado en `CONTEXTO.md`, solo referenciado — el usuario lo pegó completo en esta sesión):

> SI hubo stock todo el mes: Tickets ≤2 → Histórico · Tickets 3-4 → (Histórico + VentaRealMes)/2 · Tickets ≥5 → VentaRealMes
> SI hubo quiebre: Tickets ≤2 → Histórico · Tickets 3-4 → (Histórico + Extrapolación)/2 · Tickets ≥5 → Extrapolación

4 ejemplos numéricos: Caso 1 (1 ticket, sin quiebre) → Histórico. Caso 2 (2 tickets, sin quiebre) → Histórico ("ídem anterior", confirma que el corte `≤2` es inclusivo). Caso 3 (3 tickets, sin quiebre, VentaRealMes=30) → (Histórico + 30)/2. Caso 4 (3 tickets, con quiebre, Histórico=50, Extrapolación=(30/12)×30.5=76.25) → (50+76.25)/2 = **63.125**.

| Decisión | Definición |
|----------|-----------|
| **`sin_stock` entra a la rama "quiebre"** | El mail solo distingue dos estados ("stock todo el mes" vs. "quiebre"), no los 3 valores de `estado_mes`. `sin_stock` (0 días con stock) es un caso extremo de quiebre, no un tercer estado en la lógica del cliente — pero `Extrapolación = (VentaRealMes/días_con_stock)×días_naturales_mes` es indefinida con `días_con_stock=0` (división por cero). Cuando `Extrapolación` no se puede calcular, el criterio cae a `historico` como fallback, sin importar la cantidad de tickets — mismo patrón defensivo que ya usa `rotacion_diaria_real` (`None` cuando `ds==0`). |
| **`días_naturales_mes` real, no `30.5` fijo — el ejemplo del mail no se reproduce bit a bit** | El mail usa `30.5` en el Caso 4 (da `63.125`), pero junio 2026 tiene 30 días naturales exactos (con `30` da `62.5`). El propio `#63` (escrito en sesión anterior tras leer este mail) ya describe la fórmula como "× días naturales del mes", no un promedio fijo — el `30.5` del mail es casi seguro un redondeo casual al armar el ejemplo a mano, no una especificación deliberada. Se usa el valor exacto ya calculado por `dias_naturales_mes()` en el código. Diferencia mínima (~1%), se documenta en `#64` como discrepancia menor conocida — no amerita repreguntarle a Rodrigo. |
| **"Histórico" usa `fec_alta` para distinguir "no existía" de "existía sin vender"** | Promedio de los últimos 12 meses cerrados (o los disponibles si el SKU es más nuevo). Un mes sin fila en `ventas_historicas` puede ser "el SKU no existía todavía" (no cuenta, ni como disponible ni como cero) o "existía pero no vendió nada" (cuenta como `0`, baja el promedio). `articulos.fec_alta` es la señal para distinguir ambos casos — sin esto, un SKU con ventas intermitentes reales tendría su Histórico inflado artificialmente al excluir los meses de venta cero. |
| **SKU sin ningún mes disponible (recién agregado): usar el componente disponible sin promediar, no `NULL`** | No todas las fórmulas necesitan Histórico por igual: `≤2 tickets` depende 100% de él, `3-4` promedia con él, `≥5` no lo usa en absoluto (solo VentaRealMes/Extrapolación). Cuando falta Histórico y la fórmula lo necesita, se usa directamente el otro componente disponible sin promediar, en vez de dejar `valor_ajustado`/`criterio_frecuencia` en `NULL` — un SKU nuevo sigue necesitando un valor utilizable en la planilla. |

> **Nota:** `Extrapolación` es matemáticamente igual a `rotacion_diaria_real × dias_naturales_mes` (ambos ya se calculan hoy en `calcular_filas()`) — no es un concepto nuevo desde cero, solo una combinación de dos valores ya existentes en el código.

**Corrección encontrada durante la implementación:** las funciones nuevas se habían escrito como funciones anidadas dentro de `calcular_filas()` (mismo patrón que `clasificar_frecuencia`/`rotacion_ajustada`, que tampoco son testeables) — pero el criterio de aceptación de `#63` pide explícitamente tests unitarios del blending, y una función anidada no se puede importar aislada. Se movieron `meses_disponibles_historico`, `calcular_historico` y `valor_ajustado_y_criterio` a nivel de módulo. También se eliminó `clasificar_tickets` (quedó sin uso — la función de blending ya aplica los umbrales directamente, y el esquema de `#62` no tiene columna para ese nivel por separado).

**Implementado y verificado (2026-07-14):**

| Paso | Resultado |
|------|-----------|
| Sintaxis (`py_compile`) | OK |
| Tests existentes (regresión) | 14/14 sin cambios |
| Tests nuevos (`test_run_calc_planilla.py`) | 15 nuevos: los 4 casos exactos del mail (Caso 4 con `62.5`, no el `63.125` literal — ver decisión de días naturales arriba), boundaries (4 tickets, 5 tickets con/sin quiebre), y los 3 fallbacks (sin_stock sin historico, SKU nuevo con tickets bajo/medio). Total 29/29. |
| Corrida real contra DB local (grupo 201, 104 SKUs) | Sin errores, 824 filas. Distribución real: `sin_stock` → 80/80 filas usan `historico` (confirma el fallback funciona sin excepciones); `normal`/`quiebre_parcial` → todas usan `real_extrapolado` porque este dataset local vende casi todos los días (tickets_mes solo toma valores 25/30/31, nunca cae en el rango 3-4) — el caso "promedio" no aparece en la muestra real, pero está cubierto por tests aislados (Caso 3, Caso 4, boundary de 4 tickets). |
| Verificación manual de `valor_historico` contra datos reales | SKU `C00184`: `SUM(cantidad)` en los 12 meses cerrados = 354, `354/12 = 29.5` — coincide exacto con el valor persistido, confirma que los meses sin venta (4 de los 12) se cuentan correctamente como `0`, no se excluyen del promedio. |

---

### Indicador de color para frecuencia de venta — Issue #65 (sesión 2026-07-14)

| Decisión | Definición |
|----------|-----------|
| **Hallazgo: falta wiring de backend, no estaba en el alcance de ningún issue** | `criterio_frecuencia` no existe en ningún punto de la cadena backend (`PlanillaVentasCalculada.cs`, `PlanillaRepository.cs`, `PlanillaDtos.cs`) — solo `frecuencia_nivel` (sistema viejo de quiebre) está conectado. Se amplía `#65` para incluir este wiring (mecánico, repite el mismo patrón ya usado para `FrecuenciaNivel` en los 3 archivos) en vez de abrir un issue nuevo aparte — es un prerrequisito que bloquea `#65` por completo, no una funcionalidad independiente. |
| **Mecanismo visual: borde, no fondo** | `estadoMesBg` ya pinta el **fondo** de la celda para quiebre (amarillo/naranja/rojo/gris) — el propio mail de Rodrigo pidió evitar acumular colores ("ver cómo resolver esto, para que no sean muchos colores, o buscar otra forma"). Se usa `border-left` de color para `criterio_frecuencia`, dejando `backgroundColor` intacto — dos señales en la misma celda sin competir. |
| **Paleta fría, deliberadamente distinta de la de quiebre** | `historico` = azul, `promedio` = violeta, `real_extrapolado` = verde azulado (teal) — alejada del amarillo/naranja/rojo de quiebre para que ambas señales se distingan a simple vista. |
| **Solo en el bloque "Vta.", no en "Rot."** | La tabla tiene 2 bloques de columnas por mes. Duplicar el borde en "Rot." sería la misma señal dos veces por fila sin información nueva — alcanza con que aparezca una vez. |
| **Explicación vía el `title` (tooltip) ya existente, sin leyenda nueva** | La celda "Vta." ya tiene un `title` nativo (`"Vta.{mes} · {cantidad} uds."`) — se le agrega `· Criterio: {nombre}` al final, reusando el mecanismo ya descubierto por el usuario (pasa el mouse por la celda), en vez de sumar un elemento visual fijo más a una tabla que ya tiene leyenda + scroll horizontal. |

> **Nota de implementación:** el enum `criterio_frecuencia` solo tiene 3 valores (`historico`/`promedio`/`real_extrapolado` — ver `#62`/`#63`), pero el mail distingue 4 conceptos (Histórico, VentaRealMes, Extrapolación, y el promedio de cualquiera de los dos con Histórico). El frontend puede reconstruir la etiqueta más precisa para `real_extrapolado` usando `estadoMes` (ya disponible en el mismo `PlanillaMesDto`): `estadoMes === 'normal'` → "Venta real", cualquier otro valor → "Extrapolado". No hace falta un cuarto valor de enum en la DB para esto.

**Wiring de backend (revisión final antes de codear, más largo de lo estimado):** la cadena real son 6 archivos, no 3 — hay una capa intermedia (`IPlanillaService.cs`/`PlanillaService.cs`) que no se había mirado en detalle: `PlanillaVentasCalculada.cs` (modelo EF) → `EvalutiaDbContext.cs` (mapeo Fluent API) → `PlanillaRepository.cs` (proyección LINQ + reconstrucción, 2 lugares) → `IPlanillaService.cs` (`PlanillaMesDto`) → `PlanillaService.cs` (construcción del DTO) → `PlanillaDtos.cs` (`PlanillaMesOutDto`, respuesta final). Mismo patrón mecánico en los 6, repitiendo exactamente cómo ya fluye `FrecuenciaNivel`.

**Implementado y verificado (2026-07-14):**

| Paso | Resultado |
|------|-----------|
| Backend (`dotnet build`) | 0 errores |
| Frontend (`tsc --noEmit`) | 0 errores |
| Verificación visual con Playwright (script propio, mismo patrón que `playwright-verify/verify-issue32.js` ya usado en este proyecto) | Login real contra `/api/auth/login`, navegación a `/planilla`, inspección de estilos computados. |
| Rebuild necesario detectado a tiempo | El contenedor local `webapi` seguía sirviendo el código viejo — `dotnet build` local no alcanza, hace falta `docker compose build webapi && up -d --force-recreate webapi` para que el contenedor real lo sirva. |
| Borde solo en bloque "Vta." | 400/800 celdas con borde (exactamente la mitad del total, confirma que "Rot." no lo tiene). |
| Color y tooltip correctos | Muestra real: `rgba(20,184,166,0.55)` (teal) + `"Criterio: Venta real"` para una fila `normal`. |
| Convivencia con fondo de quiebre, sin conflicto | Celda real con ambas señales activas: `backgroundColor: rgba(234,88,12,0.18)` (quiebre media freq) + `borderLeftColor: rgba(20,184,166,0.55)` (teal) simultáneos, tooltip `"Criterio: Extrapolado"` (reconstruido bien porque esa fila es `quiebre_parcial`, no `normal`). Confirma que las dos señales no se pisan — son propiedades CSS distintas. |

---

### Export: columnas de frecuencia de venta — Issue #66 (sesión 2026-07-14)

| Decisión | Definición |
|----------|-----------|
| **"VentaReal/Extrapolación" se reconstruye en el frontend, sin nueva columna en la DB** | No está persistido por separado en `#62` (solo `valor_ajustado`, el resultado final del blending, y `criterio_frecuencia`, qué fórmula se usó). Se reconstruye con datos ya expuestos: `ventasCantidad` cuando `estadoMes === 'normal'`, o `rotacionDiariaReal × diasNaturalesMes` cuando hay quiebre — misma fórmula exacta que ya implementa `run_calc_planilla.py` en Python (`Extrapolación`). |
| **5 bloques nuevos de 13 columnas cada uno, mismo patrón que Vta./Rot.** | La hoja pasa de ~30 a ~91 columnas, pero es exportable, no una tabla en pantalla con restricción de scroll horizontal — el mail pidió explícitamente granularidad **por mes**, no un texto combinado que el cliente tendría que parsear a mano. Columnas: tickets del mes, Histórico, VentaReal/Extrapolación, criterio aplicado, valor final (`valor_ajustado`). |
| **Etiqueta legible del criterio, no el string crudo del enum** | Reusa la misma reconstrucción de `#65` ("Venta real"/"Extrapolado"/"Histórico"/"Promedio" según `estadoMes`) en vez de exportar `real_extrapolado` tal cual — el Excel lo lee el cliente directo, no un programador. Función chica (~4 líneas), se duplica en `exportPlanilla.ts` en vez de crear una dependencia cruzada entre el archivo de utilidades de export y el componente de UI (`PlanillaTable.tsx`). |

---

### Deploy a producción — resize VM + tuning MySQL + backlog acumulado (Issue #60, sesión 2026-07-14)

| Decisión | Definición |
|----------|-----------|
| **Diagnóstico confirmó #60 sin cambios** | RAM 1.9GiB (t3.small), `innodb_buffer_pool_size=128MB`, `tmp_table_size`/`max_heap_table_size=16MB` — idéntico a lo documentado semanas atrás. `stock_diario` con 25.3M filas (1.83GB datos + 4.62GB índices). |
| **Resize t3.small → t3.medium (4GiB RAM)** | Hecho por el usuario desde la consola de AWS (stop → change instance type → start). Buffer pool subido a 2GB, tmp/heap table size a 256MB vía `command:` de MySQL en `docker-compose.yml`. |
| **El `git pull` en la VM trajo mucho más que el tuning** | La VM estaba parada en el commit de #71 (previo a #80/#81/#82/#62/#63/#65/#66) — un solo `git pull` post-resize aplicó todo ese backlog de una vez. Se aplicaron a mano las migraciones `14-ventas-cantidad-signed.sql` y `15-planilla-frecuencia-tickets.sql` (no corren solas — `docker-entrypoint-initdb.d` solo se ejecuta en la creación inicial del volumen, no en un volumen ya existente), con backup previo (`mysqldump --no-tablespaces` de las 5 tablas afectadas, 372MB) y verificación de tipos de columna post-migración. Rebuild + recreate de `webapi`, `etl`, `python-worker`, `webapp` para tomar el código nuevo (todos usan `COPY . /app`, sin bind mount). |
| **Resultado medido sobre `/api/resultados/charts/abc`** (el síntoma original de #59/#60) | Antes: timeout >120s. Después del resize+tuning: 30.0s en frío (cache recién arrancada) → **10.8-11.6s en caliente**, consistente en 2 corridas. Mejora real de ~10x. |
| **Ajuste adicional: `Default Command Timeout=90` en el connection string** | La corrida en frío (30.024s) rozaba el default de MySqlConnector (30s) — un 500 real por `Command Timeout expired` durante la verificación, no un bug de código. Subir el timeout a 90s da margen para el caso de cache fría (justo después de cualquier restart) sin depender de que el cache ya esté tibia. |
| **Login vía `curl` directo a `localhost:8080` falla con 307** | `UseHttpsRedirection()` solo se salta en `Development` (`Program.cs:191-193`) — en producción hay que pegarle a través de Caddy con `--resolve dominio:443:127.0.0.1` para simular el tráfico real sin depender de DNS/hairpin NAT. |

> **Nota:** con este deploy, el código de #71/#80/#81/#82/#62/#63/#65/#66 pasa de "commiteado" a **realmente corriendo en producción** por primera vez — pendiente decidir si esto cierra también #79 (épica que se dejó abierta a propósito hasta confirmar el deploy).

### Activación prematura de mTLS por el rebuild de `etl` — hallazgo y fix (#51, sesión 2026-07-14)

| Decisión | Definición |
|----------|-----------|
| **El rebuild de `etl` del deploy de arriba activó `https` sin querer** | `#51` (`7af0867`) ya tenía `WS_URL` hardcodeado a `https://200.125.29.194:81` en `run_ofelia.sh` desde antes de esta sesión, pero el contenedor `etl` en producción no se había reconstruido desde antes de ese commit — el `docker compose build etl` + `up -d --force-recreate etl` de hoy (para desplegar #71/#80) fue el primer rebuild que incluyó el código de #51, activando el switch a `https` 4 días antes del corte coordinado con Martín (viernes 18/07). Confirma el riesgo de acoplamiento ya documentado: recrear `etl` por cualquier motivo activa todo lo que esté mergeado a `Develop`, no solo el issue puntual que motivó el rebuild. |
| **Impacto real si no se corregía** | El servidor del cliente todavía no acepta TLS en el puerto 81 (confirmado semanas atrás: `https` da "wrong version number", solo `http` responde `200 OK`) — el cron de las 3 AM iba a fallar **las 3 noches hasta el viernes**, no solo una. El job es atómico (sin corrupción, `jobs_historial` en `fallido`) y recuperable con `FORCE_START`/`FORCE_END`, pero son 3 recuperaciones manuales evitables. |
| **Fix: revert temporal a `http://`** | Commit `037c03a`, un cambio de una línea. Se vuelve a `https://` recién en el paso 3 del plan ya coordinado con Martín (después de validar los 3 pasos el viernes 9-12hs) — no antes. Verificado dentro del contenedor real (`docker compose exec etl grep WS_URL ...`), no solo en el commit. |
| **Horario exacto confirmado por Martín** | Viernes 18/07, **10:00** en punto (dentro de la ventana 9-12hs ya acordada), estimando 15-20 min de duración. Deja WhatsApp para coordinar en vivo ese día: **+598 94 961 242** (además del correo). |

---

### `infra/sql/16-catalogo-modelos.sql` — Issue #84 (sesión 2026-07-15)

| Decisión | Definición |
|----------|-----------|
| **Se agrega `rmse_test`, ausente en el alcance original del issue** | #89 (última de la cadena, la que aplica el criterio en `predict.py`) dice textualmente que el criterio de selección pasa a ser "r2_test/rmse_test real" — sin esta columna, #89 no tendría de dónde leerlo. `r2_test` y `rmse_test` miden cosas distintas (varianza explicada relativa vs. error absoluto en unidades de venta), se necesitan los dos. |
| **Índice compuesto `(sku, modelo, fecha_estimacion)`, sin `UNIQUE`** | Cubre tanto el historial ordenado de un SKU+modelo (para el análisis de #87) como la fila más reciente por `(sku, modelo)` (para la selección de #89, vía `MAX(fecha_estimacion)` agrupado). Sin `UNIQUE` porque el issue es explícito: no es upsert, puede haber más de una fila por `(sku, modelo, fecha_estimacion)` si el job corre dos veces el mismo día. |
| **Se agrega `version_modelo VARCHAR`, mismo concepto que ya usa `predicciones`** | `predicciones` ya distingue corridas de código distinto vía `version_modelo` en su índice único `(sku, modelo, version_modelo, fecha_predicha)` (ver `db.py`). `catalogo_modelos` acumula historia mientras `eval_walkforward.py` (que #86 extiende) sigue evolucionando — sin esta columna, no hay forma de filtrar "solo corridas post-cambio de lógica" al analizar en #87 sin inspeccionar el JSON de `hiperparametros`/`features` fila por fila. |

**Revisado por `/code-review` (mismo día) — 5 hallazgos, los 5 aplicados:**

| Decisión | Definición |
|----------|-----------|
| **FK cambiado de `ON DELETE CASCADE` a `ON DELETE RESTRICT`** | La recomendación original del grilling copiaba el patrón de `articulos_elegibilidad_econometrico` (upsert de estado actual, barato de perder) sin notar que `catalogo_modelos` es historial acumulativo — perder en cascada el historial completo de un SKU es justo lo que la tabla existe para evitar. `RESTRICT` tiene costo cero si `articulos` nunca borra de verdad (la premisa original se mantiene), pero protege si alguna vez se viola. Verificado: `DELETE FROM articulos` con fila referenciada queda rechazado, no cascadea. |
| **`fecha_estimacion` cambia de `DATETIME` a `TIMESTAMP(6)`** | Con precisión de segundo, dos corridas del mismo `(sku, modelo)` en el mismo segundo (retry rápido, loop de `predict.py`) quedaban indistinguibles — justo lo que la columna dice existir para evitar. Mismo patrón que `evaluado_en`/`ts_carga` en el resto del repo. `DEFAULT CURRENT_TIMESTAMP(6)` agregado para no depender de que el código futuro (#86) la setee a mano. |
| **`n_arboles`/`profundidad_max` pasan a columnas `GENERATED ALWAYS AS ... STORED`** | Como columnas propias duplicaban `hiperparametros` JSON sin ninguna garantía de consistencia (dos fuentes de verdad, nada detecta si se desincronizan). Derivarlas del JSON (`$.n_estimators`, `$.max_depth`) deja una sola fuente de verdad, mantiene las columnas tipadas/consultables que pedía el issue original, y de paso quedan `NULL` para PROPHET automáticamente (su JSON no tiene esas claves) — verificado con INSERT real de XGB y PROPHET. |
| **`CHECK chk_catalogo_fechas_obs (fecha_primera_obs <= fecha_ultima_obs)`** | El resto del repo ya tiene la convención de `CHECK` para invariantes de dominio (`chk_pred_cantidad`, `chk_stockresumen_dias`) — esta tabla no tenía ninguna para una invariante obvia. Verificado: INSERT con fechas invertidas rechazado. |
| **`CHECK chk_catalogo_n_obs (n_obs_train + n_obs_test <= n_obs_total)`** | Mismo motivo — `stock_resumen_365` ya tiene el precedente casi exacto (`dias_con_stock + dias_sin_stock = total_dias`). Verificado: INSERT con conteos inconsistentes rechazado. |

> **Nota:** sin política de retención por ahora (ya decidido en el issue original) — se revisa una vez que #87 dé una idea real de volumen.

---

### `docs/catalogo-modelos-diccionario.md` — Issue #85 (sesión 2026-07-15)

| Decisión | Definición |
|----------|-----------|
| **"Creá un agente" → correr `/implement` sobre el issue, no un subagente suelto ni un cron** | El issue ya estaba `ready-for-agent`, acotado y sin dependencias — es el caso exacto que este repo definió para `/implement`. Un subagente aislado se saltea el checklist de verificación y el registro de decisiones que `/implement` trae de fábrica; un agente programado (`/schedule`) es sobre-ingeniería para un documento de una sola vez. |
| **Archivo separado `docs/catalogo-modelos-diccionario.md`, no sección nueva en `CONTEXTO.md`** | El issue dejaba la ubicación abierta. Se prefiere archivo satélite (mismo patrón que `docs/agents/issue-tracker.md`, `triage-labels.md`, `domain.md`) porque `CONTEXTO.md` ya pesa 273.8KB y sigue creciendo — agregar más contenido inline lo hace más caro de cargar en cada sesión. El criterio de aceptación ("referenciado desde #84 y desde `CONTEXTO.md`") se cumple igual con un link. |
| **Contenido del issue verificado contra `services/python-worker/ml/models.py` antes de implementar** | El texto de triage (`lag_N`, `period`, `trend`, `eff_lags`, inputs de Prophet) se confirmó línea por línea contra `_build_lag_month_trend` (líneas 245-254) y `fit_xgb_insample`/`fit_rf_insample` (líneas 261-386) — coincide exactamente, no hacía falta corregir el brief. |

> **Nota:** sesión corta, arrancó sobre un issue puntual ya existente (no un plan sin partir) — el paso siguiente es `/implement` directo sobre #85, no `/to-tickets`.

---

### `ml/eval_walkforward.py` — Issue #86 (sesión 2026-07-15)

Grilling arrancó sobre el schema **real** ya commiteado en `infra/sql/16-catalogo-modelos.sql` (issue #84, implementado en otra sesión), no sobre el borrador original del issue — varias columnas nuevas (`version_modelo`, `rmse_test`, `n_arboles`/`profundidad_max` como columnas `GENERATED` desde `hiperparametros`) ya estaban decididas ahí y se toman como dato de entrada, no se re-discuten.

| Decisión | Definición |
|----------|-----------|
| **`hiperparametros`/`features`: fit de referencia aparte sobre `full_series`, no threadear `WalkForwardResult`** | `_aggregate_walkforward` corre el fit por cada fold y descarta el `ModelResult` completo — no se modifica esa función para params/features (evita superficie de riesgo sobre lo que ya usan #72/#73 en producción). En su lugar, `eval_walkforward.py` hace un fit adicional (`fit_rf_insample`/`fit_xgb_insample`/`fit_prophet_insample`) sobre la serie completa, mismo patrón que ya usa `n_obs_total`/fechas (calculadas sobre `full_series`, no sobre folds). |
| **`version_modelo` vía `EVAL_VERSION` + `resolve_version()`** | `eval_walkforward.py` no tenía ningún concepto de versión hasta ahora. Se agrega el env var `EVAL_VERSION` y se resuelve con `utils.versioning.resolve_version()` — misma función y mismo patrón que ya usa `predict.py`. |
| **`n_obs_test = horizon`, directo** | Confirmado en `ml/evaluate.py:walk_forward_split` — cada fold testea exactamente `horizon` puntos, fijo entre folds. Sin ambigüedad, no requiere agregación. |
| **`n_obs_train = n_train_rows_mean`, no el mínimo** | `WalkForwardResult` ya calcula ambos. Se usa el promedio (tamaño "típico" de entrenamiento, comparable entre SKUs/algoritmos); la fragilidad de folds con poca historia ya la señala la columna `estable`, no hace falta que `n_obs_train` duplique esa señal con el mínimo. |
| **`rmse_test_median`: campo nuevo en `_aggregate_walkforward`/`WalkForwardResult`** | Hallazgo de la sesión: `rmse_test` no lo daba nada — ni el fit de referencia (sin test held-out) ni `WalkForwardResult` (que hoy solo agrega `r2_test`/`mae_test`/`rmse_train`, nunca RMSE del lado de test). Es la única métrica que sí obliga a tocar `_aggregate_walkforward`, pero es un cambio aditivo chico (una lista + un campo más, mismo patrón que `r2_tests`/`mae_tests` ya existentes) — no restructura nada. |
| **`mae_train`: calculado inline en `eval_walkforward.py`, sin tocar `models.py`** | `ModelResult` no tiene campo `mae` y `WalkForwardResult` tampoco tiene `mae_train`. Se calcula directo en `eval_walkforward.py` comparando `reference_fit.holdout_pred` contra `full_series` (mismo tipo de cálculo que `_mae` en `models.py`, pero sin necesidad de exportarla — es una línea de numpy). |
| **Persistencia gateada por `EVAL_PERSIST_CATALOG`, flag nuevo y separado de `EVAL_PERSIST`** | `EVAL_PERSIST` ya gatea la escritura a `articulos_elegibilidad_econometrico`, que afecta routing real de producción (qué SKU recibe modelo econométrico). `catalogo_modelos` es puro registro histórico, no lo lee nada en producción — perfil de riesgo distinto, así que se desacopla: se puede construir historial del catálogo sin tocar la tabla de elegibilidad, y viceversa. Mismo default conservador (`false`) que ya usa `EVAL_PERSIST`. |
| **Persistencia: INSERT simple, no upsert** | Ya implícito en el schema de #84 (índice compuesto `(sku, modelo, fecha_estimacion)`, sin `UNIQUE`) — la tabla acumula histórico, cada corrida es una fila nueva. |

> **Nota:** sesión arrancó sobre un issue puntual ya existente — el paso siguiente es `/implement` directo sobre #86, no `/to-tickets`.

**Implementación + `/code-review` (mismo día).** Smoke test real contra DB local (Docker levantado, SKU sintético `TEST0001`, datos limpiados después) encontró un bug real antes de que lo hiciera el review: `XGBRegressor.get_params()` trae `missing: float('nan')` por default — `json.dumps` lo serializa como el literal `NaN`, que MySQL rechaza (confirmado también empíricamente: pymysql tira `"nan can not be used with MySQL"` antes de llegar a la DB). Se agregó `_json_safe()` para sanear recursivamente NaN/Infinity antes de serializar a JSON.

El review (`medium`, 8 ángulos) encontró 7 hallazgos reales; se corrigieron 4 antes de commitear:

| Hallazgo | Fix |
|----------|-----|
| `insert_catalogo_modelos()` sin try/except — una fila mala aborta toda la corrida | Try/except por fila dentro de la función (mismo espíritu de "no perder progreso" que ya tenía el commit-por-fila, extendido a tolerancia a fallos) |
| `r2_train`/`rmse_train`/`mae_train` sin sanear NaN (solo `hiperparametros`/`features` pasaban por `_json_safe`) | Nuevo helper `_finite()` aplicado a los 6 campos numéricos de la fila |
| Dispatch por modelo (`if/elif` sobre strings) podía desincronizarse en silencio del `name=` real y degradar a NULL sin aviso | Dict `_REFERENCE_FITTERS` + warning explícito si el nombre no matchea |
| Doble capa de `except Exception: pass` sin logging | `print("[WARN] ...")` en los 3 puntos de falla (fit de referencia, construcción de fila, insert) |

**No se corrigieron 3 hallazgos** (quedan documentados en el PR/review, no en un issue aparte salvo el primero):
- El fit de referencia duplica cómputo que el walk-forward ya hizo (costoso para Prophet — confirmado en el smoke test: 4 corridas MCMC para 1 SKU) → **issue #92**, requiere tocar `_aggregate_walkforward`/`WalkForwardResult`, fuera de alcance de esta sesión.
- `mae_train` reimplementa `_mae` de `models.py` en vez de reusarla (cleanup menor).
- `insert_catalogo_modelos` duplica el loop de `upsert_elegibilidad_metrics` (cleanup menor, mismo patrón ya usado en el repo).

---

### `ml/eval_walkforward.py` — Issue #87, redefinido a dry-run (sesión 2026-07-15)

**Hallazgo que reabre el alcance:** la DB local está completamente vacía (0 filas en `ventas_historicas`/`articulos` — no es una cobertura parcial de grupo 201 como se asumió al triagear, es cero datos). Sin acceso a la VM de producción, correr el análisis real de #87 hoy es imposible sin inventar datos — y usar datos sintéticos para el análisis real corrompería el insumo de la decisión de #88 con basura, no es un atajo válido.

| Decisión | Definición |
|----------|-----------|
| **Alcance de HOY redefinido a dry-run mecánico, el análisis real queda bloqueado** | No se toca el objetivo real de #87 (el reporte que alimenta #88) — se deja explícitamente pendiente hasta tener datos reales (VM o #38 resuelto). Lo que sí se hizo hoy: validar que el pipeline corre de punta a punta sobre un lote de SKUs sintéticos y medir tiempo, dejando todo listo para correrlo de verdad apenas haya datos. |
| **Sin query nueva de selección de universo** | `eval_walkforward.py` ya carga todos los SKUs de `ventas_historicas` sin filtro, y cada fit ya devuelve `None` silenciosamente si no alcanza la historia mínima — ese skip silencioso YA es el filtro de universo que pedía el alcance original de #87. No hace falta escribir SQL nuevo; #87 es una tarea operativa (correr un comando), no de código. |
| **~15-20 SKUs sintéticos con historia variada** | Mezcla deliberada: SKUs con historia larga (36+ meses), SKUs justo en el límite mínimo (valida el skip silencioso en el borde), y series planas/degeneradas (estresa el manejo de NaN que ya se vio en #86). Un solo SKU (repetir el smoke test de #86) no da un promedio de tiempo confiable. |
| **Persistencia real (`EVAL_PERSIST_CATALOG=true`), limpieza después** | Mide el costo de punta a punta (cómputo + escritura), no solo cómputo — mismo criterio que el smoke test de #86. Los SKUs sintéticos y sus filas se borran al final. |
| **Documentar en comentario de #87 + esta sección** | El comentario en el issue aclara explícitamente que es un dry-run, no el análisis real, para que nadie lo confunda después con el insumo de #88. |

> **Nota:** #87 sigue abierto — el análisis real queda bloqueado por #38 (sincronizar entorno local) o acceso a la VM de producción. El paso siguiente NO es `/implement` (no hay código nuevo) — es ejecución directa del dry-run.

**Resultado del dry-run (mismo día).** 15 SKUs sintéticos (6 con 36 meses variados, 5 al límite mínimo 13-15 meses, 4 degenerados: constantes/mayormente-cero), `EVAL_PERSIST_CATALOG=true`, `EVAL_VERSION=dryrun-87`.

| Métrica | Resultado |
|---|---|
| Tiempo total | 62s para 15 SKUs (~4.1s/SKU promedio, los 3 modelos juntos) |
| Filas escritas | 40 (15 RF + 15 XGB + 10 PROPHET) |
| Warnings/crashes | 0 — ninguno de los fixes del code-review de #86 se disparó (ni NaN, ni dispatch, ni excepción sin loguear) |
| SKUs límite (13-15 meses) | Prophet se salteó solo en los 5, sin romper nada — comportamiento ya existente (`min_needed=12` para MS), validado bajo el caso borde real |
| SKUs degenerados (constante/mayormente-cero) | Los 4 corrieron sin NaN en ningún campo — exactamente el escenario que motivó `_finite()`/`_json_safe()` en el review de #86 |

**Nota sobre el tiempo:** 32 fits MCMC de Prophet reales en total (folds + fit de referencia de #86, no resuelto por #92 todavía). Es una cota inferior — series sintéticas cortas y simples corren más rápido que datos reales de producción con estacionalidad/ruido genuino. No sirve para proyectar el tiempo real de miles de SKUs, pero confirma que el pipeline no tiene ningún costo estructural inesperado más allá del fit duplicado ya conocido (#92).

**Esto NO es el análisis de #87** (no hay distribución real de r2_test por algoritmo sobre datos reales) — sigue bloqueado por #38/VM.

---

### `ml/eval_walkforward.py` — Issue #87, análisis real completado (sesión 2026-07-15)

**Corrección al hallazgo de la sesión anterior:** el "0 filas" que motivó el dry-run de arriba era sobre la base local del Mac de Santiago, no una verdad general del proyecto — el volumen Docker de MySQL es local a cada máquina. La base local de esta PC (Windows) sí tenía datos reales de grupo 201 desde sesiones de backfill anteriores (104 `articulos`, 353.599 filas de `ventas_historicas`, 2016-2026). #87 no estaba bloqueado acá.

| Decisión | Definición |
|----------|-----------|
| **Universo: grupo 201 (real, pero parcial), no el catálogo completo** | La base local solo tiene grupo 201, no los ~5500 SKUs de producción (bloqueado por #38, sin resolver). Se corre igual sobre datos reales — mejor un análisis real acotado que uno sintético completo, que corrompería el insumo de #88 con basura. |
| **Piloto de 10 SKUs antes de la corrida completa** | Dado que #74 (performance con volumen) sigue sin resolver, se midió tiempo real antes de comprometerse: 124s para 10 SKUs de alta historia (9 años) — no representativo del universo completo, ver nota abajo. |
| **Corrida completa: 348s (~5.8 min) para 85-104 SKUs** | Mucho más rápido que la extrapolación ingenua del piloto (que había sobreestimado ~21 min, porque los 10 SKUs del piloto eran los de mayor historia/volumen del catálogo, no representativos del promedio real). Insumo directo para #74. |
| **Filas del piloto borradas después de medir tiempo** | Quedaban mezcladas en `catalogo_modelos` con `version_modelo` distinto (`grupo201-pilot-87` vs `grupo201-real-87`) — se borran las del piloto para dejar solo la corrida real como fuente de verdad. |

**Resultado real (223 filas en `catalogo_modelos`, `version_modelo=grupo201-real-87`):**

| Modelo | SKUs evaluados | `median_r2_test` | Estable / Volátil / Sin evaluar (1 fold) |
|--------|---------------|-------------------|-------------------------------------------|
| PROPHET | 53 | **0.3234** | 23 / 24 / 6 |
| RF | 85 | 0.0000 | 68 / 10 / 7 |
| XGB | 85 | 0.0000 | 63 / 15 / 7 |

- Selección real de producción (criterio actual, menor RMSE in-sample): PROPHET 50, RF 33, XGB 2.
- **Mediana de `r2_test` (walk-forward) del modelo elegido: 0.0769** — bastante menor que en el piloto (0.3375), porque el piloto cherry-pickeaba los SKUs de mayor historia.
- 30.6% de los SKUs elegidos son volátiles entre folds; 15.3% no tiene folds suficientes para evaluar estabilidad.
- 0% con `r2_test` negativo.

> **Veredicto textual del script (reemplaza el de #69/#78, ahora sobre datos reales):** "ZONA GRIS — no es claramente aceptable ni claramente roto. Documentar y decidir con el cliente." Insumo directo para #88 — la pregunta de #88 (mix por SKU vs. algoritmo único, y si el criterio de selección debería cambiar de RMSE in-sample a r2_test/holdout real) no tiene una respuesta obvia con este resultado: PROPHET domina en mediana pero con alta volatilidad, RF/XGB rinden peor en mediana pero son más estables. Vale la pena mostrarle este resultado al cliente antes de decidir #88, tal como sugiere el propio veredicto.

---

### Sincronización local↔producción vía S3, ejecutada — Issue #38 (sesión 2026-07-15)

Retomado tras conseguir acceso real a la cuenta de AWS (bloqueo original desde 2026-07-13). Se ejecutó el plan ya diseñado (S3, usuario IAM `evalutia-sync`), sin rediseñar nada.

| Decisión | Definición |
|----------|-----------|
| **Infra AWS creada**: bucket `evalutia-sync-dumps` (región `us-east-2`, misma que la VM), política `evalutia-sync-s3-policy` (`ListBucket` sobre el bucket + `GetObject`/`PutObject`/`DeleteObject` sobre su contenido), usuario IAM `evalutia-sync` con esa política adjunta directamente (sin acceso a consola). | Mismo diseño documentado en la sesión de 2026-07-13, ahora ejecutado. |
| **Misma credencial reusada en PC y VM, a propósito** | Decisión explícita del usuario: no crear un segundo usuario IAM por máquina/persona (aunque sería más prolijo si Santiago usa su propia Mac) — simplicidad sobre separación de credenciales para este caso. |
| **Scripts nunca commiteados, encontrados sin trackear** | `scripts/prod_dump_to_s3.sh` (nuevo) y el rediseño S3 de `scripts/sync_local_from_prod.sh` (el commiteado seguía en el diseño viejo de conexión directa) llevaban desde el 2026-07-13 solo en el disco local del usuario. Se completó el commit pendiente (`7274679`) antes de poder correrlos en la VM. |
| **Bug real encontrado: permisos de escritura en el directorio de arranque de Session Manager** | La sesión de SSM arranca en `/var/snap/amazon-ssm-agent/<id>` (propiedad de `root`, no escribible por `ssm-user`) — cualquier script que asuma que puede escribir en el directorio actual falla ahí. Se resuelve haciendo `cd /opt/evalutia` (o `/tmp`) antes de correr nada, no es un bug del script en sí. |
| **Bug real encontrado y corregido: `mktemp -t` + ruta absoluta con `/` rompen `aws.exe` en Windows** | `aws.exe` es un binario nativo de Windows, no MSYS — cuando recibe una ruta estilo `/c/Users/...` (la que produce `pwd`/`mktemp` en Git Bash), la resuelve mal y termina buscando `..\..\..\..\c\Users\...`. Ni `mktemp -t` ni construir la ruta absoluta a mano funcionan. Fix: `TMP_DUMP` pasa a ser un nombre de archivo **relativo** (`.sync_tmp_dump.sql.gz`, sin ninguna barra) ya que el script hace `cd` a `SELF_DIR` antes — sin barras, no hay nada que MSYS pueda traducir mal. Se probaron dos fixes intermedios que NO funcionaron (`MSYS_NO_PATHCONV=0` inline, y `unset` en subshell) antes de llegar a este — para MSYS alcanza con que la variable *exista* en el entorno (cualquier valor) para desactivar la conversión, así que ninguno de los dos evitaba el problema real (la ruta absoluta con `/`), solo la ruta relativa lo resuelve de raíz. |
| **Progreso de `aws s3 cp` genera miles de líneas sin salto de línea real** | Sin terminal interactiva, la barra de progreso de `aws s3 cp` imprime una línea nueva por cada actualización en vez de sobreescribir — se agrega `--no-progress` al comando para evitar inundar cualquier log/captura futura. |

**Resultado (verificado con `SELECT COUNT(*)` antes/después):**

| Tabla | Antes (solo grupo 201) | Después (catálogo completo) |
|-------|------------------------|------------------------------|
| `articulos` | 104 | **5.550** |
| `ventas_historicas` | 353.599 | **4.442.089** |
| `ventas_mensuales` | 11.639 | **153.404** |
| `stock_diario` | (no medido) | **26.652.534** |
| `grupos` | 66 | 66 (sin cambio) |
| `catalogo_modelos` | 223 (análisis de #87) | 223 (intacto — no está en la lista de tablas que sincroniza el script) |

**Criterio de aceptación adicional (2026-06-17) cumplido, mismo día:** con el catálogo completo ya local, se identificó `O00550` (BOTELLA DE TINTA BROTHER BT-5001 MG) con `estado_mes='quiebre_parcial'` real en junio/2026 (mes cerrado) y `frecuencia_nivel='alta'`. Verificado con Playwright, leyendo el `background-color` computado de la celda `VTA.JUN/26` directamente (no solo captura visual): `rgba(234, 179, 8, 0.18)` — coincide exacto con la rama "alta" (amarillo) de `estadoMesBg()`. La misma captura de pantalla mostró de paso `O00489` en rojo y `O00514` en naranja, confirmando visualmente los 3 niveles de color en una sola pantalla. Hasta ahora solo se había validado el caso `'normal'` (sin quiebre) — este es el primer caso real de `quiebre_parcial` coloreado, cerrando el gap que dejaba #34/#35 sin verificar al 100%.

**#38 cerrado.**

---

### Corte mTLS ejecutado en vivo con IT — Issues #51/#52 (sesión 2026-07-17)

Coordinado en vivo con Martín García (MG Soluciones IT) vía WhatsApp, dentro de la ventana ya acordada (viernes 9-12hs).

| Decisión | Definición |
|----------|-----------|
| **Setup replicado en Mac**: AWS CLI instalado (instalador oficial `.pkg`, Homebrew no estaba disponible), perfil `evalutia-sync` configurado y verificado (`Account: 597055632942`) | Mismo perfil reusado entre PC Windows, VM y esta Mac (decisión ya tomada). |
| **Migraciones locales atrasadas, aplicadas antes del sync**: 08 (planilla-frecuencia-quiebre), 09 (factores mensuales), 10 (grupos), 11 (stock_resumen_365), 12 (fix encoding), 13 (elegibilidad econométrico), 14 (ventas cantidad signed), 15 (frecuencia tickets) | El script de sync hace `TRUNCATE` + restore sobre tablas que no existían localmente (`grupos`, `stock_resumen_365`, `articulos_elegibilidad_econometrico`) — habría fallado a mitad de camino. Además `ventas_historicas.cantidad` seguía `UNSIGNED` (migración 14 no aplicada): restaurar notas de crédito reales de producción sin este fix habría corrompido datos por wraparound, mismo bug que ya documentó #82. |
| **Sync ejecutado**: 5.550 artículos, 4.44M ventas_historicas, 26.6M stock_diario — mismos números que la sesión de Santiago | Corrió ~35 min en background (dump 282M desde S3, restore de 26M+ filas sin batchear). |
| **3 pasos del corte, todos confirmados en vivo**: (1) rechazo sin certificado, (2) `200 OK` con certificado + WSDL completo, (3) `WS_URL` vuelto a `https://` (commit `399086f`) + rebuild/recreate de `etl` en producción + corrida manual de `run_ofelia.sh` contra datos reales — 3 jobs `exitoso` en `jobs_historial`, sin fallos | Activa juntos `#51` (mTLS), `#71` (elegibilidad SKU) y `#80` (ventas negativas) en el mismo rebuild, tal como estaba planeado. |
| **No se esperó el cron automático de las 3 AM antes de cerrar** | La corrida manual usó el mismo script (`run_ofelia.sh`) que invoca Ofelia — el pipeline completo (extracción SOAP vía mTLS, merge, predicciones, planilla) quedó probado con datos reales. El riesgo restante (¿dispara Ofelia sola?) es de un tipo distinto y menor al ya validado. |
| **Hallazgo sin resolver, no es nuestro**: tráfico de un sistema llamado "IntegraMerica" al puerto 81, rechazado tras el corte por falta de certificado | Sin registro en este repo ni conocimiento del usuario — Martín queda con la pregunta, es un tema de coordinación con el cliente/IT, no de ingeniería de este proyecto. |

**#51 y #52 cerrados.**

**Post-cierre, mismo día:**
- **`#53` cerrado como no prioritario.** El runbook de prueba manual desde PC/Mac (`cotech-dev.p12`) quedó redundante: la VM ya cubre cualquier diagnóstico manual (mismos comandos `curl` usados hoy), y en un incidente real el camino natural es entrar por la VM, no pegarle al webservice directo desde una oficina. No se le preguntó a Martín sobre las IPs dinámicas de oficina (pregunta que quedaba pendiente) porque dejó de ser necesaria.
- **`#55` (vigencia del certificado): fecha real confirmada**, `openssl pkcs12` contra `cotech-prod.p12` en la VM (sin exponer la contraseña, vía `-passin env:CERT_PASSWORD`) → vence **26 de septiembre de 2028**. Cerrado a pedido del usuario (más de 2 años de margen) — el *proceso* de rotación (quién lo gestiona, con cuánto preaviso) queda sin documentar, sin ningún issue rastreándolo. Si hace falta retomarlo más adelante, abrir uno nuevo.

---

### `run_calc_planilla.py` — Bug real encontrado y corregido, Issue #64 (sesión 2026-07-17)

**Replanteo del alcance original:** #64 pedía comparar contra una "planilla de referencia del cliente" — no existe, porque frecuencia de venta es una métrica **nueva** que pidió el cliente (#61), no algo que él ya clasifique por su cuenta (a diferencia de `estado_mes`, #36-#39, donde sí había un Excel de referencia). Se descartó también la validación final con el cliente (paso que #64 sugería) — decisión del usuario: la verificación de que el cálculo sea lógico y razonable la hacemos nosotros, no hace falta su visto bueno.

**Bug encontrado corriendo la QA contra datos reales** (posible gracias al sync completo del día): `ventas_historicas` guarda una fila por SKU por día calendario, tenga o no venta real (`cantidad=0` en ~97% de las filas). El conteo de "tickets" (`COUNT(DISTINCT vh.fecha)`) no filtraba por `cantidad`, así que contaba días del mes, no días con venta — `tickets_mes` salía 28-31 para casi todo el catálogo. Señal que lo delató: **0 filas cayeron en la banda "3-4 tickets" (`criterio_frecuencia='promedio'`) sobre 71.973 filas reales**, estadísticamente imposible con un conteo real.

| Decisión | Definición |
|----------|-----------|
| **Por qué los 33 tests unitarios no lo agarraron** | Testean `valor_ajustado_y_criterio()` con `tickets` ya calculado a mano — nunca la query SQL que produce ese número contra datos reales. El bug vivía justo en la parte que ningún test unitario podía cubrir sin datos reales. |
| **Fix**: agrega `AND vh.cantidad != 0`, extrae la query a `cargar_tickets()` (mismo patrón que `cargar_factores`/`cargar_fec_alta`) para que sea testeable en aislamiento | Nuevo test de integración (`test_cargar_tickets_excluye_filas_con_cantidad_cero`) contra MySQL real, con `pytest.skip` si no hay DB (CI no levanta MySQL para `services/etl/tests`). |
| **Verificado contra datos reales sincronizados**: `criterio_frecuencia` pasó de `(historico=52617, promedio=0, real_extrapolado=19356)` a `(historico=65360, promedio=2824, real_extrapolado=3789)` | Distribución de `tickets_mes` también cambió de mayormente 28-31 a mayormente 0-2 (65.341 filas) — coherente con un catálogo amplio donde la mayoría de los SKUs no venden todos los días. |
| **Spot-check manual de 2 SKUs** (`C00015`, `C00027`) contra `ventas_historicas` cruda | Tickets reales = 4 en ambos (coincide). Blending: `(19.25+55)/2=37.125≈37.12` ✓, `(18.83+15)/2=16.915≈16.91` ✓. |
| **`/code-review` (medium) encontró 5 hallazgos, 3 corregidos**: `except Exception` genérico en el test enmascaraba errores de config como skip silencioso; el test no era idempotente ante un corte a mitad de camino (ahora limpia antes de insertar); docstring de 13 líneas con narrativa forense, recortado a 4 | El hallazgo de mayor nivel (altitude): la ambigüedad de fondo de `ventas_historicas` (fila = evento real vs. snapshot en cero) queda documentada como invariante en un comentario nuevo arriba de `FREQ_ALTA_MIN`, para que la próxima query similar no reintroduzca el mismo bug. |
| **Pendiente real, no resuelto en esta sesión: deploy a producción** | El servicio `etl` hornea el código en la imagen (`COPY . /app`, sin volumen montado) — el fix no se activa con un `git pull` en la VM, necesita `docker compose build etl && up -d --force-recreate etl` explícito, mismo patrón que ya vivimos con el corte mTLS. Producción sigue sirviendo `tickets_mes`/`criterio_frecuencia` incorrectos (ya visibles al cliente vía #65/#66) hasta que se despliegue. |

**#64 cerrado** (bug real encontrado, corregido, testeado, verificado contra datos reales — el criterio de aceptación original ya no aplicaba tal cual, pero el espíritu de la QA se cumplió con creces).

**Actualización, mismo día — deploy a producción completado.** `docker compose build etl` + `up -d --force-recreate etl` en la VM, seguido de `run_calc_planilla.py` manual contra el catálogo real: `5559 SKUs · 71982 filas · frecuencia: alta=707 media=486 baja=4365` en 668s — casi idéntico a lo validado localmente (707/486/4356). El cliente ya ve los valores corregidos en la Planilla real, no solo en el repo.

---

### `configuracion_sistema` — Issue #67, diseño (sesión 2026-07-17)

**Reencuadre de alcance:** el issue original esperaba una conversación con el cliente antes de construir esto ("evaluar... si en el futuro se pide"). Decisión explícita del usuario: no se le pregunta al cliente — se construye, se le muestra hecho, y se ajusta después si no le sirve. El bloqueo deja de ser una decisión de negocio externa y pasa a ser puro diseño técnico, resuelto en esta sesión de `/grill-me`.

| Decisión | Definición |
|----------|-----------|
| **Tabla genérica clave-valor `configuracion_sistema`**, no columnas dedicadas | Extensible sin migrar de nuevo si en el futuro se configuran también `ESTADO_UMBRAL_NORMAL`/`FREQ_ALTA_MIN`/`FREQ_BAJA_MAX` — mismo principio que ya se usó para `catalogo_modelos` (JSON genérico) vs. columnas puntuales. |
| **Alcance de la UI: solo los 2 umbrales de tickets pedidos** (`tickets_bajo_max`, `tickets_alto_min`) | La tabla soporta más a futuro, pero no se construye UI para umbrales que nadie pidió todavía (`ESTADO_UMBRAL_NORMAL`, `FREQ_ALTA_MIN`/`BAJA_MAX` siguen como constantes Python). |
| **Validación `bajo < alto` en el backend**, no solo en el frontend | La banda "promedio" (3-4 tickets) desaparece o se invierte si se editan mal — el endpoint rechaza con 422 (mismo patrón `InvalidOperationException` que `UsuarioService`/`VentasService`) si no se cumple, no confía en que el formulario lo prevenga (alguien podría pegarle directo al endpoint). |
| **Cambios aplican en el próximo cron nocturno, no al instante** | `run_calc_planilla.py` ya recalcula toda la ventana de 13 meses desde cero cada noche (DELETE+INSERT atómico) — no hace falta un botón de "recalcular ahora", el próximo cron simplemente lee el valor nuevo. La UI debe avisar esto explícitamente para que el cliente no espere verlo reflejado al toque en la Planilla. |
| **`actualizado_por` (FK a `usuarios`), no solo `actualizado_en`** | Es un valor de negocio crítico que afecta lo que ve el cliente — si algo sale raro después de un cambio, poder decir "lo cambió Fulano el martes" vale el costo mínimo de una columna FK más. |
| **Acceso solo `administrador`**, mismo patrón `RequireAdmin` que `UsersPage`/`VentasPage`/`JobsPage` | Es configuración de sistema, no un dato operativo de solo-lectura que vea `duenoDeEmpresa`. |
| **Migración siembra la tabla con los valores actuales (2, 5)** | Cero cambio de comportamiento hasta que un admin edite algo activamente — mismo principio que el seed de `grupo_id`/`aplica_modelo_econometrico` en `10-grupos.sql`. Sin esto, la tabla vacía dejaría al ETL sin valor que leer. |

**Próximo paso:** `/implement` directo sobre #67 (arrancó como issue puntual, no un plan sin partir).

**Actualización, mismo día — implementado, revisado y cerrado.** 4 capas (SQL/ETL/backend/frontend) completas. `/code-review` (8 ángulos en paralelo) encontró 5 findings reales, todos corregidos antes de commitear: el upsert de los dos umbrales no era atómico (dos `SaveChanges()` separados dejaban una ventana donde un lector concurrente —otro admin, o la ETL— podía ver un par `bajo`/`alto` inválido a medio escribir; se unificó en un solo `UpsertMuchas`/`SaveChanges`), la ETL no validaba el invariante `bajo < alto` como defensa adicional (se agregó, mismo tipo de invariante silenciosa que causó el bug de #64), un método de repositorio sin ningún caller (`GetPorClave`, eliminado), un test frágil con `fetchone()` sin chequeo de `None`, y un typo de status code (400→422) en esta misma documentación. Verificado end-to-end con Playwright real (login → guardar → reload → persistencia confirmada) y curl contra GET/PUT/validación/auditoría. **#67 cerrado.**

---

### Tests.csproj — Issue #91 (sesión 2026-07-17)

Triage encontró `net10.0` en `Tests.csproj` (vs. `net8.0` del resto del backend), sin ningún test real dentro, no incluido en `WebApi.sln`. Investigado antes de preguntar: el archivo apareció en un commit sobre gráficos de frontend (`7e2fb3e`), sin relación con testing — confirmado con el usuario como scaffold accidental, no migración intencional.

Delegado a un subagente en worktree aislado (para no pisar el trabajo simultáneo de #72 en la rama principal): alineado a `net8.0`, sumado al `.sln`, 12 tests reales (`ConfiguracionService`, `AuthService`) cubriendo casos de éxito y validación, `dotnet test` agregado a CI. El propio subagente encontró y corrigió un bug real en el `Dockerfile` del backend (el `.sln` ahora referencia `Tests.csproj`, pero el `COPY` por capas no lo traía antes del `restore` — hubiera roto el build). Revisado independientemente (build limpio, tests leídos línea por línea) antes de mergear. **#91 cerrado.**

---

### Extender evaluación holdout a todo el catálogo — Issue #72, ejecución real (sesión 2026-07-17)

El diseño de la sesión anterior (2026-07-13, ver arriba) seguía vigente casi entero, con una excepción real: decía "correr contra producción, vía VM" porque en ese momento la base local solo tenía el grupo 201 (#38 bloqueado). Ese bloqueo se resolvió *ese mismo día* (sync completo vía S3, ver sesión de mTLS más abajo) — se re-grilló ese punto puntual antes de ejecutar.

| Decisión (re-grilling puntual) | Definición |
|----------|-----------|
| **Local en vez de VM de producción** | La base local ya tiene los 5.550 SKUs reales (sync de hoy) — mismos datos, cero riesgo sobre la base que sirve al cliente. Se aplica a producción después, ya validado. |
| **El tiempo medido localmente no es insumo válido para #74** | Hardware distinto a la VM del cron real. Se mide igual como referencia de orden de magnitud (detecta problemas graves temprano), pero #74 tiene que medir de nuevo en la VM antes de cerrar. |
| **Piloto estratificado antes de la corrida completa** | Mismo patrón que #87, pero corrigiendo su sesgo conocido: el piloto de #87 sobre-representaba SKUs de historia larga (cherry-picking involuntario) y sobre-estimó el tiempo real. Este piloto (30 SKUs) se armó con muestreo aleatorio estratificado por bucket de meses de historia. |
| **Sin filtro de historia mínima (24 meses) en #72** | Ese piso es un criterio de *elegibilidad* (#73), no de *medición* (#72) — la separación "medir vs. decidir" ya está en el diseño original. Filtrar ahora le sacaría datos a #76, que explícitamente audita el caso borde "SKUs con menos de 12 meses de historia". |
| **`EVAL_PERSIST` + `EVAL_PERSIST_CATALOG` juntos** | Mismo costo de cómputo (el walk-forward ya se paga igual); persistir también en `catalogo_modelos` le da a #88 el catálogo completo real como insumo, no solo el grupo 201 de #87. |

**Bug real encontrado antes de comprometerse a una corrida de horas:** el código de `eval_walkforward.py` (escrito en la sesión de #86) no persistía incrementalmente pese a que el diseño original de #72 lo exigía explícitamente ("commits por SKU/lote... reanudable"). En realidad acumulaba todo en memoria y escribía en un solo batch al final del loop completo — confirmado empíricamente (0 filas nuevas en `catalogo_modelos` tras ~10 min de corrida real). Con Docker Desktop ya inestable esa misma noche (se cayó una vez durante la sesión), una corrida de varias horas sin persistencia incremental real arriesgaba perder el 100% del progreso ante cualquier corte.

**Fix aplicado** (`services/python-worker/ml/eval_walkforward.py`): el cálculo del "ganador" por SKU (antes hecho una sola vez al final, sobre el DataFrame completo vía `groupby`) se movió a ocurrir apenas termina el loop interno de los 3 modelos de cada SKU — matemáticamente idéntico (el ganador de un SKU no depende de ningún otro SKU), pero permite flushear a la DB cada `EVAL_PERSIST_BATCH_SIZE` SKUs (default 100) en vez de al final. Verificado con un test de 5 SKUs y batch size 2: los checkpoints de progreso y los conteos de filas persistidas coinciden exactamente con lo esperado.

**Corrida completa terminada, limpia, sin cortes.** ~66 minutos locales (19:12→20:18) para las 1.955 SKUs con historia real en `ventas_historicas` (los ~3.595 SKUs restantes del catálogo de 5.550 no tienen ninguna venta real, se descartan casi instantáneo — confirma que la estimación cruda inicial de "hasta 15h" estaba sobreestimada, tal como se anticipó). Persistencia incremental verificada en producción real (no solo en el test de 5 SKUs): 3.010 filas en `catalogo_modelos` (1.476 SKUs distintos, `version_modelo=catalogo-completo-72`, sin contaminación de datos de piloto/test), 1.476 filas con métrica real en `articulos_elegibilidad_econometrico`.

**Resultado real, catálogo completo:**

| Modelo | SKUs evaluados | `median_r2_test` | Estable/Volátil/1-fold |
|--------|-----------------|-------------------|--------------------------|
| PROPHET | 58 | 0.3624 | 20/33/5 (57% volátil) |
| RF | 1.476 | 0.0000 | 1236/140/100 |
| XGB | 1.476 | 0.0000 | 1239/137/100 |

Selección real de producción hoy (criterio viejo, menor RMSE in-sample): RF gana 1.419 de 1.476 (96%) — muy distinto al patrón de grupo 201 solo (RF 33/104), porque a nivel catálogo completo casi ningún SKU tiene los ≥8 trimestres que Prophet necesita (58/1955 = 3%), así que RF gana por default en la enorme mayoría. Mediana de `r2_test` walk-forward del modelo seleccionado: **0.0000** (peor que grupo 201 solo, que daba 0.0769) — 0% con `r2_test` negativo, 10.4% volátiles, 7.1% sin folds suficientes para evaluar estabilidad. Promedio de `r2_test` (no mediana): 0.1514.

**Veredicto textual del script (catálogo completo, reemplaza el de grupo-201-solo de #87): "REDISEÑO NECESARIO — señales claras de sobreajuste/memorización incluso con walk-forward."** Confirma con muchos más datos (1.955 SKUs vs 104) la misma conclusión de #87/#88 — no cambia ninguna decisión ya tomada, la refuerza.

**Insumo directo para #73** (siguiente issue de la cadena): las 1.476 filas de `r2_test`/`estable`/`n_folds`/`meses_historia` ya están persistidas y listas — #73 solo necesita aplicar el criterio de elegibilidad (`r2_test ≥ 0` + no-volátil, ya definido en #70) sobre datos reales, sin tener que volver a correr nada.

**#72 cerrado.**

---

### Criterio de selección de modelo por SKU en `predict.py` — Issue #88 (sesión 2026-07-17)

**Reencuadre de proceso, confirmado con el usuario:** el veredicto textual del propio script de #87 sugiere "documentar y decidir con el cliente". Se decidió igual resolverlo internamente, mismo patrón que #64/#67 — es una decisión técnica sobre calidad de generalización de modelos, con datos concretos ya generados, no una preferencia de producto donde el cliente tenga un criterio propio que aportar (mismo tipo de llamada que #70 ya tomó al fijar `r2_test ≥ 0` sin threshold arbitrario).

**Datos usados** (agregados ya documentados de la sesión de #87 — el detalle crudo por SKU no está en la base local, `catalogo_modelos` no forma parte del sync de #38):

| Modelo | SKUs evaluados | `median_r2_test` | Estable/Volátil/1-fold |
|--------|-----------------|-------------------|--------------------------|
| PROPHET | 53 | 0.3234 | 23/24/6 (45% volátil) |
| RF | 85 | 0.0000 | 68/10/7 |
| XGB | 85 | 0.0000 | 63/15/7 |

| Decisión | Definición |
|----------|-----------|
| **Se confirma la hipótesis del issue: mix por SKU se mantiene, cambia el criterio** | De "menor RMSE in-sample" (ya demostrado propenso a sobreajuste — motivo original de #68/#78) a "mejor `r2_test` walk-forward real" — misma métrica que #70 ya usa para elegibilidad, una sola fuente de verdad para "qué tan bien generaliza este modelo". No se abandona el mix: ya viene naturalmente segmentado por disponibilidad de datos (Prophet solo es candidato cuando hay ≥8 trimestres de historia). |
| **Volatilidad entre folds: informativa, no descalifica al ganador** | Aunque el 45% de los casos donde PROPHET gana son "volátiles", no se agrega una regla de desempate por estabilidad — mismo principio de transparencia que #70 (se persiste `estable` junto con `r2_test` para que la UI lo muestre, no se oculta detrás de un flag). Evita una regla adicional cuya interacción con `r2_test` habría que validar aparte, y es consistente: un caso de 1-solo-fold (aún menos confianza que "volátil") tampoco descalifica, por la misma lógica. |
| **Mecánica de selección** | Reemplaza `rmse_train_median` por `r2_test_median` como criterio de `idxmin`/`idxmax` por SKU en `predict.py` — traducción mecánica directa, sin cambiar la forma del código. Implementación queda para #89. |

**#88 cerrado**, listo para implementar en #89.

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

### Criterio walk-forward en `predict.py` — Issue #89 (sesión 2026-07-17)

Implementa la decisión de #88: `predict.py` elige el modelo ganador por SKU por mejor `r2_test` walk-forward real, no menor RMSE in-sample.

| Decisión | Definición |
|----------|-----------|
| **`WalkForwardResult` no trae `forecast_future`** (solo métricas) | Se resuelve con el mismo patrón ya usado en `eval_walkforward.py` (#86): walk-forward de los 3 candidatos para elegir el ganador, después un fit de referencia in-sample **solo del ganador** (`fit_rf_insample`/`fit_xgb_insample`/`fit_prophet_insample`, `steps_forecast=forecast_periods`) para conseguir el forecast real. |
| **Horizonte de fold = `forecast_periods`**, no el `EVAL_HORIZON` fijo de #70/#72 | Evalúa el modelo en la misma distancia que realmente se va a predecir en producción, no en un horizonte de diagnóstico ajeno a la tarea real. |
| **`predicciones.rmse`/`.r2` pasan a ser las métricas walk-forward del ganador**, no el ajuste in-sample del fit de referencia | Mismo principio de transparencia que #70 ("el r2_test real se expone al cliente") — `ResultadosService.GetResumenGlobal()` ya lee estas columnas como "R² promedio"; el número que ve el cliente ahora es honesto, no inflado por sobreajuste. Baja de escala como consecuencia esperada, no un bug. |
| **Volatilidad entre folds: informativa, no descalifica** | Mismo criterio que #88 — un modelo volátil con mejor `r2_test` sigue ganando sobre uno estable con peor `r2_test`. |
| **`elegir_ganador()` extraída como función pura**, con `ScoredModel(NamedTuple)` | Único punto testeable sin la pila ML completa — 4 tests unitarios (mayor r2 gana, ignora None/NaN, volátil puede ganar, fallback al primero). |

**Verificado end-to-end contra los 101 SKUs reales de grupo 201** (vía `docker cp` puntual al contenedor `etl` corriendo, sin rebuild, para no interferir con la corrida de #72 en simultáneo): 56/101 procesados (45 se descartan por historia insuficiente — gate preexistente, no introducido acá), **464s (~7.7 min) para 56 SKUs, ~8.3s/SKU promedio**. Todos ganados por PROPHET, consistente con su `median_r2_test` muy superior en este grupo (visto en #72: 0.36 vs 0.0 de RF/XGB). Confirma el criterio de aceptación del issue ("impacto en tiempo medido y documentado") — manejable para la ventana del cron de las 3 AM con el universo actual (~104 SKUs); el impacto sobre el universo ampliado que dejarían #73/#75 queda para #74.

**`/code-review` (8 ángulos) encontró 5 findings reales, corregidos antes de commitear:**
- **Bug real en frontend:** `PrediccionesTable.tsx` usaba chequeo falsy (`prediccion.r2 ? ... : '—'`) en vez de null-check — con `r2` walk-forward, `0` es un valor real y alcanzable, y se renderizaba como "sin dato". Corregido a `!= null` (también en `rmse`).
- **Gate de historia mínima incompleto** en los paths `--force-end`/`--include-current-period`: no sumaban `forecast_periods` como sí hace el path por defecto, dejando pasar SKUs que después no producían ningún fold walk-forward (pérdida total del forecast en vez de solo pérdida de precisión). Corregido.
- Fake de test incompleto (`rmse_test_median` faltante), tupla sin tipar (ahora `ScoredModel`), comentario impreciso sobre paridad con `eval_walkforward.py` — corregidos, bajo riesgo.
- **No se toca:** `ResultadosService.R2Promedio` cambia de escala (consecuencia esperada de #88/#70, no renderizado hoy en ningún componente de frontend) y el eje Y fijo `max:1` de `ModelPerformanceChart.tsx` (cosmético, Chart.js auto-extiende) — quedan documentados como seguimiento, no bloquean el cierre.

**#89 cerrado.**

---

### Aplicar criterio de elegibilidad — Issue #73 (sesión 2026-07-17)

**Hallazgo previo a implementar, resuelto por grilling:** el ganador por SKU que #72 persistió en `articulos_elegibilidad_econometrico` usaba el criterio viejo de selección (menor RMSE in-sample, el único que existía cuando #72 se diseñó el 2026-07-13) — pero #88/#89, decididos y cerrados *ese mismo día* después de #72, cambiaron el criterio real que usa `predict.py` a mejor `r2_test` walk-forward. Comparado empíricamente: **481/1476 SKUs (32.6%) tenían un modelo ganador distinto** entre ambos criterios — aplicar #73 directo sobre los datos de #72 hubiera decidido elegibilidad según un modelo que ni siquiera es el que corre en producción.

| Decisión | Definición |
|----------|-----------|
| **Recalcular el ganador con el criterio de #88/#89** antes de aplicar elegibilidad, no reusar el de #72 | Sin re-correr walk-forward — `catalogo_modelos` ya tiene las 3 métricas por (sku, modelo), la recomputación es una consulta sobre datos ya persistidos. |
| **Aplicar el criterio de #70 tal cual, sin excepciones** para los SKUs ya elegibles | Confirmado a pesar de que 42/95 SKUs actualmente elegibles (44%) no pasarían el criterio real — #70 ya decidió esto a conciencia (aflojó el umbral de 0.3 a ≥0 sabiendo que afectaba al grupo 201 actual). Un SKU no-elegible no queda sin nada: cae a lo que ya calcula Planilla (`rotacion_sugerida`) para el resto del catálogo. |
| **Alcance: solo base local**, no toca producción | Mismo patrón que #72 — la expansión real en el cron nocturno (104→~1219 SKUs) queda gateada detrás de #74 (medir performance en la VM real) y #75 (rollout gradual), como ya estaba planeado. |
| **`meses_historia` no se re-chequea por separado** | El piso de 24 meses de #70 ya queda cubierto indirectamente: hacen falta ≥8 trimestres para tener ≥2 folds evaluables (`estable` no-None), así que el gate de estabilidad ya excluye la historia insuficiente sin necesidad de un chequeo aparte. |

**Bug real encontrado y corregido antes de aplicar:** `estable` llega de MySQL como `NULL` para SKUs de 1 solo fold, pero pandas lo lee como `NaN` en una columna `float64` — y `bool(float('nan'))` es `True` en Python. El chequeo ingenuo `bool(ganador["estable"])` dejaba pasar como "estable" justo los casos que #70 dice que deben quedar afuera (1324 vs 1219 elegibles, detectado comparando el dry-run del script contra el cálculo manual en SQL). Corregido con `_estable_normalizado()` (None/NaN → None, saneado antes de persistir — mismo problema que ya documentó `_finite()` en #86).

**Segundo hallazgo, post-aplicación:** 6 SKUs quedaron `elegible=TRUE` del seed original de #71 sin ninguna medición real (`r2_test`/`n_folds` NULL — sin ventas reales, mismo tipo de SKU de prueba mal cargado ya visto antes). Revocados explícitamente (`revocar_elegibilidad_sin_medicion`) — elegibilidad sin evidencia no es una opción bajo el principio de #70.

**`/code-review` (2 ángulos) encontró 5 findings reales en el script, corregidos:** `n_folds` sin el mismo saneo NaN que `estable` (mismo riesgo de crash en pymysql), sin `ORDER BY`/dedup ante una re-corrida de la misma `version_modelo` (tabla histórica sin `UNIQUE`), división por cero si ningún SKU tiene `r2_test` válido, rowcount de la escritura nunca comparado contra lo esperado (podía ocultar un `#72` corrido solo con `EVAL_PERSIST_CATALOG`), cómputo duplicado de "huérfanos" contra dos snapshots potencialmente distintos.

**Hallazgo fuera de alcance, cargado como issue nuevo (#94, `blocker`):** `ResultadosService.cs` (`GetSkusElegiblesModelo`) sigue leyendo `grupos.aplica_modelo_econometrico` (el flag viejo) — `articulos_elegibilidad_econometrico` ni siquiera está mapeada en `EvalutiaDbContext`. No es un bug de #73, es un gap de #71 que #73 recién hace consecuente: sin este fix, desplegar la elegibilidad real a producción (futuro #75) dejaría el R² promedio y los pronósticos de `/api/resultados` filtrando contra el set viejo de ~104 SKUs, aunque `predicciones` tenga datos reales para ~1.219. Bloqueante para #75, no para #73.

**Resultado real, aplicado en base local** (`services/python-worker/ml/apply_elegibilidad.py`, `APPLY_VERSION=catalogo-completo-72 APPLY_PERSIST=true`):

| | Antes (seed #71) | Después (#73, criterio real) |
|---|---|---|
| Elegibles | 104 (grupo 201 completo) | **1.219** (82.6% de 1.476 evaluados) |
| Ganan elegibilidad | — | 1.166 |
| Pierden elegibilidad | — | 42 (de 95 medibles) |
| Revocados por falta de evidencia | — | 6 |

**#73 cerrado.**

---

### Medición de performance en la VM — Issue #74, sesión interrumpida por bug crítico (sesión 2026-07-17/18)

**Decisiones de grilling previas a tocar la VM:** medir contra los 1.219 SKUs reales elegibles (no los ~5.500 candidatos del alcance original, ya descartados por #73), sin deadline duro documentado para el cron, piloto chico primero (mismo patrón que #72/#87), `version_modelo` distinto (`medicion-74-piloto`) con limpieza después.

**Valor real de `PREDICT_PERIODS` confirmado por primera vez:** revisando `run_ofelia.sh`/`job_etl_diario.kjb` en la VM, el valor real de producción es **2** (no 4, el valor usado como estimación razonable al verificar #89 localmente — nunca se había confirmado contra el `.env` real hasta ahora).

**Acceso a la VM: `ssm-user` sin grupo `docker`** — todos los comandos de Docker necesitan `sudo` explícito (no se agregó al grupo `docker` esta sesión, se optó por `sudo` en cada comando en vez de tocar permisos del sistema).

**Bug crítico encontrado en el piloto (9 SKUs reales, 3m52s, ~26s/SKU):** los 9 SKUs procesados mostraron **r2=1.000000 exacto, sin excepción**, en 3 modelos distintos (RF/PROPHET/XGB). Verificado matemáticamente: `r2_score()` = (correlación de Pearson)², y con `horizon=forecast_periods=2` (el valor real recién confirmado), cualquier correlación entre dos series de 2 puntos no-constantes es **siempre ±1** — el cuadrado es siempre 1.0, sin importar la calidad real de la predicción. La decisión de #89 de usar `horizon=forecast_periods` (evaluar en la misma distancia que se predice de verdad, en vez del horizonte fijo de diagnóstico de #70/#72) era sólida en principio, pero no contempló que el valor real de producción pudiera ser tan chico como 2 — estadísticamente degenerado. **Cargado como issue nuevo #95 (blocker)**, con el diagnóstico completo y opciones de fix a evaluar (no prescriptivo, requiere diseño propio).

**Importante: los datos ya calculados de #72/#73 NO están afectados** — `eval_walkforward.py` usa `EVAL_HORIZON=4` (no 2) para su propia evaluación, así que los 1.219 SKUs elegibles que ya aplicó #73 vienen de una muestra de 4 puntos por fold, no degenerada. El bug es específico de la evaluación walk-forward *interna y en tiempo real* que `predict.py` (#89) hace con `horizon=forecast_periods`.

**Mitigación de emergencia aplicada, dado el cron real de esta noche (3 AM Montevideo, ventana de pocas horas al momento del hallazgo):**
1. Piloto corrido y limpiado (`DELETE FROM predicciones WHERE version_modelo='medicion-74-piloto'`, 18 filas — 9 SKUs × 2 períodos).
2. `services/python-worker/predict.py` **revertido en la VM** (`git checkout 0e580ef -- services/python-worker/predict.py`, el commit inmediato anterior a #89) + `docker compose build etl` + `up -d --force-recreate etl`. Confirmado con `grep -c elegir_ganador` (0 ocurrencias) que el contenedor corre la versión vieja.
3. **Este es un parche temporal sin commitear, solo en el working tree de la VM** — el próximo `git pull` + rebuild normal en la VM lo va a sobreescribir con el código roto de vuelta a menos que #95 se resuelva antes. Anotado explícitamente en #95 para no perderlo.

**Dato preliminar útil para #74 (no bloqueado por el bug):** la duración del walk-forward no depende de que el r2 resultante sea significativo — 3m52s para 9 SKUs reales (~26s/SKU) en hardware real de la VM es un primer dato de referencia, más lento que la extrapolación local de #89 (~8.3s/SKU) pero medido con solo 9 SKUs, no representativo todavía. **#74 queda abierto**, retomar junto con el fix de #95 (no tiene sentido medir performance de punta a punta con una metodología que #95 va a cambiar).

**Decisión explícita del usuario:** documentar todo y parar acá por esta noche, en vez de forzar un fix apurado contra el reloj del cron — ya se resolvió el riesgo principal (producción protegida para esta noche).

---

### Incidente real detectado la mañana siguiente: migración de #67 nunca aplicada a producción (sesión 2026-07-18)

Verificando el cron de la noche anterior (`jobs_historial`), se encontró que el paso `calc_planilla` había **fallado** (`(1146, "Table 'evalutia.configuracion_sistema' doesn't exist")`, job id 224, 0.31s). El `git pull` de anoche trajo el código de #67 (que ya lee `configuracion_sistema` para los umbrales de frecuencia), pero la migración SQL nunca se había aplicado a producción — solo se probó localmente en su momento.

**Impacto real (contenido, no catastrófico):** `run_calc_planilla.py` hace `DELETE`+`INSERT` de `planilla_ventas_calculada` recién al final de `main()` — el crash ocurrió en `cargar_configuracion()`, al principio, antes de tocar esa tabla. La Planilla no quedó vacía ni corrupta, pero el cliente vio los datos de la noche anterior (un día de atraso) en vez de los de hoy, hasta la intervención manual. El resto del pipeline (`calc_sugerencias`, `calc_stock_resumen`) corrió sin problema — falla contenida a un solo paso.

**Fix aplicado en el momento:**
1. `infra/sql/17-configuracion-sistema.sql` aplicada a producción (idempotente, sin cambio de comportamiento — sembró `tickets_bajo_max=2`/`tickets_alto_min=5`, los valores ya vigentes).
2. `run_calc_planilla.sh` corrido manualmente en el contenedor `etl` — **540.93s, 5.559 SKUs, 71.982 filas, frecuencia alta=707/media=486/baja=4365** (números idénticos a la verificación de producción de #64, mismo dataset real). Planilla refrescada con datos de hoy.

**Lección para el pipeline de deploy:** un `git pull` + rebuild de `etl` trae el código nuevo, pero **no aplica migraciones SQL automáticamente** — cada feature con migración (#67, y cualquier futura) necesita un paso explícito de `mysql ... < infra/sql/NN-*.sql` contra producción, separado del deploy de código. Ya había pasado algo similar con las migraciones 14/15 en la sesión del corte mTLS (documentado más arriba) — patrón recurrente, no un caso aislado.

---

### Fix del r2_test degenerado — Issue #95 (sesión 2026-07-18)

**Diseño, vía `/grill-me`:** de las dos opciones planteadas en el issue (desacoplar el horizonte de evaluación del horizonte de forecast real, vs. agrupar los puntos de test de todos los folds antes de calcular un solo r2), se eligió **desacoplar** — `predict.py` evalúa internamente con un horizonte fijo (`PREDICT_EVAL_HORIZON`, mismo default 4 que `EVAL_HORIZON` en `eval_walkforward.py`/#72), no con `forecast_periods` (2, el valor real de producción). El forecast final que se persiste sigue siendo a `forecast_periods` reales — solo cambia la vara con la que se *mide* la calidad del modelo. Se descartó agrupar folds porque hubiera perdido la señal de `estable` (necesita varianza *entre* folds) y arriesgado otra divergencia de metodología entre `eval_walkforward.py` y `predict.py` — el mismo tipo de problema que ya costó una sesión entera en #73.

| Decisión | Definición |
|----------|-----------|
| **`PREDICT_EVAL_HORIZON`**, constante propia de `predict.py`, no compartida con `eval_walkforward.py` | Mismo patrón ya establecido con `PREDICT_MAX_FOLDS`/`EVAL_MAX_FOLDS` — configurables por separado, mismo default, sin acoplar los dos scripts. |
| **Los 3 gates de historia mínima de #89 se corrigen a `max(forecast_periods, PREDICT_EVAL_HORIZON)`** | El walk-forward real ahora exige `len(train) >= PREDICT_EVAL_HORIZON + 2`, no `forecast_periods + 2` — sin este ajuste, el gate viejo hubiera dejado pasar SKUs que después no producen ningún fold. |
| **Guard en runtime si `PREDICT_EVAL_HORIZON < 3`** | Encontrado en `/code-review`: sin esto, alguien podría re-introducir el bug en silencio seteando la env var a un valor chico. Solo un `log.warning`, no bloquea la corrida (es un valor operativo, no algo que deba abortar el job). |
| **Comentario defensivo en `r2_score()`** (`ml/evaluate.py`) | Documenta la trampa matemática en la función compartida misma, no solo en este issue — para que no se repita en otro caller futuro. |
| **Test nuevo `test_evaluate.py`** | Fija la propiedad matemática (2 puntos → siempre 1.0, incluso con predicción en tendencia opuesta; 4 puntos → sí puede dar r2 bajo) y que el default de `PREDICT_EVAL_HORIZON` sea seguro (`>=3`) — encontrado como gap real en `/code-review` (nada pineaba el comportamiento corregido, un futuro "as I simplify this" podía reintroducir el bug sin que ningún test lo note). |

**Verificado localmente:** suite completa (4 archivos de test) pasa. Smoke test real contra la base local sincronizada con `--periods=2` (el valor real de producción) — los r2 ahora muestran variación real (0.066 a 1.000 en 10 SKUs reales), y **coinciden exactamente** con los valores ya vistos en la primera verificación de #89 (cuando por error se probó con `--periods=4`) — confirma que la evaluación ya no depende de `forecast_periods`, tal como se buscaba.

**Desplegado a producción (mismo día).** Parche de emergencia revertido (`git checkout HEAD -- services/python-worker/predict.py` — el archivo había quedado *staged* en la VM, un plano `git checkout --` sin `HEAD` no alcanzaba) + `git pull` + rebuild normal de `etl`. Piloto real (mismos 20 SKUs del piloto original de #74) re-corrido contra la VM: **r2 con variación real (0.066 a 0.687 en 4 SKUs)**, ya no 1.0 sistemático. Menos SKUs pasaron el filtro que en el piloto original (4 de 20 vs. 9 de 20) — efecto esperado del gate más estricto (`max(2,4)=4` en vez de `2`), no un problema. Datos de prueba limpiados (8 filas, `version_modelo='verificacion-95-vm'`).

**#95 cerrado.** #74 retoma desde acá con la metodología ya corregida — el próximo piloto/corrida completa mide contra el código real, no el buggy.

---

### Corrida completa de #74 e incidente real de la VM (sesión 2026-07-18, tarde)

**Decisiones de grilling:** medir directo contra los 1.219 SKUs completos (sin piloto adicional, ya validado en #95), correr ahora en horario diurno (la VM tenía margen de CPU en ese momento), `nohup`+background para sobrevivir un corte de sesión SSM (mismo riesgo ya documentado en #72), persistencia incremental de `predict.py` quedó como deuda técnica aparte (**issue #96**, no bloqueante para esta medición puntual).

**Bug operativo real, no de código:** el primer intento de lanzar la corrida falló silenciosamente — el comando armaba `--skus="$(cat /tmp/skus_1219_clean.txt)"` **dentro** de `docker compose exec -T etl bash -c '...'`, pero ese archivo vivía en el filesystem de la VM, no en el del contenedor (son filesystems separados). El `cat` fallo con "No such file", pero el `$(...)` vacío no abortó el comando — `predict.py` arrancó igual con `--skus=""`, probablemente procesando `ventas_historicas` sin ningún filtro. Ese proceso quedó corriendo sin que lo notáramos, corriendo en paralelo con el intento correcto (relanzado después de copiar el archivo con `docker compose cp`).

**Consecuencia:** ambos procesos corrieron ~3.5 horas en simultáneo en un `t3.medium` (4GB RAM) — el no filtrado, con `predict.py` acumulando todo en memoria antes de persistir (el mismo problema que ya documenta #96), probablemente agotó la RAM de la instancia. Efecto observado: **comprobación de estado de EC2 en "2/3 aprobadas"**, CPU baja (2.31%, descartando saturación de CPU) pero el agente de SSM dejó de responder por completo (sesiones que "conectan" a nivel AWS pero la terminal interactiva queda congelada, después ni siquiera se pueden iniciar sesiones nuevas). **Se resolvió con un reinicio de la instancia** (EC2 → Acciones → Estado de la instancia → Reiniciar) — los contenedores volvieron solos (`restart: unless-stopped`), sin necesidad de reconstruir nada.

**Resultado real, rescatado de `jobs_historial` después del reinicio** (el job había terminado ANTES de que hiciera falta reiniciar — el problema era la sesión/agente, no el proceso en sí):

| Job | version_modelo | Estado | Inicio | Fin | Duración |
|-----|-----------------|--------|--------|-----|----------|
| 229 | `medicion-74` (correcto, 1.219 SKUs reales) | **exitoso** | 15:25:02 | 18:52:09 | **3h27m** |
| 230 | (huérfano, `--skus` vacío) | fallido | 15:27:16 | 18:47:58 | 3h20m |

**3h27m para el volumen real (1.219 SKUs) entra cómodo en la ventana del cron** — arrancando a las 3 AM terminaría ~6:30 AM, muy por debajo de cualquier horario de apertura del cliente. Responde la pregunta central de #74. El desglose fino (SKUs procesados exactos, por modelo) quedó pendiente de extraer — la sesión se volvió inestable para pegar comandos largos, se pausó antes de forzarlo.

**Desglose fino, extraído con `JSON_EXTRACT` (evitando el array de warnings, >50k caracteres):**

| Job | Estado | Duración | SKUs pedidos | **SKUs procesados** | Modelos ganadores |
|-----|--------|----------|---------------|----------------------|---------------------|
| 229 (`medicion-74`) | exitoso | 12427s (3h27m) | 1.219 | **58 (4.8%)** | PROPHET 57, XGB 1 |

Confirmado contra `predicciones` directo: 57 SKUs×2 filas (PROPHET) + 1 SKU×2 filas (XGB) = 116 filas, `avg_r2` 0.376/0.392 — valores razonables, no degenerados, confirma que el fix de #95 funciona bien a escala real también.

**Hallazgo importante, más allá de la performance:** de los 1.219 SKUs que #73 marcó `elegible=TRUE`, **solo 58 (4.8%) tienen suficiente historia real para que `predict.py` los procese** — el gate de `predict.py` exige 12 trimestres (3 años), más estricto que el piso de #73/#70 (~8-9 trimestres para 2 folds evaluables). Esto ya se había insinuado en el piloto chico de #95 (4/20 = 20%, muestra no representativa) pero ahora queda cuantificado con el volumen real. El "salto de 104 a 1.219 SKUs elegibles" que documentó #73 es la cifra correcta para la tabla de elegibilidad, pero el impacto *práctico* inmediato en cuántos SKUs nuevos reciben forecast real es mucho más chico (104 + 58 ≈ 162, no 1.219) hasta que haya más historia acumulada. No se abre issue nuevo por esto — es información para #75 (rollout), no un bug: cuantos más meses pasen, más SKUs cruzan el piso de 3 años naturalmente.

**Limpieza de producción:** 116 filas de `medicion-74` borradas de `predicciones`. El job huérfano (230, `--skus` vacío) nunca llegó a persistir nada (crash antes de `upsert_predicciones`, `skus_procesados`/`modelos` quedaron `NULL` en su `detalle`) — nada que limpiar ahí. Se encontró de paso un `version_modelo='mvp-002'` con 76 SKUs reales (fechas de predicción 2026-06-19 a 2026-09-19) que no es de esta sesión — no se toca, queda fuera de alcance.

**Sin plan de mitigación necesario** — 3h27m tiene margen enorme contra cualquier ventana nocturna razonable, y el volumen real que efectivamente se procesa (58, no 1.219) es aún menor de lo que preocupaba el alcance original del issue.

**Lección para la próxima corrida larga contra la VM:** cuando se arma un comando con `$(cat archivo)` dentro de `docker compose exec ... bash -c '...'`, el archivo tiene que existir **dentro** del contenedor (copiarlo con `docker compose cp` primero), no alcanza con que exista en el host de la VM. Y verificar SIEMPRE que el proceso anterior murió de verdad (`ps aux` en el host Y dentro del contenedor) antes de asumir que un reintento arrancó limpio.

**#74 cerrado.**

---

### ResultadosService lee la tabla de elegibilidad real — Issue #94 (sesión 2026-07-18)

**Decisiones de grilling (dentro de #75):** #94 se resuelve **antes** de desplegar la elegibilidad real de #73 a producción (evita el bug silencioso que motivó el issue), sin rollout gradual (el volumen real que reveló #74 es chico, 58 SKUs nuevos), y la elegibilidad se porta directo desde los datos ya calculados localmente (no se re-corre walk-forward contra producción).

**Fix:** nuevo modelo EF Core `ArticuloElegibilidadEconometrico` mapeado a `articulos_elegibilidad_econometrico` (mismo patrón exacto que `ConfiguracionSistema` de #67 — Model + `DbSet` + bloque en `OnModelCreating`). `GetSkusElegiblesModelo()` en `ResultadosService.cs` pasa de un `JOIN` contra `grupos.aplica_modelo_econometrico` (flag muerto desde #71) a filtrar directo `articulos_elegibilidad_econometrico.elegible` — el mismo criterio que `get_skus_modelo.py` ya usa desde #71. Confirmado por grep que `Grupo.AplicaModeloEconometrico` no tiene ningún otro lector en el backend — no queda un segundo call site roto.

**`/code-review` encontró 3 findings reales, corregidos:**
- Los tests sembraban `articulos_elegibilidad_econometrico`/`predicciones` para SKUs que nunca se insertaban en `articulos` — la tabla real tiene FK (`fk_elegibilidad_articulo`), pero EF InMemory no la valida, así que los tests pasaban afirmando un estado imposible contra MySQL real. Corregido sembrando `Articulos` también.
- `GetStockAnalysis()` (el segundo consumidor real de `GetSkusElegiblesModelo()`, vía `PronosticoProximoTrimestre`) no tenía ningún test — solo se cubría `GetResumenGlobal()`. Agregado.
- `MesesHistoria` estaba tipado `short?` para una columna `SMALLINT UNSIGNED` — rompe la convención ya establecida en el codebase (`VentasMensuales` mapea el mismo tipo MySQL a `ushort`). Corregido a `ushort?`.

**Hallazgo operativo, no de código:** esta Mac tenía el mismo problema de #91 (solo runtime net10 instalado, tests de C# no podían correr localmente) — resuelto de forma **persistente** esta vez (a diferencia del scaffold temporal de #91): runtime net8 descargado e instalado con un `sudo cp` puntual dentro de la instalación existente de `dotnet`, en vez de un `DOTNET_ROOT` combinado con symlinks (que no funcionó — el resolver de .NET no lo respetó). Verificado con `dotnet --list-runtimes`: net8.0.29 y net10.0.5 conviven sin conflicto. Este problema no debería repetirse en sesiones futuras en esta máquina.

**Verificado:** build limpio, **16/16 tests pasan** (los 12 de #91 + 4 nuevos de #94), corridos localmente de punta a punta (no solo leídos).

**#94 cerrado.**

---

### Deploy final de #75 — elegibilidad real en producción (sesión 2026-07-18)

**Script de sync** (`scripts/sync_elegibilidad_73_a_produccion.sql`): porta los 1.476 SKUs ya evaluados localmente (walk-forward real de #72, criterio de #70 aplicado por #73) directo a `articulos_elegibilidad_econometrico` en producción — `INSERT ... ON DUPLICATE KEY UPDATE`, sin re-correr walk-forward contra la VM (misma copia sincronizada de ventas reales, resultado equivalente). Verificado localmente antes de tocar producción: idempotente (1219/1482, igual antes y después de aplicarlo).

**Desplegado en orden:**
1. `git pull` en la VM.
2. `webapi` reconstruido y recreado — trae de una vez el fix de #94 **y** el backend de #67/#91, que nunca se habían desplegado como contenedor (solo se había aplicado la migración SQL de #67 esa misma mañana).
3. Script de elegibilidad aplicado contra producción — **confirmado 1219/1482 elegibles, idéntico a la base local.**
4. `get_skus_modelo.py` confirmado en producción: ya devuelve los 1.219 SKUs reales (antes devolvía 104).

**Decisión explícita:** no se disparó `run_predict.sh` manualmente esta noche — se deja que lo haga el cron natural de las 3 AM (ya validado end-to-end en #74, sin necesidad de otra intervención manual después de una noche ya larga con el incidente de RAM). Verificación de las predicciones reales generadas queda para la próxima sesión, revisando `jobs_historial` del cron de esta noche.

**#75 sigue abierto** — pendiente confirmar mañana que el cron de las 3 AM generó predicciones reales para los SKUs recién elegibles (criterio de aceptación del issue: "predicciones generadas y verificadas en producción"), antes de cerrar.

---

### Persistencia incremental en predict.py (Issue #96, sesión 2026-07-18/19)

Mismo anti-patrón que tenía `eval_walkforward.py` antes del fix de #72, encontrado durante el grilling de #74: `predict.py` acumulaba todas las filas de `predicciones` en `rows_buffer` (memoria) y recién las persistía con `upsert_predicciones()` una sola vez, al final de `main()`. Con el catálogo ampliado de #73/#75 (104 a 1.219 SKUs elegibles) y el walk-forward más pesado por SKU de #89/#95, una corrida nocturna real que se corte a mitad de camino perdería el 100% del progreso, no solo lo que faltaba.

**Fix, mismo patrón que #72:** `PREDICT_PERSIST_BATCH_SIZE` (misma convención de nombre que `EVAL_PERSIST_BATCH_SIZE`, default 50) controla cada cuántos SKUs *iterados* (no solo procesados con éxito, también los omitidos/fallidos cuentan para la cadencia) se hace flush de `rows_buffer` contra `predicciones`, vía una función interna `_flush_predicciones()` con `nonlocal` sobre `rows_buffer`/`inserted`. Cola final después del loop, igual que `eval_walkforward.py`. La lógica de `jobs_historial` (`insert_job_start`/`update_job_end`, una sola vez por job completo) no se tocó, tal como pedía el issue.

| Decisión | Definición |
|----------|-----------|
| **Cadencia sobre `n_skus_iterados`, no sobre `processed`** | El `finally` del try/except por SKU incrementa el contador y chequea el módulo pase lo que pase (éxito, omitido por poca historia, o excepción). Un SKU que no genera filas igual "cuenta" para la cadencia, mismo criterio que `n_skus_procesados` en `eval_walkforward.py`. |
| **Log de progreso movido adentro de `_flush_predicciones()`** | Encontrado en el self-review: la primera versión del fix solo logueaba `[PROGRESS]` en el flush periódico dentro del loop, no en la cola final (a diferencia de `eval_walkforward.py`, donde el `print` de progreso vive dentro de `_flush()` mismo y por lo tanto corre en cada llamada, periódica y final). Corregido para que la última tanda (menor a `PREDICT_PERSIST_BATCH_SIZE`) también quede logueada, igual que el patrón original de #72. |
| **`rows_buffer` se vacía por completo en cada flush, sin retener historial** | A diferencia de `eval_walkforward.py` (que arma `catalog_rows`/`rows` aparte para el resumen final), `predict.py` ya tenía `summary_rows` como lista separada para el resumen. `rows_buffer` no necesita sobrevivir al flush. |

**Test nuevo, `test_flush_incremental_predicciones_no_espera_al_final_del_loop()`** (`services/python-worker/tests/test_predict.py`): con `PREDICT_PERSIST_BATCH_SIZE=3` y 7 SKUs fake, mockeando `get_engine`/`insert_job_start`/`update_job_end`/`upsert_predicciones`/`load_series_by_sku`/`fit_rf_with_walkforward`/`fit_xgb_with_walkforward`/`fit_rf_insample`/`fit_xgb_insample` (nada toca MySQL ni entrena modelos reales), corre `predict.main()` completo y verifica que `upsert_predicciones` se invoca 3 veces (cadencia `[6, 6, 2]` filas) en vez de una sola vez al final, y que el total persistido (14 filas = 7 SKUs × 2 períodos) es idéntico al que hubiera dado un único batch final. Mismo patrón de verificación que pedía el criterio de aceptación del issue, inspirado en cómo #72 verificó su propio fix.

**Verificado:** suite completa (`test_predict`, `test_evaluate`, `test_eval_walkforward`, `test_apply_elegibilidad`) corrida dentro del contenedor `etl` (`/app/services/python-worker`, no el `python-worker` vacío, ver nota de infraestructura en `docs/agents/`), las 4 pasan. El log real de la corrida del test nuevo confirma la cadencia esperada: tres líneas `[PROGRESS]` (3/7, 6/7 y 7/7 SKUs, con predicciones acumuladas 6, 12 y 14 respectivamente); la última línea solo aparece después del fix del log movido a `_flush_predicciones()`.

**#96 cerrado.**

---

### Elimina el fit de referencia duplicado en catalogo_modelos — Issue #92 (sesión 2026-07-19)

Encontrado por `/code-review` durante el smoke test de #86: `_build_catalog_row()` en `eval_walkforward.py` hacía un fit *aparte*, sobre la serie completa, solo para sacar `hiperparametros`/`features`/`r2_train`/`rmse_train` "limpios" para la tabla diagnóstica `catalogo_modelos` — encima de los folds que el walk-forward ya había corrido momentos antes para ese mismo SKU/modelo. Confirmado empíricamente en #86: 4 corridas MCMC de Prophet por SKU (3 folds + 1 fit de referencia extra) en vez de 3.

**Decisiones de grilling:**

| Decisión | Definición |
|----------|-----------|
| **Aplica a los 3 modelos (RF/XGB/Prophet), no solo a Prophet** | `_aggregate_walkforward` ya es un único código compartido por los 3 vía `fit_rf_with_walkforward`/`fit_xgb_with_walkforward`/`fit_prophet_with_walkforward` — semántica pareja (misma fuente de `r2_train`/`hiperparametros` para los 3) vale más que ahorrar unos ms extra solo en RF/XGB, que ya eran baratos. |
| **`WalkForwardResult` retiene el `ModelResult` del último fold exitoso** | Nuevo campo `last_fold_result` (default `None`, agregado al final del dataclass — no rompe construcciones existentes). `_walk_forward_split` siempre devuelve folds en orden ascendente de ventana de entrenamiento, así que el último fold que llega a `r2_tests.append(...)` en el loop de `_aggregate_walkforward` es, por construcción, el de mayor ventana entre los que tuvieron éxito (verificado con test que fuerza el último fold de la lista a fallar). |
| **`_REFERENCE_FITTERS` se elimina por completo, sin fallback** | `_build_catalog_row` solo se llama cuando `wf_result` no es `None`, lo que exige ≥1 fold exitoso — `last_fold_result` está garantizado no-`None` en ese caso. No hay caso alcanzable que necesite un fit de respaldo. |
| **`mae_train` cambia de dirección de reindex** | Antes: `ref.holdout_pred.reindex(s.index)` (seguro cuando `ref` venía de un fit sobre la serie completa). Ahora `ref` es el último fold, cuya ventana excluye los últimos `horizon` períodos (`EVAL_HORIZON=4`, ~1 año en `FREQ=QS`) — reindexar hacia arriba metería NaN. Se invirtió: `s.reindex(ref.holdout_pred.index)`, y se reusa `_mae()` de `ml/models.py` en vez de reimplementarlo inline (hallazgo de `/code-review`, ángulo Reuse). |
| **Semántica de `r2_train`/`rmse_train`/`hiperparametros`/`features` cambia** | Antes: fit sobre la serie completa. Ahora: fit del último fold walk-forward (ventana algo menor). Aceptado porque `catalogo_modelos` es tabla puramente diagnóstica — confirmado que ningún código de producción la lee (ni `apply_elegibilidad.py`, que solo usa `r2_test`/`estable`/`n_folds`, ni backend, ni frontend). |

**`/code-review` (8 ángulos) no encontró bugs de correctness** — 3 ángulos independientes verificaron por separado que `last_fold_result` es no-`None` siempre que se necesita, que el reindex nuevo no introduce NaN, y que `predict.py` (que también usa `fit_*_with_walkforward` pero nunca lee `last_fold_result`) queda intacto. 2 findings aplicados: reusar `_mae()` en vez de reimplementarlo, y reforzar el docstring de `last_fold_result` en `ml/models.py` para dejar explícito que sigue siendo un fit de fold (ventana incompleta) y que `.forecast` no debe usarse como pronóstico real de producción — hallazgo del ángulo Altitude, pensando en un futuro consumidor de `WalkForwardResult` que no fuera `eval_walkforward.py`.

**Medición real (criterio de aceptación del issue), benchmark aislado sobre 10 SKUs con historia larga (40 trimestres) para forzar que Prophet corra de verdad:**

| | Antes (#86) | Después (#92) |
|---|---|---|
| Walk-forward (igual en ambas versiones) | 230.96s | 230.96s |
| Fit de referencia extra | 51.14s | 0s (eliminado) |
| **Total** | **282.10s** | **230.96s** |

**18.1% de reducción** en el tiempo total de construir `catalogo_modelos` para este lote. Un SKU individual (C00204/PROPHET) mostró 38.16s de fit duplicado eliminado por sí solo — el caso exacto que motivó el issue.

**Verificado:** suite completa (`test_predict`, `test_evaluate`, `test_eval_walkforward`, `test_apply_elegibilidad`) corrida en el contenedor `etl`, las 4 pasan. 3 tests nuevos en `test_eval_walkforward.py` (TDD): que `last_fold_result` captura el último fold exitoso, que ignora folds que fallan al final de la lista, y que `_build_catalog_row` usa `last_fold_result` sin re-fit y calcula `mae_train` correctamente contra la ventana del fold.

**#92 cerrado.**

---

### Re-scope de #76 + hallazgo crítico #97: r2_test degenerado en 96% de catalogo_modelos (sesión 2026-07-19)

**Re-scope de #76:** la mitad original sobre calibración de pesos del ensemble quedó obsoleta (confirmado por grep: cero referencias a ensemble/pesos en `predict.py`, #88/#89 reemplazaron el blending por selección winner-take-all). Issue editado para dejar solo los 3 casos borde, re-anclados a la arquitectura actual, con dependencia de #68 corregida (walk-forward real de #89/#95 ya cubre lo que #68 pedía) y estimación bajada de 4-6h a 3-4h.

**Metodología para identificar SKUs candidatos:** en vez de derivar detección de "baja frecuencia"/"quiebre" desde cero en Python, se usó `planilla_ventas_calculada` (dominio de planilla, `estado_mes`/`tickets_mes` ya validados contra el Excel del cliente en #36-39) para encontrar candidatos reales:

| Caso | Criterio de selección | Candidatos con ≥6 trimestres (mínimo para walk-forward) |
|------|------------------------|------------------------------------------------------------|
| 1. Baja frecuencia | `tickets_mes` entre 1-3 en ≥50% de los meses, con ventas reales >0 | 9 SKUs (ej. C00702, E00342, C00401) |
| 2. Quiebre de stock frecuente | `estado_mes IN ('quiebre_parcial','sin_stock')` en ≥30-40% de los meses, con ventas reales | 12 SKUs (ej. I01236, I01673, I01943) |
| 3. <12 meses de historia | `meses_historia < 12` en `ventas_historicas` | 15 SKUs, **todos con exactamente 1 mes de historia** |

**Caso 3 resuelto trivialmente:** los 15 candidatos locales tienen 1 mes de historia -- muy por debajo del mínimo de `_walk_forward_split` (necesita ≥6 trimestres). Walk-forward ni siquiera arranca (0 folds), y `predict.py`'s `min_history_periods` (12 trimestres en producción, confirmado en #74) los excluye de entrada. No hace falta tratamiento especial -- el gate existente ya los maneja. Limitación anotada: localmente no hay SKUs entre 30-40 meses (cerca del gate real de producción de 36 meses) para auditar ese borde específico; la distribución local se concentra en ~25 meses de historia.

**Casos 1 y 2 destaparon un hallazgo mucho más grande que el propio alcance de #76:** al correr walk-forward real sobre los 21 SKUs candidatos (`EVAL_VERSION=audit-76`), **el 100% de las 42 filas resultantes (21 SKUs × RF/XGB) dieron `r2_test` exactamente `0.0`**, con `n_obs_train=1` en todas. Para descartar que fuera un artefacto del lote curado, se revisó la distribución completa de `catalogo_modelos` sobre las 3010 filas de corridas reales previas (excluyendo el lote de auditoría y los benchmarks de #92):

| Métrica | Valor sobre 3010 filas reales |
|---|---|
| `r2_test` exactamente 0.0 | 83.3% |
| `r2_test` exactamente 1.0 | 12.7% |
| **Total degenerado (0.0 o 1.0 exacto)** | **96.0%** |
| `n_obs_train` ≤ 1 | 95.1% (mediana global = 1) |

**El patrón no es específico de los casos borde de #76 -- es sistémico en casi todo el catálogo.** Mecanismo (hipótesis con evidencia fuerte, no 100% confirmada): `EVAL_LAGS=8` consume 8 períodos como features de lag; con el tamaño de fold que genera `_walk_forward_split` (ventana expanding, folds tempranos chicos), a la mayoría les queda ~1 fila útil de entrenamiento tras restar los lags -- el modelo no tiene de qué aprender, predice casi una constante, y `r2_score` (Pearson² con manejo de varianza-cero desde #95) satura en exactamente 0.0 o 1.0 en vez de dar un valor intermedio informativo. Mismo síntoma que #95 (r2 en un valor exacto sospechoso) pero causa distinta (lags devorando el training window, no el horizonte de test) -- **abierto como issue separado, #97, crítico**, porque `catalogo_modelos` es la fuente exacta que #73 usó para calcular los 1219 SKUs elegibles ya desplegados a producción en #75: el criterio `r2_test>=0 AND estable` deja pasar tanto 0.0 como 1.0 exactos sin distinguirlos de un ajuste real.

**Consecuencia para #76:** con la métrica de referencia (`r2_test`) contaminada en ~96% del catálogo, no se puede dar una "decisión documentada" confiable sobre si los casos borde necesitan tratamiento especial en el criterio de #70 -- cualquier conclusión hoy estaría midiendo ruido, no señal real, para prácticamente cualquier SKU, no solo los de baja frecuencia/quiebre. **#76 queda bloqueado por #97**, no cerrado: su criterio de aceptación original solo se puede cumplir de forma honesta una vez que #97 tenga un fix y se pueda re-correr el mismo lote de 21 SKUs con `r2_test` confiable.

**#76 permanece abierto (bloqueado por #97, no cerrado). #97 abierto, crítico, ready-for-human -- diagnóstico completo, remedio sin decidir (candidato a `/grill-me` antes de `/implement`, mismo patrón que #95).**

---

### Fix de #97: filtro de folds degenerados en `_aggregate_walkforward` (sesión 2026-07-19)

**Decisiones de grilling:** filtrar folds degenerados dentro de `_aggregate_walkforward` (afecta uniformemente `eval_walkforward.py` y `predict.py`, que comparten la función) en vez de bajar `EVAL_LAGS` o esconder el síntoma aguas abajo en `apply_elegibilidad.py`. Umbral inicial: `n_train_rows >= lags`. Medición de impacto: re-correr local + `apply_elegibilidad.py` en dry-run, diff contra los 1219 SKUs ya elegibles en producción.

**3 experimentos empíricos antes de fijar el umbral** (60 SKUs elegibles reales, muestra aleatoria):

| Variante | Cobertura (SKUs con algún resultado) | r2_test |
|---|---|---|
| `n_train_rows>=lags` (lags=8 sin tocar) | 2/60 (3.3%) | Sano donde sobrevive (mediana 0.31) |
| `n_train_rows>=lags/2` | 2/60 (3.3%) | Sin cambio -- el piso no era el cuello de botella real |
| `lags=4` (mitad) | 19/60 (31.7%) | RF/XGB vuelven a degenerar en 0.0 exacto (89.5% con 1 solo fold evaluable) |

Bajar `lags` sube la cobertura pero no arregla la señal -- solo mueve el mismo problema a más SKUs. Se descartó tocar `lags` y se shippeó la variante 1 (umbral sin modificar `lags`), aceptando la caída de cobertura como consecuencia honesta, con la pregunta "¿RF/XGB necesitan otro enfoque de features para historias cortas?" como seguimiento aparte (conectado al caso "baja frecuencia" de #76).

**`/code-review` (8 ángulos) encontró un bug real, no solo un matiz:** el piso `n_train_rows>=lags` viene de cómo RF/XGB construyen features de lag (`_build_lag_month_trend`), pero `fit_prophet_insample` recibe `lags` y **nunca lo usa para features** -- solo chequea internamente `len(tr)>=min_needed` (8 o 12), independiente de `lags`. Aplicarle el mismo piso a Prophet descartaba folds válidos sin ninguna base real. **Fix aplicado:** el chequeo ahora es `if name != "PROPHET" and n_train_rows < lags: continue`, y se movió ANTES de `fit_one_fold()` (evita el fit caro para folds ya sabidos degenerados, mismo espíritu que #92) -- Prophet corre su propio gate interno sin pasar por este filtro. Test nuevo (`test_filtro_de_n_train_rows_no_aplica_a_prophet`) fija el comportamiento. Otros findings del review (documentación de esta decisión, comentario duplicado con `r2_score()`, tests que podrían compartir fixtures) quedaron anotados pero no bloquearon el fix -- son cleanup menor, no correctness.

**Medición de impacto real (no extrapolada), re-corrida completa de los 1219 SKUs actualmente elegibles en producción, con el fix corregido:**

- Corrida completa: **40 minutos** (mucho más rápido que la estimación inicial de ~2-3h, porque la mayoría de los folds ahora se descartan ANTES del fit caro).
- **Solo 20/1219 SKUs (1.6%) producen algún resultado de walk-forward real** (Prophet: 20 SKUs, todos estables, 0 volátiles, 0 con 1-solo-fold; RF: 15 SKUs; XGB: 15 SKUs -- se solapan, 20 SKUs distintos en total).
- `apply_elegibilidad.py` en dry-run sobre esos 20: **14 pasan el criterio real (`r2_test>=0 AND estable`), 6 lo pierden.**
- Los otros **1199 SKUs quedan revocados por no tener ninguna medición real** (todos sus folds, en los 3 modelos, degenerados).

**Resultado final: de 1219 SKUs "elegibles" hoy en producción, solo 14 (1.1%) tienen señal genuina bajo la métrica corregida.** Los otros 1205 estaban marcados elegibles sobre `r2_test` que en realidad no medía nada -- exactamente la preocupación que motivó abrir #97.

**Verificado:** suite completa (`test_predict`, `test_evaluate`, `test_eval_walkforward` con 3 tests nuevos, `test_apply_elegibilidad`) corrida en el contenedor `etl`, las 4 pasan.

**Alcance explícito de este fix, no confundir con algo más amplio:** esto es un parche de correctness puntual (filtra señal falsa), NO una solución al problema de fondo (RF/XGB necesitan mucha más historia de la que tiene la mayoría del catálogo real para producir señal confiable con `lags=8`). Ese problema de fondo queda abierto, sin resolver, y conectado al caso "baja frecuencia" de #76.

**Pendiente, decisión de negocio, no técnica:** si desplegar esta corrección a producción (bajaría la elegibilidad real de 1219 a 14 SKUs) queda fuera del alcance de #97 -- mismo patrón que #73→#75 (medir/decidir primero, desplegar como paso separado y explícito). No se tocó producción en esta sesión.

**#97: diagnóstico, fix y medición de impacto completos localmente. Deploy a producción pendiente de decisión aparte.**

---

### Cierre real de #76: conclusión sobre casos borde (sesión 2026-07-19, con r2_test ya confiable)

Con #97 resuelto, se re-corrieron los casos borde de #76. **Los 21 candidatos originales (≥6 trimestres, el piso mínimo de `_walk_forward_split`) dieron 0 resultados** -- el fix de #97 exige mucha más historia de la que esos candidatos tenían. Se buscaron candidatos nuevos combinando el patrón de baja frecuencia/quiebre CON suficiente historia (≥16 trimestres) para tener chance de sobrevivir el filtro: solo **5 candidatos de baja frecuencia y 2 de quiebre** cumplen ambas condiciones en todo el catálogo local -- un hallazgo en sí mismo (SKUs con patrón de baja frecuencia/quiebre Y suficiente historia para evaluar son raros).

**Resultado real (7 SKUs, criterio real de #70 aplicado al modelo ganador de cada uno):**

| SKU | Caso | Modelo ganador | r2_test | estable | Elegible |
|---|---|---|---|---|---|
| E00204 | baja frecuencia | PROPHET | 0.261 | No | ❌ |
| E00428 | baja frecuencia | XGB | 0.982 | **No** | ❌ |
| E00678 | baja frecuencia | XGB | 0.815 | **Sí** | ✅ |
| I00724 | quiebre | PROPHET | 0.774 | No | ❌ |
| I00963 | baja frecuencia | PROPHET | 0.894 | No | ❌ |
| I01089 | baja frecuencia | XGB | 0.490 | N/A (1 fold) | ❌ |
| I01303 | quiebre | PROPHET | 0.632 | No | ❌ |

**Solo 1/7 (14%) queda elegible**, contra 70% (14/20) en la población general con historia suficiente medida en #97 -- los casos borde de #76 tienen una tasa de elegibilidad real mucho menor que el resto del catálogo. El caso E00428 es el más elocuente: r2_test=0.982 (casi perfecto) pero `estable=False` -- el criterio de `estable` ya lo descarta correctamente, exactamente el escenario que preocupaba el alcance original de #76 ("¿hay escenarios donde un modelo mal calibrado domina la predicción?").

**Decisión documentada (criterio de aceptación de #76):** no hace falta agregar una exclusión especial para baja frecuencia/quiebre en el criterio de #70. El chequeo de `estable` ya existente cumple ese rol -- descarta 6 de los 7 casos borde probados, incluyendo el caso de r2 engañosamente alto. Combinado con el fix de #97 (que ya excluye la mayoría de estos SKUs por falta de historia suficiente antes de siquiera llegar a evaluarlos), el criterio actual queda protegido en dos capas: primero por datos insuficientes, después por inestabilidad. **Caso 3** (<12 meses de historia) ya se había resuelto trivial en la primera pasada de #76 -- sin cambios.

**#76 cerrado. Los 3 casos borde quedan reportados; ninguno requiere tratamiento especial nuevo en #70.**

---

### Cierre de #75: cron real confirmado en producción (sesión 2026-07-20)

Acceso a la VM recuperado (clave SSH nueva, autorizada por el socio -- ver nota de seguridad abajo). Verificado contra `jobs_historial`/`predicciones` reales:

**Job 231** (`tipo_job='forecast'`, `version='mvp-001'`): `2026-07-19 03:17:58` a `03:22:08` (4 min), `estado='exitoso'`. `skus_procesados=20` de los 1219 elegibles -- el resto quedó fuera con warnings explícitos `"omitido por pocos datos (N periodos tras aplicar force-end)"`, consistente con el hallazgo de #97 (la mayoría del catálogo elegible no tiene historia suficiente para generar una predicción real, más allá de si pasa el criterio de elegibilidad).

**Confirmado en `predicciones`:** 40 filas reales, 20 SKUs distintos, 2 modelos (`PROPHET`/`XGB`), r2 en rango razonable (0.06-0.69, sin valores degenerados visibles en esta muestra). Cumple el criterio de aceptación de #75 ("predicciones generadas y verificadas en producción").

**Nota de seguridad, acceso nuevo a la VM:** el socio generó una clave SSH (ED25519) como alternativa al flujo de sesión SSM usado el resto de la sesión. Se recibió inicialmente en `~/Downloads` (carpeta sincronizada a la nube) con permisos `0644` -- movida a `~/.ssh/` con permisos `600` antes de usarla, y borradas las copias de `Downloads`. `ubuntu` (el usuario de esta clave) está en el grupo `docker` directo (no hace falta `sudo` para comandos docker, a diferencia de `ssm-user`) pero SÍ hace falta `sudo` para leer `/opt/evalutia/.env` (propiedad de `ssm-user`).

**#75 cerrado.**

---

### Deploy del fix de #97 a producción (sesión 2026-07-20)

Decisión explícita del usuario: desplegar la elegibilidad real corregida ahora ("por ahora es lo que tenemos, después se va mejorando en base a trabajo y esfuerzo"), aceptando la caída de 1219 a 14 SKUs como el número honesto actual.

**Hallazgo adicional antes de desplegar:** `revocar_elegibilidad_sin_medicion` (de #73) solo tocaba `elegible`, dejando `r2_test`/`estable`/`n_folds` con el valor VIEJO (potencialmente degenerado, de antes del fix de #97) en SKUs sin ninguna medición real hoy. Corregido para dejarlos en `NULL` -- encontrado al generar el script de sync, antes de tocar producción (ver commit `4e6a131`).

**Desplegado:**
1. Acceso a la VM recuperado vía clave SSH nueva (autorizada por el socio, ver nota de seguridad en el cierre de #75 más arriba).
2. `git pull` en la VM vía `sudo -u ssm-user` (el usuario `ubuntu` de la clave nueva no tenía el deploy key de GitHub configurado; `ssm-user` sí).
3. `docker compose build etl python-worker && up -d --force-recreate etl python-worker` -- ambos servicios bakean el código de `ml/models.py`/`predict.py`/`eval_walkforward.py` por separado (Dockerfiles distintos, `services/etl/Dockerfile` y `services/python-worker/Dockerfile`), los dos necesitaban rebuild.
4. `scripts/sync_elegibilidad_97_a_produccion.sql` aplicado directo contra producción (mismo patrón que #75: `docker compose exec mysql` con redirección del lado del host, no dentro del `bash -c` del contenedor).

**Verificado en producción:** `articulos_elegibilidad_econometrico` -- 1482 filas totales, **14 elegibles**, valores idénticos a la medición local (r2_test 0.016-0.69, todos `estable=TRUE`). Los 1205 restantes revocados, con `r2_test`/`estable`/`n_folds` en `NULL` (no valores viejos engañosos). Todos los servicios (`etl`, `python-worker`, `webapi`, `mysql`, etc.) saludables tras el redeploy.

**#97 desplegado a producción. La elegibilidad real hoy es 14 SKUs -- crecerá con más historia de ventas acumulada y, eventualmente, con trabajo futuro sobre el enfoque de features de RF/XGB para historias cortas (pregunta abierta, no resuelta en esta sesión).**

---

### Hallazgo del backfill de 2 años (#44), retomado y convertido en tickets #104/#105 (sesión 2026-07-21)

Surgió en el `/grill-me` del plan de modelos econométricos (sesión 2026-07-20, que derivó en #98-#103) como una pista deliberadamente dejada sin ticket a pedido del usuario. Retomada al día siguiente vía `/grill-me` dedicado.

**El hallazgo original:** issue #44 (cerrado, sesión 2026-06-23) limitó el backfill histórico de los grupos no-201 a "hoy − 2 años" por **decisión explícita del cliente, no por límite técnico** -- el grupo 201 ya tiene 10 años cargados desde el mismo mecanismo. La mediana real de historia del catálogo (~9 trimestres) coincide casi exactamente con ese límite.

**Verificación técnica real, corrida en producción antes de decidir nada:** se conectó por SSH a la VM (misma clave `nueva_key_ec2.pem` de la sesión anterior, usuario `ubuntu`, confirmado con un chequeo de solo lectura antes de tocar nada) y se corrió manualmente `run_extract_sales_chunk.sh` contra el SOAP real (`ConsStockVenta`, `WS_URL=https://200.125.29.194:81` -- la URL del README estaba desactualizada, quedó en HTTP de antes del corte mTLS de #51/#52) para el grupo 50 (PERIFÉRICOS, el no-201 más grande, 744 artículos), pidiendo la semana 01-07/07/2022 (~4 años atrás). Resultado real: **644 unidades de venta confirmadas** (ej. SKU I00724 vendió 1 unidad el 01/07/2022), insertadas en `ventas_historicas_stage` (staging, truncado después, nunca tocó la tabla real). Confirma que el sistema de origen sí tiene historia real disponible mucho más allá de los 2 años actuales.

**Decisión tomada directamente** (el usuario explícitamente no quiso pasar por el cliente para esto, toma la responsabilidad): igualar la profundidad del grupo 201 (~10 años, desde `2016-10-03`) para todos los grupos no-201.

**Hallazgos adicionales durante el `/grill-me` de esta sesión, antes de armar los tickets:**
- Todos los grupos no-201 arrancan `ventas_historicas` en `2024-06-25` (coincide con "hoy − 2 años" al momento en que corrió #44), excepto el grupo 76 que ya tiene historia completa hasta `2016-10-03` (artefacto de re-categorización histórica de SKUs entre grupos).
- **Bug real en `backfill_jobs.py`**: `cmd_check` solo compara `grupo_id` contra corridas `exitoso` previas, no compara `fecha_desde`/`fecha_hasta` -- correr el backfill extendido tal cual hubiera salteado los 65 grupos de una, sin extraer nada (no-op silencioso). Se agrega como bloqueante del mismo ticket, no un ticket aparte.
- **Timing real medido** (no estimado): el backfill original de 2 años tardó ~13.7 horas en total para 65 grupos (`jobs_historial`), el grupo más grande (200) solo él ~3.8h. Extendiendo a 10 años (5x el rango), se espera **varios días de corrida real** -- se agrega como criterio de rollout (piloto de 1 grupo primero, `nohup` para sobrevivir el cierre de la sesión SSH).

**Tickets publicados:**
- [#104](https://github.com/Evalutia/App-Forecast/issues/104) -- fix de resumibilidad + backfill extendido a ~10 años. Sin bloqueos, listo para arrancar.
- [#105](https://github.com/Evalutia/App-Forecast/issues/105) -- medir el impacto real en elegibilidad post-backfill, reusando `ml/run_eval_elegibilidad_dry_run.py` (#102). Bloqueado por #104.

---

### Suma ETS (Holt-Winters) como modelo candidato, issue #98 (sesión 2026-07-21)

Parte del plan de #98-#103 (mismo `/grill-me` que originó el hallazgo del backfill de 2 años, sesión anterior). SARIMA y ETS estaban en el alcance ORIGINAL del cliente (issue #30) pero nunca se conectaron al pipeline real. Este ticket agrega ETS, mirror exacto del patrón ya establecido por Prophet en #81/#97: univariado (no consume `lags` como features tabulares), sin dependencia nueva (`statsmodels>=0.14.1` ya estaba en `requirements.txt`, `ExponentialSmoothing` ya importado sin usar).

**Decisiones de implementación:**

| Decisión | Definición |
|----------|-----------|
| **`trend="add"`/`seasonal="add"`, no `"mul"`** | Issue #81 exige no filtrar valores negativos (notas de crédito) antes de entrenar. `ExponentialSmoothing` exige datos estrictamente positivos para componentes multiplicativos -- aditivo es la única opción compatible con esa regla. |
| **`damped_trend=True`** | Más conservador para el forecast futuro (la tendencia se aplana en vez de extrapolarse en línea recta indefinidamente a mayor horizonte). |
| **Historia mínima propia: 2 ciclos estacionales completos** (`min_needed = 2 * seasonal_periods`, 8 trimestral / 24 mensual) | Análogo al `min_needed=8/12` de Prophet, pero basado en lo que `ExponentialSmoothing` necesita internamente para estimar el componente estacional -- por debajo de eso tira `ValueError`. Gate propio, independiente de `lags` (mismo criterio que Prophet). |
| **Exceptuado del filtro de folds degenerados de #97** | `_aggregate_walkforward`: `if name not in ("PROPHET", "ETS") and n_train_rows < lags` -- ETS no consume `lags` como features tabulares (igual que Prophet), el filtro no le aplica. Comentario del código deja espacio explícito para sumar `"SARIMA"` en #99 sin reescribir la condición. |
| **`--model-set full`/`classic` en `predict.py` suman ETS** | Ambos ya eran alias del mismo branch (`RF+XGB+PROPHET`) desde antes de este ticket -- se mantuvo la equivalencia agregando ETS a los dos. `--model-set prophet` (modo aislado de un solo modelo) y `tree` quedan sin tocar. |

**Tests (TDD, `tests/test_models.py` nuevo + 1 test agregado a `test_eval_walkforward.py`):** resultado válido con historia trimestral suficiente (16 trimestres), no crashea ni descarta filas con un valor negativo en el training (holdout_pred cubre las 16 filas igual), serie corta (4 trimestres) devuelve `None`, exención del filtro de #97 (mismo patrón que `test_filtro_de_n_train_rows_no_aplica_a_prophet`).

**Smoke test real** (5 SKUs elegibles reales, `EVAL_ONLY_SKUS`, `EVAL_PERSIST_CATALOG=1 EVAL_VERSION=smoke-98`): ETS produjo resultado walk-forward no degenerado en los 5/5 SKUs (mediana `r2_test=0.3458`, comparable a PROPHET 0.1866, RF 0.2018, XGB 0.2196), y ganó como modelo elegido (menor RMSE in-sample) en 1 de los 5 SKUs frente a la simulación de selección real.

**Documentación:** nueva sección "ETS (Holt-Winters)" en `docs/catalogo-modelos-diccionario.md`, mismo formato que la sección de Prophet -- ETS no tiene columnas `lag_N`/`period`/`trend`, sus "features" son los hiperparámetros (`trend`, `damped_trend`, `seasonal`, `seasonal_periods`).

**`/code-review` (angulos correctness, removed-behavior, cross-file callers, reuse, altitude)** no encontró bugs -- verificado que la columna `modelo` en `predicciones`/`catalogo_modelos` es `VARCHAR(64)` (sin restricción de enum, no hace falta migración), que no hay lista fija de modelos hardcodeada en webapi/frontend, y que `docs/script-de-prediccion.md` ya mencionaba `want_ets`/`want_sarima` como diseño aspiracional nunca implementado (inconsistencia preexistente, fuera de alcance de este ticket, no tocada).

**Verificado:** suite completa (`test_predict`, `test_evaluate`, `test_eval_walkforward`, `test_models`, `test_apply_elegibilidad`) corrida dentro del contenedor `etl`, las 5 pasan.

**#98 cerrado.**

---

### Suma SARIMA como modelo candidato, issue #99 (sesión 2026-07-21)

Parte del mismo plan de #98-#103. Bloqueado deliberadamente por #98 para copiar un patrón real ya revisado (ETS) en vez de uno hipotético. SARIMA estaba en el alcance ORIGINAL del cliente (issue #30) pero nunca se conectó al pipeline real. Mirror exacto de `fit_ets_insample`/`fit_ets_with_walkforward`: univariado (no consume `lags` como features tabulares), sin dependencia nueva (`statsmodels>=0.14.1` ya estaba en `requirements.txt`, `SARIMAX` ya importado sin usar).

**Decisiones de implementación:**

| Decisión | Definición |
|----------|-----------|
| **Orden fijo `(1,1,1)(1,1,1,s)`, no auto-búsqueda por SKU** | Decisión de diseño explícita de #99: `pmdarima.auto_arima` u otro order-search por SKU es más flexible pero puede fallar en converger o ser lento corriendo sobre miles de SKUs heterogéneos en la corrida nocturna. `d=1`/`D=1` (una diferenciación regular y una estacional) más un término AR y uno MA en cada parte -- análogo trimestral/mensual del "modelo airline" clásico de Box-Jenkins `(0,1,1)(0,1,1,s)`, con un AR adicional en cada parte por robustez general. `s=4` trimestral / `s=12` mensual, igual que `seasonal_periods` en ETS. |
| **`enforce_stationarity=False`/`enforce_invertibility=False`** | Evita que `SARIMAX.fit()` falle por quedar en el borde de la región de estacionariedad/invertibilidad al forzar el mismo orden fijo sobre series heterogéneas -- coherente con devolver `None` en vez de crashear ante cualquier fallo de ajuste (`try/except` alrededor de todo `fit_sarima_insample`, SARIMA puede no converger). |
| **Historia mínima propia: 2 ciclos estacionales completos** (`min_needed = 2 * seasonal_periods`, mismo criterio que ETS/#98) | Verificado empíricamente contra el contenedor `etl`: con exactamente el mínimo (8 trimestres), `SARIMAX.fit()` converge sin `NaN` en `fittedvalues` (statsmodels usa inicialización diffusa, no lanza `ValueError` como sí hace `ExponentialSmoothing` estacional). El único costo real observado es un `UserWarning` ("Too few observations to estimate starting parameters...") en el borde exacto del mínimo -- silenciado igual que `ConvergenceWarning`. |
| **Exceptuado del filtro de folds degenerados de #97** | `_aggregate_walkforward`: `if name not in ("PROPHET", "ETS", "SARIMA") and n_train_rows < lags` -- SARIMA no consume `lags` como features tabulares (igual que Prophet/ETS), el filtro no le aplica. |
| **`--model-set full`/`classic` en `predict.py` suman SARIMA** | Mismo patrón que ETS en #98: ambos ya eran alias del mismo branch (ahora `RF+XGB+PROPHET+ETS+SARIMA`). `--model-set prophet` y `tree` quedan sin tocar. No se agregó ningún valor nuevo a `--model-set` (eso es alcance de #100, bloqueado por #98 y #99, no tocado). |

**Tests (TDD):** 4 tests nuevos agregados a `tests/test_models.py` (mismo archivo que ETS, no un archivo separado, ya que la suite completa referencia `test_models` como módulo único) -- resultado válido con historia trimestral suficiente (16 trimestres), no crashea ni descarta filas con un valor negativo en el training, serie corta (4 trimestres) devuelve `None`, walk-forward produce resultado con historia suficiente (24 trimestres). 1 test agregado a `test_eval_walkforward.py` (`test_filtro_de_n_train_rows_no_aplica_a_sarima`, mismo patrón que el de ETS/Prophet). Los 5 tests se corrieron primero contra el código sin implementar (fallaron por `ImportError`/`AssertionError`, confirmando TDD real) antes de escribir `fit_sarima_insample`/`fit_sarima_with_walkforward`.

**Smoke test real** (5 SKUs elegibles reales, `EVAL_ONLY_SKUS`, `EVAL_PERSIST_CATALOG=1 EVAL_VERSION=smoke-99`): SARIMA produjo resultado walk-forward no degenerado en los 5/5 SKUs -- mediana `r2_test=0.3709`, el más alto de los 5 modelos en esta muestra (ETS 0.3458, XGB 0.2196, RF 0.2018, PROPHET 0.1866). No ganó la selección real de producción en esta muestra puntual (criterio de menor RMSE in-sample: PROPHET 4/5, ETS 1/5), pero el criterio de aceptación del issue (resultado válido, no degenerado, no filtrado) queda cumplido.

**Documentación:** nueva sección "SARIMA" en `docs/catalogo-modelos-diccionario.md`, mismo formato que ETS -- SARIMA no tiene columnas `lag_N`/`period`/`trend`, sus "features" son el orden fijo `(p,d,q)(P,D,Q,s)`.

**Self-review (correctness, removed-behavior, cross-file callers, reuse, altitude, efficiency)** no encontró bugs -- verificado que no hay lista fija de modelos hardcodeada en webapi/frontend (mismo hallazgo que #98, re-confirmado con grep), que el `UserWarning` silenciado es real (confirmado corriendo sin el filtro) y no oculta un problema distinto, y que `params` (con tuplas `SARIMA_ORDER`/`seasonal_order`) serializa correctamente vía `json.dumps` en `_build_catalog_row` sin necesitar cambios en `_json_safe`.

**Verificado:** suite completa (`test_predict`, `test_evaluate`, `test_eval_walkforward`, `test_models`, `test_apply_elegibilidad`) corrida dentro del contenedor `etl`, las 5 pasan.

**#99 cerrado.**

---

### Herramienta de comparación de hiperparámetros, issue #101 (sesión 2026-07-21)

Automatiza el proceso manual que llevó al fix de #97 (3 experimentos: setear env vars a mano, correr `eval_walkforward.py` dentro del contenedor `etl`, escribir a mano una query SQL contra `catalogo_modelos` para interpretar el resultado). Todos los hiperparámetros relevantes ya eran configurables por env var, leídos a tiempo de importación en `eval_walkforward.py`/`models.py` -- no hacía falta ningún mecanismo nuevo, solo orquestación.

**Script nuevo:** `services/python-worker/ml/compare_hyperparams.py`, corrible como `python3 -m ml.compare_hyperparams` (misma convención que `ml.eval_walkforward`/`ml.apply_elegibilidad`).

**Decisión de diseño clave:** invoca `eval_walkforward.py` como SUBPROCESO fresco (`subprocess.run` con `os.environ` modificado), no como import + llamada directa -- los hiperparámetros de `eval_walkforward.py`/`models.py` se leen una sola vez a nivel de módulo (`X = int(os.getenv("X", "default"))`), así que una segunda llamada a `main()` en el mismo proceso Python no recogería nuevos valores de env var.

**CLI:** `--skus SKU1,SKU2` (explícito) o `--random-n N` (N SKUs aleatorios entre los elegibles, mismo patrón de query que los pilotos de #97) para la muestra; `--lags`/`--horizon`/`--max-folds` como atajos dedicados más `--env KEY=VALUE` (repetible) como escape hatch genérico para cualquier otro hiperparámetro (`RF_MAX_DEPTH`, `XGB_LEARNING_RATE`, etc.); `--version` opcional, si no se pasa se autogenera como `compare-<timestamp>`. No hace sampling estratificado ni compara corridas pasadas entre sí (fuera de alcance, YAGNI, explícito en el issue).

**Los 4 criterios de #97/#101 se reportan SEPARADOS, nunca colapsados en un solo score** (mediana `r2_test` real, brecha train-test etiquetada "informativo, NO usar aislado", % `estable=True`, cobertura de la muestra pedida) más una quinta línea explícita, la **flag de degeneración** (% de filas con `r2_test` EXACTAMENTE 0.0 o 1.0, igualdad de float exacta) que se marca visualmente como sospechosa por encima de 15%. Esta separación es la lección central de #97: una brecha chica entre `r2_train`/`r2_test` no prueba generalización, un modelo casi-constante puede dar r2 exacto 0.0/1.0 en ambos y "coincidir" sin haber aprendido nada.

**Tests (`tests/test_compare_hyperparams.py`, 27 tests):** parseo de CLI (incluye mutua exclusión `--skus`/`--random-n`), merge de env vars (atajos vs. `--env` genérico, `--env` gana en colisión), y sobre todo `compute_report` con filas fabricadas a mano cubriendo r2_test=0.0 exacto, r2_test=1.0 exacto, 0.999999/0.000001 (regresión: NO deben contar como degenerados), `estable=None`, cobertura incompleta (simula exactamente el error de #97: un hiperparámetro que "gana" en r2 pero excluye la mayoría de la muestra), y el caso central "misma brecha chica, un caso con r2 alto genuino y otro degenerado" -- confirma que el reporte los distingue.

**Verificación real** (dentro del contenedor `etl`, 5 SKUs elegibles aleatorios cada vez, `MYSQL_PASS=evalutia` porque el env del contenedor expone `MYSQL_PASSWORD`, no `MYSQL_PASS`, mismo patrón ya usado por el resto de `ml/`):

- **Corrida 1 (`EVAL_LAGS` default=8):** RF/XGB solo produjeron resultado válido para 3/5 SKUs (cobertura 60%), con 33.3% de esas filas degeneradas (r2_test exacto 0/1) -- coincide con el patrón de #97 (RF/XGB necesitan mucha historia con `lags=8`).
- **Corrida 2 (`--env EVAL_LAGS=4`):** RF/XGB pasaron a cobertura 100% (5/5), degeneración bajó a 20% -- confirma el hallazgo ya documentado en el cierre de #97 ("bajar `lags` sube la cobertura pero no arregla la señal por completo": la cobertura mejora claramente, la degeneración baja pero no desaparece).
- Ambas corridas usaron muestras aleatorias distintas (no una comparación A/B estrictamente controlada), pero el reporte reflejó en ambos casos números reales, coherentes entre sí y con el diagnóstico ya conocido de #97 -- exactamente lo que #101 pedía verificar.

**Self-review** (correctness, cross-file callers, reuse, simplificación, eficiencia, altitud, convenciones): sin bugs reales. Único hallazgo menor dejado sin resolver: `compute_report`/`format_report` recalculan cada uno el `set()` de SKUs solicitados (trabajo duplicado insignificante sobre listas chicas, herramienta de uso manual/secuencial, no vale la pena el refactor).

**Verificado:** suite completa (`test_predict`, `test_evaluate`, `test_eval_walkforward`, `test_models`, `test_apply_elegibilidad` con `APPLY_VERSION=v1`, `test_compare_hyperparams` nuevo) corrida dentro del contenedor `etl`, las 6 pasan.

**#101 cerrado.**

---

### Automatización de la medición periódica de elegibilidad (dry-run), issue #102 (sesión 2026-07-21)

Decisiones ya tomadas en la sesión `/grill-me` previa, no re-discutidas acá: (1) `jobs_historial.tipo_job` necesita un valor de ENUM nuevo, `eval_elegibilidad`; (2) `apply_elegibilidad.py` debe exponer una función reusable que devuelva un dict estructurado en vez de solo imprimir.

**Migración:** `infra/sql/18-jobs-historial-eval-elegibilidad.sql`. `ALTER TABLE ... MODIFY COLUMN tipo_job ENUM('etl','forecast','backfill','export','eval_elegibilidad') NOT NULL`, con el mismo patrón defensivo del resto de `infra/sql/` (chequeo de `information_schema.COLUMNS.COLUMN_TYPE` antes de alterar, para que re-correrla no dependa de que MySQL tolere en silencio un ALTER repetido). Aplicada y verificada idempotente localmente (segunda corrida no vuelve a alterar la columna). No aplicada a la VM, deploy a producción queda como paso humano separado.

**Refactor de `apply_elegibilidad.py`:** se extrajo el cómputo que antes vivía inline en `main()` en funciones puras/reusables: `fetch_catalogo`, `fetch_actual_elegibilidad`, `build_decisiones`, `compute_summary` (los números: evaluados/elegibles/ganan/pierden/sin_cambio/revocados) y `get_elegibilidad_summary` (orquesta las 4 anteriores). `get_elegibilidad_summary` es de **lectura pura** (2 SELECT, cero INSERT/UPDATE, no lee ni usa `APPLY_PERSIST`) -- no existe, ni por error, un camino de código en la nueva automatización que pueda escribir en `articulos_elegibilidad_econometrico`. `main()` (el CLI existente) se reescribió para usar estas mismas funciones pero imprime exactamente los mismos mensajes/números que antes -- comportamiento del CLI sin cambios, confirmado con los tests preexistentes de `test_apply_elegibilidad.py` sin modificar (siguen pasando tal cual).

**Hallazgo real durante la integración (no bug de negocio, bug de diseño del refactor):** `APPLY_VERSION`/`APPLY_PERSIST` se leían a nivel de módulo (`os.environ["APPLY_VERSION"]` al importar) -- esto rompía el propósito mismo de exponer `get_elegibilidad_summary` como función reusable, porque cualquier script que solo quisiera importar esa función (como la automatización nueva) se topaba con un `KeyError` con solo hacer el `import`, sin necesitar `APPLY_VERSION` para nada. Se movieron ambas lecturas adentro de `main()` -- mismo comportamiento exacto para el CLI (sigue exigiendo `APPLY_VERSION`, sigue fallando si falta), pero ya no bloquea el import por otros módulos.

**Script nuevo:** `services/python-worker/ml/run_eval_elegibilidad_dry_run.py`, corrible como `python3 -m ml.run_eval_elegibilidad_dry_run` (misma convención de `ml.eval_walkforward`/`ml.apply_elegibilidad`/`ml.compare_hyperparams`). Mismo patrón de subproceso fresco que `ml/compare_hyperparams.py` (#101) para invocar `eval_walkforward.py` (los hiperparámetros se leen una sola vez a nivel de módulo, no se puede reusar el mismo proceso Python). A diferencia de `compare_hyperparams`, corre **siempre full-catalog**: `build_env()` hace `pop` explícito de `EVAL_ONLY_SKUS` del entorno base antes de lanzar el subproceso, para que una corrida real nunca herede por accidente un filtro dejado por una sesión de desarrollo anterior. `EVAL_VERSION` se autogenera con grano mensual (`eval-mensual-YYYY-MM`, ej. `eval-mensual-2026-07`) -- correrlo más de una vez en el mismo mes pisa la medición de ese mes en vez de acumular versiones indistinguibles (`catalogo_modelos` igual conserva el histórico completo por `fecha_estimacion`). Al terminar, llama a `apply_elegibilidad.get_elegibilidad_summary()` (nunca `APPLY_PERSIST=true`, nunca pasa por `main()` de `apply_elegibilidad.py`) y escribe el resumen como `detalle` JSON en `jobs_historial` (`tipo_job='eval_elegibilidad'`, `estado='exitoso'`/`'fallido'`).

**Ofelia:** job nuevo `eval_elegibilidad_mensual` en `ofelia.ini`, `schedule = 0 0 4 1 * *` (4am del día 1 de cada mes, una hora después del cron diario de las 3am para evitar contención de recursos). Wrapper bash nuevo `services/etl/run_eval_elegibilidad_mensual.sh` (mismo patrón que `run_backfill_ventas.sh`: script chico con chequeos `: "${VAR:?missing}"`, NO pasa por Pentaho/`kitchen.sh`, invoca directo el entrypoint de Python). Deriva `MYSQL_PASS` de `MYSQL_PASSWORD` (mismo problema de nombres de env var ya documentado en el cierre de #101).

**Uso manual documentado** (en el docstring del script nuevo): correr `python3 -m ml.run_eval_elegibilidad_dry_run` directo dentro del contenedor `etl`, sin pasar por Ofelia/cron, para medir el impacto de un modelo/hiperparámetro nuevo (ej. justo después de desplegar #98/#99/#101) sin esperar al próximo primero de mes.

**Verificación real (contenedor `etl`, no solo tests):**
- Dos corridas piloto con `EVAL_ONLY_SKUS` (5 SKUs cada una, para iterar rápido) invocando las mismas funciones internas del script: job 214 (SKUs sin historia suficiente, catálogo vacío para esa versión, resumen en cero) y job 215 (5 SKUs elegibles reales: `skus_evaluados=5, elegibles=3, ganan=0, pierden=2, sin_cambio=3`, más 9 SKUs listados en `revocados_sin_medicion` -- esperable, son SKUs elegibles en producción que esta muestra chica no midió). Ambos jobs quedaron en `jobs_historial` con `tipo_job='eval_elegibilidad'`, `estado='exitoso'`, `detalle` con el JSON completo.
- Corrida de confirmación real, full-catalog, **sin `EVAL_ONLY_SKUS`**, disparada con el wrapper de producción real (`services/etl/run_eval_elegibilidad_mensual.sh`, el mismo comando que correría Ofelia): job 216, `estado='exitoso'`, 595 segundos (~10 min). `detalle`: `skus_evaluados=58, elegibles=14, ganan=6, pierden=6, sin_cambio=46, revocados_sin_medicion=[]`. Hallazgo real de paso: **6 SKUs ganarían elegibilidad hoy** si este dry-run se aplicara -- consistente con que #98/#99 (ETS/SARIMA) ya están sumando candidatos nuevos al pool de `elegir_ganador` desde que se desplegaron.
- `articulos_elegibilidad_econometrico` sin tocar por ninguna de las 3 corridas (214/215/216): mismo total de filas (1482) y mismo conteo de elegibles (14) antes y después, y `MAX(evaluado_en)` siguió siendo `2026-07-20 17:18:39.388531` (el timestamp del deploy de #97 del día anterior) después de correr el job 216 -- si cualquier fila hubiera sido tocada, `evaluado_en` se hubiera actualizado a `NOW(6)`. Nota metodológica: se había planeado usar un checksum `MD5(GROUP_CONCAT(sku,elegible,r2_test,estable,n_folds))` para esta verificación, pero `group_concat_max_len` es 1024 por default en este MySQL (muy por debajo de lo que hace falta para concatenar 1482 filas sin truncar) y `GROUP_CONCAT` sin `ORDER BY` no garantiza el mismo orden entre corridas -- dos ejecuciones de la misma query contra datos idénticos pueden dar hashes distintos por truncamiento/orden, no por un cambio real (se reprodujo este falso positivo: mismo dato, hash distinto). Se descartó ese método a favor del chequeo de conteo + `evaluado_en`, más simple y sin ese punto ciego.

**Self-review** (correctness, removed-behavior, cross-file callers, reuse, simplificación, eficiencia, altitud, convenciones de CLAUDE.md): un hallazgo real corregido (el bug de import de `APPLY_VERSION` a nivel de módulo, arriba) y un error de comentario corregido (`get_elegibilidad_summary` decía "3 SELECT", son 2). Sin más bugs encontrados. `grep` confirmó que ningún otro módulo dependía de las constantes `APPLY_VERSION`/`APPLY_PERSIST` a nivel de módulo que se movieron adentro de `main()`.

**Verificado:** suite completa (`test_predict`, `test_evaluate`, `test_eval_walkforward`, `test_models`, `test_apply_elegibilidad` con `APPLY_VERSION=v1`, `test_compare_hyperparams`, `test_run_eval_elegibilidad_dry_run` nuevo) corrida dentro del contenedor `etl`, las 7 pasan.

**#102 cerrado.**

---

### #103: casos borde de baja frecuencia/quiebre, re-auditados con muestra ampliada y ETS/SARIMA (sesión 2026-07-21)

Retoma el hallazgo de #76 (1/7, 14% elegible en casos borde, contra 70% en población general con historia suficiente, medido en #97). #103 pedía: (1) decidir si la volatilidad es de los MODELOS o de la SEÑAL, (2) decidir si `estable` (#70) necesita tratamiento extra, (3) evaluar si vale la pena ampliar la muestra de 7 SKUs, ahora que #98/#99 (ETS/SARIMA) suman candidatos nuevos.

**Ampliación de muestra (script nuevo, no productivo, `ml/audit_103_casos_borde.py`):** mismos criterios de dominio que #76 vía `planilla_ventas_calculada` (`tickets_mes`/`estado_mes`). El piso de historia de #76 (16 trimestres) era una elección conservadora sin anclaje a ningún umbral real -- se probó primero con el piso nominal de producción (24 meses/8 trimestres), pero resultó no discriminar nada: 5535 de los 5550 SKUs de `ventas_historicas` ya tienen ≥24 meses de historia. La población recién se vuelve selectiva en 30 meses (10 trimestres, donde el conteo cae a 103 SKUs), y ahí el patrón borde se estabiliza en **17 candidatos** (8 baja frecuencia + 9 quiebre) desde piso=10 hasta piso=16 -- techo real del catálogo local, no un límite arbitrario. Expansión real sobre los 7 de #76, aunque más modesta de lo esperado.

**Corrida real** (`EVAL_VERSION=eval-audit-103`, `model-set` completo: RF+XGB+PROPHET+ETS+SARIMA, vía `eval_walkforward.py` con `EVAL_ONLY_SKUS`):

- **Cobertura walk-forward** (al menos 1 modelo evaluable): solo 8/17 (47%), y muy desigual por caso -- baja frecuencia 6/8 (75%), quiebre 2/9 (22%). El resto ni junta datos suficientes para un fold.
- **Elegibilidad final** (criterio real de #70, sobre los 8 evaluables): **0/8 (0%)** -- peor que el 14% de #76, muy por debajo del ~70% de la población general.
- **Detalle por modelo** (estabilidad entre folds, sobre los evaluables, 38 filas en `catalogo_modelos`):

| Modelo | Estable / evaluables |
|---|---|
| RF | 4/6 (66.7%) |
| XGB | 4/6 (66.7%) |
| SARIMA | 3/8 (37.5%) |
| ETS | 1/8 (12.5%) |
| PROPHET | 1/8 (12.5%) |

**Hallazgo clave:** RF/XGB son notablemente más estables que los modelos univariados en estos casos borde específicos, pero tienen `r2_test` promedio más bajo -- pierden la competencia de "mejor r2" (criterio de selección de ganador de #88/#89) contra ETS/Prophet/SARIMA, que ganan más seguido pero son volátiles. El ganador real de cada SKU es casi siempre el modelo de mayor r2, no el más estable, y por eso la elegibilidad final termina en 0%.

**Decisión documentada -- pregunta 1 (¿modelo o señal?):** predominantemente **señal**. Sumar 2 familias de modelo completamente distintas (ETS/SARIMA, exponential smoothing y ARIMA, frente a árboles y Prophet) no mejoró la elegibilidad, la empeoró -- ninguna de las 5 familias generaliza de forma consistente entre folds en estos SKUs, evidencia fuerte de que la demanda real de estos casos borde es intrínsecamente más errática (estructuralmente inestable entre períodos, no solo difícil de ajustar). Matiz real: el criterio de selección de ganador amplifica el efecto al preferir sistemáticamente el modelo de mayor r2 aunque sea más volátil, existiendo una alternativa (RF/XGB) con menor r2 pero mucha mayor estabilidad -- esto no cambia el veredicto de "señal", pero significa que parte de la brecha observada es de mecanismo de selección, no solo de la señal en sí.

**Decisión documentada -- pregunta 2 (¿tratamiento nuevo en #70?):** no. El chequeo de `estable` sigue haciendo su trabajo correctamente -- reconfirmado con una muestra más grande (0/8 casos de r2 alto colándose inestable, igual que en #76). No hace falta agregar una exclusión especial nueva.

**Propuesta concreta, sin ticket nuevo por ahora** (documentada acá, no implementada): evaluar si el criterio de selección de ganador (#88/#89, hoy "mejor r2_test" puro) debería ponderar estabilidad además de r2_test, dado que en estos casos borde RF/XGB (menor r2, mucho más estables) pierden sistemáticamente contra modelos más volátiles. Si se retoma, es un cambio al mecanismo de selección de #88/#89, no al criterio de exclusión de #70.

**Decisión documentada -- pregunta 3 (¿ampliar muestra?):** sí, y ya se hizo -- de 7 a 17 candidatos, techo real del catálogo local con el patrón borde (confirmado: el conteo no crece entre piso=10 y piso=16 trimestres).

**#103 cerrado.**

---

### #124: un fallo de la llamada SOAP de ventas escribía cero de forma permanente y silenciosa (sesión 2026-08-08)

Hallazgo de severidad ALTA de la verificación profunda del 2026-08-04. Diagnosticado con `/diagnosing-bugs`: tres capas independientes, las tres necesarias para que el bug ocurra, las tres confirmadas con repros reales antes de tocar código (Docker local, MySQL real con FK, sin dejar rastro).

**Capa 1 -- `run_extract_sales_chunk.sh` tragaba el fallo.** Respuesta vacía, JSON ilegible o `<MensError>` del WS terminaban en `[WARN]... continuando` y el script siempre salía con `exit 0`. Peor de lo que sugiere el issue original: incluso un **crash real de Python** (`JSONDecodeError`) quedaba invisible, por una sutileza de bash -- `call_for_grupo_deposito` se invoca como `... || echo`, y eso suspende `set -e` para *toda* la función (no solo el último comando), así que el `rm -f` final (que casi siempre da 0) terminaba pisando el código de salida real. Reproducido con un `curl` mockeado dentro del contenedor `etl`: respuesta vacía, JSON malformado y `MensError` bien formado, los tres casos daban `EXIT_CODE=0`.

**Capa 2 -- el merge SQL pisaba sin preguntar.** El paso `MERGE STAGING -> VENTAS (con snapshot)` de `job_etl_diario.kjb` hace `SUM(cantidad) GROUP BY fecha,sku` sobre lo que haya en staging esa noche, `ON DUPLICATE KEY UPDATE cantidad = VALUES(cantidad)` -- sin chequear si faltó algún depósito. Reproducido contra `evalutia-mysql` real (transacción + rollback, SKU descartable `__TEST124__`): una venta real de 50 quedó en 0 tras correr ese SQL exacto con staging simulando solo los depósitos de logística.

**Capa 3, no estaba en el issue original -- los hops del `.kjb` eran `unconditional=Y`.** Aunque se arreglara el script para salir con error, Pentaho corría el MERGE igual: el flujo no estaba configurado para frenar ante un fallo del paso anterior. Sin esta capa, el fix de la capa 1 no alcanza para cumplir el criterio de aceptación del issue ("no se toca el día, o la corrida queda marcada como fallida").

**Fix (3 archivos):**
- `run_extract_sales_chunk.sh`: detecta `<MensError>` (mismo patrón que ya usaba `run_extract_articulos.py`, que sí lo miraba), captura el `rc` de Python explícitamente en vez de dejarlo pisar por el `rm -f`, acumula fallos por grupo/depósito y sale con `exit 1` si hubo alguno.
- `run_extract_sales_chunk.py`: `json.loads` envuelto en `try/except` -- error `[ERROR]` limpio en vez de traceback crudo.
- `job_etl_diario.kjb`: el hop `RUN EXTRACT VENTAS -> MERGE` pasa a condicional (`evaluation=Y`, solo si el script salió con éxito); rama nueva `MARK VENTAS EXTRACT FAILED` que no toca `ventas_historicas` y deja un registro `fallido` en `jobs_historial`, y después reincorpora el flujo normal (predict/planilla siguen corriendo con el dato del día anterior, no se frena todo el pipeline nocturno).

**Verificado (contenedor `etl` + MySQL real, no solo lectura de código):** los 3 escenarios de la AC, antes en verde falso (`exit 0`) ahora en rojo correcto (`exit 1`, mensaje `[ERROR]` claro, cero traceback). Happy path confirmado sin falsos positivos: datos reales válidos y el caso legítimo "0 ventas hoy" (array vacío del WS) siguen dando `exit 0` -- la distinción es entre "no hubo venta" y "no se pudo saber si hubo venta", no un endurecimiento genérico. Datos de prueba (`__TEST124__`) limpiados en las 4 tablas afectadas tras cada repro.

**Sin seam de test previo:** `services/etl/tests/` solo cubre los scripts `calc_*`, nada de extracción u orquestación Pentaho. No se agregó test automatizado nuevo -- los repros de arriba (curl mockeado + MySQL real con rollback) quedan como la verificación documentada, siguiendo la disciplina de `/diagnosing-bugs` cuando no existe un seam correcto.

**Post-mortem:** lo que hubiera prevenido esto es cobertura de test sobre el flujo de orquestación (bash + `.kjb`), inexistente hoy en el repo -- candidato directo para `/improve-codebase-architecture` si se retoma. El patrón `unconditional=Y` copiado en cadena por los 10 hops del job original es la causa estructural de la capa 3; vale revisarlo si se agregan pasos nuevos al mismo `.kjb`.

**#124 cerrado.**

---

## Documentación adicional

| Archivo | Contenido |
|---------|-----------|
| `docs/arquitectura-mysql.md` | Diseño de BD, relaciones, índices, patrones de consulta |
| `docs/script-de-prediccion.md` | Detalles de predict.py, modelos ML, ensemble |
| `docs/catalogo-modelos-diccionario.md` | Diccionario de variables de entrada (`lag_N`, `period`, `trend`, `ds`/`y`, hiperparámetros ETS/SARIMA) de RF/XGB/Prophet/ETS/SARIMA -- issue #85/#98/#99 |
| `services/etl/README_ETL_Diario_actualizado.md` | Flujo ETL completo, variables, backfills |
