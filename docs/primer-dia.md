# A first day with the fleet

One example from start to end: you hand the fleet a repository, two sessions work on
it, you bring their work home, and you change one of the fleet's own rules. What you
type is in Spanish, as you would say it; the fleet answers in Spanish too.

The example: `mdsim`, a simulation code of yours. You want it to build with the new
compiler, and to know how fast it runs on a cluster.

## 0. The fleet is running

After installing (`de-cero.md`), `flota arrancar` opens tmux as `claude` with the
coordinator, **coord**, in its window. You talk to coord; it talks to the rest.

## 1. Hand over the repository

In a terminal of yours:

    flota entregar ~/agents/mdsim claude

The `claude` AI user gets its own copy in `~/work/mdsim`. Yours is untouched.

## 2. Give coord the objective

In coord's window:

> Quiero que mdsim compile con gcc 15 y saber cuánto tarda en serafin con 1, 2 y 4
> nodos.

coord answers with a plan, not with work: two working sessions, `mdsim` (fix the
build, in `~/work/mdsim`) and `mdsim-bench` (the runs on serafin, once the build is
fixed); what each one does, in what order, and what is left out. Nothing starts until
you say so:

> Dale.

## 3. Open the sessions

coord gives you the lines to type, because no session types into another's window.
In `tclaude`, a new tmux window for each:

    cd ~/work/mdsim && claude -n mdsim

and the same for `mdsim-bench`. coord briefs each one.

## 4. While they work

They talk to each other when they need to: `mdsim-bench` asks `mdsim` which commit
builds; `mdsim` tells it when the fix is in. You do not relay anything.

What needs you arrives at one place. Ask coord:

> ¿Quién me espera?

Each question comes as a menu. Some only you can answer in the session's own window:
anything irreversible, such as deleting data on a cluster.

## 5. Bring the work home

`mdsim` says its branch is ready: `claude/gcc15`, what changed, how it was tested.
In your terminal:

    flota traer

It shows the branch's commits and diff, and merges it into your clone if you say yes.
Then you push to GitHub, as always: the agents never push.

`mdsim-bench` leaves its numbers in its notes and tells coord; coord tells you.

## 6. Change how the fleet works

Say you want every working session to run the tests before handing over a branch.
That is a rule of the fleet, and the **architect** owns the rules. In `tclaude`:

    cd ~/arquitecto && claude -n arquitecto

> Quiero que las sesiones de trabajo corran los tests antes de entregar una rama.

It says where the rule goes and shows you the change; with your yes, it makes a
branch of `flota`. Then:

    flota traer            # review and merge the branch
    flota instalar --go    # install the new rule
    flota reiniciar        # the sessions load it

New kinds of agent work the same way: a permanent role (a reviewer, a librarian) is a
brief, and the architect writes it. A one-off job needs no role: tell coord, as in
step 2.

## 7. Let the fleet learn

At the end of a week:

> Procesar lo aprendido.

Every session sends the architect a proposal: a rule that got in the way, a tool
that is missing. When coord says they are in, tell the architect "procesá lo
aprendido": it shows you one plan, and you choose what goes in.

Next: `seguridad.md` (what protects what), `COMANDOS.md` (everything you can ask),
`aportes.md` (sending changes back to the group).
