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
