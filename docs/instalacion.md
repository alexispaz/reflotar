# Installing the fleet

How to set the fleet up on a machine, bring it back after a reinstall, and keep it
up to date. The short path, for a first install, is `de-cero.md`; this is the full
recipe. The reasons behind every step are in `../DECISIONS.md`. Everything runs
as **you**, the human; only the plan the planner prints runs with sudo, after you
have read it.

What a reinstall keeps:

| | OS reinstall (the `/home` disk is kept) | new machine |
| :--- | :--- | :--- |
| agent homes, `~/work`, transcripts | **kept** | lost: restore from your copies |
| `/home/agents` (mailbox, tools, rules) | **kept** | recreated by the installer |
| pensadero data (`/home/<pensadero>/work`) | **kept** | lost: restore from your clones |
| users, groups, `/etc/fstab`, bind mounts | **lost**: recreated below | recreated below |

## 0. Software

What the machine must have. Written and tested on Arch Linux; on another
distribution each of these must hold, and none has been tried there yet:

- **Linux with systemd** and `machinectl` (the AI users are launched with it, each in
  its own slice), **cgroup v2** (the planner reads `/sys/fs/cgroup/user.slice/`), and
  bind mounts in `/etc/fstab`.
- **Homes under `/home/<user>`**, for you and every AI user, and `/home/agents` for
  what is shared. `useradd -m` must create them there.
- **bash**, as your shell (the planner's aliases go in your `~/.bashrc`) and the AI
  users' (tmux starts `bash -l`).
- **tmux 3.2 or newer**, Python 3.11 or newer, git, sudo, `runuser` (util-linux).
- Some features need one more program, and only they do: **bindfs** for `[machine] readable`
  (on Arch it is not in the official repositories: build it from the AUR, with
  `aur sync bindfs` and `sudo pacman -S bindfs`, or `yay -S bindfs`). Without it the
  planner leaves that feature out, whole, and says so in its report under "FEATURES
  LEFT OUT": what the feature does and how to get the program.
- `tmux`, `bash`, `ssh-agent` and `ssh-add` are run by the absolute path **your** PATH
  gives, so they must be installed system-wide, not in a folder an AI user can write.

And the AI users' tools:

- **Claude Code**, installed for the whole system, so it belongs to root and no AI
  user can change it. Where your distribution has a package (Arch), use it: keep its
  updates off (`DISABLE_UPDATES=1` in the `claude` wrapper) and update it with the
  package manager. Where it has none, install it as root in a system folder (for
  example `sudo npm install -g @anthropic-ai/claude-code`, which needs Node.js), with
  automatic updates off (`DISABLE_AUTOUPDATER=1` in the environment of every AI
  user), and update it as root. Not the per-user installer: it puts `claude` in the
  AI user's own `~/.local/bin`, where the AI user can change it.
- **Codex**, if you use it, installed **per agent**: its daemon (`codex agents`, which
  a codex coordinator needs) wants codex's own package in the agent's `~/.codex`,
  which a distribution's `/usr/bin/codex` lacks. Declare the version in `fleet.toml`
  (`[software] codex`) and, after installing the configuration (step 3), run
  `sistema/flota actualizar codex`: it installs that version as each agent, with no
  automatic updates, and checks that each still loads its rules. The planner sets
  `check_for_update_on_startup = false` in each AI user's `~/.codex/config.toml`, so
  codex does not offer to update itself; a new version goes through the steps below.

### Moving codex to a new version

codex changes between versions how it loads rules, what its sandbox allows and how
its sessions find each other, and the fleet depends on all three. 0.167 hid its
app-server from every sandbox, so `codex agents` and `codex queue` stopped working
from a codex session, and its tools `list_threads` and `send_message_to_thread`
took their place (2026-11-08). So a new version is a change like any other:

1. Change `[software] codex` in `fleet.toml`, commit, and `flota entregar` it to the
   architect.
2. `flota instalar --go`, then `flota actualizar codex`: it installs the version and
   checks that each agent still loads its rules.
3. Ask the architect to have the aparejador check, from codex, what the fleet uses:
   the rules it loads (`codex debug prompt-input`), what its sandbox may write
   (`buzon enviar`, `~/work/propuestas`), how sessions are listed and reached
   (`list_threads`, `send_message_to_thread`), opening a session from tmux, and the
   ssh to a cluster.
4. What changed, the architect fixes on a branch, and the aparejador tests it.
   Restart the codex sessions when it is installed.

## 1. Your configuration

Next to your clone of `flota` you keep your own configuration repository,
`flota-<you>` (`<you>` is your Linux user: the architect looks for that name), with
one file, `fleet.toml`: your name, your Linux user and time zone, which agents you
have (each a Linux user, with its provider and its roles), each user's resources,
and your clusters. Start from the example:

    mkdir -p ~/agents && cd ~/agents
    git clone <where your group keeps flota> flota
    mkdir flota-<you> && cp flota/ejemplo-config/fleet.toml flota-<you>/
    cd flota-<you> && git init -q -b main && $EDITOR fleet.toml && git add fleet.toml && git commit -qm "My fleet"

Keep in your configuration's README what is only yours: the numeric ids of your
users (step 2), your aliases (step 5), anything particular to your machine.

## 2. The AI users, with the SAME numeric ids after a reinstall

The installer creates the AI users on a new machine. **After a reinstall this
is the step that matters**: files on the kept `/home` disk record their owner as a
number. If an agent's user comes back with a different uid, its home belongs to
nobody, or to someone else. So, before the installer, create the groups and users
with their old ids (`ls -ln /home` shows them), groups first:

    sudo groupadd -g <gid> <agent>
    sudo useradd -u <uid> -g <agent> -M -d /home/<agent> -s /bin/bash <agent>

`-M` keeps the home that is already on the disk; on a new machine leave this step to
the installer. Do not let anything else take those ids.

## 3. Install, and every later change

    cd ~/agents/flota
    sistema/instalar          # what would change: the machine's plan and the tools'
    sistema/instalar --go     # asks, runs the plan with sudo, installs the tools

The planner (`sistema/plan-agentes.py`) changes nothing itself: it prints the
commands still missing (users, groups, homes, `/home/agents`, bind mounts, mailbox,
rules, roles, skills, `fleet.toml`, tmux, resources), and the diff of every file it
would install, with your name and time zone filled in from `fleet.toml`. The plan has
two parts. **Changes**: what is missing or wrong; read each. **Routine checks**, at
the end: what the planner cannot see, because it runs as you, and what the AI
users' tools keep private in their homes (`~/.codex`, for one) is closed to you. Each asks the system and changes nothing when all is in
place, so they appear on every run. Each is one line calling a shell function the
plan defines at its top (`carpeta`, `enlace`, `sandbox_codex`...): read the functions
once, and the lines say what they check. The header counts both
(`# changes: N, routine checks: M`), and `instalar` says "nada nuevo" when there are
only routine checks.
`herramientas/install` copies the fleet tools into `/home/agents`.

**Run them only from your own clones.** The plan runs as root, and an agent's copy
can change between your review and the run, so both refuse a source file that is not
yours or is a symlink.

When an AI user has a branch for you, `flota traer` does it all: it fetches the
branches of every clone under `~/agents`, shows each one's commits and diff, merges
the ones you accept (`--ff-only`), and hands your new `main` back. It does not install:
when `flota` or your configuration changed, it says so. `flota actualizar` is the
fleet's own update: it brings the branches of `flota` and `flota-<you>` only, then runs
`sistema/instalar --go` (even when nothing new came), and points to `flota reiniciar`.
By hand (sudo asks for your password on fetch):

    cd ~/agents/flota                                  # or ~/agents/flota-<you>
    git fetch claude
    git log --oneline main..claude/<topic>             # what the branch brings
    git diff main...claude/<topic>                     # READ ALL OF IT
    git merge --ff-only claude/<topic>                 # if it refuses, tell the agent
    sistema/instalar --go

What keeps this safe:
- **Never run git inside an agent's repository as yourself**: its `.git/config` and
  hooks could run programs as you. Never add `safe.directory` for it, and never push
  to an agent.
- **Never copy an agent's repository with `cp`**: its configuration and hooks would
  come with it.
- **Read the diff before merging.** The planner and the tools run as you; rules and
  roles are only read by agents, but they steer them.

## 4. Repositories between you and the agents

The agents have no credentials for any git remote: you are the bridge.

- **To give an AI user a repository**, or bring its copy up to date:
  `flota entregar <your <AI user> clone>` (it runs `sistema/entregar-repo ... --go`). It hands over a bundle
  (history only: none of your clone's configuration or hooks), written in the
  agent's `~/work`, never in `/tmp`, and adds the agent to your clone as a fetch-only
  remote. Later runs hand over your `main` as `<you>/main`.
- **To clone a repository an AI user created**: `flota clonar <AI user> <repo>`
  shows the commands (`sistema/clonar.py`) and runs them if you say so. A new
  repository has no `main` yet (conventions rule 12): the clone starts from the AI
  user's only branch, or the one `--rama` names; once you accept it,
  `git switch -c main`. The reading process runs as the agent
  (`uploadpack = sudo -H -u <agent> git-upload-pack`), the clone does not hardlink
  the agent's files, and a push to the agent fails on your side
  (`pushurl = /dev/null/no-push-fetch-only`).
- On a new machine, give the agents back their repositories with `entregar-repo`,
  `flota` and `flota-<you>` included for the architect. The pensadero's are repos like
  any other's (`flota entregar ~/agents/lineas pensadero`), from the clones you keep of
  them.

## 5. Launching the sessions

1. The planner prints, at the end, one alias per AI user for **your** `~/.bashrc`, of
   the form `alias t<user>='sudo machinectl shell <user>@ /usr/bin/tmux new -As
   flota'` (with your tmux's path; the pensadero's opens in its home). Each opens a
   real login session for the AI user, so it runs in its own slice with its limits.
2. Log each AI user into its tool, inside its alias: into both, for an agent with
   `providers = ["claude", "codex"]`, which goes on with the other tool when one runs
   out of tokens (`relevo`, in `COMANDOS.md`).
3. After a reboot or a crash, `sistema/flota arrancar` unlocks each working AI user's
   cluster key in your terminal, opens its tmux with its coordinator, asked to resume
   the rest, and resumes the pensadero's maestro (`flota arrancar codex` for one).
   By hand, each role in its own tmux window: `cd ~/<role> && claude -n <role>`
   (codex: `codex`), and a working session `cd ~/work/<repo> && claude -n <name>`.
4. A codex role (its coordinator, the aparejador) must start able to write its
   workspace: `/status` says `Workspace`. The planner marks codex's role folders as
   trusted in `~/.codex/config.toml`; if `/status` says `Read Only`, start it with
   `codex -s workspace-write`.

`sistema/flota` shows what you can do (`COMANDOS.md`) and what is pending.

## 6. Check that it holds

From a working agent's session:

| check | expected |
| :--- | :--- |
| `id` | its own group, `agents`, `buzon` |
| `umask` | `0002` |
| `command -v buzon` | `/home/agents/bin/buzon` |
| `ls /home/agents/pares/<other agent>` | lists the other agent's work |
| `touch /home/agents/pares/<other agent>/x` | *Permission denied* |
| `touch /home/agents/bin/x` | *Permission denied* |
| `ls /home/<pensadero>` | *Permission denied* |
| `cat /proc/$(tmux display -p '#{pid}')/cgroup` | `/user.slice/user-<its uid>.slice/...`, not yours |

Then ask each one something it can only know from its rules, without reading any
file: any session, "¿qué dice la regla 10 de las convenciones?" (the mailbox rule);
a coordinator, "¿cuál es tu primer paso?"; the maestro (in `~/maestro`), "¿cuáles son
tus reglas?".

For codex, from the AI user's shell and **outside** codex (inside its sandbox the
command fails with "Read-only file system"):

    cd ~ && codex debug prompt-input | grep -c "Fleet conventions"          # 1 or more
    cd ~/<role> && codex debug prompt-input | grep -c "Brief: <role>"       # 1 or more
    codex debug prompt-input | grep -c "{{"                                 # 0: no template left

**Repeat these questions after every upgrade of an agent's tool.** They depend on
each tool loading its instruction files and following symlinks; if an upgrade
changes that, the rules stop arriving without any error.
