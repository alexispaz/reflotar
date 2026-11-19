"""The clusters an agent works on, and what it has running there.

Configuration: one [cluster.<name>] per cluster in fleet.toml, where <name> is also
the ssh alias in the agent's ~/.ssh/config. An agent works on a cluster only if it
has a box there (`box`). See docs/clusters.md.

State: never recorded here. Every question is answered by asking the cluster,
through the fixed report `puerta-estado` that the cluster's door (puerta) runs
outside the agent's box: from inside one box the kernel will not show where a
process of another box runs, so the box itself cannot answer.

  host|<login node>
  proc|<pid>|<ppid>|<starttime>|<seconds running>|<cwd>|<command>
  job|<array parent>|<job id>|<state>|<reason>|<workdir>
  squeue|ok|failed|absent
  final|<job>|<state>,<state>,...
  end|

Only the agent's own processes whose cwd is in its box, and jobs whose workdir is
in its box or a folder declared under `writable`, are reported. `end|` closes a
complete report: an ssh that failed halfway is never read as "nothing running".
"""
import os
import subprocess

HELD = ("JobHeldUser", "JobHeldAdmin")
TIMEOUT = 60            # seconds a cluster's report may take, unless query_timeout says
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL",
            "PREEMPTED", "BOOT_FAIL", "DEADLINE", "REVOKED")


def clusters(cfg, agent):
    """[cluster] where `agent` has a box, in the order written. Each one a dict with
    name, ssh_host (default: the name), user, box, writable, slurm (bool), held, and
    timeout: the seconds its report may take (query_timeout, default 60)."""
    out = []
    for name, c in cfg.get("cluster", {}).items():
        box = c.get("box", {}).get(agent)
        if not box:
            continue
        out.append({
            "name": name,
            "ssh_host": c.get("ssh_host", name),
            "user": c.get("user", ""),
            "box": box.rstrip("/"),
            "writable": [w.rstrip("/") for w in c.get("writable", {}).get(agent, [])],
            "slurm": bool(c.get("slurm_in_box")),
            "held": tuple(c.get("held_reasons", HELD)),
            "timeout": int(c.get("query_timeout", TIMEOUT)),
        })
    return out


def owner(path, c):
    """The session a path belongs to: the first folder under the box, by the
    convention that each session works in box/<session>/. None for the box itself,
    a writable folder, or anything else: unattributed, never guessed."""
    rel = path.rstrip("/")[len(c["box"]):] if (path + "/").startswith(c["box"] + "/") else None
    if not rel:
        return None
    return rel.strip("/").split("/")[0] or None


def parse(text):
    """The report of puerta-estado, as a dict. `complete` is False unless the closing
    line arrived."""
    r = {"complete": False, "host": "", "procs": [], "jobs": [], "squeue": "", "finals": {}}
    for line in text.splitlines():
        kind, _, rest = line.partition("|")
        f = rest.split("|")
        if kind == "end":
            r["complete"] = True
            break
        if kind == "host":
            r["host"] = rest
        elif kind == "proc" and len(f) >= 6:
            try:
                r["procs"].append({"pid": int(f[0]), "ppid": int(f[1]), "start": f[2],
                                   "seconds": int(f[3] or 0), "cwd": f[4],
                                   "command": "|".join(f[5:]).strip()})
            except ValueError:
                continue
        elif kind == "job" and len(f) >= 5:
            r["jobs"].append({"parent": f[0], "id": f[1], "state": f[2], "reason": f[3],
                              "workdir": "|".join(f[4:])})
        elif kind == "squeue":
            r["squeue"] = rest
        elif kind == "final" and len(f) >= 2:
            r["finals"][f[0]] = {s for s in f[1].split(",") if s}
    return r


def ended(reg, state):
    """Whether the cluster shows a registration's target ended: True, False (live), or
    None when it cannot tell (an incomplete report, another login node, a job sacct
    has no final state for). Only True lets a registration go while its watcher lives."""
    t = str(reg.get("target", ""))
    if not state["complete"]:
        return None
    if t.startswith("build:"):
        if reg.get("host") != state["host"]:
            return None
        pid = t.split(":", 1)[1]
        return not any(str(p["pid"]) == pid and p["start"] == reg.get("remote_start")
                       for p in state["procs"])
    if any(j["parent"] == t for j in state["jobs"]):
        return False
    st = state["finals"].get(t)
    return True if st and all(x in TERMINAL for x in st) else None


def ssh_config(home=None):
    """-F with the user's own ~/.ssh/config (or /dev/null without one): ssh then skips
    the system's files, which codex's sandbox shows with owner 65534 and ssh refuses
    ("Bad owner or permissions", 2026-10-16). The cluster blocks add-cluster writes
    are all in the user's file."""
    f = os.path.join(home or os.path.expanduser("~"), ".ssh", "config")
    return ["-F", f if os.path.isfile(f) else "/dev/null"]


def query(c, job_ids=(), run=subprocess.run, timeout=None):
    """What is running on cluster `c`, as parse() returns it. `job_ids`: jobs whose
    final state is wanted (sacct). An ssh that cannot connect, or that is cut, comes
    back with complete=False and the reason in `error`; one that took longer than the
    cluster's timeout, also with `timed_out`."""
    timeout = timeout or c.get("timeout", TIMEOUT)
    cmd = ["ssh", *ssh_config(), "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", c["ssh_host"],
           " ".join(["puerta-estado", *map(str, job_ids)])]
    try:
        p = run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return dict(parse(""), timed_out=True,
                    error=f"puerta-estado took longer than {timeout} s (query_timeout of [cluster.{c['name']}])")
    except OSError as e:
        return dict(parse(""), error=str(e))
    r = parse(p.stdout)
    if not r["complete"]:
        r["error"] = (p.stderr.strip().splitlines() or [f"ssh exit {p.returncode}"])[-1]
    return r
