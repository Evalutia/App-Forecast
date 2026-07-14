# CLAUDE.md

Guía para Claude Code (u otro agente) trabajando en este repo.

## Contexto del proyecto

Ver `.claude/CONTEXTO.md` — stack, estructura de carpetas, esquema de DB, endpoints, y el log de decisiones de diseño por sesión. Leerlo antes de tocar código si no está ya en contexto.

## Agent skills

Este repo trae copiadas en `.claude/skills/` las skills de ingeniería relevantes para el proyecto (viajan con el `git clone`, no hace falta instalar nada aparte en otra máquina). Origen: [`mattpocock/skills`](https://github.com/mattpocock/skills) (actualizado 2026-07-14) + 2 de la librería personal del usuario (`skills-master`, `ponytail` y `graphify`). Se invocan como `/nombre-skill` en Claude Code.

Se dividen en dos tipos (mismo criterio que usa el repo de origen):

- **User-invoked** — solo se disparan si las tipeás vos (`disable-model-invocation` en su frontmatter). Orquestan trabajo grande o tocan estado del repo (crear issues, editar config).
- **Model-invoked** — puedo llegar a ellas solo cuando el trabajo lo pide, sin que las tipees. Son la disciplina reutilizable que las de arriba invocan por dentro.

### Issue tracker

GitHub (`Evalutia/App-Forecast`), vía CLI `gh`. Sin PRs externas como superficie de triage. Incluye las operaciones de wayfinding (dependencias nativas de issues) para `/wayfinder`. Ver `docs/agents/issue-tracker.md`.

### Triage labels

5 roles canónicos (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) ya creados como labels de GitHub, conviven con los labels de categoría existentes (`etl`, `backend`, `frontend`, `ml`, `database`, `blocker`, etc.). Ver `docs/agents/triage-labels.md`.

### Domain docs

Single-context: todo el contexto de dominio vive en `.claude/CONTEXTO.md` (no hay `CONTEXT.md`/`docs/adr/` separados). Ver `docs/agents/domain.md`.

### Qué skill usar en cada situación

**User-invoked** (las tipeás vos):

| Situación | Skill | Qué hace |
|---|---|---|
| Tenés una idea o pedido en lenguaje natural, todavía sin forma | `/to-spec` | Sintetiza la conversación en una spec y la publica, sin interview — ya se habló lo suficiente |
| Ya tenés una spec/plan/conversación y hay que partirlo en trabajo concreto | `/to-tickets` | Lo parte en tickets independientes (vertical slices) con dependencias explícitas — así se armaron #84-89 (con `to-issues`, su nombre anterior) |
| Hay issues abiertos sin clasificar o en estado ambiguo | `/triage` | Los mueve por el estado de triage (needs-triage → ready-for-agent/ready-for-human, etc.) |
| Trabajo grande, más de lo que entra en una sesión, con decisiones sin resolver | `/wayfinder` | Charts el camino como un mapa de tickets de decisión en GitHub, los resuelve de a uno hasta que el camino queda claro — pensar antes de ejecutar |
| Ya está la spec/tickets, hay que construirlo | `/implement` | Implementa, usa `/tdd` en las costuras acordadas, cierra con `/code-review` (el propio de este entorno, ver nota abajo) antes de commitear |
| No sabés qué skill te sirve para lo que querés hacer | `/ask-matt` | Router — te pregunta la situación y te dice cuál usar |
| Arrancás un repo nuevo o cambiás de tracker/labels/estructura de contexto | `/setup-matt-pocock-skills` | Re-configura lo de arriba (ya corrido una vez en este repo) |
| Cierre de sesión larga, para retomar después sin releer todo | `/handoff` | Compacta la conversación en un documento de traspaso, sugiere qué skills cargar en la próxima |

**Model-invoked** (puedo llegar solo, o las invocás igual si querés forzarlas):

| Situación | Skill | Qué hace |
|---|---|---|
| Algo se rompe o anda lento y no se sabe por qué | `/diagnosing-bugs` | Protocolo disciplinado: reproducir → minimizar → hipótesis → instrumentar → arreglar → test de regresión. Mismo tipo de trabajo que #59/#60 |
| Sospechás duplicación o código que se volvió difícil de mantener | `/improve-codebase-architecture` | Escanea el repo, prioriza por hot-spots de `git log`, propone refactors, genera un reporte visual |
| Diseñando o retocando la interfaz de un módulo | `/codebase-design` | Vocabulario compartido para módulos "deep" (mucho comportamiento detrás de una interfaz chica) |
| Feature o fix con TDD, un vertical slice a la vez | `/tdd` | Red-green-refactor |
| Un término de dominio quedó ambiguo o hay que registrar una decisión de arquitectura | `/domain-modeling` | Formaliza vocabulario y decisiones en el contexto de dominio |
| Hace falta investigar algo (librería, API, doc externa) sin frenar el trabajo principal | `/research` | Agente en background que investiga contra fuentes primarias y deja un `.md` citado |
| Conflicto de merge/rebase en curso | `/resolving-merge-conflicts` | Resuelve hunk por hunk según la intención de cada lado, nunca `--abort` |
| Vas a correr un comando de git que preocupa (push --force, reset --hard, etc.) | `git-guardrails-claude-code` | Hook que bloquea esos comandos automáticamente — se configura una vez, no se invoca a mano |
| Quiero que el código sea lo más simple/lazy posible, sin sobre-ingeniería | `/ponytail` | Modo de trabajo (no lee/escribe nada del repo): YAGNI, reusar antes que crear, el diff más chico que funcione. `lite`/`full`/`ultra` |
| Preguntas sobre arquitectura, relaciones entre archivos, o "¿qué toca esto?" en el monorepo | `/graphify` | Construye un grafo de conocimiento del codebase (nodos, comunidades, BFS/DFS) — útil para navegar `apps/`+`services/` cruzados sin releer todo a mano |

**Nota sobre `/code-review`**: el repo de origen trae su propia skill `code-review` (revisión en dos ejes, Standards + Spec, con sub-agentes paralelos). **No la copié** — este entorno ya tiene un `/code-review` propio (con modo `ultra` para review multi-agente en la nube vía `/code-review ultra`), y copiar la de mattpocock la taparía sin que lo pidas. Cuando `/implement` diga "usá `/code-review`", corre el que ya existe acá.

Estas 18 son un subconjunto curado del total disponible — el resto de las skills personales del usuario (`premortem`, `grill-me`, `grill-with-docs`, etc.) siguen disponibles globalmente sin necesidad de copiarlas acá; se invocan igual con `/nombre-skill` aunque no vivan en este repo.

### Encadenar skills, no usarlas aisladas

Ninguna de estas skills vive en un silo — cuando la salida de una alimenta naturalmente a otra, seguir la cadena en vez de parar en la primera. Ejemplos ya validados en este repo o previstos por el propio diseño de las skills:

- **`/grill-me` (u otra sesión de decisión) → `/to-tickets`**: primero destrabar la decisión pregunta por pregunta, después convertir el plan resultante en tickets con dependencias explícitas. Así se armó el catálogo de modelos (#84-89).
- **`/to-spec` → `/to-tickets` → `/triage`**: una idea se estructura primero, se parte en trabajo concreto después, y los tickets resultantes quedan clasificados con el label de triage correcto en vez de quedar sueltos como `needs-triage` por defecto.
- **`/wayfinder` → `/to-tickets` o `/implement`**: cuando el mapa de decisiones queda resuelto (el "camino" ya es visible), lo que sigue es convertir eso en tickets de ejecución o implementarlo directo.
- **`/implement` → `/tdd` → `/code-review`**: esta cadena viene de fábrica dentro de la skill misma, no hay que armarla a mano.
- **`/diagnosing-bugs` → `/domain-modeling`**: si el diagnóstico revela un concepto de dominio nuevo o contradice una decisión ya documentada en `.claude/CONTEXTO.md` (como pasó con #59/#60), registrar eso explícitamente en vez de dejarlo solo en el comentario del issue.
- **`/improve-codebase-architecture` → `/codebase-design` → `/to-tickets`**: el escaneo prioriza por hot-spots, el vocabulario de módulos deep ayuda a definir la costura, y el refactor aceptado se formaliza como ticket accionable.
- **Cierre de sesión larga → `/handoff`**: si se tocaron varias skills en la misma sesión, el handoff debe listar cuáles se usaron y qué decisiones quedaron, no solo el resumen de código.
- **`/graphify` → `/improve-codebase-architecture` o `/domain-modeling`**: cuando la pregunta es "qué toca esto" en el monorepo (backend/frontend/etl/python-worker cruzados), el grafo da el mapa de relaciones antes de decidir dónde escanear o qué término formalizar.
- **`/ponytail` no encadena, se superpone**: es un modificador de estilo que corre en paralelo a cualquier otra skill de esta lista (`/implement`, `/tdd`, un fix suelto) — no es un paso de una cadena, es cómo se hace cada paso.

Esto es sobre **combinar el pensamiento de las skills**, no sobre disparar acciones sin que las pidas — las user-invoked (`/to-tickets`, `/triage`, `/wayfinder`, `/implement`, `/setup-matt-pocock-skills`) siguen requiriendo que vos las invoques, porque crean issues, tocan config, o commitean código. La cadena se sigue cuando ya estás dentro de una de estas skills y el siguiente paso es obvio, no antes.
