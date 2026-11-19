# From zero to flota

The short path: from a Linux machine with nothing on it to a fleet you can talk to,
and the operations you will use every day. Each step links to the full recipe in
`instalacion.md` when you need more.

## What you get

```text
you (your own Linux user, never reachable by the agents)
 │
 ├── claude     an AI user: Claude Code sessions run as this Linux user
 │    ├── ~/coord        the coordinator: you talk to it; it proposes and supervises
 │    ├── ~/arquitecto   the architect: builds and repairs the fleet itself
 │    └── ~/work/<repo>  working sessions, one per project, each reporting to coord
 ├── codex      an AI user running Codex (optional): its own coordinator, and the
 │              aparejador, who reviews the architect's changes on the codex side
 └── pensadero  an AI user apart, a fleet for thinking: sees nobody, nobody sees it
      ├── ~/maestro              the maestro: thinks with you, weighs the líneas, opens them
      ├── ~/work/lineas/<línea>  one repo per línea; one agent each, when you open one
      └── ~/work/<repo>          documents you give it (classes, texts), repos too
```

Each AI user is a Linux user with its own home, its own share of CPU and memory, and
no way into your files. You are the bridge for everything that matters: you approve
what starts, you merge their branches, you install their changes, and only you
unlock the key that opens the clusters. `seguridad.md` explains how each part holds.

The words used everywhere: an **AI user** is one of those Linux users; a
**session** is one running claude or codex; a **role session** has a brief you
installed (coord, arquitecto, aparejador, maestro); a **working session** has
none and works on a project; a **task** is an objective coord gives a working
session.

## 1. Before you start

- A Linux machine with systemd, cgroup v2, bash, tmux 3.2+, Python 3.11+, git and
  sudo (the full list, and what is untested: `instalacion.md` §0). Written on Arch.
- **Claude Code installed for the whole system**, owned by root, with its automatic
  updates off: an AI user must not be able to change the program it runs.
- A Claude plan for the claude AI users; a ChatGPT plan if you add codex.

## 2. Your configuration

Two repositories side by side: `flota` (the product, the same for everyone) and
`flota-<you>` (one file, `fleet.toml`: who you are and what your fleet has).
`<you>` is your Linux user (`flota-ana` for `ana`): the architect looks for that name.

    mkdir -p ~/agents && cd ~/agents
    git clone <where your group keeps flota> flota
    mkdir flota-<you> && cp flota/ejemplo-config/fleet.toml flota-<you>/
    cd flota-<you> && git init -q -b main && $EDITOR fleet.toml

In `fleet.toml`, fill in:

- `[human]`: your name, your Linux user, your time zone;
- `[ai_users]`: which AI users you want and their roles. Start with the example,
  or with just `claude` (`coord`, `arquitecto`) and add the rest later;
- `[resources]`: how much CPU and memory each may take; your session comes first.

Then commit it, on `main`: `flota entregar` hands the architect that branch.

    git add fleet.toml && git commit -qm "My fleet"

## 3. Install

    cd ~/agents/flota
    sistema/instalar          # shows what it would do; changes nothing
    sistema/instalar --go     # asks, then runs the plan with sudo

The plan is a list of shell commands. Read the **changes** (users, groups, folders,
the rules each AI user loads); the **routine checks** at the end change nothing when
all is in place. At the end it prints, under "BY HAND", what is left to you:

- the aliases for your `~/.bashrc`: one per AI user (`tclaude`, `tcodex`,
  `tpensadero`) and `flota`;
- **log out of your desktop session and back in.** The plan added you to the AI
  users' groups, and Linux applies a new group only to a new login: a new terminal
  is not enough. Until then `flota entregar` and `flota traer` stop and say so. To go
  on in the same terminal: `exec su -l $USER`.

## 4. Log each AI user into its tool

    tclaude                   # a tmux session as the claude user, in its own slice
    claude                    # log in once (/login), then /exit

If you use codex: `flota actualizar codex` installs it for each codex AI user at the
version `fleet.toml` fixes; then `tcodex` and `codex` to log in. The pensadero logs
into each tool it may use.

## 5. Check that it holds

From `tclaude`:

    id                                    # its own group, agents, buzon
    touch /home/agents/bin/x              # Permission denied
    ls /home/<you>                        # Permission denied

and ask a session something only its rules say: "¿qué dice la regla 10 de las
convenciones?". The whole list: `instalacion.md` §6.

## 6. Start the fleet

    flota arrancar

It asks for the clusters' key passphrase (with no key yet, it says so and goes on),
opens tmux as claude with the coordinator, and tells it "Retomá la flota". From then
on you talk to **coord**: give it an objective, it proposes which sessions to start
and how far, and nothing starts until you say yes.

## 7. Give it work, and take the work back

    flota entregar ~/agents/<repo> claude     # hand a clone of yours to the claude AI user

Tell coord the objective. The working sessions commit on branches named
`claude/<topic>`; they never push and have no credentials. When something is ready:

    flota traer                               # fetch, show each branch's diff, merge what you accept
    flota instalar --go                       # only if it changed flota or your fleet.toml

Then push from your own clone, as you always do.

## 8. Clusters (optional)

1. In `tclaude`: make the AI user's key, **with a passphrase**:
   `/usr/bin/ssh-keygen -t ed25519`.
2. From your clone: `clusters/add-cluster <cluster> claude` (shows the plan), then
   `--go`. It installs a box on the cluster that only that key can open.
3. Paste the block it prints into `fleet.toml`, commit, `flota instalar --go`.
4. `flota arrancar` unlocks the key for the session (you type the passphrase).

The details, and what the box does not protect (Slurm jobs): `clusters.md`.

## Everyday operations

| I want to… | do |
| :--- | :--- |
| see what is pending (branches, proposals, things to install) | `flota` |
| start everything after a reboot | `flota arrancar` |
| give the fleet an objective | tell coord, in its window |
| know who is waiting for me | ask coord: "¿quién me espera?" |
| bring the agents' work home | `flota traer` |
| install a change to the fleet or to `fleet.toml` | `flota instalar`, then `flota instalar --go` |
| restart claude sessions so they load new rules | `flota reiniciar` (not one waiting on a job) |
| hand a repo to an AI user | `flota entregar <your <AI user> clone>` |
| clone a repo an AI user created | `flota clonar <AI user> <repo>` |
| have a session read a message | tell it: "leé lo que te mandó X en el buzón" |
| let the fleet improve its own rules | tell coord "procesar lo aprendido", then the architect "procesá lo aprendido" |
| open / close the clusters | `flota arrancar` / in `tclaude`, `ssh-add -D` |
| see what runs on the clusters | in `tclaude`: `fleetwatch` |
| shrink a big session | `/compact` in its window; coord tells you which |
| see how much plan is left | `/usage` in a claude session |

The full cheat sheet, in Spanish: `COMANDOS.md` (`flota` prints it).
