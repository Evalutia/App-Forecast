# Triage Labels

Las skills hablan en términos de 5 roles canónicos de triage. Esta tabla los mapea a los labels reales de este repo.

| Rol canónico | Label en este repo | Significado |
|---|---|---|
| `needs-triage` | `needs-triage` | El maintainer necesita evaluar este issue |
| `needs-info` | `needs-info` | Esperando más información del reporter |
| `ready-for-agent` | `ready-for-agent` | Completamente especificado, listo para que un agente lo tome sin contexto humano |
| `ready-for-human` | `ready-for-human` | Requiere implementación humana |
| `wontfix` | `wontfix` | No se va a accionar (ya existía en el repo) |

Cuando una skill menciona un rol (ej. "aplicar el label de listo para agente"), usar el string correspondiente de esta tabla.

## Labels de categoría (no son de triage, no confundir)

Este repo ya usa labels de área/tipo que conviven con los de triage sin pisarse: `bug`, `enhancement`, `question`, `documentation`, `etl`, `backend`, `frontend`, `ml`, `database`, `blocker`, `fase-1`, `fase-2`, `fase-3`. Un issue puede tener un label de categoría (`ml`) y uno de triage (`ready-for-human`) al mismo tiempo.
