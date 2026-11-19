# Briefs

One brief per agent: **who it is**. Its role, its kind, its territory, who it works
with, what it never does, and its first step. It is the equivalent of the
`examples/brief.example.md` template in `fleet`.

How a brief reaches its agent, so that it loads at the start of **every** session
(including after `/clear`) instead of depending on a first prompt:

- `plan-agentes.py` installs it at `/home/agents/etc/briefs/<name>.md`, owned by
  the human, with the human's name filled in from `fleet.toml`. The agent can read
  it and cannot edit it.
- The agent's `CLAUDE.md` is a **visible symlink** to that installed copy:
  - the maestro: `/home/<agent>/maestro/CLAUDE.md` and, if it may run codex,
    `AGENTS.md` beside it, both links to `maestro.md`. Its home's own `CLAUDE.md` and
    `AGENTS.md` are the pensadero's conventions (`../reglas/conventions-pensadero.md`),
    which every session of that user loads, each agent of a línea included;
  - a role of a claude agent (`arquitecto`, `coord`): `CLAUDE.md` in the role's
    own folder (`/home/<agent>/<role>/`), from `<role>.md`;
  - a role of a codex agent (`coord`, `aparejador`): `AGENTS.md` in the role's own folder, from
    `<role>-codex.md`. codex reads the working directory's `AGENTS.md` when it is
    not inside a repository.

  Which AI user has which roles is declared in `[ai_users]` of `fleet.toml`. A
  brief is filled in for its AI user (`{{ai_user.name}}`, `{{ai_user.peers}}`), so
  one role has one AI user per provider.

`aparejador-codex.md` has no claude version: it is the architect's counterpart on
codex, and the architect runs on claude.

`coord.md` and `coord-codex.md` are one role in two vendors' words. Change them
together (see `DECISIONS.md`).

Rules shared by every claude session are not in briefs. They are in
`../reglas/conventions.md`, installed at `/home/agents/etc/conventions-<agent>.md`
and linked as `/home/<agent>/CLAUDE.md`. Claude Code loads `CLAUDE.md` files from
the working directory upwards, so every session under the agent's home gets them.
A codex agent's are `../reglas/conventions-codex.md`, linked as
`/home/<agent>/AGENTS.md`, and loaded through `~/.codex/AGENTS.md`, a link to it. The pensadero gets neither: its own conventions take their place.

Why these mechanisms, tested on 2026-09-28 with Claude Code 2.1.282:

- a `CLAUDE.md`, in the working folder or a parent folder, that is a symlink to a
  file outside the project: **loads**;
- `@AGENTS.md`, a relative import inside the project: **loads**;
- an `@/absolute/path` import of a file outside the project, or an import of a
  symlink that points outside: **does not load**.

Nothing here is in a hidden folder: `ls` shows every `CLAUDE.md` an agent gets.

Skills (`../skills/`) are for **how-to** manuals shared by several agents,
never for roles: a skill opens only when a task matches its description.
