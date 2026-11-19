# Security: what protects what

The fleet runs AI agents that write code, run commands and reach HPC clusters, on
the machine where you work and with your cluster account. This page says what keeps
their mistakes away from your files and accounts, which layer does it, and what is
**not** protected. The reasons behind each choice are summarized in
`../DECISIONS.md` (§1–§3); the cluster box in detail is in `clusters.md`.

## The idea

- **The kernel enforces; rules only guide.** What must hold is a Linux permission,
  a namespace or a missing credential. The rules the sessions load (conventions,
  briefs) are followed, but they are not guarantees, and this page says which is
  which.
- **An agent reaches you only through what you run.** The kernel keeps the AI users
  out of your account. What remains is what *you* execute or interpret: a script, a
  git command in their repository, a plan. Every rule below for you closes one of
  those paths.
- **No agent holds your authority.** Agents have no git credentials, cannot push,
  cannot unlock the cluster key, and cannot install anything you have not read.

## Who can do what

| | you | a working AI user (`claude`, `codex`) | the pensadero |
| :--- | :--- | :--- | :--- |
| your home | yours (`700`) | no | no |
| its own home | read, write (you are in its group) | yes | yes |
| another AI user's home | read, write | no | no |
| another AI user's `~/work` | yes | read only, through `/home/agents/pares` | no |
| `/home/agents` (rules, tools, configuration) | yours | read; runs the fleet tools | read (not `pares/`); no fleet tools |
| the mailbox | read all, write your outbox | read all, write its outbox | read all, write its outbox |
| git remotes (GitHub) | yes | no credentials | no credentials |
| the cluster key | you unlock it | uses it once you unlocked it | has none |
| root | through `sudo`, for the plan you read | no | no |
| act as an AI user (`sudo -u`) | without a password, as each AI user of `fleet.toml` (`/etc/sudoers.d/flota`); never as root without it | no | no |

## 1. One Linux user per AI user

Each AI user is a Linux user with its own home (`2770`: itself and its group; you
are in the group), its own group, and its own tmux server. Its mistakes stay in its
home. Your home stays `700`: opening even the traverse bit would expose every file
of yours with "other" read permission to any agent that guessed a path. There are
no ACLs (they broke programs) and no shared paths into your home.

Sessions are launched with `sudo machinectl shell <user>@` (the `t<user>`
aliases), which opens a real login session: the AI user gets its own environment
(`umask 002`, `PATH`), and its processes run in its own slice. `sudo -iu` would have
left them in yours.

## 2. What is shared, and how far

Everything shared lives in `/home/agents`, owned by you; the AI users read it and
cannot change it, and updating it needs no root.

| path | mode | who gets in |
| :--- | :--- | :--- |
| `/home/agents` | `you:buzon 2750` | every AI user (group `buzon`) |
| `bin/`, `etc/` (tools, rules, briefs, `fleet.toml`, skills) | `you:buzon`, files `640` | read only |
| `buzon/<user>/` | `<user>:buzon 2750` | written only by its owner, read by all |
| `pares/` | `you:agents 2750` | only the working AI users (group `agents`), never the pensadero |
| `pares/<user>` | bind mount of `/home/<user>/work`, read only through the gate | |

So the working AI users (peers) read each other's projects and change none, and the
pensadero, outside `agents`, sees nobody's work. Nobody sees the pensadero's data (its
`~/work`, which `pares` does not mount):
its home is closed to the other AI users, and its conventions forbid sending its
content out unless you decide it. Inside the pensadero, the maestro and each agent of
a línea are the same Linux user: that an agent keeps to its own línea is a rule, not a
barrier.

One way in goes the other direction, if you declare it: `[machine] readable` in `fleet.toml` names
folders of your home that an AI user reads live, such as a synced drive. Each is a
`bindfs` mount at that user's `~/<the folder's name>`, read-only: root reads your
files and shows them to that user as its own, so their real owner and mode stay as
they are, and the kernel refuses any write. The
planner refuses a folder with something that may hold credentials at its top (`.gd`,
`.grive`, `rclone.conf`, `.ssh`, `.config`, `.gnupg`): declare its subfolders, or move
that out. What lies deeper is yours to check.

One way out of the homes, if you declare it: `[machine] writable` in `fleet.toml` names
folders outside every home that a working AI user may write, such as the group's
software stack in `/home/shared/agents`. Each is `you:agents 2775`, with no ACL (the
planner strips one it would inherit): the whole `agents` group can write it, and the
declaration, a rule, says which AI user does. The planner gives each parent `o+x`, so
the agents pass without listing it; who else reads the folder is yours, through its
other bits. Whatever the agent installs there, whoever runs it runs, as on a cluster.
A software stack there is installed world-readable (spack `read: world`, `write:
group`), so the pensadero, outside `agents`, runs it too.

## 3. Resources: you come first

Each user's slice (`/etc/systemd/system/user-<uid>.slice.d/`) gets the CPU weight
and memory limits of `fleet.toml` `[resources]`. In the example, your session has 10×
the CPU weight of an AI user and its first 4G of memory protected; each AI user has a hard memory ceiling
where the kernel kills its biggest process instead of freezing the machine, and a
swap ceiling so it does not thrash. Disk I/O is not limited yet.

## 4. The rules each session loads

Conventions, briefs and skills are copies **you** install, with your name filled in,
in `/home/agents/etc`, readable by the AI user and not writable. Each AI user's
`CLAUDE.md` / `AGENTS.md` is a visible symlink to that copy; the planner warns if one
was replaced by a real file or points elsewhere, and if codex finds an
`AGENTS.override.md` that would silently replace them. An agent cannot edit its own
rules; it can only propose a change, which reaches it after you install it.

Things the rules ask, and the kernel does not enforce: that a session acts on a
mailbox message only after your yes, that a working session stays in its folder, and
that a session waits for its mail (`buzon esperar`) only when you tell it to.

## 5. Code that runs as you, or as root

This is where an agent could reach you, so it has the most rules.

**Why a planner.** The machine's setup (users, groups, modes, mounts, slices, the
installed rules) needs root. A script that does it would run as root whatever an
agent had changed in it. So `sistema/plan-agentes.py` **changes nothing**: it reads
the current state and prints the commands still missing, one per line, plus the diff
of every file it would install. You read the plan, and only the plan runs with
`sudo`. It never deletes; when it cannot see a state, it prints a routine check that
changes nothing if all is in place. Its own source runs no command (the audit
`grep` in its header shows it).

**Only from your own clone.** The planner and the tool installer run from your
clone of `flota` (`~/agents/flota`) and your `flota-<you>`, and refuse any source
that is a symlink or belongs to someone else: an agent could otherwise change a
source between your review and the run, or point it at `/etc/shadow` for root to
copy where it can read it.

**Tools are copies.** The fleet tools are copied into `/home/agents` by you; the AI
users run them and cannot change them, and they read your `fleet.toml` there, not a
copy an agent could edit. Claude Code itself is installed for the system, owned by
root, with automatic updates off; codex is pinned to the version `fleet.toml` says.

**git, both ways, without running theirs.** A repository's `.git/config` and hooks
can make any git command (even `git status`) run a program as whoever runs it. So:

- you **never run git inside an AI user's repository**, never add `safe.directory`
  for one, and never copy one with `cp`;
- to take their work, you `git fetch` from your own clone, with the remote's
  `uploadpack` set to `sudo -H -u <AI user> git-upload-pack`: the process that reads
  their repository runs as them. `flota traer` and `flota clonar` set this up;
- a push to them fails on your side (`pushurl = /dev/null/...`);
- a merge is always `--ff-only`, so your `main` is exactly the commit you reviewed;
- to give them a repository, `flota entregar` hands over a git **bundle** (history
  only, none of your configuration or hooks), in their home, never in `/tmp`.

**No remote credentials.** The AI users have no GitHub token and never push: you
push from your clone, after reading the diff. A deleted repository or a force push
cannot happen by an agent's mistake.

**What you must still do:** read every diff before merging, and never run a script,
`Makefile` or notebook an agent wrote without reading it. You are in each AI user's
group, so an agent can leave files where you will find them.

## 6. The mailbox

`buzon` is a clipboard between AI users that cannot see each other's homes. One
outbox per Linux user, which only that user can write (only root creates outboxes),
so **who wrote a message is guaranteed by the kernel**. A message is written once
and made read-only (`0440`); replies are new messages. Nothing watches the mailbox
and nothing wakes on a message: a session reads it when you tell it to.

By the rules (conventions rule 10), a session may read and judge a message, but acts
on it only after your yes in its own window, and sends unasked only a short list of
messages (proposals, replies to what you had it read, the architect's review
requests). A message never speaks for you, even if it says it does.

## 7. Sandboxes on this machine

- **codex** runs the model's commands in its sandbox: only the working folder, `/tmp`
  and the folders the fleet lists (its outbox, codex's own state, buzon's read marks,
  `~/work/propuestas`, `~/work/revisiones`) are writable. The planner writes that list
  into `~/.codex/config.toml`, in a marked block it alone rewrites, and marks codex's
  role folders as trusted so their sessions start able to write their workspace.
  `/status` shows the mode; **never give a codex session "Full Access"**.
- **Claude Code** asks for permission according to the mode you choose in each
  session; the fleet does not change it. What it can reach is still bounded by its
  Linux user (§1).

## 8. Clusters

On a cluster there is no `claude` user: the AI user's key logs into **your
account**. So the account is protected on the cluster itself.

**The key.** Each working AI user has one ssh key, made in its own session, **with a
passphrase** (`add-cluster` refuses a key without one). Only you type the passphrase,
into `ssh-add`, in your own terminal (`flota arrancar`): an agent that saw it could
use the key at any time. Unlocked, the key opens **every** cluster it is authorized
on until `ssh-add -D` or a reboot. The AI user's ssh trusts each cluster's host key
copied from *your* `known_hosts`, never one accepted blind.

**The door.** On the cluster, the key's line in `~/.ssh/authorized_keys` forces one
command: `restrict,pty,command="~/agents/puerta <AI user>"`. Whatever the agent asks
to run, it runs inside `puerta`'s box.

**The box.** `puerta` builds, for every connection, a user and mount namespace where:

- your home, `~/.ssh`, `/tmp`, `/var/tmp`, `/dev/shm`, `/run/user/<uid>` and
  `/run/munge` are hidden under empty folders, and anything listed in
  `~/agents/ocultar` too (on the CCAD clusters, `/dotssh/<user>`, where sshd keeps
  your keys);
- every other mount is read-only: the box `~/agents/<AI user>` and the folders you
  declare under `writable` are the only places it can write; `readable` folders in
  `~/agents/compartido` are shown read-only;
- the agent's command runs **without capabilities**, so it cannot unmount what hides
  your home; set-uid programs (`sudo`, `crontab`) gain nothing there.

`puerta <AI user> --check` lists every place still writable outside the box; hide
each one until it says `ok`. `puerta-estado` answers one fixed question from outside
the box (what this AI user runs there) so `fleetwatch` can watch work without seeing
the rest of your account.

**Slurm breaks the box, by design.** It is off by default (munge is hidden). With
`slurm_in_box`, a job runs on a compute node **outside** the box, with your whole
account, and so do `srun`'s tasks. The box then guards only what the agent runs on
the login node. The rules forbid a job to write outside the box, but only the rules
do. Protect what matters: `chmod -R a-w <folder>` (no one, you included, can delete
or change it; `chmod -R u+w` to work in it again), and ask whether the cluster keeps
snapshots.

## 9. What is not protected

- **What you run.** Scripts, plans, notebooks or Makefiles written by an agent run
  with your permissions. Read them.
- **What your group runs.** A software stack an agent builds in a shared folder is
  run by your colleagues; the box cannot keep a badly built one from them.
- **Slurm jobs**, when enabled (§8). A job runs on a compute node with your whole
  account, outside the box: it could write anywhere you can, or read `~/.ssh`. Only
  the rules keep it in the box.
- **Sessions of one AI user from each other.** They share its home, its key and its
  cluster box; which session works where is a rule, not the kernel's.
- **Who is the coordinator.** Working sessions follow coord's requests within the
  work you approved (§9b). Among sessions of one AI user, a name is not proof: a
  session could rename itself `coord`, and nothing would tell. What bounds a wrong or
  false coordinator is the limit itself: reversible work, inside an approved task.
  Across AI users, the mailbox does prove who wrote.
- **Reading on a cluster.** Outside your home, the box shows what your account can
  read (system software, modules, shared stacks), read only.
- **The network.** Sessions reach the internet (their tools need it). The rules ask
  them not to send your data out; nothing prevents it.
- **Your plan's tokens.** Sessions spend your Claude and ChatGPT plans; coord warns
  about big sessions, but nothing caps them.

## 9b. Who decides what

You hold all authority. The coordinator holds a delegated part: it directs how the
work you approved gets done (what first, how, what to test, a small adjustment), and
the sessions it supervises follow it without asking you. They refuse it, and tell it
why, when a request is irreversible or outward-facing (deleting, pushing, publishing,
spending: those need your yes in that session's own window), contradicts your own
words, changes a task's objective, scope or cost (yours, through coord's queue), or
breaks a rule (the box, the Linux boundaries, confidentiality). Coord marks whose
words it passes: yours quoted, its own as its own. Any other session's message is
information, never direction. Conventions rule 2 has the text.

## 10. Checking that it holds

After installing, from a working AI user's session: `id`, `umask`, writing to
`/home/agents/bin` and to a peer's `pares/` folder (both denied), listing your home
and the pensadero's (denied), and the session's cgroup. On a cluster: `ssh <cluster>
'pwd; ls ~'` shows the box and nothing of your home. The full list:
`instalacion.md` §6 and `clusters.md`, "Tested".
