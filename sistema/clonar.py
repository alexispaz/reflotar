#!/usr/bin/env python3
"""clonar.py -- print the commands to clone an agent's repo safely, or to add it as a remote.

    python3 ~/agents/flota/sistema/clonar.py claude buzon      # -> ~/agents/buzon
    python3 ~/agents/flota/sistema/clonar.py codex dana ~/x    # another destination
    python3 ~/agents/flota/sistema/clonar.py claude grupo --rama claude/init

A new repository has no main until you accept its first branch (conventions rule
12): then the clone starts from the AI user's one branch, or from the one --rama
names when it has several. A command is never printed with a placeholder in it.

Like plan-agentes.py, it changes nothing: it only reads files and prints. Run it
from YOUR clone of flota, never from the agent's copy.

What the printed commands take care of:
  - the process that reads the agent's repo (git-upload-pack) runs AS THE AGENT,
    through sudo, never as you. Nothing of the agent's repo runs with your user, so
    no safe.directory is needed, not even with -c. Your git only receives the data,
    as from any remote;
  - git clone --no-local: no hardlinks to object files the agent owns;
  - --branch main: you start on what you accepted, not on the agent's current branch
    (a new repository: its <agent>/* branch, to review before you make it your main);
  - the remote is named after the agent and fetches its <agent>/* branches, nothing
    else: not its main, which it does not use (conventions rule 12) and may delete,
    and a refspec naming a deleted branch aborts the whole fetch;
  - your branch follows no remote: a plain `git push` would go to the agent, where it
    fails; the first push is yours, `git push -u origin <branch>`;
  - the remote cannot be pushed to: a push would start git-receive-pack in the
    agent's repo AS YOU, with the agent's hooks, which is what git's "dubious
    ownership" stops. Pushing to it fails on your side, before reaching it.
After that, a plain `git fetch <agent>` asks for your sudo password and fetches.
Nothing here runs git inside the agent's repo with your user.
"""
import os
import shlex
import sys
import zlib

FLEET_TOML = "/home/agents/etc/fleet/fleet.toml"   # installed by the planner


def agentes_de_trabajo():
    """Every AI user of the installed fleet.toml, the pensadero included: its ~/work
    holds repos like any other's."""
    import tomllib
    try:
        with open(FLEET_TOML, "rb") as f:
            cfg = tomllib.load(f)
        agents = cfg.get("ai_users") or cfg.get("agents", {})   # [agents]: the old name
    except OSError as e:
        sys.exit(f"cannot read {FLEET_TOML} ({e.strerror}): run the planner first")
    if not agents:
        sys.exit(f"no [ai_users] in {FLEET_TOML}: run the planner with your flota-<you>/fleet.toml first")
    return tuple(agents)
PUSHURL = "/dev/null/no-push-fetch-only"   # a path that cannot exist: any push to the agent fails here, at once, without the network
q = shlex.quote


def rama_por_defecto(repo):
    """main or master, read from the agent's refs as plain files (no git is run there)."""
    for rama in ("main", "master"):
        if os.path.exists(f"{repo}/.git/refs/heads/{rama}"):
            return rama
    try:
        with open(f"{repo}/.git/packed-refs") as f:
            refs = f.read()
    except OSError:
        return None
    for rama in ("main", "master"):
        if f" refs/heads/{rama}\n" in refs:
            return rama
    return None


def ramas_de(repo, agente):
    """The <agente>/* branches, read from the repo's refs as plain files."""
    ramas = set()
    base = f"{repo}/.git/refs/heads"
    for raiz, _, archivos in os.walk(f"{base}/{agente}"):
        ramas.update(os.path.relpath(os.path.join(raiz, a), base) for a in archivos)
    try:
        with open(f"{repo}/.git/packed-refs") as f:
            for linea in f:
                partes = linea.split()
                if len(partes) == 2 and partes[1].startswith(f"refs/heads/{agente}/"):
                    ramas.add(partes[1][len("refs/heads/"):])
    except OSError:
        pass
    return sorted(ramas)


def sha_de(repo, rama):
    """The commit a branch points to, read from its loose ref or packed-refs; None if absent."""
    try:
        with open(f"{repo}/.git/refs/heads/{rama}") as f:
            return f.read().strip()
    except OSError:
        pass
    try:
        with open(f"{repo}/.git/packed-refs") as f:
            for linea in f:
                partes = linea.split()
                if len(partes) == 2 and partes[1] == f"refs/heads/{rama}":
                    return partes[0]
    except OSError:
        pass
    return None


def padres(repo, sha):
    """A commit's parents, from its loose object (zlib, read as a plain file); None when
    the object is not loose (packed) or not a commit: then nobody can tell from here."""
    try:
        with open(f"{repo}/.git/objects/{sha[:2]}/{sha[2:]}", "rb") as f:
            datos = zlib.decompress(f.read())
    except (OSError, zlib.error):
        return None
    cabecera, _, cuerpo = datos.partition(b"\0")
    if not cabecera.startswith(b"commit "):
        return None
    out = []
    for linea in cuerpo.split(b"\n"):
        if not linea:
            break
        if linea.startswith(b"parent "):
            out.append(linea[7:].decode())
    return out


def contiene_a_todas(repo, rama, otras, limite=10000):
    """True when every branch in otras is an ancestor of rama (or the same commit);
    False when one is not; None when a commit could not be read here."""
    faltan = {sha_de(repo, o) for o in otras}
    if None in faltan:
        return None
    vistos, pila = set(), [sha_de(repo, rama)]
    while pila and faltan and len(vistos) < limite:
        sha = pila.pop()
        if sha in vistos:
            continue
        vistos.add(sha)
        faltan.discard(sha)
        ps = padres(repo, sha)
        if ps is None:
            return None
        pila.extend(ps)
    if not faltan:
        return True
    return False if not pila else None                    # walked it all, or hit the limit


def rama_tope(repo, ramas):
    """The one branch that holds all the others, if the history here says so; None
    otherwise (they diverge, or a commit is packed and cannot be read)."""
    for rama in ramas:
        if contiene_a_todas(repo, rama, [r for r in ramas if r != rama]):
            return rama
    return None


def elegir_rama(origen, agente, elegida=None):
    """(branch to start from, whether the repository is new: no main yet). A new one
    starts from the AI user's only branch, the one named, or the one that holds all
    the others; several that diverge and none named, or none at all, stop here: a command never carries a placeholder."""
    rama = rama_por_defecto(origen)
    suyas = ramas_de(origen, agente)
    if elegida:
        if elegida not in suyas + ([rama] if rama else []):
            sys.exit(f"clonar.py: no branch {elegida} in {origen}; its branches: "
                     f"{', '.join(suyas + ([rama] if rama else [])) or 'none'}")
        return elegida, elegida != rama
    if rama:
        return rama, False
    if len(suyas) > 1:
        tope = rama_tope(origen, suyas)
        if tope:
            print(f"clonar.py: {origen} has no main yet; {tope} holds every other {agente}/* branch "
                  f"({', '.join(r for r in suyas if r != tope)}): starting from it", file=sys.stderr)
            return tope, True
    if len(suyas) != 1:
        sys.exit(f"clonar.py: {origen} has no main yet, and "
                 + (f"several {agente}/* branches: {', '.join(suyas)}. Name one with --rama"
                    if suyas else f"no {agente}/* branch to start from"))
    return suyas[0], True


def main():
    args = sys.argv[1:]
    elegida = None
    if "--rama" in args:
        i = args.index("--rama")
        if i + 1 >= len(args):
            sys.exit("clonar.py: --rama needs a branch name")
        elegida = args[i + 1]
        del args[i:i + 2]
    if len(args) not in (2, 3) or args[0] not in agentes_de_trabajo():
        sys.exit(__doc__.split("\n\n")[1])
    agente, nombre = args[0], args[1]
    origen = f"/home/{agente}/work/{nombre}"
    destino = os.path.expanduser(args[2] if len(args) == 3 else f"~/agents/{nombre}")
    uploadpack = f"sudo -H -u {agente} git-upload-pack"
    refspec = f"+refs/heads/{agente}/*:refs/remotes/{agente}/*"

    if not os.path.isdir(f"{origen}/.git"):
        sys.exit(f"clonar.py: {origen} is not a git repo (or you cannot read it)")
    rama, nueva = elegir_rama(origen, agente, elegida)

    print(f"# {agente}/{nombre} -> {destino}")
    if os.path.isdir(f"{destino}/.git"):
        print(f"# {destino} already exists: add {agente} as one more remote")
        print(f"cd {q(destino)}")
        print(f"git remote add -t {q(rama)} {agente} {q(origen)}")
    else:
        if nueva:
            print(f"# {origen} has no main yet (a new repository): starting from {rama}. Review it;")
            print(f"# if you accept it, it becomes your main:  git switch -c main")
        print(f"mkdir -p {q(os.path.dirname(destino))}")
        print(f"git clone --no-local --upload-pack={q(uploadpack)} --single-branch --branch {q(rama)} "
              f"--origin {agente} {q(origen)} {q(destino)}")
        print(f"cd {q(destino)}")
    print(f"git config remote.{agente}.uploadpack {q(uploadpack)}")
    print(f"git config remote.{agente}.pushurl {q(PUSHURL)}")
    # only its <agent>/* branches: its main is not used (conventions rule 12), and if the
    # agent deletes it, a refspec naming it would abort every fetch (2026-10-20)
    print(f"git config --replace-all remote.{agente}.fetch {q(refspec)}")
    if not os.path.isdir(f"{destino}/.git"):
        # your main must not follow the agent: a plain `git push` would go there and fail
        print("git branch --unset-upstream")
        # the clone's own tracking ref of that branch, which the new refspec no longer updates
        print(f"git update-ref -d refs/remotes/{agente}/{rama}")
    print(f"git fetch {agente}")
    print("# your branch follows no remote: the first time, git push -u origin <branch>")
    print(f"# from now on: git fetch {agente}; git diff main...{agente}/<topic>; git merge --ff-only {agente}/<topic>")


if __name__ == "__main__":
    main()
