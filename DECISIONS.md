# Decisions

This is a summary of the decisions behind the fleet, and why each was taken. It is
condensed from the decision log of the `flota` of a DQTC group, from which reflotar was
copied; the full log, with its incidents and dates, stays private. Read this before
changing anything structural. Undoing a decision is fine, but undo it knowing what it
protected.

The architect records the decisions of *your* fleet at the end, under "## Your
fleet's decisions", dated, with what was decided and why.

---

## 1. Users and permissions

**Each AI user is its own Linux user, and the human's account is never reachable.**
An agent's mistakes stay inside its own home. The human's home stays `700`: even the
traverse bit would expose every world-readable file to an agent that guesses a path.

**Least privilege, and no all-seeing agent.**
Each AI user sees only what its role needs. The working AI users (one per provider)
are peers and read each other's work; a thinking AI user (the pensadero) sees no one's
home and no one sees its home. Agents that cannot see each other's reasoning can
criticise each other for real; one that sees everything is a single point of failure.

**The kernel enforces; rules only guide.**
Anything that must hold is a Linux permission. Rules of conduct are followed strictly,
but they are not guarantees, and the documents say which is which.

**No ACLs.**
ACLs on an agent's home broke ordinary programs (pdflatex among them). Only owner,
group and other bits, `umask`, setgid directories, bind mounts and read-only `bindfs`
mounts are used; the planner strips inherited default ACLs from folders it creates.

**Peers share through a gatekeeper directory and bind mounts.**
`/home/agents/pares` (human-owned, group `agents`, `2750`) holds bind mounts of each
peer's `~/work`. Only the `agents` group gets through, so the peers read each other
while their homes stay closed and the pensadero stays out.

**`umask 002` for every agent, setgid on shared directories, and what an agent brings
in is made group-readable.**
The human is in each AI user's group and reads its work through it. A copy keeps its
origin's mode, so files copied, downloaded or unpacked can land `600`; agents copy with
`--no-preserve=mode` and `chmod -R g+rX`, and `flota pasar` sets group read itself.

**Each AI user gets its own systemd slice, and the human comes first.**
The human must be able to use the machine without it freezing. Per-user drop-ins give
the human a high `CPUWeight` and `MemoryLow`, and each agent a hard `MemoryMax` and a
small `MemorySwapMax`, with no `MemoryHigh`. A soft limit with capped swap throttled the
whole cgroup and froze tmux and every session; a hard one kills only the runaway
process.

**A local calculation runs one at a time, in its own scope, with outputs on disk.**
`systemd-run --user --scope -p MemoryMax=... -p MemorySwapMax=0 nice timeout ...`,
named so it can be stopped. `/tmp` is in memory and counts against the same ceiling:
several runs at once with gigabytes of output there got a session, its tmux and its
keyring killed.

**Folders the agents write outside their homes are declared, human-owned, and shared
by group.**
`[machine] writable` in `fleet.toml` names them per AI user; the planner makes each
`human:agents 2775`. The declaration, not the permissions, says who writes. A shared
software stack there is installed world-readable, so an AI user outside `agents` can
run it without being let into `pares`.

**The human's own folders are shown to agents live and read-only (`[machine]
readable`).**
A read-only `bindfs` mount at `~/<name>`, the human's modes untouched. Copying a
living tree over and over is the wrong tool, and writing back would let an agent's
mistake reach wherever that tree syncs. A folder holding credentials is refused.

## 2. Code that runs as the human or as root

**An agent reaches the human only through what the human runs or interprets.**
The kernel stops agents reaching each other. The remaining paths are scripts the human
runs, repos the human runs git in, and files whose programs execute content. Every
decision below closes one of them.

**Never run git inside a repo an agent can write, and never add `safe.directory`.**
A repo's `.git/config` (`core.fsmonitor`) and hooks make any git command, even
`git status`, run a program as whoever runs it; `safe.directory` is exactly the
protection against that. The human fetches from their own clone, with `uploadpack`
set to run as the agent, and merges `--ff-only`. A `.git` never comes home by copy.

**Never run as root a script an agent can edit.**
The planner prints a plan and changes nothing; the human reads it and runs it.
Installed tools and configuration are copies the human installs after reading a diff.

**The planner installs only from the human's own clone, and refuses foreign sources.**
Between the human's review and the run, an agent could swap a source for a symlink to
a root-only file, which `install` as root would copy where the agent can read it. The
planner exits if any source, or a folder above it, belongs to someone else or is a
symlink.

**The planner describes the final state, never deletes, and says when it cannot see.**
A one-line-per-action plan is easy to review. Routine checks on state the planner
cannot read go last, as calls to a few named shell functions defined once, so the
human can tell what a plan would actually change. One-off migrations are separate
commands, never kept in the planner.

**Shared things live in `/home/agents`, owned by the human.**
On the `/home` disk they survive an OS reinstall; owned by the human, they update
without root; agents read but cannot change them.

**On a cluster, an agent's key opens only a box.**
A cluster has no agent users: the key logs into the human's account. `authorized_keys`
forces a door script that runs every command in a user and mount namespace: the home
and temporary folders under empty tmpfs, the box mounted back, everything else
read-only, `~/.ssh` (and wherever sshd really reads keys) hidden. No capabilities, so
the tmpfs cannot be unmounted. A Slurm job runs outside the box (containing it would
rule out `srun` and multi-node MPI), so Slurm is off unless the human enables it, and
rule 13 alone keeps a job's writes inside the box.

**The cluster key has a passphrase, and only the human unlocks it.**
Without one, any session could reach the cluster at any time. Agents never run
`ssh-add` or handle the passphrase: a window an agent opened could capture it.

**No ssh to a VPN cluster while its VPN is down.**
A name behind a VPN can resolve to a private address the local network routes to
someone else, and a cluster's admins can block a machine that keeps retrying. The
cluster's block declares its VPN interface, and the agent's ssh refuses to start
without it.

## 3. GitHub and remotes

**Agents hold no GitHub or remote credentials, and never push.**
No chance of approving a repo deletion or a force push by mistake. Agents commit
locally on `<ai user>/<topic>` branches; the human fetches, reviews and pushes. If a
credential is ever needed, it is scoped to one repo and cannot administer it.

**Repos reach an agent as a bundle, and come back by the human's fetch.**
The human hands a repo over (`flota entregar`), written into the agent's `~/work`, not
the world-readable `/tmp`, with no `origin`; updates arrive as `<human>/main`. A clone
fetches only the agent's topic branches and tracks no agent remote, so a plain
`git push` can never aim at the agent.

**One branch per topic, chained, with the human's `main` merged on top.**
The human's `main` is accepted by definition and the agent never commits to its own.
A new branch starts on the agent's pending one, because `flota traer` only
fast-forwards and the human does not resolve merges between sibling branches.

## 4. Communication

**The mailbox (`buzon`) is a clipboard between agents, not a command channel.**
It saves the human copying between panes. Pull-based delivery fails safely: unread,
a message just waits. Nothing acts on a message by itself.

**Authorship is the owner of the outbox, and messages are immutable.**
One outbox per Linux user, writable only by it, so the kernel proves who wrote a
message. Messages are written once, `0440`; replies and marks are new messages. Only
root creates outboxes, so no one squats on another's name.

**Read and judge freely; act only on the human's yes (rule 10).**
A session may read a message and what it points to and form an opinion; changing
anything, writing it into notes, starting work or touching a cluster waits for the
human. A short list of messages may be sent unasked (proposals, replies, review
requests), so the human is not handed a stream to dispatch.

**A message is a pointer and a one-line conclusion, under 800 characters.**
A message is re-read on every later turn of the receiver: a median message survived
about 120 turns. Content goes in a file.

**The coordinator directs the work the human approved; the human keeps what is
decided.**
A coordinator runs from a brief it cannot change and sees the whole fleet, so working
sessions follow its requests within an approved task. They refuse what is
irreversible or outward-facing, contradicts the human's words, or changes objective,
reach or cost. Without this the human answered every question twice.

**Reversible work inside an approved task needs no yes from anyone.**
Editing, testing, committing on the topic branch. A doubt whether something is inside
the task goes to the coordinator, not to the human.

**Questions for the human have one place: the coordinator's queue.**
A session asks in its own window only what authorizes something it will do itself,
and never another session's authorizations: a yes in one window never authorizes
another. Work that crosses tasks goes through the coordinator, so it sees what crosses.

**One coordinator per provider, sharing the machine through `ESTADO.md`.**
A coordinator reaches only its own Linux user's sessions, so neither sits above the
other. What runs is observed live; only intentions are written, one file each, read
through `pares`. The coordinators do not negotiate; a clash goes to the human.

**Within one Linux user, sessions talk with the provider's own messages; nobody types
into another's pane.**
A session cannot tell `tmux send-keys` from the human, and the kernel cannot stop it
within one user. Prompts come only from the human or a script the human runs
(`flota arrancar`, `flota reiniciar`).

**A session waits for its mail only when told "quedate atento".**
The explicit word is the control, not a list of sessions. The wait lasts until the
matter is settled or a long quiet period passes. Where a provider cannot wait past its
turn, a despertador started by the human's script queues a fixed note with validated
ids only, never message content, and trusts nothing a sandbox can write.

**Watching cluster work is derived from the clusters, by one tool: `vigilar`.**
Every session's own polling loop retried forever at its own pace. `vigilar` registers
itself, asks one fixed query every 5 minutes at least, gives up after 3 failures in a
row and clears its registration; `fleetwatch` compares the registrations with what the
clusters report. Whose work it is comes from the folder `<box>/<session>/`, not a
hand-kept table. Job ids always carry their cluster.

**Agents propose changes to their own rules; the human decides.**
No agent should steer itself with rules the human has not seen. A proposal (what,
change, why, for whom) goes in a file or a short message to the architect, and on the
human's word becomes a branch. Pending means unmarked in the mailbox, never a list.

## 5. The fleet style

**A manual, token-frugal fleet.**
No autonomous parallel work: the human decides objectives, priority and every launch,
and no job is submitted unless the human is working on that task. An idle session
costs nothing.

**No fixed number of sessions; the coordinator schedules by resources.**
The risk is many sessions at full speed with nobody choosing which goes first. The
coordinator proposes launches from the human's priorities and what is free (tokens,
load, memory, the other coordinator's intentions), and the human's own work comes
first.

**Derive, don't record.**
Anything observable (who runs, which job has a watcher, what is pending) is derived
from `/proc`, the scheduler, git or the mailbox. Hand-kept tables, maps and "next
steps" rotted unnoticed.

**Several clusters from the start, and one skill per site.**
Designs never assume one cluster. What a session learns about a site goes in
`skills/<site>/SKILL.md` (CCAD's clusters share one skill, a section each), visible and
loaded when relevant; a cluster's block in `fleet.toml` names its skill.

**The architect has a counterpart on the other provider, the aparejador.**
The architect writes the other provider's rules but cannot run it. The aparejador
reviews, from inside that provider, branches that touch its side, from a patch file
(never running git in the architect's repo). It changes nothing and approves nothing:
the human decides.

**A sandboxed provider writes `.git` and systemd scopes only by leaving the sandbox,
one approved command at a time.**
A `.git/config` or hook written from inside would later run outside the sandbox.
Writable roots are opened only for the provider's own state and the outbox.

**A separate, closed AI user can think with the human.**
The pensadero (with its maestro role) is outside `agents`: it reads no peer and no
peer reads it. Its conventions add confidentiality and no execution; it may publish
a private artifact only on the human's explicit request for that case, after a fixed
warning, with nothing of unpublished research.

## 6. Where things live

**Three layers: product, configuration, usage data.**
`flota` (tools, rules, roles) is the same for every member; `flota-<member>` holds
that member's `fleet.toml`; usage data (messages, state, logs, projects) lives in
neither. Mixing them makes every fleet change look like code, and fills a template
with things that happened once.

**A role is a brief, loaded as a visible `CLAUDE.md` link to the installed copy, not
a skill.**
A skill opens only when a task matches, so a role in one goes missing after a
`/clear`. The agent can read its brief but not edit it; a replaced link is detected.

**No hidden instructions.**
Conventions sit at the top of each AI user's home, visible: `ls` shows everything an
agent gets. The codex copy is `~/AGENTS.md`, with the hidden file only a link to it.
Re-check after every upgrade: rules can stop arriving without any error.

**Repo notes go in `AGENTS.md`, and `CLAUDE.md` only imports it. Repos are never
nested.**
Both providers read one file. A repo inside another silently inherits the outer
instructions; related repos share a plain folder instead.

**A project is a folder in `~/work`, in one fleet at a time.**
One repo, or a plain folder of repos and files kept out of git. Its copy is the same
path under the human's `~/agents`. Repos travel by git (`entregar`, `traer`), the rest
by `pasar`, the whole by `mover`; two fleets never work on one repo.

**Paired files change together, and shared rules carry a marker.**
Conventions and coordinator briefs exist per provider and cannot share text. A rule
for every fleet carries the same marker in each file, and a test fails when one lacks
it, so the fleets do not drift apart.

**The human's commands are written down, in `COMANDOS.md`, and agents quote them.**
When an agent needs a fleet step from the human, it gives the exact `flota` command,
never a `cp`, `scp` or push, which skip the checks `flota` makes.

## 7. One product, many members

**One shared product repository, and one configuration repository per member.**
`flota` holds everything generic; `flota-<member>` holds one `fleet.toml` (the human,
the AI users and their roles, resources, clusters). Splitting by what is shared and
what is personal keeps a member's machine out of the product.

**Personal values are templates filled at install time.**
Rules and roles say `{{human.name}}`, `{{ai_user.name}}` and the like; the planner
fills them from `fleet.toml` and refuses an unknown placeholder or a value outside a
safe character set, so no value carries shell or markup into a plan.

**The planner reads the AI users from `fleet.toml`.**
A member without a second provider or a pensadero declares fewer users and gets no
steps for them; nothing assumes the example's users.

**Nothing personal in the product.**
What is personal, site-specific or sensitive goes elsewhere: identity to templates,
machines and clusters to `fleet.toml`, site knowledge to skills. A thinking AI user's material is never in a repository.

**Changes come back to the group as pull requests; a member may diverge.**
A member's architect proposes a change as a branch on top of the group's `main`; the
member opens the pull request, since agents never reach GitHub. The maintainer reviews
with their own architect (and the aparejador for the other provider's side). Local
changes are fine; what helps everyone is proposed.

**A role is not tied to a provider.**
When one provider runs out of tokens the human goes on with the other: a pensadero may
run either tool, and `relevo` prints the other tool's last conversation as a record,
since neither tool sees the other's memory.

## Your fleet's decisions

*Each entry: the date in bold, the decision as a bold line, then why: the risk it
protects against, or the incident that showed it.*
