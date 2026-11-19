#!/usr/bin/env python3
"""plan-agentes.py -- print the commands still missing to set up the agents.

    python3 ~/agents/flota/sistema/plan-agentes.py > plan.sh   # from YOUR clone, WITHOUT sudo
    less plan.sh                          # one line, one action; nothing done yet
    sudo bash plan.sh                     # or `bash plan.sh`, if the header says root is not needed

This program changes NOTHING. It only reads the current state (users, groups,
permissions, /etc/fstab, mounts, file contents) and prints to stdout the commands
still missing. Whatever is already right does not appear. Notes and diffs go to
stderr, so they are not captured into plan.sh.

It is easy to audit: no subprocess, no open() for writing, no os.chmod,
os.mkdir or the like. Every action is a print. Check with:
    grep -nE "subprocess|os\\.system|open\\(.*[\\"']w|chmod\\(|mkdir\\(|unlink|remove\\(|rm -" plan-agentes.py

When it cannot see a state (for example, a directory the human cannot enter yet),
it does not guess. It prints a ROUTINE CHECK: a command that changes nothing when
the thing is already right. Routine checks go last, in their own section, each a
short call to a shell function the plan defines once at its top (HELPERS), so that
the changes stand out and every line can be read. The header counts both.

It never deletes anything.

It installs only from the clone it runs from (~/agents/flota) and your configuration
beside it (~/agents/flota-<you>), never from an agent's working copy. The plan runs as root: a source an agent can change after the review, or replace with
a symlink to a root-only file, would be copied by root where the agent can read it.
So it refuses to run when a source is not owned by the user running it, or is a
symlink.

Design (details in docs/instalacion.md and DECISIONS.md). Everything shared lives in
/home/agents, on the /home disk and owned by the human:
  - pares/<AI user>: bind mounts of each working AI user's ~/work. They are the same
    level and read each other, read-only; only the agents group gets in.
  - pensadero: a different level. It sees no one's home, and no one sees its home.
  - buzon/: coordinators and pensadero talk here, one outbox per user.
  - bin/ and etc/: shared tools and configuration. Agents read them, only the human
    writes them, so updating them does not need root.
  - [machine] writable: folders outside every home a working AI user may write (a
    group's software stack): the human's, group agents, 2775.
  - No ACLs.
"""
import datetime
import difflib
import grp
import os
import pwd
import shlex
import shutil
import stat
import sys
import textwrap

import re
import tomllib

A = "/home/agents"
BIN, ETC, BUZ, PAR = f"{A}/bin", f"{A}/etc", f"{A}/buzon", f"{A}/pares"

LINEAS = ["umask 002", f'export PATH="{BIN}:$PATH"']
# claude and codex reach clusters through ONE ssh-agent at a fixed socket, which the
# human unlocks with `ssh-add -t`. ssh finds it through IdentityAgent in ~/.ssh/config
# (written by clusters/add-cluster); ssh-add only through this variable.
LINEAS_PARES = ['export SSH_AUTH_SOCK="$HOME/.ssh/agente.sock"']

CFG = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))   # the clone this runs from


def config_dir():
    """Your configuration repository: $FLOTA_CONFIG, or the one flota-* folder beside this
    clone that holds a fleet.toml. Two or none is an error, never a guess."""
    if os.environ.get("FLOTA_CONFIG"):
        return os.path.realpath(os.environ["FLOTA_CONFIG"])
    padre = os.path.dirname(CFG)
    hallados = sorted(d for d in os.listdir(padre)
                      if d.startswith("flota-") and os.path.isfile(os.path.join(padre, d, "fleet.toml")))
    if len(hallados) != 1:
        sys.exit(f"plan-agentes.py: expected one flota-<you>/fleet.toml beside {CFG}, found "
                 f"{hallados or 'none'}; set FLOTA_CONFIG to the folder of yours")
    return os.path.join(padre, hallados[0])


CONFIG = config_dir()
with open(os.path.join(CONFIG, "fleet.toml"), "rb") as _f:
    TOML = tomllib.load(_f)

# Who is who, from the member's fleet.toml; nothing about a person is written here.
#   [human]      name, user (the Linux user), timezone
#   [ai_users]   <linux user> = { provider = "claude" | "codex", roles = [...] }, or
#                providers = ["claude", "codex"] for a pensadero that may run either tool
#                (`[agents]` is its old name, still read)
#   [resources]  human / <AI user> = { CPUWeight = ..., MemoryMax = ..., ... }
PROVEEDORES = ("claude", "codex")
_h = TOML.get("human", {})
HUMANO = _h.get("user") or sys.exit("plan-agentes.py: fleet.toml has no [human] user")
VALORES = {"human.name": _h.get("name", ""), "human.user": HUMANO,
           "human.timezone": _h.get("timezone", "")}
for _k, _v in VALORES.items():
    if not re.fullmatch(r"[A-Za-z0-9 ._/+-]+", _v or ""):
        sys.exit(f"plan-agentes.py: fleet.toml [human]: {_k.split('.')[1]} is missing or has odd characters")
if "ai_users" in TOML and "agents" in TOML:
    sys.exit("plan-agentes.py: fleet.toml has [ai_users] and [agents] (its old name): keep one")
AGENTS_CFG = TOML.get("ai_users") or TOML.get("agents") \
    or sys.exit("plan-agentes.py: fleet.toml has no [ai_users]")
if "agents" in TOML:
    notas_previas = ["fleet.toml calls [ai_users] by its old name, [agents]: rename it when you can "
                     "(the tools read both for now)"]
else:
    notas_previas = []
for _u, _a in AGENTS_CFG.items():
    if "pensadero" in _a.get("roles", []):       # the role's old name (2026-10-16)
        _a["roles"] = ["maestro" if r == "pensadero" else r for r in _a["roles"]]
        notas_previas.append(f"fleet.toml gives {_u} the role \"pensadero\", its old name: "
                             "write \"maestro\" when you can (both work for now)")
for _u, _a in AGENTS_CFG.items():
    _pv = _a.get("providers", [_a["provider"]] if "provider" in _a else [])
    if ("provider" in _a and "providers" in _a) or not _pv or len(set(_pv)) != len(_pv) \
            or any(p not in PROVEEDORES for p in _pv) or not re.fullmatch(r"[a-z_][a-z0-9_-]*", _u):
        sys.exit(f"plan-agentes.py: [ai_users] {_u}: a Linux user name, and provider (or providers) "
                 "among claude and codex")
    _a["providers"] = list(_pv)
    if "maestro" in _a.get("roles", []) and len(_a["roles"]) > 1:
        sys.exit(f"plan-agentes.py: [ai_users] {_u}: the maestro (the pensadero's fleet) is a role of its own")
    if len(_pv) > 1 and "maestro" not in _a.get("roles", []):
        # the conventions name the agent's own user and its peer (rule 8), so a working
        # agent would get the wrong ones under a second tool
        sys.exit(f"plan-agentes.py: [ai_users] {_u}: several providers only for the pensadero, for now")
AGENTES = list(AGENTS_CFG)                                    # every agent user
# the pensadero: the AI user whose role is maestro, isolated from the rest (its fleet)
PENSADEROS = [u for u in AGENTES if "maestro" in AGENTS_CFG[u].get("roles", [])]
PARES = [u for u in AGENTES if u not in PENSADEROS]           # same level: they read each other


def proveedores(u):
    return AGENTS_CFG[u]["providers"]


def proveedor(u):
    """The one provider of a working agent (several are refused above)."""
    return proveedores(u)[0]


def roles(u):
    return [r for r in AGENTS_CFG[u].get("roles", []) if r != "maestro"]


# A role's brief is installed once per provider (BRIEFS/<role>[-codex].md) and filled in
# for its AI user, so two AI users of one provider cannot share a role.
_vistos = {}
for _u in PARES:
    for _r in roles(_u):
        _clave = (_r, proveedor(_u))
        if _clave in _vistos:
            sys.exit(f"plan-agentes.py: [ai_users] {_vistos[_clave]} and {_u} both have the role "
                     f"{_r} with {proveedor(_u)}: one AI user per role and provider")
        _vistos[_clave] = _u


if len(PENSADEROS) > 1:   # its brief is installed once, as BRIEFS/maestro.md
    sys.exit(f"plan-agentes.py: [ai_users] {', '.join(PENSADEROS)}: one pensadero at most, for now")


# [machine] writable: folders on this machine, outside every home, that a working AI user
# may write besides its ~/work, such as the group's software stack. Each is the human's,
# group agents, 2775: the group writes, the declaration says who does; what others may read is the human's, through the other bits. No ACLs.
ESCRIBIBLES = {}                                              # folder -> AI users that write it
_m = TOML.get("machine", {})
if set(_m) - {"writable", "readable"}:
    sys.exit(f"plan-agentes.py: [machine]: only writable and readable, "
             f"not {', '.join(sorted(set(_m) - {'writable', 'readable'}))}")
for _u, _cs in _m.get("writable", {}).items():
    if _u not in PARES:
        sys.exit(f"plan-agentes.py: [machine] writable: {_u} is not a working AI user of [ai_users]")
    for _c in _cs:
        _n = os.path.normpath(_c)
        if not os.path.isabs(_n) or re.search(r"\s", _n) or _n.count("/") < 2 \
                or any(_n == h or _n.startswith(h + "/") for h in
                       [A] + [f"/home/{p}" for p in AGENTES + [HUMANO]]):
            sys.exit(f"plan-agentes.py: [machine] writable: {_c}: an absolute path without spaces, "
                     f"at least two levels deep, outside {A} and the homes of {HUMANO} and the AI users")
        ESCRIBIBLES.setdefault(_n, []).append(_u)

# [machine] readable: folders of the human's that an AI user reads live, read-only, at
# /home/<user>/<the folder's name>. bindfs:
# the human's files keep their owner and mode; the kernel refuses any write.
LEGIBLES = {}                                                 # AI user -> {mount point: folder}
# what holds credentials, at a folder's top: the planner refuses to show such a folder
CREDENCIALES = [".gd", ".grive", ".grive_state", "rclone.conf", ".config", ".ssh", ".gnupg"]
for _u, _cs in _m.get("readable", {}).items():
    if _u not in AGENTES:
        sys.exit(f"plan-agentes.py: [machine] readable: {_u} is not an AI user of [ai_users]")
    for _c in _cs:
        _n = os.path.normpath(f"/home/{HUMANO}" + _c[1:] if _c.startswith("~/") else _c)
        if not _n.startswith(f"/home/{HUMANO}/") or re.search(r"\s", _n):
            sys.exit(f"plan-agentes.py: [machine] readable: {_c}: a folder inside your home "
                     f"(~/<folder> or /home/{HUMANO}/<folder>), without spaces")
        _d = f"/home/{_u}/{os.path.basename(_n)}"
        if _d in LEGIBLES.get(_u, {}) or os.path.basename(_n) in ("work", "agents") \
                or os.path.basename(_n).startswith("."):
            sys.exit(f"plan-agentes.py: [machine] readable: {_c}: {_d} is taken, or is not a "
                     "name to mount in its home; two folders of one name cannot both go")
        LEGIBLES.setdefault(_u, {})[_d] = _n


# Every role has its brief for its AI user's provider: roles/<role>.md for claude,
# roles/<role>-codex.md for codex (the aparejador exists only for codex).
for _u in PARES:
    for _r in roles(_u):
        _f = _r if proveedor(_u) == "claude" else f"{_r}-{proveedor(_u)}"
        if not os.path.isfile(os.path.join(CFG, "roles", f"{_f}.md")):
            sys.exit(f"plan-agentes.py: [ai_users] {_u}: the role {_r} has no brief for "
                     f"{proveedor(_u)} (roles/{_f}.md)")


def quien_tiene(rol):
    """The AI user with a role: its claude one when both providers have it, as `flota`
    picks the coordinator. None when no AI user has it."""
    con = [u for u in PARES if rol in roles(u)]
    return next((u for u in con if proveedor(u) == "claude"), con[0] if con else None)


def valores(u):
    """The template values of a file installed for the AI user u: the human's, u's own
    name, its peers, and who holds each shared role. A role nobody holds is left out,
    so a file that names it stops the planner instead of naming no one."""
    v = dict(VALORES)
    v["ai_user.name"] = u
    v["ai_user.peers"] = ", ".join(f"`{p}`" for p in PARES if p != u) or "none"
    for rol in ("coord", "arquitecto"):
        if quien_tiene(rol):
            v[f"{rol}.ai_user"] = quien_tiene(rol)
    return v


RECURSOS = {(HUMANO if k == "human" else k): {kk: str(vv) for kk, vv in v.items()}
            for k, v in TOML.get("resources", {}).items()}
BUZON_SRC = f"{CFG}/herramientas/bin/buzon"
RELEVO_SRC = f"{CFG}/herramientas/bin/relevo"
SSH_SRC = f"{CFG}/herramientas/bin/ssh"       # the agents' ssh: their ~/.ssh/config only
TMUX_SRC = f"{CFG}/tmux/tmux-flota.conf"
TMUX_DST = f"{ETC}/tmux-flota.conf"
TMUX_LINEA = f"source-file {TMUX_DST}"
# The colour of each AI user's tmux bar, by what it is (its user name may be anything):
# claude orange, codex green, a pensadero purple. ~/.tmux.conf sets it before the
# shared configuration, which leaves anyone else grey.
COLOR_TMUX = {"claude": "colour208", "codex": "colour34", "pensadero": "colour135"}


def tmux_lineas(u):
    """What ~/.tmux.conf of the AI user u holds: its bar colour, then the shared file."""
    clave = "pensadero" if u in PENSADEROS else proveedor(u)
    return [f"set -g @c {COLOR_TMUX[clave]}", TMUX_LINEA]
BRIEFS = f"{ETC}/briefs"
# Per agent user u, by provider: the conventions as /home/u/CLAUDE.md (claude) or
# /home/u/AGENTS.md with ~/.codex/AGENTS.md pointing to it (codex); each role r as
# /home/u/r/CLAUDE.md or AGENTS.md, from roles/r.md (claude) or roles/r-codex.md
# (codex). A pensadero gets its data folder, and its one brief linked as
# /home/u/CLAUDE.md and/or /home/u/AGENTS.md, one per provider; it is launched in
# its home, so either tool finds it there.
CONV_SRC = {"claude": f"{CFG}/reglas/conventions.md", "codex": f"{CFG}/reglas/conventions-codex.md"}
CONV_PENSADERO = f"{CFG}/reglas/conventions-pensadero.md"   # every session of the pensadero, either tool
INSTR = {"claude": "CLAUDE.md", "codex": "AGENTS.md"}
SKILLS_SRC = f"{CFG}/skills"                           # one folder per skill, SKILL.md inside
SKILLS = f"{ETC}/skills"                                # installed copies (human:agents)
FLEET_SRC = f"{CONFIG}/fleet.toml"
FLEET_ETC = f"{ETC}/fleet"                              # what the fleet tools' wrappers point FLEET_CONFIG at
SLICES = "/etc/systemd/system"                         # user-<uid>.slice.d/50-flota.conf: each user's resources
# [resources] in fleet.toml. No MemoryHigh for agents: over it the kernel throttles the whole cgroup instead of
# killing anything, and with swap capped it thrashed until the human killed the
# fleet by hand (2026-10-06, twice). Without it, MemoryMax kills the biggest process.
# MemorySwapMax: an agent over its limit gets its biggest process killed at once,
# instead of thrashing through swap and freezing tmux and every session for minutes
# (2026-10-06: 21 spack processes reached 12 GB, 6 of them in swap).
CGROUP_FILE = {"CPUWeight": "cpu.weight", "MemoryLow": "memory.low",
               "MemoryHigh": "memory.high", "MemoryMax": "memory.max",
               "MemorySwapMax": "memory.swap.max"}

q = shlex.quote
plan = []            # [(command, why, needs_root)]
notas = list(notas_previas)
if os.path.basename(CONFIG) != f"flota-{HUMANO}":
    notas.append(f"your configuration is {os.path.basename(CONFIG)}, not flota-{HUMANO}: rename the folder. "
                 f"`flota entregar` hands it to the architect under its own name, and the "
                 f"architect's brief looks for ~/work/flota-{HUMANO}.")
diffs = []           # [(name, installed path, unified diff)]: the files that change

# Programs that only some features of the fleet need, beyond what docs/instalacion.md
# step 0 asks of every machine: how to get each one. A feature whose program is missing
# is left out, whole, and the report says which feature, what it would do and how to
# get the program. Found by YOUR PATH, as root will run them.
PROGRAMAS = {
    "bindfs": "on Arch it is not in the official repositories: build it from the AUR "
              "(`aur sync bindfs` and then `sudo pacman -S bindfs`, or `yay -S bindfs`); "
              "elsewhere, the distribution's `bindfs` package",
}
no_disponibles = []  # [(feature, what it does, program, how to get it)]


def requiere(programa, funcion, que_hace):
    """True when programa is installed. If not, the feature funcion (as fleet.toml names
    it) is left out: say so in the report, with what it does and how to get programa."""
    if shutil.which(programa):
        return True
    no_disponibles.append((funcion, que_hace, programa, PROGRAMAS[programa]))
    return False
UNKNOWN = object()   # a state that could not be read


def color(stream):
    """ANSI colours, only when the stream is a terminal and NO_COLOR is unset: a
    plan.sh redirected to a file stays plain text."""
    on = stream.isatty() and not os.environ.get("NO_COLOR")
    return lambda texto, codigo: f"\033[{codigo}m{texto}\033[0m" if on else texto


def pintar_nota(nota, c):
    """A note for the screen: warnings in red, diffs in colour."""
    lineas = []
    for l in nota.splitlines():
        if l.startswith("!!"):
            lineas.append(c(l, "1;31"))
        elif l.startswith(("+++", "---")):
            lineas.append(c(l, "1"))
        elif l.startswith("@@"):
            lineas.append(c(l, "36"))
        elif l.startswith("+"):
            lineas.append(c(l, "32"))
        elif l.startswith("-"):
            lineas.append(c(l, "31"))
        else:
            lineas.append(l)
    return "\n".join(lineas)


def banner(texto, c):
    """A part of the screen report: hard to miss when scrolling."""
    return "\n" + c(f" {texto} ".ljust(88), "1;7;34") + "\n"


def do(cmd, why, root=True, rutina=False):
    """One line of the plan. rutina: a routine check (the planner cannot see the
    state; the command changes nothing if it is already right)."""
    plan.append((cmd, why, root, rutina))


# Shell functions the plan defines at its top, only those it uses. They hold the
# conditionals of the routine checks, so each check is one readable line, and the
# logic is read once.
HELPERS = {
    "carpeta": r'''# carpeta PATH OWNER:GROUP MODE [USER]: the folder exists (created as USER, if
# given), with that owner and mode.
carpeta() {
  if [ -n "${4:-}" ]; then runuser -u "$4" -- mkdir -p "$1"; else mkdir -p "$1"; fi
  chown "$2" "$1"
  chmod "$3" "$1"
}''',
    "linea": r'''# linea USER FILE LINE: FILE holds LINE; it is added at the end, as USER, if missing.
linea() {
  grep -qxF "$3" "$2" 2>/dev/null || printf '%s\n' "$3" | runuser -u "$1" -- tee -a "$2" >/dev/null
}''',
    "tmux_conf": r'''# tmux_conf USER FILE LINE...: FILE holds exactly these LINEs. A real configuration
# there (any other line) is first copied to FILE.antes-flota, never over an older copy;
# if grep cannot read it, the copy is made too.
tmux_conf() {
  local u=$1 f=$2 r=0; shift 2
  if [ -e "$f" ]; then
    grep -qvxE '(source-file .*|set -g @c .*)?' "$f" || r=$?
    [ "$r" = 1 ] || runuser -u "$u" -- cp -pn "$f" "$f.antes-flota"
  fi
  printf '%s\n' "$@" | cmp -s - "$f" 2>/dev/null || printf '%s\n' "$@" | runuser -u "$u" -- tee "$f" >/dev/null
}''',
    "enlace": r'''# enlace USER LINK TARGET: LINK is a symlink to TARGET (made as USER). A real file or
# folder at LINK is left alone, with a warning.
enlace() {
  runuser -u "$1" -- mkdir -p "$(dirname "$2")"
  if [ -L "$2" ] || [ ! -e "$2" ]; then
    [ "$(readlink "$2")" = "$3" ] || runuser -u "$1" -- ln -sfnT "$3" "$2"
  else
    echo "!! $2 is not a symlink: left as it is, move it aside by hand" >&2
  fi
}''',
    "sandbox_codex": r'''# sandbox_codex USER NET OUTBOX FOLDER...: the FOLDERs exist, and USER's codex sandbox
# may write OUTBOX and the FOLDERs, and reach the network if NET is true. In
# ~/.codex/config.toml (codex's file): the fleet's block is added when there is no
# [sandbox_workspace_write]; when the block is the fleet's (its marker line), only its
# writable_roots and network_access lines are rewritten; one someone else wrote is
# left alone, with a warning.
sandbox_codex() {
  local u=$1 red=$2 buzon=$3 cfg=/home/$1/.codex/config.toml d
  local marca='# flota: what the sandbox may write besides the working folder'
  shift 3
  if [ -e "$cfg" ] && [ ! -r "$cfg" ]; then
    echo "!! cannot read $cfg: what $u's codex sandbox may write was NOT checked" >&2
    return 0
  fi
  runuser -u "$u" -- mkdir -p "$@"
  local raices="\"$buzon\""
  for d in "$@"; do raices="$raices, \"$d\""; done
  local linea="writable_roots = [$raices]" lred="network_access = $red"
  if ! grep -qx '\[sandbox_workspace_write\]' "$cfg" 2>/dev/null; then
    printf '%s\n' '' "$marca" '[sandbox_workspace_write]' "$linea" "$lred" | runuser -u "$u" -- tee -a "$cfg" >/dev/null
  elif grep -qxF "$marca" "$cfg"; then
    # the fleet's block: its two lines right after the header, any older copy dropped
    awk -v m="$marca" -v w="$linea" -v n="$lred" '
      $0 == m { print; marca = 1; next }
      marca && $0 == "[sandbox_workspace_write]" { print; print w; print n; dentro = 1; marca = 0; next }
      dentro && (/^writable_roots *=/ || /^network_access *=/) { next }
      dentro && (/^\[/ || /^$/) { dentro = 0 }
      { marca = 0; print }' "$cfg" | runuser -u "$u" -- sh -c 'cat > "$1.new" && mv "$1.new" "$1"' - "$cfg"
  else
    echo "!! $cfg has its own [sandbox_workspace_write]: add $buzon $* to its writable_roots by hand" >&2
  fi
}''',
    "sin_aviso_codex": r'''# sin_aviso_codex USER: USER's codex does not offer to update itself at start. The
# fleet pins codex's version ([software] codex, `flota actualizar codex`), and the offer
# stopped `codex resume` before it showed the conversation (2026-11-12). A top-level key,
# so it goes first in config.toml, before any table; one someone else set is left alone.
sin_aviso_codex() {
  local u=$1 cfg=/home/$1/.codex/config.toml
  if [ -e "$cfg" ] && [ ! -r "$cfg" ]; then
    echo "!! cannot read $cfg: codex's update offer was NOT checked" >&2
    return 0
  fi
  if grep -qE '^check_for_update_on_startup *=' "$cfg" 2>/dev/null; then
    grep -qE '^check_for_update_on_startup *= *false' "$cfg" \
      || echo "!! $cfg sets check_for_update_on_startup itself: left as it is" >&2
    return 0
  fi
  { printf '%s\n' '# flota: the fleet pins codex'"'"'s version; no update offer at start' \
      'check_for_update_on_startup = false' ''; cat "$cfg" 2>/dev/null; } \
    | runuser -u "$u" -- sh -c 'cat > "$1.new" && mv "$1.new" "$1"' - "$cfg"
}''',
    "confiar_codex": r'''# confiar_codex USER FOLDER...: USER's codex trusts each FOLDER (a role folder), so a
# session started there may write its workspace, as when the human answers codex's
# "trust this folder?". A FOLDER that already has its [projects."FOLDER"] entry is left
# as it is, whatever it says: that entry is codex's, or the human's.
confiar_codex() {
  local u=$1 cfg=/home/$1/.codex/config.toml d; shift
  if [ -e "$cfg" ] && [ ! -r "$cfg" ]; then
    echo "!! cannot read $cfg: the trust of $* was NOT checked" >&2
    return 0
  fi
  for d in "$@"; do
    grep -qxF "[projects.\"$d\"]" "$cfg" 2>/dev/null ||
      printf '%s\n' '' "[projects.\"$d\"]" 'trust_level = "trusted"' | runuser -u "$u" -- tee -a "$cfg" >/dev/null
  done
}''',
    "sin_override": r'''# sin_override FOLDER WHAT: warn if FOLDER/AGENTS.override.md exists: codex would
# load it instead of WHAT.
sin_override() {
  [ ! -e "$1/AGENTS.override.md" ] || echo "!! $1/AGENTS.override.md exists: codex loads it INSTEAD of $2; move it aside by hand" >&2
}''',
    "repo_git": r'''# repo_git USER FOLDER: FOLDER is a git repository (created as USER, shared with its group).
repo_git() {
  [ -d "$2/.git" ] || runuser -u "$1" -- git init -q --shared=group "$2"
}''',
    "sudoers_flota": r'''# sudoers_flota FILE LINE...: FILE in /etc/sudoers.d holds exactly these lines, checked
# by visudo before it is installed (a broken sudoers file can lock sudo out). A file
# already the same is left alone; visudo refusing it installs nothing.
sudoers_flota() {
  local f=$1 t; shift
  t=$(mktemp) || return 1
  printf '%s\n' "$@" > "$t"
  if [ -f "$f" ] && cmp -s "$t" "$f"; then rm "$t"; return 0; fi
  if visudo -cqf "$t"; then
    install -o root -g root -m 440 "$t" "$f"
  else
    echo "!! visudo refused the rule for $f: nothing installed" >&2
  fi
  rm "$t"
  grep -Eq '^[@#]includedir[[:space:]]+/etc/sudoers.d' /etc/sudoers \
    || echo "!! /etc/sudoers does not read /etc/sudoers.d: add @includedir /etc/sudoers.d by hand (visudo)" >&2
}''',
}
usados = []          # the HELPERS the plan calls, in the order first used


def llamar(funcion, *args):
    """A call to one of HELPERS, its arguments quoted for the shell."""
    if funcion not in usados:
        usados.append(funcion)
    return " ".join([funcion, *(q(a) for a in args)])


REINICIAR = set()   # agents whose plan changes groups, PATH or tmux: their sessions restart


def seccion(titulo, porque):
    """A section of the plan: its title and one or two plain lines on what it is
    for. Printed only when the section has actions."""
    plan.append((None, (titulo, porque), False, False))


# ---- reading state (read-only) -------------------------------------------------

def user_exists(u):
    try:
        pwd.getpwnam(u)
        return True
    except KeyError:
        return False


def group_exists(g):
    try:
        grp.getgrnam(g)
        return True
    except KeyError:
        return False


def in_group(u, g):
    try:
        gr = grp.getgrnam(g)
    except KeyError:
        return False
    if u in gr.gr_mem:
        return True
    try:
        return pwd.getpwnam(u).pw_gid == gr.gr_gid
    except KeyError:
        return False


def stat_of(path):
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except PermissionError:
        return UNKNOWN


def name_of_uid(uid):
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def name_of_gid(gid):
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return str(gid)


def tiene_acl(path, default=False):
    """Whether path carries an ACL (default: an ACL its new entries inherit)."""
    nombre = "system.posix_acl_default" if default else "system.posix_acl_access"
    try:
        return nombre in os.listxattr(path, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        return UNKNOWN


def mounted(target):
    with open("/proc/self/mountinfo") as f:
        return any(line.split()[4] == target for line in f)


def in_fstab(target):
    with open("/etc/fstab") as f:
        for line in f:
            campos = line.split("#", 1)[0].split()
            if len(campos) >= 2 and campos[1] == target:
                return True
    return False


def montar_lectura(u, montajes, revisar=False):
    """Mount the human's folders read-only for AI user u with bindfs, through /etc/fstab so
    they come back at boot: {mount point: (folder, what fleet.toml calls it, description)}.
    revisar: refuse a folder that holds credentials at its top (CREDENCIALES)."""
    nuevo, montar = False, []
    for destino, (origen, clave, que) in montajes.items():
        if not os.path.isdir(origen):
            notas.append(f"!! {clave}: {origen} does not exist. Create it, or fix fleet.toml, "
                         "and run the planner again.")
            continue
        malas = [c for c in CREDENCIALES if os.path.lexists(os.path.join(origen, c))] if revisar else []
        if malas:
            notas.append(f"!! {clave}: {origen} holds {', '.join(malas)}, which may hold credentials: "
                         f"not mounted for {u}. Move them out, or declare its subfolders instead.")
            continue
        linea = (f"{origen}  {destino}  fuse.bindfs  "
                 f"ro,force-user={u},force-group={u},perms=u=rD:go-rwx  0 0")
        actual = linea_fstab(destino)
        if actual is None:
            if not mounted(destino):
                do(f"runuser -u {u} -- mkdir -p {q(destino)}", "mount point")
            do(f"printf '%s\\n' {q(linea)} >> /etc/fstab", f"{que}, read-only for {u}")
            nuevo = True
        elif actual != linea.split():
            notas.append(f"!! /etc/fstab mounts something else at {destino}. Replace that line "
                         f"by hand with:\n   {linea}\n   then: sudo umount {destino}; sudo mount {destino}")
            continue
        if not mounted(destino):
            montar.append(destino)
    if nuevo:
        do("systemctl daemon-reload", "systemd rereads fstab")
    for destino in montar:
        do(f"mount {q(destino)}", "mount it now")


def linea_fstab(target):
    """The fields of the /etc/fstab line that mounts at target, or None."""
    with open("/etc/fstab") as f:
        for line in f:
            campos = line.split("#", 1)[0].split()
            if len(campos) >= 2 and campos[1] == target:
                return campos
    return None


def servidores_tmux(u):
    """Why u's running tmux servers should restart: a list of reasons ([] when they are
    fine, or when none runs), or UNKNOWN when /proc does not show them."""
    try:
        pw = pwd.getpwnam(u)
    except KeyError:
        return []
    esperados = set(os.getgrouplist(u, pw.pw_gid))
    try:
        with open("/proc/stat") as f:
            arranque = next(int(l.split()[1]) for l in f if l.startswith("btime "))
        conf = os.stat(TMUX_DST).st_mtime if os.path.exists(TMUX_DST) else 0
    except (OSError, StopIteration):
        return UNKNOWN
    razones = set()
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/stat") as f:
                stat_ = f.read()
            if stat_[stat_.index("(") + 1:stat_.rindex(")")] != "tmux: server":
                continue
            with open(f"/proc/{pid}/status") as f:
                campos = dict(l.split(":", 1) for l in f if ":" in l)
            if int(campos["Uid"].split()[0]) != pw.pw_uid:
                continue
            with open(f"/proc/{pid}/cgroup") as f:
                cgroup = f.read()
        except (OSError, ValueError, KeyError):
            continue                               # gone meanwhile, or not ours to see
        if esperados - {int(g) for g in campos.get("Groups", "").split()}:
            razones.add("it lacks groups")
        if f"user-{pw.pw_uid}.slice" not in cgroup:
            razones.add("it runs outside its slice")
        inicio = arranque + int(stat_[stat_.rindex(")") + 2:].split()[19]) / os.sysconf("SC_CLK_TCK")
        if inicio < conf:
            razones.add("it predates the tmux configuration")
    return sorted(razones)


def alias_faltantes(alias):
    """The alias lines not in the human's ~/.bashrc or ~/.bash_aliases."""
    casa = pwd.getpwuid(os.getuid()).pw_dir
    tiene = set()
    for archivo in (".bashrc", ".bash_aliases"):
        try:
            with open(os.path.join(casa, archivo)) as f:
                tiene |= {l.strip() for l in f}
        except OSError:
            pass
    return [a for a in alias if a not in tiene
            and not (a.startswith("alias flota=") and any(l.startswith("alias flota=") for l in tiene))]


def grupos_sin_activar():
    """Your groups that this login does not carry yet: a group applies only to a new
    login, and a new terminal in the same desktop session inherits the old ones."""
    activos = set(os.getgroups())
    yo = pwd.getpwuid(os.getuid()).pw_name
    return sorted(g.gr_name for g in grp.getgrall() if yo in g.gr_mem and g.gr_gid not in activos)


# ---- planning ------------------------------------------------------------------

def ensure_group(g):
    if not group_exists(g):
        do(f"groupadd {g}", f"create group {g}")


def ensure_member(u, g):
    if not in_group(u, g):
        do(f"usermod -aG {g} {u}", f"{u} into group {g}")
        REINICIAR.add(u)


def ensure_dir(path, owner, group, mode, why, create_as=None):
    mk = f"runuser -u {create_as} -- mkdir -p {q(path)}" if create_as else f"mkdir -p {q(path)}"
    st = stat_of(path)
    if st is UNKNOWN:
        do(llamar("carpeta", path, f"{owner}:{group}", f"{mode:o}", *([create_as] if create_as else [])),
           why, rutina=True)
        return
    if st is None:
        do(mk, why)
        do(f"chown {owner}:{group} {q(path)}", "owner")
        do(f"chmod {mode:o} {q(path)}", "permissions")
        return
    if (name_of_uid(st.st_uid), name_of_gid(st.st_gid)) != (owner, group):
        do(f"chown {owner}:{group} {q(path)}",
           f"it is {name_of_uid(st.st_uid)}:{name_of_gid(st.st_gid)}")
    if stat.S_IMODE(st.st_mode) != mode:
        do(f"chmod {mode:o} {q(path)}", f"it is {stat.S_IMODE(st.st_mode):o}")


def ensure_escribible(path, quienes):
    """A [machine] writable folder: the human's, group agents, setgid and group-writable
    (2775 when created; the other bits are the human's to change afterwards), with no
    ACL, inherited or not. Each parent lets the agents pass (o+x: pass, not list). The
    parent itself must exist: it is the human's, and the planner does not invent it."""
    padre = os.path.dirname(path)
    st = stat_of(padre)
    if st is None or st is UNKNOWN or not stat.S_ISDIR(st.st_mode):
        notas.append(f"!! [machine] writable {path}: cannot see its parent {padre} as a folder. "
                     "Create it (it is yours), and run the planner again.")
        return
    cadena = []
    while padre != "/":
        cadena.append(padre)
        padre = os.path.dirname(padre)
    for p in reversed(cadena):
        st = stat_of(p)
        if st is UNKNOWN:
            notas.append(f"!! [machine] writable {path}: cannot read {p}; nothing done there")
            return
        if not (st.st_mode & stat.S_IXOTH or (name_of_gid(st.st_gid) == "agents" and st.st_mode & stat.S_IXGRP)):
            do(f"chmod o+x {q(p)}", f"the agents pass through it to {path}, without listing it "
                                    f"(it is {stat.S_IMODE(st.st_mode):o})")
    st = stat_of(path)
    if st is UNKNOWN:
        notas.append(f"!! [machine] writable {path}: cannot read it; nothing done there")
        return
    quien = f"{', '.join(quienes)} write{'s' if len(quienes) == 1 else ''} it"
    if st is None:
        do(f"mkdir {q(path)}", f"{quien}, as fleet.toml declares")
        if tiene_acl(os.path.dirname(path), default=True) is not False:
            do(f"setfacl -b -k {q(path)}", "no ACL: drop what it inherits from its parent")
        do(f"chown {HUMANO}:agents {q(path)}", "yours; the agents group writes")
        do(f"chmod 2775 {q(path)}", "setgid: what is created inside stays in the agents group")
        return
    if not stat.S_ISDIR(st.st_mode):
        notas.append(f"!! [machine] writable {path} is not a folder: fix fleet.toml, or move it aside")
        return
    acl = [tiene_acl(path), tiene_acl(path, default=True)]
    if UNKNOWN in acl:
        notas.append(f"!! [machine] writable {path}: cannot tell whether it has an ACL")
    elif any(acl):
        do(f"setfacl -b -k {q(path)}", "it has an ACL: the fleet uses groups")
    if (name_of_uid(st.st_uid), name_of_gid(st.st_gid)) != (HUMANO, "agents"):
        do(f"chown {HUMANO}:agents {q(path)}",
           f"{quien}; it is {name_of_uid(st.st_uid)}:{name_of_gid(st.st_gid)}")
    if (0o2770 & ~stat.S_IMODE(st.st_mode)):
        do(f"chmod u+rwx,g+rwxs {q(path)}", f"the agents group writes it; it is {stat.S_IMODE(st.st_mode):o}")


def read_lines(path):
    """The file's lines; None if it does not exist; UNKNOWN if it cannot be read."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [l.rstrip("\n") for l in f]
    except FileNotFoundError:
        return None
    except PermissionError:
        return UNKNOWN


def ensure_line(u, archivo, linea):
    path = f"/home/{u}/{archivo}"
    agregar = f"printf '%s\\n' {q(linea)} | runuser -u {u} -- tee -a {q(path)} >/dev/null"
    lineas = read_lines(path)
    if lineas is UNKNOWN or (lineas is None and not os.path.isdir(f"/home/{u}")):
        do(llamar("linea", u, path, linea), f"{archivo} of {u}", rutina=True)
    elif lineas is None or linea not in lineas:
        do(agregar, f"{archivo} of {u}")
        REINICIAR.add(u)


def fuente_propia(path):
    """The source and every folder above it, up to the clone, must belong to whoever runs
    the planner, and none may be a symlink: the plan runs as root."""
    yo = os.getuid()
    raiz = CONFIG if (path + "/").startswith(CONFIG + "/") else CFG
    p = path
    while True:
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode) or st.st_uid != yo:
            sys.exit(f"plan-agentes.py: refusing to run: {p} is "
                     f"{'a symlink' if stat.S_ISLNK(st.st_mode) else 'owned by ' + name_of_uid(st.st_uid)}. "
                     "Run the planner from YOUR clone (git fetch from the agent's copy, review, merge).")
        if p == raiz or p == os.path.dirname(p):
            return
        p = os.path.dirname(p)


PLANTILLA = re.compile(r"\{\{([a-z_.]+)\}\}")


def render(texto, src, vals=VALORES):
    """The text with its {{...}} replaced from vals: {{human.*}} everywhere, and for a
    file installed for one AI user also {{ai_user.*}} and {{<role>.ai_user}} (valores).
    Any other stops the planner: a value missing from fleet.toml is never guessed."""
    otros = sorted({m for m in PLANTILLA.findall(texto) if m not in vals})
    if otros:
        sys.exit(f"plan-agentes.py: {src} uses {', '.join(otros)}, which fleet.toml does not give"
                 + (" (no AI user has that role)" if any(o.endswith(".ai_user") for o in otros) else ""))
    return PLANTILLA.sub(lambda m: vals[m.group(1)], texto)


def ensure_installed(src, dst, mode, nombre, group="buzon", vals=VALORES):
    """Plan `install` of src into dst (human:<group>) when they differ, with its templates
    filled from vals (fleet.toml's values; valores(u) for a file of one AI user). The diff
    goes to the notes. Needs no root: the human owns dst and its directory."""
    if not os.path.lexists(src):
        notas.append(f"no {src}; {nombre} is not installed")
        return
    fuente_propia(src)
    with open(src) as f:
        texto = f.read()
    if PLANTILLA.search(texto):
        usados = sorted(set(PLANTILLA.findall(texto)))
        texto = render(texto, src, vals)
        sed = " ".join(f"-e {q('s#{{' + k + '}}#' + vals[k] + '#g')}" for k in usados)
        cmd = f"sed {sed} {q(src)} | install -o {HUMANO} -g {group} -m {mode:o} /dev/stdin {q(dst)}"
    else:
        cmd = f"install -o {HUMANO} -g {group} -m {mode:o} {q(src)} {q(dst)}"
    nuevo = texto.splitlines(True)
    viejo = read_lines(dst)
    if viejo is UNKNOWN:
        notas.append(f"cannot read {dst}: review {src} by hand before running the plan")
        do(cmd, f"install {nombre} (unknown state; review the source)", root=False)
        return
    viejo = [l + "\n" for l in viejo] if viejo is not None else []
    if nuevo != viejo:
        diff = "".join(difflib.unified_diff(viejo, nuevo, dst, src))
        diffs.append((nombre, dst, diff))
        do(cmd, f"install {nombre} (its diff is under FILES THAT CHANGE)", root=False)


def ensure_tmux_conf(u):
    """~/.tmux.conf of u must be exactly tmux_lineas(u): its bar colour and the
    source-file line. A real configuration is backed up first (never overwriting an
    earlier backup); one the planner wrote (only such lines) is simply replaced."""
    path = f"/home/{u}/.tmux.conf"
    backup = f"/home/{u}/.tmux.conf.antes-flota"
    quiero = tmux_lineas(u)
    contenido = " ".join(q(l) for l in quiero)
    escribir = f"printf '%s\\n' {contenido} | runuser -u {u} -- tee {q(path)} >/dev/null"
    guardar = f"runuser -u {u} -- cp -pn {q(path)} {q(backup)}"
    nuestra = re.compile(r"source-file .*|set -g @c .*")
    lineas = read_lines(path)
    if lineas is UNKNOWN or (lineas is None and not os.path.isdir(f"/home/{u}")):
        do(llamar("tmux_conf", u, path, *quiero), f"~/.tmux.conf of {u}: its colour and the shared file",
           rutina=True)
        return
    if lineas is None:
        do(escribir, f"~/.tmux.conf of {u} -> its colour and the shared configuration")
        REINICIAR.add(u)
        return
    reales = [l for l in lineas if l.strip()]
    if reales == quiero:
        return
    REINICIAR.add(u)
    if all(nuestra.fullmatch(l) for l in reales):
        do(escribir, f"~/.tmux.conf of {u}: its colour and the shared configuration, as now written")
    else:
        do(guardar, f"backup of the current ~/.tmux.conf of {u}")
        do(escribir, f"~/.tmux.conf of {u} -> its colour and the shared configuration")


def ensure_link(u, link, target, nombre):
    """link (owned by u) must be a symlink to target. Anything else is warned about:
    it may be tampering, since u can replace a link in its own home."""
    fijar = f"runuser -u {u} -- ln -sfnT {q(target)} {q(link)}"
    padre = os.path.dirname(link)
    try:
        actual = os.readlink(link)
    except FileNotFoundError:
        if not os.path.isdir(padre):
            do(f"runuser -u {u} -- mkdir -p {q(padre)}", f"folder for {nombre}")
        do(fijar, f"{nombre} -> copy installed by the human")
        return
    except PermissionError:
        do(llamar("enlace", u, link, target), nombre, rutina=True)
        return
    except OSError:   # it exists and is not a symlink: a real file or directory
        notas.append(f"!! {link} exists and is NOT a symlink (a copy the agent could edit?). "
                     "Look at it, and move it aside by hand before running the plan.")
        return
    if actual != target:
        notas.append(f"!! {link} points to {actual!r}, not to {target}. "
                     f"Look at it before running the plan: {nombre} may have been replaced.")
        do(fijar, f"fix {nombre} (see the warning)")


def bytes_of(valor):
    """systemd size ("5G", "512M") to the bytes the cgroup file shows."""
    unidades = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30, "T": 1 << 40}
    if valor[-1] in unidades:
        return str(int(valor[:-1]) * unidades[valor[-1]])
    return valor


def ensure_slice(u, props):
    """The slice of u (user-<uid>.slice) must carry props, in a drop-in. Returns whether
    it plans a change. When the slice is active, its live values are checked too."""
    try:
        uid = pwd.getpwnam(u).pw_uid
    except KeyError:
        notas.append(f"no user {u} yet: its resource limits wait for it")
        return False
    carpeta = f"{SLICES}/user-{uid}.slice.d"
    path = f"{carpeta}/50-flota.conf"
    lineas = ["# Installed by plan-agentes.py (flota). Change RECURSOS there, not this file.",
              "[Slice]"] + [f"{k}={v}" for k, v in props.items()]
    temporal = f"/run/systemd/system.control/user-{uid}.slice.d"
    if os.path.isdir(temporal):
        notas.append(f"{temporal} holds limits set with `systemctl set-property --runtime`. "
                     "They override the plan's until the next reboot (or remove them by hand).")
    # Modes are explicit, never left to root's umask: a folder or file only root can
    # read would look different to this planner (it runs as the human) on every run.
    st = stat_of(carpeta)
    if st is None or st is UNKNOWN or stat.S_IMODE(st.st_mode) != 0o755:
        do(f"install -d -m 755 {q(carpeta)}", f"drop-in folder for the slice of {u} (uid {uid}), readable")
    actual = read_lines(path)
    if actual != lineas:
        do(f"printf '%s\\n' {' '.join(q(l) for l in lineas)} | install -m 644 /dev/stdin {q(path)}",
           f"resources of {u}: {' '.join(f'{k}={v}' for k, v in props.items())}"
           + (" (could not read the current file)" if actual is UNKNOWN else ""))
        return True
    vivo = f"/sys/fs/cgroup/user.slice/user-{uid}.slice"
    if os.path.isdir(vivo):
        for k, v in props.items():
            actual = read_lines(f"{vivo}/{CGROUP_FILE[k]}")
            esperado = v if k == "CPUWeight" else bytes_of(v)
            if isinstance(actual, list) and actual[:1] != [esperado]:
                notas.append(f"the running slice of {u} has {CGROUP_FILE[k]} = {actual[:1]}, not {esperado}. "
                             f"Run `sudo systemctl daemon-reload`; if it persists, restart {u}'s sessions.")
    return False


def codex_sandbox(u):
    """codex runs the model's commands in a sandbox where everything but the working
    folder and /tmp is read-only (EROFS, not a permission error). Let it write what the
    fleet needs and nothing more: its outbox; the daemon's state and codex's own
    temporary folder under ~/.codex (not the rest of ~/.codex, where its configuration,
    this setting included, lives); ~/.local/state/buzon, where `buzon leer` keeps what
    was read; and, for a working agent, ~/work/propuestas, where
    the architect can read its proposals (and ~/work/revisiones, an aparejador's
    reviews). config.toml is codex's file: the section is
    added when absent, and only the fleet's own block (after its marker) is ever
    rewritten; a section someone else wrote is left alone, with a warning."""
    home = f"/home/{u}"
    cfg = f"{home}/.codex/config.toml"
    # the app-server's state: app-server-daemon up to codex 0.162, app-server-control
    # from a later version (0.167 on 2026-11-08); both, so either version starts
    carpetas = [f"{home}/.codex/app-server-daemon", f"{home}/.codex/app-server-control",
                f"{home}/.codex/tmp",
                f"{home}/.local/state/buzon"]                # buzon leer's read marks
    if u in PARES:
        carpetas.append(f"{home}/work/propuestas")
    if u in PARES and "aparejador" in roles(u):
        carpetas.append(f"{home}/work/revisiones")              # its reviews, read by the architect
    carpetas += [c for c, quienes in ESCRIBIBLES.items() if u in quienes]   # [machine] writable
    if u in PENSADEROS:
        carpetas.append(f"{home}/work")         # the maestro works from ~/maestro and writes here
    raices = [f"{BUZ}/{u}"] + carpetas
    # a working agent reaches the clusters by ssh, from inside the sandbox
    red = "true" if u in PARES else "false"
    marca = "# flota: what the sandbox may write besides the working folder"
    linea = "writable_roots = [" + ", ".join(f'"{r}"' for r in raices) + "]"
    texto = read_lines(cfg)
    if texto is not UNKNOWN and texto is not None and all(os.path.isdir(d) for d in carpetas):
        if marca in texto and linea in texto and f"network_access = {red}" in texto:
            return                                          # already as it should be
        if marca not in texto and "[sandbox_workspace_write]" in (l.strip() for l in texto):
            notas.append(f"!! {cfg} has its own [sandbox_workspace_write]: add "
                         f"{', '.join(raices)} to its writable_roots by hand")
            return
    # the helper writes the same marker and line (sandbox_codex in HELPERS)
    do(llamar("sandbox_codex", u, red, f"{BUZ}/{u}", *carpetas),
       f"what {u}'s codex sandbox may write: {', '.join(os.path.basename(r) for r in raices)}"
       + ("; and the network, for ssh to the clusters" if red == "true" else ""),
       rutina=texto is UNKNOWN)


def codex_sin_aviso(u):
    """codex offers to update itself at start; the fleet pins its version, and the offer
    stopped `codex resume` (2026-11-12). check_for_update_on_startup = false, a top-level
    key at the head of config.toml (sin_aviso_codex in HELPERS)."""
    cfg = f"/home/{u}/.codex/config.toml"
    texto = read_lines(cfg)
    if texto is not UNKNOWN and texto is not None and \
            any(re.fullmatch(r"check_for_update_on_startup *=.*", l.strip()) for l in texto):
        if not any(re.fullmatch(r"check_for_update_on_startup *= *false", l.strip()) for l in texto):
            notas.append(f"!! {cfg} sets check_for_update_on_startup itself: left as it is")
        return
    do(llamar("sin_aviso_codex", u), f"{u}'s codex: no update offer at start (the fleet pins its version)",
       rutina=texto is UNKNOWN)


def confianza_codex(u, carpetas=None):
    """codex starts a session in an untrusted folder read-only, and asks whether to
    trust a new folder only sometimes (~/aparejador was never asked, 2026-10-13). Each
    role folder of a codex AI user gets its [projects."<folder>"] trust entry in
    ~/.codex/config.toml, appended only when missing (confiar_codex in HELPERS)."""
    carpetas = carpetas or [f"/home/{u}/{rol}" for rol in roles(u)]
    if not carpetas:
        return
    texto = read_lines(f"/home/{u}/.codex/config.toml")
    if texto is not UNKNOWN and texto is not None \
            and all(f'[projects."{c}"]' in (l.strip() for l in texto) for c in carpetas):
        return
    do(llamar("confiar_codex", u, *carpetas),
       f"{u}'s codex trusts its role folders: {', '.join(os.path.basename(c) for c in carpetas)}",
       rutina=texto is UNKNOWN)


def vigilar_override(u, carpeta, que):
    """codex reads AGENTS.override.md INSTEAD of AGENTS.md in the same folder: say so."""
    override = stat_of(f"{carpeta}/AGENTS.override.md")
    if override is UNKNOWN:
        do(llamar("sin_override", carpeta, que), f"no AGENTS.override.md in {carpeta}", rutina=True)
    elif override is not None:
        notas.append(f"!! {carpeta}/AGENTS.override.md exists: codex loads it INSTEAD "
                     f"of {que}. Look at it, and move it aside by hand.")


def main():
    seccion(f"1. agent users, with homes private to themselves and {HUMANO}",
            "Each agent is a Linux user of its own, so the kernel keeps it out of your files and the other agents'. You are in each agent's group, so you can read their homes.")
    for u in AGENTES:
        if not user_exists(u):
            do(f"useradd -m -U {u}", f"create user {u} with its own group")
        st = stat_of(f"/home/{u}")
        if st is None or st is UNKNOWN or stat.S_IMODE(st.st_mode) != 0o2770:
            do(f"chmod 2770 /home/{u}", "owner + group; setgid")
        ensure_member(HUMANO, u)

    seccion(f"2. groups: agents = {', '.join(PARES)} (never a pensadero); buzon = everyone",
            "agents: the working agents may read each other's work and run the fleet tools; you are in it to install them. buzon: everyone may use the mailbox. A pensadero is in no group that reads the others.")
    ensure_group("agents")
    for u in PARES + [HUMANO]:     # the human too: herramientas/install gives the tools this group
        ensure_member(u, "agents")
    for u in PENSADEROS:
        if in_group(u, "agents"):
            do(f"gpasswd -d {u} agents", f"{u} is a pensadero and must NOT read the other agents")
            REINICIAR.add(u)
    ensure_group("buzon")
    for u in AGENTES + [HUMANO]:
        ensure_member(u, "buzon")

    seccion(f"3. umask 002, {BIN} on PATH, and the ssh-agent socket of the working agents",
            "Lines in the agents' .profile and .bashrc: files they create stay readable to their group, they find the shared tools, and the working agents find the ssh-agent you unlock for clusters.")
    for u in AGENTES:
        for archivo in (".profile", ".bashrc"):
            for linea in LINEAS + (LINEAS_PARES if u in PARES else []):
                ensure_line(u, archivo, linea)

    seccion(f"4. {A}: everything shared, owned by {HUMANO}",
            'The root of everything the agents share. Yours, on the /home disk, so it survives a reinstall.')
    ensure_dir(A, HUMANO, "buzon", 0o2750, "shared root (only the buzon group gets in)")

    seccion(f"5. {PAR}: each working agent's ~/work, for the agents group only",
            "Read-only views of each working agent's ~/work, so each can read the others' projects and change none.")
    for u in PARES:
        ensure_dir(f"/home/{u}/work", u, u, 0o2775, "create ~/work", create_as=u)
    ensure_dir(PAR, HUMANO, "agents", 0o2750, f"gatekeeper: only agents (and {HUMANO}, the owner)")
    fstab_nuevo = False
    for u in PARES:
        destino = f"{PAR}/{u}"
        if not mounted(destino):
            do(f"mkdir -p {destino}", "mount point")
        if not in_fstab(destino):
            linea = f"/home/{u}/work  {destino}  none  bind  0 0"
            do(f"printf '%s\\n' {q(linea)} >> /etc/fstab", "permanent bind mount")
            fstab_nuevo = True
    if fstab_nuevo:
        do("systemctl daemon-reload", "systemd rereads fstab")
    for u in PARES:
        if not mounted(f"{PAR}/{u}"):
            do(f"mount {PAR}/{u}", "mount it now")

    if ESCRIBIBLES:
        seccion("5b. folders the agents write outside their homes, as [machine] writable declares",
                "Such as the group's software stack: yours, group agents, setgid, no ACL. The agents group can write it; fleet.toml says which AI user does, and their rules hold them to it. Who else reads it is yours to decide, with its other bits. Its parents let the agents pass (o+x), not list.")
        for carpeta, quienes in ESCRIBIBLES.items():
            ensure_escribible(carpeta, quienes)

    seccion(f"6. {BUZ}: mailbox, one outbox per user",
            'The mailbox: one outbox per user, written only by its owner, so who wrote a message is never in doubt.')
    ensure_dir(BUZ, HUMANO, "buzon", 0o2750, "create mailbox (only root creates outboxes)")
    for u in AGENTES:
        ensure_dir(f"{BUZ}/{u}", u, "buzon", 0o2750, f"outbox of {u} (only {u} writes)")

    seccion(f"7. {BIN} and {ETC}: shared tools and configuration",
            'Tools and configuration the agents use and cannot change: buzon, relevo (to go on with another tool), the tmux setup, and COMANDOS.md (your cheat sheet, which agents show you when you ask).')
    ensure_dir(BIN, HUMANO, "buzon", 0o2750, f"tools: the agents read, {HUMANO} writes")
    ensure_installed(BUZON_SRC, f"{BIN}/buzon", 0o750, "buzon")
    ensure_installed(RELEVO_SRC, f"{BIN}/relevo", 0o750, "relevo")
    ensure_installed(SSH_SRC, f"{BIN}/ssh", 0o750, "ssh (the agents' own ~/.ssh/config only)")
    ensure_dir(ETC, HUMANO, "buzon", 0o2750, f"configuration: the agents read, {HUMANO} writes")
    ensure_installed(TMUX_SRC, TMUX_DST, 0o640, "tmux-flota.conf")
    ensure_installed(f"{CFG}/COMANDOS.md", f"{ETC}/COMANDOS.md", 0o640, "COMANDOS.md")
    for u in AGENTES:
        ensure_tmux_conf(u)

    ensure_dir(BRIEFS, HUMANO, "buzon", 0o2750, f"briefs: one per agent role, installed by {HUMANO}")

    seccion("8. pensadero: its ~/work, its conventions, and the maestro's brief, for each tool",
            "The pensadero is a fleet of its own: its conventions at the top of its home (every session loads them: the maestro, and each agent of a línea in ~/work/lineas/<línea>), and the maestro's brief in ~/maestro. Both as CLAUDE.md (claude) and AGENTS.md (codex); they load them and cannot edit them. Its ~/work holds repos like anyone's, but no peer reads it: it is not in pares.")
    for u in PENSADEROS:
        # ~/work as any AI user's; ~/work/lineas, a plain folder: the group of the líneas,
        # one repo each (2026-10-20). Closed to others: no pares mount, no "other" bits.
        ensure_dir(f"/home/{u}/work", u, u, 0o2770, "~/work of the pensadero (no peer reads it)", create_as=u)
        ensure_dir(f"/home/{u}/work/lineas", u, u, 0o2770, "the líneas: a group, one repo per línea",
                   create_as=u)
        conv = f"{ETC}/conventions-{u}.md"
        ensure_installed(CONV_PENSADERO, conv, 0o640, f"conventions for {u}", group=u, vals=valores(u))
        brief = f"{BRIEFS}/maestro.md"
        ensure_installed(f"{CFG}/roles/maestro.md", brief, 0o640, "maestro brief", group=u,
                         vals=valores(u))
        for pv in proveedores(u):
            ensure_link(u, f"/home/{u}/{INSTR[pv]}", conv,
                        f"/home/{u}/{INSTR[pv]} (its conventions, for {pv})")
            ensure_link(u, f"/home/{u}/maestro/{INSTR[pv]}", brief,
                        f"/home/{u}/maestro/{INSTR[pv]} (the maestro's brief, for {pv})")
            if pv == "codex":
                vigilar_override(u, f"/home/{u}", "its conventions")
                vigilar_override(u, f"/home/{u}/maestro", "the maestro's brief")
                vigilar_override(u, f"/home/{u}/.codex", "its conventions")
                codex_sandbox(u)
                codex_sin_aviso(u)
                confianza_codex(u, [f"/home/{u}/maestro"])

    legibles = LEGIBLES
    if legibles and not requiere(
            "bindfs", "[machine] readable",
            "the AI users read folders of yours live, read-only, in their homes. None is mounted."):
        legibles = {}
    if legibles:
        seccion("8b. readable: folders of yours the AI users read live",
                "Each folder [machine] readable names, shown to that AI user at ~/<its name> with bindfs: it reads it as its own, up to date, and the kernel refuses any write. Your files keep their owner and mode. A folder with credentials at its top is refused.")
    for u, carpetas in legibles.items():
        montar_lectura(u, {d: (o, "[machine] readable", f"{o}, read live") for d, o in carpetas.items()},
                       revisar=True)

    seccion("9. conventions: the rules every session of a working agent loads",
            "The fleet conventions, in each provider's words, at the top of each agent's home: every session under it loads them.")
    for u in PARES:
        pv = proveedor(u)
        conv = f"{ETC}/conventions-{u}.md"
        ensure_installed(CONV_SRC[pv], conv, 0o640, f"conventions for {u}", group=u, vals=valores(u))
        ensure_link(u, f"/home/{u}/{INSTR[pv]}", conv, f"/home/{u}/{INSTR[pv]} (conventions)")
        if pv == "codex":
            ensure_link(u, f"/home/{u}/.codex/AGENTS.md", f"/home/{u}/AGENTS.md",
                        f"~{u}/.codex/AGENTS.md (loaded at every start)")
            vigilar_override(u, f"/home/{u}/.codex", "the conventions")
            codex_sandbox(u)
            codex_sin_aviso(u)

    seccion("10. roles: each brief at the top of the role's own folder",
            "Each role (coordinator, architect, aparejador) gets its brief as the CLAUDE.md or AGENTS.md of its folder; a session started there loads it. Restart a role's session to pick up a new brief.")
    for u in PARES:
        pv = proveedor(u)
        for rol in roles(u):
            nombre = rol if pv == "claude" else f"{rol}-{pv}"
            brief = f"{BRIEFS}/{nombre}.md"
            ensure_installed(f"{CFG}/roles/{nombre}.md", brief, 0o640, f"{nombre} brief", group=u,
                             vals=valores(u))
            ensure_link(u, f"/home/{u}/{rol}/{INSTR[pv]}", brief,
                        f"/home/{u}/{rol}/{INSTR[pv]} ({nombre} brief)")
        if pv == "codex":
            confianza_codex(u)

    seccion("10c. fleet.toml: your limits, and the clusters the agents may use",
            "Read by the fleet tools and the coordinators: how many messages a coordinator may exchange before reporting to you, and each cluster's boxes. The agents read it and cannot change it. The tools themselves are installed by herramientas/install.")
    ensure_dir(FLEET_ETC, HUMANO, "buzon", 0o2750, f"fleet configuration: the agents read, {HUMANO} writes")
    ensure_installed(FLEET_SRC, f"{FLEET_ETC}/fleet.toml", 0o640, "fleet.toml")

    seccion("10d. skills: shared how-to manuals, installed for the working agents",
            "Each skill in flota/skills is copied to /home/agents/etc/skills, readable by the working agents. Claude Code finds it through a link in ~/.claude/skills of each claude agent; codex reads it by its path, named in the conventions. Agents read them and cannot change them.")
    if os.path.isdir(SKILLS_SRC):
        ensure_dir(SKILLS, HUMANO, "buzon", 0o2750, f"skills: the agents read, {HUMANO} writes")
        for nombre in sorted(os.listdir(SKILLS_SRC)):
            origen = os.path.join(SKILLS_SRC, nombre)
            if not os.path.isdir(origen):
                continue
            destino = f"{SKILLS}/{nombre}"
            ensure_dir(destino, HUMANO, "agents", 0o2750, f"skill {nombre}")
            for archivo in sorted(os.listdir(origen)):
                if os.path.isfile(os.path.join(origen, archivo)):
                    ensure_installed(os.path.join(origen, archivo), f"{destino}/{archivo}", 0o640,
                                     f"skill {nombre}/{archivo}", group="agents")
            for u in PARES:
                if proveedor(u) == "claude":       # codex reads them by path
                    ensure_link(u, f"/home/{u}/.claude/skills/{nombre}", destino,
                                f"~{u}/.claude/skills/{nombre} (skill {nombre})")

    seccion("10e. sudo: you may act as each AI user without your password, never as root",
            f"`sudo -u <AI user>` without a password, for {HUMANO} only, towards the AI users of fleet.toml only: flota runs their side of a fetch, a copy, a restart as them. `sudo` alone, root, still asks. The agents get no sudo at all.")
    sudoers = "/etc/sudoers.d/flota"
    lineas_sudo = [f"# flota: {HUMANO} acts as the AI users without a password; root still asks. "
                   "Written by plan-agentes.py.",
                   f"{HUMANO} ALL=({','.join(AGENTES)}) NOPASSWD: ALL"]
    try:
        with open(sudoers) as f:
            al_dia = f.read() == "\n".join(lineas_sudo) + "\n"
    except FileNotFoundError:
        al_dia = False
    except OSError:
        al_dia = None                         # /etc/sudoers.d is root's: a routine check
    if not al_dia:
        do(llamar("sudoers_flota", sudoers, *lineas_sudo),
           f"{HUMANO} may run commands as {', '.join(AGENTES)} without a password (not as root)",
           rutina=al_dia is None)

    seccion("11. resources: your session first, then the agents, as fleet.toml says",
            'CPU, memory and swap per user (systemd slices), so your own session always comes first, and an agent that runs out of memory loses its biggest process instead of freezing everything.')
    cambios = [ensure_slice(u, props) for u, props in RECURSOS.items()]
    if any(cambios):
        do("systemctl daemon-reload", "systemd rereads the slice limits")

    # ---- output ------------------------------------------------------------------
    acciones = [p for p in plan if p[0]]
    cambios = [p for p in acciones if not p[3]]
    rutinas = [p for p in acciones if p[3]]
    root = any(p[2] for p in acciones)
    out = sys.stdout
    out.write(f"# plan generated {datetime.datetime.now():%Y-%m-%d %H:%M} by plan-agentes.py\n")
    # the counts line is read by sistema/instalar and flota: keep its form
    out.write(f"# changes: {len(cambios)}, routine checks: {len(rutinas)}\n")
    if not acciones:
        out.write("# nothing to do: everything is already configured\n")
    elif root:
        out.write("# NEEDS ROOT. Run with:  sudo bash plan.sh\n")
    else:
        out.write("# Does NOT need root. Run with:  bash plan.sh\n")
    out.write("set -euo pipefail\n")
    out.write("umask 022    # whatever root's umask is, what the plan creates stays readable to the planner\n")
    c = color(out)
    e = color(sys.stderr)

    def funciones(w, c):
        """The HELPERS the plan calls, defined once, before any line uses them."""
        if not usados:
            return
        w("\n" + c("# == helpers: what the routine checks run. Read them once; each is called below", "1;36")
          + "\n" + c("#    with its arguments, one line per check.", "2") + "\n")
        for f in usados:
            w("\n" + HELPERS[f] + "\n")

    def secciones(w, c, rutina):
        """The changes (rutina False) or the routine checks (True), by section: titles
        in bold cyan, what each is for dimmed, commands in green, why each runs dimmed."""
        pendiente = None
        for cmd, why, _, es_rutina in plan:
            if cmd is None:
                pendiente = why                    # only sections that have actions
                continue
            if es_rutina != rutina:
                continue
            if pendiente:
                titulo, porque = pendiente
                w("\n" + c(f"# == {titulo}", "1;36") + "\n")
                if not rutina:
                    for linea in textwrap.wrap(porque, 84):
                        w(c(f"#    {linea}", "2") + "\n")
                pendiente = None
            w(c(cmd, "32") + "    " + c(f"# {why}", "2") + "\n")

    def todo(w, c):
        funciones(w, c)
        if cambios:
            w("\n" + c(f"# ==== CHANGES ({len(cambios)}) " + "=" * 60, "1;33") + "\n")
            secciones(w, c, False)
        if rutinas:
            w("\n" + c(f"# ==== ROUTINE CHECKS ({len(rutinas)}): they change nothing when all is in place "
                        + "=" * 6, "1;33") + "\n")
            for linea in textwrap.wrap(
                    "The planner runs as you and cannot see what the AI users' tools keep "
                    "private in their homes (~/.codex, for one), so it cannot tell whether "
                    "these are already right. Each line asks the system and "
                    "acts only if something is missing or wrong. They run last: they concern only "
                    "what already exists. They appear on every run.", 84):
                w(c(f"#    {linea}", "2") + "\n")
            secciones(w, c, True)

    todo(out.write, c)

    # The screen report, on stderr: the plan itself may be going to a file.
    w = sys.stderr.write
    w(banner(f"1. FILES THAT CHANGE ({len(diffs)}): read every diff", e))
    if not diffs:
        w("  none\n")
    for nombre, dst, diff in diffs:
        w("\n" + e(f">> {dst}", "1;33") + e(f"  ({nombre})", "33") + "\n" + pintar_nota(diff, e) + "\n")
    raiz = "with sudo" if root else "without root"
    w(banner(f"2. COMMANDS OF THE PLAN ({len(cambios)} changes, {len(rutinas)} routine checks; {raiz})", e))
    if not acciones:
        w("  none: everything is already configured\n")
    elif out.isatty():
        w("  printed above, on the terminal\n")
    else:
        todo(w, e)
    if no_disponibles:
        w(banner(f"FEATURES LEFT OUT ({len(no_disponibles)}): a program they need is missing", e))
        for funcion, que_hace, programa, como in no_disponibles:
            w("\n" + e(f"!! {funcion} is in fleet.toml, but {programa} is not installed", "1;31") + "\n")
            for linea in textwrap.wrap(f"What it does: {que_hace}", 84) + \
                    textwrap.wrap(f"To get {programa}: {como}. Then run the planner again.", 84):
                w(f"   {linea}\n")
    w(banner(f"3. NOTES ({len(notas)})", e))
    for n in notas or ["none"]:
        w("\n" + pintar_nota(n, e) + "\n")
    w(banner("4. BY HAND, NOT PART OF THE PLAN", e))
    alias = []
    tmux = shutil.which("tmux") or "/usr/bin/tmux"   # by YOUR PATH, never an agent's
    for u in AGENTES:
        if u in PENSADEROS:
            alias.append(f"alias t{u}='sudo machinectl shell {u}@ {tmux} new -As {u} -c /home/{u}'")
        else:
            alias.append(f"alias t{u}='sudo machinectl shell {u}@ {tmux} new -As flota'")
    casa = pwd.getpwuid(os.getuid()).pw_dir
    clon = "~" + CFG[len(casa):] if CFG.startswith(casa + "/") else CFG
    alias.append(f"alias flota={clon}/sistema/flota")
    if any(dst == TMUX_DST for _, dst, _ in diffs):
        REINICIAR.update(AGENTES)
    reiniciar = {u: ["this plan changes its groups, PATH or tmux"] for u in REINICIAR if u != HUMANO}
    for u in AGENTES:
        r = servidores_tmux(u)
        if r is UNKNOWN:
            reiniciar.setdefault(u, []).append("its processes are not visible in /proc")
        elif r:
            reiniciar.setdefault(u, []).extend(r)
    faltan = alias_faltantes(alias)
    sin_activar = grupos_sin_activar()
    n = 0
    if HUMANO in REINICIAR or sin_activar:
        n += 1
        w(f"""
  {n}. Log out of your desktop session and back in, so that your login carries your new
     groups{' (' + ', '.join(sin_activar) + ')' if sin_activar else ''}. Until then `flota entregar`, `flota traer`
     and the fleet tools fail with "Permission denied". A new terminal is not enough;
     to go on in this one now: exec su -l $USER
""")
    if reiniciar:
        n += 1
        w(f"""
  {n}. Restart these agents' tmux servers (tmux kill-server as each user, then its alias),
     so they pick up groups, PATH and tmux configuration in their own slice:
""" + "".join(f"       {u}: {', '.join(r)}\n" for u, r in sorted(reiniciar.items())))
    if faltan:
        n += 1
        w(f"\n  {n}. Add to YOUR ~/.bashrc:\n" + "".join(f"       {a}\n" for a in faltan))
    if not n:
        w("\n  nothing: the agents' tmux servers are up to date and your aliases are in place\n")
    w(e("\n  Never run git inside a repo an agent can write, nor add safe.directory for it:"
        "\n  git fetch from YOUR clone.", "2") + "\n")


if __name__ == "__main__":
    main()
