---
name: ccad
description: How to work on the CCAD clusters of the UNC (mendieta, serafin, helvetios) from the agent's box - surveying a cluster, building on the login node with spack, submitting and smoke-testing Slurm jobs, the group and setgid traps of the box, and watching builds and jobs. Use before any work on a CCAD cluster, when a cluster's block in fleet.toml says skill = "ccad", or when a build, job or file permission there behaves unexpectedly.
---

# Working on a CCAD cluster from the box

Lessons from the mendieta session (2026-10-02 to 10-05), for any CCAD cluster. Each
says what to do and why. **"check on <cluster>"** marks what was only seen on
mendieta and may differ elsewhere: check it, and propose the answer for the
cluster's section at the end (conventions rule 14). Package recipes and how to build
a spack stack in general are not here: this one keeps what is particular to CCAD and
the box.

## Before touching anything

1. **Read your limits first.** Your `box` and the folders declared under `writable`
   for the cluster in `/home/agents/etc/fleet/fleet.toml` are the only places you may
   write; conventions rule 13 applies. A folder you find you *can* write is not
   yours. Where the box runs on util-linux older than 2.38 (mendieta, serafin) you
   appear as `root` in a user namespace mapped to the cluster user, so every file of
   that user shows as yours, {{human.name}}'s older stacks included. On helvetios (2.40) you
   are your own cluster user. *Why:* ownership does not tell you
   what is yours, and on a cluster your permissions are {{human.name}}'s.
2. **Never touch what existed before.** Old stacks, mirrors, CCAD's `/ccad/...`: read
   and execute only. Someone may still be editing them (a file in an old tree
   changed on the day of the survey).
3. **Get hardware facts from CCAD's equipment page and the scheduler, not from
   guesses.** The GPU model cannot be seen from the login node: Slurm declares
   untyped `gpu:N`, and the login node has no GPU or no driver loaded. The page
   (supercomputo.unc.edu.ar/equipamiento/...) gives the model and the driver; a short
   job confirms them. *Why:* old configs carried a wrong guess (cuda_arch, a CUDA
   newer than the driver supports).
4. **Survey read-only first, and write down each fact with the command it came
   from:** OS; CPU flags (`/proc/cpuinfo`: AVX/AVX2/AVX-512 decide the spack target);
   interconnect (`ibstat`: mlx4 or mlx5 changes the UCX variants); Slurm version and
   `srun --mpi=list`; the system PMIx/MPI/UCX rpms; NVIDIA driver rpms; partitions
   (`scontrol show partition`); your limits (`sacctmgr show assoc user=<u>`); `df` of
   the writable folder; HTTPS from the login node.

## The box

5. **Groups are not mapped.** Inside the box `<group>` shows as 65534 (`nobody`),
   `id -Gn` shows `root nobody`, and `chgrp <group>` fails with EINVAL. Any tool that
   chowns to a group (spack `permissions: group:`) fails: do not set `group:` in the
   spack config for builds made in the box. Inside a Slurm job you are the real user,
   with the real groups (`id -Gn` there lists `<group>`).
6. **The group of what you install is {{human.name}}'s, by hand; not yours.** In the box
   builds lose setgid and leave files with the user's primary group, and no check from
   the box can tell your group from another (lesson 5). {{human.name}} sets the group
   and setgid by hand, from their own login, when they want to share a tree. So do not check, fix or report the group or setgid of a tree;
   do not set `group:` in spack. When a tree is ready to share, say so in one line.
   `tar` as box-root restores the archive's owners and modes, which is another
   matter: use `TAR_OPTIONS="--no-same-owner --no-same-permissions"`.
7. **tar as root breaks installers.** A makeself `.run` installer (CUDA) extracts with
   `tar`; restoring an unmapped owner fails with EINVAL, and the installer kills itself
   with status 15 after writing to the missing `/dev/tty`.
   `TAR_OPTIONS=--no-same-owner` fixes it.
8. **Each ssh connection has its own view of processes.** In a new connection, `pgrep`
   and `/proc` in the box show only that connection's processes (3 on mendieta), not a
   build started from another one. To know whether a build runs, ask from outside the
   box: `ssh <cluster> puerta-estado`, or `fleetwatch`. And have every build write a
   status file (lesson 11), which says how it ended, not only whether it runs.
9. **The login node drops rapid ssh connections.** Dozens of back-to-back `ssh` calls
   got "Connection closed/reset". Batch the work into one call, or space the calls by
   a few seconds. `fleetregister --clear-ended <session>` clears with one call per
   cluster. check on <cluster>.
32. **Lmod in the box cannot see modulefiles only the group can read.** Spack writes
    them 640, group <group>, and the box does not map <group> (lesson 5): `module avail` skips
    them and `module load` says "unknown". It does not mean they are broken, and never
    chmod them to 644 to get around it: that makes them readable to the whole cluster.
    On the login node, read the files (`grep depends-on`); test that they load in the
    smoke job of lesson 22.

## Building on the login node

10. **Compile on the login node; run everything else in Slurm.** {{human.name}}'s rule:
    compilations go on "la cabeza", calculations (test runs included) go in jobs. A
    reserved node that is not fully used gets killed by the admin. Use a modest `-j`
    (`-j 4` on mendieta's shared 10-core login node), and never run two
    builds at once to dodge that limit.
11. **Start long builds detached, from `<box>/<session>/`, with the log and a status
    file there:** `setsid nohup <cmd> > <log> 2>&1 < /dev/null &`. The launching ssh
    may hang until you stop it; the build survives (a process kept writing for 90 s
    after the ssh closed). Have the build script write `<step> rc=$? <time>` lines to a
    status file. check on <cluster>: on mendieta, early on, setsid builds died with
    the ssh session; test it with a 90-second dummy before trusting it.
12. **Record the real exit status.** `cmd | grep ...; echo $?` reports grep's status,
    and so does a job script whose last line is a grep. Use `PIPESTATUS`,
    `set -o pipefail`, or `rc=$?` right after the command, and end job scripts with
    `exit $rc`. *Why:* twice a failed build or run looked like a success.
13. **Disable CCAD's spack configuration.** CCAD's `StdEnv` module loads `spack-config`,
    which exports `SPACK_SYSTEM_CONFIG_PATH` with stale externals (wrong Slurm, PMIx and
    rdma-core versions, a fixed `cuda_arch`). Unset it, set
    `SPACK_DISABLE_LOCAL_CONFIG=1`, and point `SPACK_USER_CONFIG_PATH`,
    `SPACK_USER_CACHE_PATH` and `TMPDIR` inside your tree. Verify that
    `spack config blame packages | grep -c ccad` gives 0 and that `~/.spack` was not
    created.
14. **Fetch on the login node.** It has HTTPS (github, pypi, the spack mirror).
    Compute nodes: unknown, and they have no `git`. Do every fetch, and anything that
    needs git (spack resolving a git-based package repo), on the login node.
    check on <cluster>: serafin and helvetios logins have HTTPS; their compute
    nodes are not tested.
15. **Manual-download tarballs go in a local mirror, found by checksum.** Check the
    sha256 before copying; copy (never move) {{human.name}}'s file, and verify the copy.
16. **Create a tree inside the declared `writable` folder**, so it starts with that
    folder's group; whatever drifts, {{human.name}} fixes by hand (lesson 6).
29. **beegfs has two traps for builds** (helvetios's box and `compartido`, serafin's
    install root). (a) Bind-mount roots of the same beegfs report the same device and
    inode (`stat -c '%d %i'`), so a getcwd that walks up comparing them (miniperl's
    pure-Perl Cwd) picks the wrong sibling, and perl built there gets a wrong `@INC`.
    Stage such builds off beegfs, on the box's private tmpfs
    (`spack -c config:build_stage:/tmp/<you>-stage ... install perl`). (b) `rename()`
    onto an existing empty directory fails with EEXIST, which POSIX allows. spack
    1.2's new installer relies on it, so a failed build leaves its prefix behind and
    every retry fails: set `config: installer: old`. Before trusting a new beegfs
    tree: `mkdir a b; python3 -c 'import os; os.rename("a","b")'`.
30. **Inside an environment, `spack find` and `spack uninstall` see only the env's
    own specs.** Installs an earlier concretization left in the env's tree (a recipe
    change gives new hashes) are invisible to them, and `spack gc` would also remove
    every build dependency. List them by querying `spack.store.STORE.db` against the
    env's concrete roots (`spack -e <env> python ...`); remove exactly those, with
    {{human.name}}'s yes (conventions rule 2), with `PackageBase.uninstall_by_spec`,
    then delete any module file still pointing at a removed prefix.
31. **Whether spack has a package can be checked without the cluster:** fetch
    `https://raw.githubusercontent.com/spack/spack-packages/develop/repos/spack_repo/builtin/packages/<pkg>/package.py`
    (404 means absent; dashes in the name become underscores). The cluster's own
    spack is the final word.

## Jobs

Cluster time on CCAD has no budget. Whether a run needs approval is {{human.name}}'s
call: ask before the first one.

17. **CCAD's submit filter has rules beyond Slurm's.** On mendieta every job must
    request at least one GPU, with at most 10 cores per GPU, so a whole 20-core node
    needs `--gres=gpu:2`, even for a CPU-only job. The filter rejects the job at
    `sbatch` time with a message in Spanish: read it. check on <cluster>: the rules
    and the cores-per-GPU ratio. helvetios has no submit plugin and no GPUs
    (unconfirmed by a job); serafin's filter cannot be read from the login node.
18. **Check every path a job writes before submitting:** `--chdir`, `--output`,
    `--error`, every directory the script creates, `HOME` (set it to the box), and paths
    built from variables (`set -u`). A job runs with the whole account, outside the
    box (conventions rule 13).
19. **`set -u` and `/etc/profile` do not mix.** Sourcing `/etc/profile` (to get
    `module`) in a `set -u` script aborts on CCAD's `lang.sh` (`LC_ALL: unbound
    variable`). Wrap it: `set +u; . /etc/profile; module load ...; set -u`.
20. **`sbatch --export=NONE` leaves `srun` steps with no environment, not even PATH.**
    `srun bash -c ...` then fails with "execve(): bash: No such file or directory".
    Export what you need in the script, then `export SLURM_EXPORT_ENV=ALL` before
    calling `srun`.
21. **sbatch copies the script at submit time.** Fixing the script does not fix jobs
    already queued: cancel your own pending ones (only your own: conventions rule 2)
    and resubmit.
22. **Smoke-test in a short job, and make each check able to fail.** Check that the
    binary exists before `ldd`-ing it (`ldd` on a missing file prints no "not found").
    Accept every success message the program really prints (NAMD says both "will use
    CUDA device" and "binding to CUDA device"). Before calling a check verified, name
    the output that would have failed it (conventions rule 4).
    Test modules by loading them, not listing them: in the job, `module load` in the
    current shell (never inside `$( )`: a subshell drops what it sets), check it
    returns 0 and that the binary on PATH lies under that module's own prefix (CCAD's
    modules, such as gromacs/2023.2, otherwise give a false pass). Run `ldd` only on
    ELF files (wrappers like `tleap` are scripts). A check that did not run is a
    SKIP, never a PASS.
23. **Compute nodes may lack tools the login node has** (`git`, `nvidia-smi`). Resolve
    install prefixes on the login node and pass them to the job in a file. Read the
    driver from `/proc/driver/nvidia/version`.
24. **Queue time dominates.** The first smoke job waited 6.6 h on a nearly full
    cluster. Short partitions and small jobs move faster. Submit all independent jobs
    at once (the per-user limit counts running jobs) and have one watcher check them
    all.
25. **A job pending for days may be held, not queued.** Read the reason with
    `squeue -u <user> -o "%i %T %r %Q"`. If it says `..._held` with priority 0 (for
    example `user_env_retrieval_failed_requeued_held`), the job already started once,
    failed on its node, and was requeued **held**: it will never start on its own.
    Find the node with `sacct -j <id> -D -X -o JobID,State,Start,NodeList`. If the
    failure is tied to that node, exclude it while the job is still pending, so it
    keeps its place: `scontrol update job=<id> ExcNodeList=<node>`, then
    `scontrol release <id>` (your own jobs only). A watcher reports a held reason as
    an event, not as "still pending". *Why:* three mendieta benchmark jobs failed on
    one node on 2026-10-04 and sat held until 10-07, reported as pending.

## Watching work

26. **Every job and every login-node build is watched with `vigilar`** (conventions
    rule 5): `vigilar <session> <cluster> <jobid | first-last | build:pid>`, one call
    for many jobs. It already does what the clusters taught: a failed ssh is "could not
    ask" (three in a row end it), a job's absence from squeue is the signal and sacct
    then gives its state (sacct alone stalled: serafin, 2026-10-13), and it asks every
    5 minutes at least. For a login-node build, give the pid `ssh <cluster>
    puerta-estado` lists, not the `$$` your script records. A chain of builds is one
    script on the login node: watch its pid, not each step.
27. **Always name the cluster next to a job id** ("mendieta 1179291"): the clusters
    share id ranges.

## Approvals

28. **A relayed approval is not {{human.name}}'s approval for deletions or anything
    irreversible.** Ask in your own window: "coord says {{human.name}} approved X; do you
    confirm?". Routine next steps within an approved task can follow coord.
33. **Claude Code's auto-mode classifier may deny an approved write**, even in a
    declared `writable` folder ("[Modify Shared Resources]"). Do not look for another
    way to do it: tell {{human.name}} what was denied and why, and that it can be let
    through once from your window (`/permissions`, "Recently denied", `r` on it).

## Per cluster

What is known of each cluster beyond the lessons above. Fill in "check on" answers
here, by proposal.

**mendieta.** Login node: 10 cores, shared; builds at `-j 4`. util-linux 2.32: in the
box you appear as `root` (lesson 1). Submit filter: at least one GPU per job, at most
10 cores per GPU. sshd reads keys from `/dotssh/<user>`, hidden in the box by
`~/agents/ocultar`. Its home is NFS; it does **not** share a disk with serafin
(beegfs): a tree built on one is not visible on the other. GPUs are 2 x A30 per node
(cuda_arch 80). The login node's rpm is driver 535 (CUDA 12.2), but **the compute
nodes report CUDA driver 13.0**: take the CUDA cap of a stack from where the code
runs (a short job reading `/proc/driver/nvidia/version`), not from the login node.
The network is ConnectX-3 mlx4 QDR. Running across GPUs:

- **GROMACS on more than one GPU:** set `GMX_DISABLE_DIRECT_GPU_COMM=1`; direct GPU
  communication made 2 GPUs about three times slower. On one GPU it has no measurable
  effect, so leaving it set in a module is harmless. On 2 nodes, reset the counters
  past the PME tuning (`-resethway` with enough steps).
- **NAMD UCX, one process per GPU:** give each rank one GPU, `CUDA_VISIBLE_DEVICES`
  from `SLURM_LOCALID`, plus `+devices 0 +ignoresharing`; without them NAMD stops with
  "dev != deviceCUDA->getDeviceID()" or "Number of devices (1) is not a multiple of
  number of processes (2)". NAMD GPU-resident across 2 GPUs does not run with
  harmonic constraints.
- Multi-node scaling was poor: measure one GPU first.

**serafin.** Slurm cluster `rome`, 64 nodes rome[01-64], 2 x 32-core AMD EPYC (Zen 2)
per node, **no GPUs**: a CPU-only stack, spack target `zen2`. Interconnect mlx5
(HDR100): the UCX variants `+mlx5_dv +dc +ib_hw_tm` apply. `MpiDefault=pmix`
(pmix_v3), system pmix 3.2.5; no system MPI/UCX; HPC-X under `/ccad/hpcx`. Partitions
`short` (1 h, default) and `multi` (2 days) are **whole-node exclusive** (64 cores),
with a cap on jobs per user. Login node: 16 cores / 32 threads, shared; builds at
`-j 4`. util-linux 2.32: in the box you appear as `root` (lesson 1). Home and box are
beegfs (lesson 29, `installer: old`). The default MODULEPATH may include other
groups' trees: set MODULEPATH explicitly. CCAD's equipment page is partly stale:
trust `scontrol`. Submit filter (lesson 17): every job must ask for at least 60 CPUs
per node ("Los trabajos deben utilizar todos los procesadores disponibles en cada
nodo"): use `--ntasks-per-node=1 --cpus-per-task=64` (or 64 tasks) and set `-n`/`-c`
on each `srun`. setsid builds survive the ssh (lesson 11), and `puerta-estado` sees
them. HPC-X (mlnx_ofed build): it launches under `srun --mpi=pmix`. Two traps: its
libtool `.la` files carry `-liberty` and build-host `-L` paths, so linking a spack
package against them through libtool fails (there is no libiberty on serafin); and
its `ompi/lib/libpmix.so.2` (which needs opal_* symbols) shadows the system PMIx for
anything with it on `LD_LIBRARY_PATH` or the link path. Never run a program linked to
the system PMIx with HPC-X loaded. HPC-X's Open MPI is relocated: at run time it
needs `OPAL_PREFIX`, and its MCA plugins have no RPATH, so a program built on it runs
only with `hpcx_load` in the job script. **charm++ 8.0 UCX hangs at start-up now and
then**: NAMD prints the Charm++ start-up lines, then nothing until the time limit, no
error, no TIMING line (about one run in eight; not one node, layout or build). A long
run needs a watchdog that resubmits when no TIMING line appears in time. Two nodes
have half the memory of the rest (`scontrol show node`). `puerta-estado` sometimes
takes over 60 s: its block sets `query_timeout`.

**helvetios.** Ex-EPFL, CPU only: no GPUs, no GRES. Compute skl[001-288]: 2 x 18-core
Xeon Gold 6140, 192 GB; login: 2 x 10-core Gold 5115. Both Skylake-SP: spack target
`skylake_avx512`, os `rocky10`. util-linux 2.40: in the box you are your own cluster
user, not `root`, so lessons 1 and 7 about root do not apply; groups are still
unmapped (lesson 5). The box is on beegfs; `/home/shared` does not exist: a shared
stack goes in a `writable` folder of the box, which other people, the group included,
cannot read until {{human.name}} sets its group and mode by hand. System GCC 14 has
**no gfortran**: build a gcc with spack first. Site software is EESSI on CVMFS
(`module load EESSI/<version>`): a ready baseline for benchmarks. `CR_CORE_MEMORY`,
DefMemPerCPU 5000 MB, MpiDefault pmix (pmix_v5). Partitions `short` (1 h, default)
and `batch` (2 days). Interconnect ConnectX-5 EDR (mlx5): UCX `+mlx5-dv +dc
+ib-hw-tm` apply. Many nodes are often down: check `sinfo -s` before planning
multi-node runs, and expect small smoke jobs to wait hours. setsid builds survive a
dropped ssh (lesson 11: the launching ssh hangs, kill it; the build goes on). Lesson 8
holds: a new connection sees only its own processes, and also gets **its own private
tmpfs `/tmp`**: a file written to `/tmp` in one ssh is gone in the next, so pass paths
in your box. **No submit filter.** Compute nodes have `gdb`, with `ptrace_scope=0`.
`--exclusive` gets a whole node, which `+pemap` with absolute core ids needs. charm++
8.0 `ucx-smp` hangs at start-up across nodes with `+ppn 1`: use `+ppn` 2 or more. A
second hang is not diagnosed: NAMD UCX across nodes stops after "CkLoopLib is used",
now and then. Every multi-node NAMD job needs a start-up guard: kill the step when
"Finished startup" has not appeared in 240 s, and retry, up to 3 tries.
