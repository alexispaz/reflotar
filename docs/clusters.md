# AI users on a cluster: one box per AI user

On a cluster there is no `claude` or `codex` user: an AI user's key logs into **the
human's account**. So the account is protected on the cluster itself. The agent's
key can only open `puerta`, which runs every command in a box where, of the
human's files, only the agent's own folder exists. Inside it the agent may do
anything. Outside it, the human's home, `~/.ssh`, `/tmp` and the user's systemd do
not exist for it, and Slurm does not either unless you enable it (below).

What is enforced, and how, is in the comment at the top of `puerta`. What it does
**not** cover, by design for now:

- **Jobs, when you enable Slurm.** A job runs on a compute node outside the box,
  with the whole account (and so do `srun`'s tasks). See "Slurm" below.
- **One box per Linux user, not per session.** All of claude's sessions share
  claude's key and box. Which session works in which subfolder is the
  coordinator's rule, not the kernel's.
- **Reading is not restricted outside the human's home.** System software, modules,
  shared software stacks and anything else the human's user can read stay visible,
  READ-ONLY, as builds need them. The box is the only place the agent can write.

## One key per AI user

Each working AI user (`claude`, `codex` in the example) has **one** key, the same for every cluster.
You make it once, inside the agent's session (`tclaude` or `tcodex`), and you type
its passphrase, so the key works only while you have unlocked it. **Without a
passphrase any session of that agent reaches every cluster at any time**;
`add-cluster` refuses such a key. Full paths, so
no program the agent could put on its PATH sees the passphrase:

    /usr/bin/ssh-keygen -t ed25519 -C "$(whoami)@$(hostname)"    # ~/.ssh/id_ed25519
    cat ~/.ssh/id_ed25519.pub

`add-cluster` writes the agent's `~/.ssh/config` for you (below).

## Adding a cluster

From your clone, as yourself, once the agent has its key:

    cd ~/agents/flota/clusters
    ./add-cluster <cluster> <agent>          # checks the cluster, shows the plan
    ./add-cluster <cluster> <agent> --go     # does it

`<cluster>` is the name you ssh to (`ssh <cluster>` must work for you), `<agent>`
is a working AI user of `fleet.toml` (`claude` or `codex` in the example). **`fleet.toml` is the one place where you declare what the
agent may do there**: its `box`, the folders under `writable`, and `slurm_in_box`.
`add-cluster` makes the cluster match it, so the usual cycle is: edit
`flota-<you>/fleet.toml`, commit, `sistema/instalar --go`, `add-cluster --go`. The first time, before the
cluster is declared, it sets up the box alone and prints the block to declare. `--from <address>` makes the cluster accept the agent's key
only from this machine's address, if it is fixed. It asks for your sudo password,
to read the agent's public key and write its ssh config as the agent.

What it does, in order (run it again at any time; what is in place stays):

1. **On the cluster:** checks that user namespaces work; without them there is no
   box, and it stops. Copies `puerta` to `~/agents/puerta`, makes the box
   `~/agents/<agent>`, and writes one line in `~/.ssh/authorized_keys`:

       restrict,pty,command="<home>/agents/puerta <agent>" ssh-ed25519 AAAA... <agent>

   with a timestamped backup first. An older line for the same key is replaced.
2. **On the cluster:** runs `~/agents/puerta <agent> --check`, which lists every
   directory of yours still writable from inside the box but outside it. Each one
   is a hole: hide it (below) and run the check again until it says `ok`. Sticky
   shared folders (like `/var/tmp`) are listed apart; others' files there are
   protected anyway.
3. **Here:** a `Host <cluster>` block in the agent's `~/.ssh/config`, with the
   address, user and port of YOUR `ssh -G <cluster>`, and once a `Host *` block with
   the key and the agent socket. Only its own marked blocks are ever rewritten. And
   the cluster's host key, copied from YOUR `known_hosts` to the agent's, so the
   agent knows the server by the key you verified and never accepts one blind.
4. **For you:** it prints the `[cluster.<cluster>]` block for
   `flota-<you>/fleet.toml`. Commit it in your clone and run `sistema/instalar --go`.
   The coordinators read it there; nobody needs restarting.

## codex on the clusters

codex gets the same: its own key and box, and the fleet tools (`fleetregister`,
`fleetwatch`), which belong to the `agents` group. In `tcodex`, make its key with a
passphrase (`/usr/bin/ssh-keygen -t ed25519`), then from your clone:

    ./add-cluster <cluster> codex --go

and declare its box (and any `writable` folder) in that cluster's block of
`fleet.toml`, next to claude's: `box = { claude = "...", codex = "..." }`. Its box is
`~/agents/codex` on the cluster, apart from claude's. `fleetlog` still reads only
claude's transcripts.

codex runs its commands in a sandbox with no network by default; the planner turns
`network_access` on for the working codex AI users, so their ssh reaches the
clusters. Inside that sandbox ssh also refuses the system's configuration files (they
show owner 65534 there), so the agents' `ssh` is the fleet's, in `/home/agents/bin`:
it reads only `~/.ssh/config` (`-F`). `flota` names a working AI user that has a box on no cluster.

## A shared folder the agent may write (a group's software stack)

To let the agent install, say, the software stack your group uses, declare one
folder there, inside the group's shared space, in the cluster's block of
`flota-<you>/fleet.toml`:

    writable     = { claude = ["/home/shared/<group>/agents"] }

commit, run `sistema/instalar --go`, and then `./add-cluster <cluster> <agent> --go`. It creates
the folder (as you, so with your group's permissions) and lists it in
`~/agents/escribir-<agent>` on the cluster, exactly as declared: a folder you take
out of `writable` is taken out there too. Inside the box that folder is writable
and the rest of the shared space stays read-only. puerta refuses to open if a
listed folder is missing or lies under something it hides.

**What the box cannot do here:** what the agent installs there, your colleagues
run. The box keeps your files from the agent; it cannot keep a badly built or
altered stack from your group. Decide when they start using what it built.

## Hiding more paths: `~/agents/ocultar`

puerta always hides your home, `~/.ssh`, `/tmp`, `/var/tmp`, `/dev/shm`,
`/run/user/<uid>` and `/run/munge`. Anything else goes in `~/agents/ocultar` on the
cluster, one path per line (`#` starts a comment). Each one becomes an empty,
read-only folder inside every box of that cluster. From your account:

    ssh <cluster> 'grep -qxF <path> ~/agents/ocultar 2>/dev/null || echo <path> >> ~/agents/ocultar; cat ~/agents/ocultar'

It takes effect at the agent's next connection. Check it from the agent's session:

    ssh <cluster> 'ls -A <path>; echo end'      # only "end": the folder is empty

What to hide:
- **What `--check` lists** as writable outside the box.
- **Where sshd keeps your keys, when it is not `~/.ssh`.** The check cannot see it:
  outside the box everything is read-only already, so it is not writable, only
  readable. On the CCAD clusters sshd reads `/dotssh/<user>/authorized_keys`, so
  `/dotssh/<user>` goes in `ocultar`. `ls -d /dotssh/$USER` tells whether a cluster
  does the same.

On clusters that share your home (mendieta and serafin, it seems), `~/agents` is
one folder for all of them, and so is `ocultar`.

## A folder in your home that agents share

When there is no group folder outside your home (helvetios, for now), the shared
place is `~/agents/compartido` on the cluster, or folders in it: the one part of your home
`puerta` will show. Declare it in the cluster's block, `writable` for the agent that
builds there and `readable` for the ones that only use it:

    writable     = { claude = ["/home/<you>/agents/compartido"] }
    readable     = { codex = ["/home/<you>/agents/compartido"] }

Folders inside it (`compartido/stack`, `compartido/datos`) let each thing shared have
its own grants; the whole of it is simpler while there is one.

then `sistema/instalar --go` and `add-cluster` for each agent. Inside the box the folder appears at
its own path, writable or read-only; the rest of `~/agents` (puerta, the lists, the
other boxes) stays hidden. `puerta` refuses a listed folder in your home anywhere
else, `~/agents` itself, or a link that leads out of `compartido`.

## Slurm

Off by default: munge is hidden in the box, and `sbatch` fails. To let the agents
submit jobs on a cluster, or stop them, set `slurm_in_box` in its block of
`flota-<you>/fleet.toml`, commit, run `sistema/instalar --go`, and run `./add-cluster <cluster> <agent>
--go`, which creates or removes `~/agents/slurm-<agent>` there to match. The agent
then uses `sbatch`, `srun` and MPI as you would.

**With Slurm on, the box is no longer a limit.** A job runs outside it, with your
whole account, on nodes that mount your home and the shared folders: a mistaken
`rm -rf "$DIR/"` in a job script reaches them. The box still guards against
mistakes in what the agent runs on the login node, which is most of it. What
stays safe is what you protect yourself:

    chmod -R a-w <folder>     # nobody, you included, can delete or change it
    chmod -R u+w <folder>     # when you want to work in it again

Deleting a file needs write permission on its folder, so `rm -rf`, `find -delete`,
overwriting and renaming inside it all fail, from any node and through `srun`. It
guards against mistakes, not against intent: your own processes, the agent's jobs
among them, could `chmod` it back. Beyond that, backups: ask whether the cluster
keeps snapshots of your home.

A wrapper around `sbatch` was considered and dropped: whatever it checked at
submission, the job, running with the whole account, could undo or bypass,
`sbatch` included.

## Watching what runs there: puerta-estado and fleetwatch

From inside one box the kernel will not show where a process of another box runs,
so the box cannot say what the agent has running. `puerta` therefore answers one
fixed command outside the box, `ssh <cluster> puerta-estado [job ids]`: the
agent's processes whose working folder is in its box, and its jobs whose workdir
is in its box or a `writable` folder. It takes nothing else from the agent and
tells nothing about the rest of your account.

`fleetwatch` (in the fleet repo) asks every cluster that way and compares with the
watchers the sessions registered (`fleetregister`). Conventions rule 5 says how a
session works with them:

- each session works in `<box>/<session>/`, which is how the work is attributed;
- a build on the login node is started detached, so it outlives the connection:

      ssh <cluster> 'cd <box>/<session>/stack; setsid nohup spack install foo > build.log 2>&1 < /dev/null & echo $!'

- and is watched by a loop in the session that asks `puerta-estado`, for instance

      while ssh <cluster> puerta-estado | grep -q "^proc|<pid>|"; do sleep 300; done

  registered with `fleetregister <session> <cluster> build:<pid> <pid of the loop>`.
  Not `/proc` from inside the box: on mendieta it shows only that box's own
  processes, so a build started from another connection looks gone while it runs.
  `puerta-estado` looks from outside the boxes and sees them all.

## Opening access for a working session

Access exists only while you have unlocked the key. `flota arrancar` does it for
every working AI user (claude, codex), in your terminal. By hand, in the agent's session:

    /usr/bin/ssh-agent -a ~/.ssh/agente.sock      # once per boot; ignore "address in use"
    /usr/bin/ssh-add

`SSH_AUTH_SOCK` points to that socket in the agents' shells (the planner sets it):
`ssh-add` finds the agent only through it, while `ssh` finds it through
`IdentityAgent` in `~/.ssh/config`.

That opens **every** cluster the key is authorized on, until you run `ssh-add -D`
or the machine (or the agent's ssh-agent) restarts. Only you run `ssh-add`: an
agent that saw the passphrase could use the key at any time. Then check from an agent session that the box is what it says:

    ssh <cluster> 'pwd; ls ~; ls <home>'      # the box; its contents; nothing

**"Permission denied" from an agent's ssh** looks the same whether the key is locked
or ssh is using another configuration. Ask ssh, as the agent, what it uses:

    ssh -G <cluster> | grep -E '^(hostname|user|identityagent|identityfile) '

`identityagent` must be `~/.ssh/agente.sock` and the first `identityfile`
`~/.ssh/id_ed25519`. ssh keeps the first value it finds, so a `Host` block written by
hand earlier in `~/.ssh/config` wins: `add-cluster` now puts its blocks first and
checks `ssh -G` itself. It also drops, from the cluster's `authorized_keys`, any line
with another key of the agent: an older key would open your account without the box.

## A machine of your own: a user for the agents

On a workstation where you have root, the agents need not enter your account: make a
user for them, and the box goes in that user's home. Same tools, same box: the box
still keeps the user's `~/.ssh/authorized_keys` (an agent there could add a key with no
passphrase), its cron and its systemd out of the agents' reach, and claude apart from
codex. As root on the machine:

    useradd -m -s /bin/bash <agents-user>
    passwd -l <agents-user>                     # key only
    install -d -m 700 -o <agents-user> -g <agents-user> ~<agents-user>/.ssh
    install -m 600 -o <agents-user> -g <agents-user> /dev/null ~<agents-user>/.ssh/authorized_keys
    sudo -u <agents-user> unshare -Ur true && echo ok      # the box needs user namespaces
    systemctl set-property user-$(id -u <agents-user>).slice MemoryMax=<n>G MemorySwapMax=0 CPUWeight=50

Your key, from this machine through your own account there:
`cat ~/.ssh/id_<type>.pub | ssh <machine> 'sudo tee -a ~<agents-user>/.ssh/authorized_keys'`.
In your `~/.ssh/config`, a `Host <alias>` with `User <agents-user>`, `ForwardX11 no` and
`ForwardAgent no` (a process of that user could otherwise reach your display or your
keys while you are logged in). Then `add-cluster <alias> <agent>` as for any cluster;
it prints `scheduler = "none"`.

**The ceiling.** Memory cannot be shared gently: `MemoryMax` = total, minus ~2 GB for
the system, minus what the people who sit there use (`free -g` while they work). Swap
off for the user (`MemorySwapMax=0`), or a run past its ceiling slows the whole machine
instead of being killed. CPU is a share, not a cap: `CPUWeight=50` lets the agents take
every core when the machine is idle and gives a person at it two thirds when both
want it. Inside the box there is no `systemd-run --user`, so this ceiling is the only
one the kernel keeps; note it, and why, as a comment in the machine's block.

**A `writable` folder there** (a stack the others on the machine use too): the
agents' user cannot create anything in `/home`, so add-cluster cannot make it. Make it
as root first, owned by that user (`install -d -m 755 -o <agents-user> -g <agents-user>
/home/shared/agents`; 700 if only the agents use it), then declare it and run add-cluster.

Check also that nothing of other people there is readable by everyone (`ls -ld
/home/*`): neither the box nor the user hides it.

## A cluster behind a VPN

Some clusters answer ssh only through a VPN (openfortivpn, OpenVPN, a vendor
client). The fleet adds nothing for them; what changes is who opens the way, and
what the agents see when it is closed.

- **You bring the VPN up, never an agent.** A VPN client changes the machine's
  routes and devices, so it needs root, and it needs your credentials (often a
  second factor). Neither is the agents'. While it is up, every user of the machine
  reaches the cluster, the agents too; when it drops, nobody does. Bring it up
  before `flota arrancar` when the day's work needs that cluster.
- **Adding it is the usual `add-cluster`,** with the VPN up and `ssh <cluster>`
  working for you. The agent's `Host` block copies the address your `ssh -G` gives:
  if that is a name the VPN's DNS resolves, the agent's ssh also works only with
  the VPN up, which is what you want.
- **No `--from`.** The cluster sees the address the VPN gives you, not this
  machine's own; it may change from one connection to the next.
- **If the network blocks the VPN itself,** the fix belongs to the machine's
  network setup (a profile, a route), kept with your machine's configuration, not
  in the fleet.
- **With the VPN down, `fleetwatch` says `COULD NOT ASK THE CLUSTER`** (with `vpn`
  declared, without sending anything). That is not
  "nothing running": jobs there go on. Bring the VPN up and ask again.
- **Declare the VPN: `vpn = "ppp*"`** in the cluster's block (the interface the VPN
  client makes: `ppp*` for openfortivpn, `tun*` for OpenVPN), and run `add-cluster`
  again. The agent's `Host` block gets a `Match` that makes ssh fail on this machine,
  before a single packet, while no such interface exists. Without it, a cluster's name
  may still resolve with the VPN down, to an address the local network routes
  somewhere else: one cluster's resolved to a private address of the local network,
  a watcher kept trying it, and that network's admins blocked this machine (2026-11-18).
  The machine's own firewall may refuse that traffic too (your machine's
  configuration, not the fleet's).
- **Watch only with `vigilar`** (conventions rule 5): it gives up after 3 failed asks
  in a row, asks every 5 minutes at least, and never retries a cluster it cannot reach.

- **Say where it lives in the cluster's skill.** Which VPN, how you start it, and
  what it allows, are facts of that site: they go in its site skill, with the rest
  of what the agents need to know there.

## Tested

On this machine, 2026-10-01 (util-linux 2.42; the fallback was forced): the box is
writable, the home hidden, stdin reaches the command (rsync, sftp), and
`umount2` of the tmpfs fails both directly and from a nested namespace, while the
same test without dropping capabilities does see the home again. `--check` finds
the writable places outside the box and says `ok` once they are hidden. On a
cluster: mendieta, below.

`add-cluster` was tested here against a stand-in for ssh and sudo: plan changes
nothing; `--go` installs puerta (700), the line (600, backup), the agent's config;
a second run changes nothing; a new `--from` replaces the old line; a key file
with options, two keys or another key type is refused.

On mendieta (2026-10-01, util-linux 2.32, so the `setpriv` path) the first
`--check` found `/dotssh/<user>` (where its sshd reads `authorized_keys`) and other
users' group-writable folders writable from the box. Since then `~/.ssh` is hidden by its
real path, and every other mount is made read-only inside the box.

End to end on mendieta, 2026-10-01, from a claude session: `pwd` is the box, the
home shows only the way to the box, `/dotssh/<user>` is empty, writes to the home
and to `/home/shared/<group>` fail (read-only), `sbatch` fails (no munge), the box is
writable, and after `ssh-add -D` ssh asks for the passphrase again.
The `writable` folder was tested here only (writable; its neighbours
read-only; a missing or hidden one keeps the door shut).
