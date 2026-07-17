# Domain Docs

Cómo deben consumir las skills de ingeniería la documentación de dominio de este repo.

## Antes de explorar, leer esto

- **`.claude/CONTEXTO.md`** — contexto de dominio único para todo el repo (backend, frontend, ETL, ML). Cubre stack, estructura de carpetas, esquema de DB, endpoints, y un log cronológico de decisiones de diseño por sesión (equivalente a ADRs, pero todas juntas en un solo archivo en vez de `docs/adr/` separado).

No hay `CONTEXT.md` en la raíz ni `docs/adr/` — este repo es **single-context**: un solo archivo cubre todas las áreas (`apps/backend`, `apps/frontend`, `services/etl`, `services/python-worker`). Las decisiones de arquitectura quedan documentadas como secciones fechadas dentro de `.claude/CONTEXTO.md`, no como archivos ADR individuales.

Si en algún momento hace falta afinar terminología o registrar una decisión nueva de forma más formal, `/domain-modeling` es la skill que lo hace (se puede invocar directo, o llega sola desde `/improve-codebase-architecture` cuando surge un término ambiguo durante un escaneo de arquitectura).

## Usar el vocabulario del glosario

`.claude/CONTEXTO.md` ya fija términos de dominio (ej. `elegibilidad econométrica`, `estado_mes`, `frecuencia de venta`, `SKU`, `grupo`). Al nombrar conceptos de dominio en un issue, propuesta de refactor o nombre de variable, usar el término tal como está definido ahí — no derivar sinónimos.

## Señalar contradicciones

Si una propuesta contradice una decisión ya documentada en `.claude/CONTEXTO.md`, señalarlo explícitamente en vez de pisarla en silencio.
