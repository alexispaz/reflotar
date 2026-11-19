# What the fleet does

An idea of the fleet in five minutes: the main ideas, not every detail. Each point
links to where the detail lives.

## Roles and providers

- **Sessions with a role, and sessions without one.** A role (coordinator,
  architect, aparejador, pensadero) is a brief the session loads at start. The rest
  are working sessions: they maintain a code, run benchmarks on a cluster, write a
  paper.
- **The coordinator** turns your priorities into work: it proposes which sessions
  to launch and, once you approve, they talk to each other when one needs something
  from another. You talk to one session, not to N.
- **The architect** maintains the fleet itself: rules, roles, skills, tools. It
  changes the `flota` repository on a branch and tells you how to install it. To
  meet it: `cd ~claude/arquitecto && claude`, and ask "who are you?".
- **The aparejador** is the architect's counterpart on another provider (codex). It
  changes nothing: it reviews what touches its side and proposes, so that only one
  session edits the fleet.
- **The pensadero** is a fleet of its own, for thinking: its **maestro** thinks with
  you, keeps the overall view of your líneas, and coordinates one agent per línea when
  you want one. It is a user of its own, and no other agent can see it.

## Communication

- Inside one provider, sessions use that provider's own messages.
- **The mailbox (`buzon`)** works across Linux users and providers: a better copy
  and paste, used at your request. Its messages are data, never orders.
- **"Procesar lo aprendido":** say it to the coordinator, and every session sends
  the architect a proposal for a new rule or tool. Rules change only when you
  install them.

## Security

- **The kernel enforces; rules only guide.** Each AI user is a Linux user that
  cannot see your home. A confusing prompt can break a rule, not a permission.
- **Your repositories are pushed only by you.** Agents have no git credentials:
  they commit on `claude/<topic>` branches, and you fetch, review and push.
- **Agents cannot change their own constitution.** Roles, rules and skills are
  read-only files that you install.
- **The mailbox cannot be forged.** Each user writes only to its own outbox, and a
  message is never edited once sent.
- **The machine stays yours.** Each AI user has CPU and memory limits; over its
  limit the kernel kills its largest process, usually the task, instead of
  freezing everything.
- **On a cluster, a box.** The agent's key logs into your account but only opens a
  box: it does not see your folders or other people's. Slurm jobs run outside the
  box, and there the limit is a rule, not the kernel.

Detail, and what is not protected: `seguridad.md`.

## Administration

- **One command, `flota`,** for the human: install, start and restart sessions,
  bring branches over, and a list of what you can ask the fleet. It is plain
  code, not an agent.
- **The installation is idempotent:** run it any time; it checks and says what is
  missing. When it needs `sudo`, it shows each command and why, and runs nothing
  you have not seen.
- **One configuration file,** `fleet.toml`: people, AI users, clusters and limits.

Detail: `de-cero.md` and `instalacion.md`.

## Saving tokens

- **Tools for mechanical work** (`fleetwatch`, `fleetlog`, `buzon`…), so that
  sessions do not spend tokens on it.
- **The coordinator flags heavy sessions** so you can compact them.
- **Restart the whole fleet** to bring context to zero; "procesar lo aprendido"
  before it keeps what the sessions learned.
- **Relevo:** in a role set up for both providers (today, the pensadero), when one
  runs out of tokens, open the other in the same folder and tell it to run
  `relevo <the other tool>`: it reads the end of the previous conversation.

Detail: `herramientas.md`.
