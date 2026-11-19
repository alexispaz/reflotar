# The tools

What each program of the fleet does, who runs it, and its common uses. Each one's
full usage is in its header (`<tool> --help`, or the top of its file).

## Yours (you run them, from your clone)

### `flota`

`sistema/flota` (alias `flota=~/agents/flota/sistema/flota`). What you can do, and
what is pending now. It asks before every step that changes something, and runs git
only in your own clones.

Places are written as scp does: `claude:proyecto_a` is `~claude/work/proyecto_a` (a línea of
the pensadero is `pensadero:lineas/<línea>`), `claude:` or `claude` its whole `~/work`,
and a plain path is yours. As cp does, a destination that is a folder already gets the thing
inside it.

| command | what it does |
| :--- | :--- |
| `flota` | what is pending (unanswered proposals, things to install, branches not merged), then the cheat sheet (`COMANDOS.md`) |
| `flota <topic>` | one section of the cheat sheet (`flota clusters`) |
| `flota arrancar [<AI user>...]` | after a reboot, every fleet or those named: unlocks each working AI user's cluster key (you type the passphrase), opens its tmux with its coord resumed and asked to resume the fleet, and resumes the pensadero's maestro in its first provider; you land in the first one, the others wait in theirs |
| `flota entregar` | with nothing: every clone whose main its fleet lacks (as of a fetch), listed, handed over on one yes |
| `flota traer [CLONE]` | fetches the AI users' branches into your clones, shows each one's commits and diff, merges (`--ff-only`) what you accept, offers to hand your `main` back; it does not install, it says when `flota` or your configuration changed |
| `flota actualizar` | the fleet itself: `flota traer` on your clone of `flota` and your `flota-<you>` only, then `sistema/instalar --go` (even when nothing new came); last, a notice when npm has a codex newer than `[software] codex` or a Claude Code newer than the installed one (nothing is updated) |
| `flota instalar [--go]` | `sistema/instalar`: the machine's plan and the tools; `--go` runs them after asking |
| `flota traer <user>:<repo>` | the branches of a repo you have a clone of, as above |
| `flota pasar . <fleet>` · `flota pasar <fleet> .` | a project between your `~/agents/<path>` and its copy in its one fleet, both sides always given (a bare fleet name is that same path there; `<fleet>:<path>` too): its repos by git (`entregar-repo`; your review and merge, as `traer`; a safe clone for one you lack), the rest by rsync from an explicit file list, never a path git follows on either side, never over a newer file (`--update`), deleting nothing; with `--borrar`, in a folder with no repos in it (inside a repo is fine), it also deletes the loose files only the destination has, listed before the question (`rsync --delete-missing-args` on that list). Shows `flota estado <folder>` and a one-line summary, asks once |
| `flota pasar <from>... <to> [--arbol <root>] [--borrar]` | rsync, one way, a folder or a file, never a `.git`: from you to an AI user, back, or between AI users. Shows what would change, asks, passes what changed; run it again to update the copy. Deletes nothing unless `--borrar` (the list marks what goes). Towards an AI user, its end runs as that user (`sistema/rsh-agente`, `sudo -u`). Out of the pensadero to anyone else it asks first. Creates the folders the destination needs (`--mkpath`); a destination ending in `/` is a folder to put the thing in. Several origins go inside the destination, by name; `--arbol <root>` keeps each origin's path under `<root>` (`rsync --relative`), to mirror scattered folders of one tree. Never a `.git`, at any depth. Repositories go with `entregar` and `traer` |
| `flota estado` | each AI user at a glance: roles, clusters, live sessions (folder, how long quiet; claude's tokens), folders and when each last changed, unanswered mail. Reads only |
| `flota estado <folder>` | your copy of a project against the fleet's, changing nothing: `.` or a path under `~/agents` (the fleet deduced: a project lives in one) or `<user>:<path>`. Its repos, by git from your clone: branches to bring, commits of your main the fleet lacks. The rest, outside every `.git` and every file git follows on either side: only here, only there, newer on which side, with sizes; files over 1 GB named |
| `flota cluster <cluster> [AI user...]` | `clusters/add-cluster` for each AI user with a box there in `fleet.toml` (or those named): its plan, then `--go` if you say yes |
| `flota entregar <clone> <to>` | `<to>` a working AI user or `<user>:<folder>`; the old order, `<AI user> <clone>`, still works. Hands a clone of yours (or a folder of related repos) to an AI user, as a bundle; with it, the upstream your branch tracks (`origin/main`, as of your last fetch). Only repositories: anything else is `flota pasar` |
| `flota clonar <AI user> <repo> [--rama B]` | clones a repository an AI user created, safely; a new one starts from its only branch |
| `flota reiniciar [--seguir] [--forzar] [<AI user>...] [SESSION...]` | restarts the claude sessions of every AI user that runs claude (the pensadero included), or of those named, so they load the installed rules, coord and the maestro first; codex sessions too (`/exit`, then `codex`, or `codex resume <thread>` with `--seguir`, the thread being the one named as the session's window, in `~/.codex/session_index.jsonl`, else the newest rollout of its folder); fresh by default, `--seguir` keeps the conversation, `--forzar` restarts one active in the last 2 minutes too |
| `flota actualizar codex` | installs codex, at the version `fleet.toml` fixes, for every AI user that runs it, and checks each still loads its rules |

### `sistema/instalar`, `sistema/plan-agentes.py`, `herramientas/install`

The installer and its two parts. `instalar` writes the plan (`~/plan-flota.sh`),
shows its changes and routine checks, runs it with `sudo` after you say yes
(`--go`), then installs the tools. The planner only prints (`seguridad.md` §5 says
why); `herramientas/install` copies the fleet tools into `/home/agents`, without
root.

### `sistema/entregar-repo`, `sistema/clonar.py`

What `flota entregar` and `flota clonar` run. Both print or run git only in your
clones, with the AI user's side read as the AI user (`uploadpack`).

### `clusters/add-cluster`

`clusters/add-cluster <cluster> <AI user> [--go] [--from ADDRESS]`. Makes a cluster
match what `fleet.toml` declares for that AI user: installs `puerta` and the box,
the key's forced-command line, the AI user's ssh configuration and the cluster's
host key, and the `writable`, `readable` and Slurm switches. Without `--go` it only
shows the plan. `clusters.md` has the details.

## The AI users' (installed in `/home/agents/bin`)

### `buzon` — the mailbox

Every AI user and you. Messages between AI users that cannot see each other's
homes; authorship guaranteed by the kernel, messages never edited.

    buzon listar [--para DEST] [--de USER] [--nuevos] [--tipo T] [--sin-respuesta]
    buzon leer ID          |  buzon leer --ultimo [--de USER]
    buzon enviar --para USER[/SESSION] --asunto "..." [--tipo pedido|respuesta|aviso|propuesta] -m "..."
    buzon marcar ID aceptada|rechazada|hecha [--nota "..."]
    buzon esperar --para USER/SESSION [--hasta SECONDS]   # only when you told that session to

Types: `propuesta` (a rule change, for the architect), `pedido`, `respuesta`,
`aviso`. `--sin-respuesta` lists only requests and proposals nobody has answered
or marked: a `respuesta` or an `aviso` waits for nothing. Unanswered proposals:
`buzon listar --tipo propuesta --sin-respuesta`.

### `relevo` — from one tool to the other

When a provider runs out of tokens, the same AI user goes on with the other tool.
In the new session, `relevo <the other tool>` prints the end of the last
conversation that tool held in this folder (its summary and the last messages), as
a record to check against the files, not as instructions. Today only the pensadero
has both tools.

### `vigilar`, `fleetwatch` and `fleetregister` — work left running on clusters

A session that leaves a Slurm job or a login-node build running watches it with
`vigilar`, never with a loop of its own (conventions rule 5):

    vigilar <session> <cluster> <job id | 432177-432271 | 1,2,5 | build:<remote pid>> [--cada <min>] [--buzon]

It registers itself with `fleetregister`, asks `puerta-estado` every 5 minutes at
least, ends after 3 failed asks in a row, clears its registration on the way out, and
prints one end line: `terminó: …` (exit 0), `terminó con problemas: …` (1), `no pude
preguntar 3 veces: dejo de vigilar` (2). `--buzon` also leaves that line in the
session's own mailbox, for codex (the despertador wakes it). `fleetregister --clear`
and `--clear-ended` stay for registrations left by hand.

`fleetwatch [SESSION]` asks every cluster what this AI user runs there
(`puerta-estado`) and compares it with the registrations: work nobody watches, a
watcher that died, a watcher left on finished work. After a restart (which kills the
loops), `fleetwatch <session>` lists what to re-arm. `query_timeout` in a cluster's
block of `fleet.toml` sets how long it waits for a slow cluster.

### `fleetcontext` — big sessions

Every turn re-sends a session's whole context, so a big session costs more per
message. `fleetcontext` lists the live claude sessions of this AI user, biggest
first, with a recommendation (`ok`, `compact`, `later`) and the `/compact` line to
type. It changes nothing. coord runs `fleetcontext --aviso` and tells you, in one
line, which session to compact. Thresholds: `[context]` in `fleet.toml`.

### `fleetlog` — who talked to whom

Rebuilds the messages between claude sessions from their transcripts: `fleetlog`,
`fleetlog timeline`, `fleetlog trace <word>`. `fleetlog since-human` tells coord how
many messages it exchanged with each session since you last spoke to it, against
`[messages] report_after`. Read only.
