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

> **Nota para frontend (#19):** `fiabilidad_porcentaje` debe mostrarse como badge de color en la columna AE: verde (≥70), amarillo (40–69), rojo (<40). NULL = sin datos suficientes, mostrar "—". `rotacion_sugerida` NULL también muestra "—" sin crashear.

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
| **SKUs con NULLs** | Se incluyen en el response. `rotacionSugerida = null` significa menos de 3 meses normales — señal explícita para que el frontend muestre "—" en columna AE. |
| **Autorización** | `[Authorize]` heredado de `PlanillaController` — sin restricción de rol. Tanto `administrador` como `duenoDeEmpresa` pueden acceder. |
| **Ubicación** | Nuevo método `[HttpGet("sugerencias")]` dentro del `PlanillaController` existente. Sin controller separado. |

> **Nota para frontend (#19, #20):** el frontend carga este endpoint al montar `PlanillaPage` (una sola vez), lo indexa por SKU, y une los valores a cada fila de la tabla de planilla client-side. No hacer un request por página de planilla.

### Columna AE en `PlanillaTable` — Issue #19 (sesión 2026-06-07)

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
