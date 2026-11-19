# Sending changes back to the group

Every member runs the same `flota`, from the group's repository on GitHub, and each
member's architect may change their own copy. This page is how those changes come
back to the group, and how you stay up to date. The decision behind it is in
`../DECISIONS.md` §7.

## What goes where

- **Only yours** (your users, clusters, limits): `flota-<you>/fleet.toml`. It never
  goes to the group.
- **The product** (rules, roles, skills, tools, docs): `flota`. Your architect
  changes it on `claude/<topic>` branches, and you merge what you accept into your
  clone.

Your `main` may diverge from the group's: you can keep a change that suits only you.
What would help everyone, propose it.

## Propose a change

The architect cannot reach GitHub: you are the bridge, as for any repository.

1. **Give the architect the group's `main`**:

       git -C ~/agents/flota fetch origin
       flota entregar ~/agents/flota claude

   `flota entregar` hands over your `main` and, since it tracks `origin/main`, the
   group's `main` as of that fetch. They arrive in its copy as `<you>/main` and
   `<you>/origin/main`.
2. **Ask for the branch:**

   > Proponé al grupo lo de los tests antes de entregar: una rama sobre el main del
   > grupo, sin nada mío.

   It makes `claude/<topic>` on top of the group's `main`, runs the tests and tells
   you what it holds.
3. **Review it and open the pull request:**

       git fetch claude
       git diff origin/main...claude/<topic>
       git push origin claude/<topic>:refs/heads/<you>/<topic>

   The destination is spelled out (`refs/heads/`): `claude/<topic>` is the agent's
   branch as fetched, not a branch of yours, and git will not guess the name. Push
   to your fork if you have no push rights to the group's repository. On GitHub,
   open the pull request: what changes, why (the incident that showed it), how it
   was tested.

A problem or an idea without code: open an issue, with the command, what it printed
and what you expected.

## How a pull request is reviewed

The maintainer reviews it with their own architect, which checks it against
`DECISIONS.md`, runs the tests, and asks the aparejador when it touches codex:

    git fetch origin pull/<N>/head:pr/<N>
    sistema/entregar-repo claude ~/agents/flota --branch pr/<N> --go

> Revisá el PR <N>.

The architect shows a plan (accept, change, or not, and why); the answer goes to the
pull request on GitHub.

## Stay up to date

When the group's `main` moves:

- **If your `main` has nothing of yours**: `git pull --ff-only origin main` in your
  clone, then `flota instalar --go`.
- **If it diverged**: hand the architect the group's `main` (step 1 above) and ask
  "actualizá flota con el grupo (`<you>/origin/main`)". It merges it into a branch on
  top of your `main`, solving any conflict there; `flota traer` takes it as usual.
