# Issue tracker: GitHub

Issues para este repo viven en GitHub Issues (`Evalutia/App-Forecast`). Usar el CLI `gh` para todas las operaciones.

## Convenciones

- **Crear un issue**: `gh issue create --title "..." --body "..."`. Usar heredoc para bodies multi-línea.
- **Leer un issue**: `gh issue view <number> --comments`.
- **Listar issues**: `gh issue list --state open` (agregar `--label`/`--state` según haga falta).
- **Comentar**: `gh issue comment <number> --body "..."`
- **Aplicar / quitar labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Cerrar**: `gh issue close <number> --comment "..."`

El repo se infiere de `git remote -v` — `gh` lo hace automático corriendo dentro del clon.

## Pull Requests externas

No se tratan como superficie de triage — este repo no recibe PRs de colaboradores externos, solo del equipo interno. `triage` no necesita cubrir PRs acá.

## Cuando una skill dice "publish to the issue tracker"

Crear un issue de GitHub con `gh issue create`.

## Cuando una skill dice "fetch the relevant ticket"

Correr `gh issue view <number> --comments`.

## Operaciones de wayfinding

Usado por `/wayfinder`. El **mapa** es un issue con issues **hijos** como tickets.

- **Mapa**: un issue con label `wayfinder:map`, con el cuerpo Notes / Decisions-so-far / Fog. `gh issue create --label wayfinder:map`.
- **Ticket hijo**: issue linkeado al mapa como sub-issue de GitHub (`gh api` sobre el endpoint de sub-issues). Si los sub-issues no están habilitados, agregar el hijo a una task list en el body del mapa y poner `Part of #<mapa>` al principio del body del hijo. Labels: `wayfinder:<tipo>` (`research`/`prototype`/`grilling`/`task`). Al reclamarlo, se asigna al dev que lo está llevando.
- **Bloqueos**: usar las **dependencias nativas de issues** de GitHub — la representación canónica, visible en la UI. Agregar un edge con `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, donde `<blocker-db-id>` es el **id numérico de base de datos** del bloqueante (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, no el `#numero` ni el `node_id`). GitHub reporta `issue_dependencies_summary.blocked_by` (solo bloqueantes abiertos). Si no están disponibles las dependencias nativas, usar una línea `Blocked by: #<n>, #<n>` al principio del body del hijo — mismo patrón que ya usamos a mano en #84-89 (`## Depende de`). Un ticket queda desbloqueado cuando todos sus bloqueantes están cerrados.
- **Frontier query**: listar los hijos abiertos del mapa (`gh issue list --state open`, acotado a los sub-issues/task list del mapa), descartar los que tengan un bloqueante abierto o ya tengan asignado, el primero en el orden del mapa gana.
- **Reclamar**: `gh issue edit <n> --add-assignee @me` — la primera escritura de la sesión.
- **Resolver**: `gh issue comment <n> --body "<respuesta>"`, después `gh issue close <n>`, después agregar un puntero de contexto al Decisions-so-far del mapa.
