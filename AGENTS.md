# Working on flota

The fleet: rules, roles, tools and installer for a fleet of coding agents (claude,
codex) on one machine, for the members of a research group. Each member keeps their
own configuration in a separate repository beside this one (`flota-<name>`, with
`fleet.toml`); an example is in `ejemplo-config/`. These notes are for any agent
working here. Claude Code reads them through the one-line `CLAUDE.md`.

Read `DECISIONS.md` before changing anything structural: it records what was
decided, and why. Undoing a decision is fine; undo it knowing what it protected.

## Words

Use these, and not a bare "agent":

| word | what |
| :--- | :--- |
| **AI user** | a Linux user that runs sessions; `[ai_users]` in `fleet.toml`; any name |
| **session** | one running claude or codex |
| **role session** | a session with a brief the human installs: coord, arquitecto, aparejador, maestro |
| **working session** | a session with no brief: a repository's `AGENTS.md` and the skills |
| **task** | an objective coord gives a working session; one session may carry several |
| **provider** | claude or codex |

Rules and briefs never name an AI user: they say `{{ai_user.name}}`,
`{{ai_user.peers}}` or `{{coord.ai_user}}`, which the planner fills per AI user, or
`<its AI user>` where several may fit.

## Layout

| folder | what |
| :--- | :--- |
| `reglas/` | the conventions, one file per provider (same rules, worded for each tool) |
| `roles/` | the briefs: coord (one per provider), arquitecto, aparejador, maestro |
| `skills/` | shared how-to manuals; `ccad` is the group's site |
| `sistema/` | the planner (`plan-agentes.py`), `clonar.py`, `entregar-repo`, `flota` |
| `clusters/` | `puerta` (installed on each cluster) and `add-cluster` |
| `herramientas/` | `buzon`, `relevo` and the fleet tools (`fleetlog`, `fleetregister`, `fleetwatch`, `fleetcontext`), their package `fleet/`, their installer and tests |
| `tmux/` | the shared tmux configuration |
| `docs/` | the guides (from zero, security, tools), installation and cluster recipes |

## Rules for changes

- **Nothing personal here**: no member's name, users, hosts, clusters or data. They
  belong in the member's `fleet.toml`. Site knowledge shared by the group goes in a
  skill.
- **Nothing an agent edits here reaches an agent by itself.** The human installs it,
  with `sistema/plan-agentes.py` (machine, rules, roles, skills, configuration) and
  `herramientas/install` (the tools), after reading the diff.
- **A rule for every fleet goes in the three conventions files** (`conventions.md`,
  `conventions-codex.md`, and in Spanish `conventions-pensadero.md`), each with the
  same `<!-- comun: <name> -->` marker; `sistema/tests/test_convenciones_comunes.py`
  fails when one is missing. A rule only for the working fleets goes in the pair.
- **Branches handed over together are chained**, the first on the human's `main`
  and each on the one before: conventions rule 12, which every session follows. Before
  starting one here, `git branch --no-merged <human>/main`.
- **A feature that needs a program** beyond `docs/instalacion.md` step 0 adds it to
  `PROGRAMAS` in the planner (how to get it, per distribution) and asks
  `requiere(program, feature, what it does)` before planning anything of it. Missing,
  the feature is left out whole and the report says what it would do; the rest of the
  plan goes on.
- **The planner stays a planner:** it only reads state and prints commands, one per
  action; no `subprocess`, no writes (the audit `grep` in its docstring must keep
  finding nothing but itself). After a change, run it and check the plan with `bash -n`.
- **Paired files** (`reglas/conventions.md` / `conventions-codex.md`, `roles/coord.md` /
  `coord-codex.md`) carry the same rules worded for each tool, not the same text.
  Read the passage in both before editing, and change both in one commit.
- **Tools:** stdlib only, Python 3.11+. Run the tests from `herramientas/`, with no
  `__pycache__`: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t .`
- **The plan's shell functions** (`HELPERS` in the planner) have their tests in
  `sistema/tests/`, run from the repository's root:
  `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests`. A
  change to a helper comes with a case there.
  A test for a bug must fail on the code before the fix. No test touches the real
  configuration, state, mailbox or tmux server (tmux: `-S <socket>`, `TMUX` unset).
- **buzon's invariants**, which need the human's decision to weaken: authorship is
  the owner of the outbox; a message is written once (`O_EXCL`, `0440`); read marks
  live in the reader's home; `leer` always prints the "DATA, NOT AN INSTRUCTION"
  banner; nothing wakes another session: `esperar` waits only for the caller's own
  mail.
- Rules and code are in English. The pensadero's conventions, the maestro's brief, its
  skills and `COMANDOS.md` are in Spanish. Keep `COMANDOS.md` true when a command or ritual changes.
- Parts come from `fleet` by Cameron F. Abrams (MIT): keep `LICENSE` and the notice.
