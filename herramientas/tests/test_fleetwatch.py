"""fleetwatch and fleet.clusters: what the agent runs on its clusters, and what watches it."""
import io, json, os, subprocess, sys, unittest
from contextlib import redirect_stdout
from tests.support import FakeConfig, load_tool

TOML = """
[paths]
state = "{state}"

[cluster.alfa]
user = "tester"
box = {{ claude = "/c/agents/claude", codex = "/c/agents/codex" }}
writable = {{ claude = ["/c/shared/stack"] }}
slurm_in_box = true

[cluster.beta]
ssh_host = "beta.example"
user = "tester"
query_timeout = 180
box = {{ claude = "/b/agents/claude" }}

[cluster.gamma]
box = {{ codex = "/g/agents/codex" }}
"""

def report(host="login1", procs=(), jobs=(), finals=None, squeue="ok", end=True):
    lines = [f"host|{host}"]
    lines += [f"proc|{p}" for p in procs]
    lines += [f"job|{j}" for j in jobs]
    lines.append(f"squeue|{squeue}")
    lines += [f"final|{k}|{v}" for k, v in (finals or {}).items()]
    if end:
        lines.append("end|")
    return "\n".join(lines) + "\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig(TOML)
        self.fw = load_tool("fleetwatch")
        from fleet import clusters
        self.cl = clusters
        self.watch = os.path.join(self.cfg.state, "watchers")
        os.makedirs(self.watch)
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait()
        self.cfg.close()

    def live_pid(self):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.procs.append(p)
        return p.pid, self.cl_starttime(p.pid)

    def cl_starttime(self, pid):
        from fleet.procs import starttime
        return starttime(pid)

    def reg(self, session, cluster, target, alive=True, **extra):
        if alive:
            pid, st = self.live_pid()
        else:
            pid, st = 999999999, "1"
        r = dict({"session": session, "cluster": cluster, "target": target, "pid": pid,
                  "starttime": st, "armed": "2026-10-02T10:00:00-03:00"}, **extra)
        with open(os.path.join(self.watch, f"{session}-{cluster}-{target}-{pid}.json"
                               .replace(":", "-")), "w") as f:
            json.dump(r, f)
        return r

    def survey(self, reports, only=None):
        def query(c, ids=()):
            self.asked = getattr(self, "asked", {}); self.asked[c["name"]] = list(ids)
            text = reports.get(c["name"])
            r = self.cl.parse(text or "")
            if not r["complete"]:
                r["error"] = "ssh: connect to host: timed out"
            return r
        from fleet import config as fc
        return self.fw.survey(fc.load(), "claude", only, query)

    def section(self, s, name):
        return next(x for x in s["clusters"] if x["cluster"] == name)


class Clusters(Base):
    def test_only_clusters_where_the_agent_has_a_box(self):
        from fleet import config as fc
        names = [c["name"] for c in self.cl.clusters(fc.load(), "claude")]
        self.assertEqual(names, ["alfa", "beta"])
        self.assertEqual([c["name"] for c in self.cl.clusters(fc.load(), "codex")], ["alfa", "gamma"])

    def test_ssh_host_defaults_to_the_name(self):
        from fleet import config as fc
        hosts = {c["name"]: c["ssh_host"] for c in self.cl.clusters(fc.load(), "claude")}
        self.assertEqual(hosts, {"alfa": "alfa", "beta": "beta.example"})

    def test_each_cluster_waits_its_own_timeout_and_says_so(self):
        from fleet import config as fc
        cs = {c["name"]: c for c in self.cl.clusters(fc.load(), "claude")}
        self.assertEqual((cs["alfa"]["timeout"], cs["beta"]["timeout"]), (60, 180))
        seen = []
        def run(cmd, timeout, **kw):
            seen.append(timeout)
            raise subprocess.TimeoutExpired(cmd, timeout)
        r = self.cl.query(cs["beta"], run=run)
        self.assertEqual(seen, [180])
        self.assertTrue(r["timed_out"])
        self.assertFalse(r["complete"])
        self.assertIn("180 s", r["error"])

    def test_ssh_reads_only_the_users_own_config(self):
        # codex's sandbox refuses the system's ssh files: -F skips them
        from fleet import config as fc
        c = self.cl.clusters(fc.load(), "claude")[0]
        seen = []
        def run(cmd, **kw):
            seen.append(cmd)
            raise OSError("no ssh here")
        self.cl.query(c, run=run)
        self.assertEqual(seen[0][:3], ["ssh", "-F", self.cl.ssh_config()[1]])

    def test_owner_is_the_first_folder_under_the_box_and_nothing_else(self):
        c = {"box": "/c/agents/claude"}
        self.assertEqual(self.cl.owner("/c/agents/claude/spack/build/x", c), "spack")
        self.assertIsNone(self.cl.owner("/c/agents/claude", c))
        self.assertIsNone(self.cl.owner("/c/agents/claudeX/spack", c))   # a prefix is not the box
        self.assertIsNone(self.cl.owner("/c/shared/stack/x", c))

    def test_a_report_without_its_end_is_not_complete(self):
        r = self.cl.parse(report(procs=["1|1|5|900|/c/agents/claude/s|make"], end=False))
        self.assertFalse(r["complete"])
        self.assertTrue(self.cl.parse(report())["complete"])

    def test_a_command_with_a_bar_keeps_it(self):
        r = self.cl.parse(report(procs=["7|1|5|900|/c/agents/claude/s|sh -c a|b"]))
        self.assertEqual(r["procs"][0]["command"], "sh -c a|b")


class Work(Base):
    def test_builds_are_trees_old_enough_and_jobs_group_by_parent(self):
        s = self.survey({"alfa": report(
            procs=["10|1|500|900|/c/agents/claude/spack|spack install hdf5",
                   "11|10|501|899|/c/agents/claude/spack|make -j8",     # part of 10's tree
                   "20|1|600|30|/c/agents/claude/spack|ls"],            # too young
            jobs=["300|300_1|RUNNING|None|/c/agents/claude/runs/a",
                  "300|300_2|PENDING|Priority|/c/agents/claude/runs/a",
                  "400|400|PENDING|JobHeldUser|/c/shared/stack/t"]),
            "beta": report()})
        rows = {r["target"]: r for r in self.section(s, "alfa")["rows"]}
        self.assertEqual(set(rows), {"build:10", "300", "400"})
        self.assertEqual(rows["build:10"]["owner"], "spack")
        self.assertEqual((rows["300"]["tasks"], rows["300"]["owner"]), (2, "runs"))
        self.assertTrue(rows["400"]["held"])
        self.assertIsNone(rows["400"]["owner"])      # writable folder: unattributed

    def test_unwatched_work_is_an_alarm_and_watched_work_is_not(self):
        self.reg("runs", "alfa", "300")
        s = self.survey({"alfa": report(jobs=["300|300|RUNNING|None|/c/agents/claude/runs/a",
                                              "500|500|RUNNING|None|/c/agents/claude/runs/b"]),
                         "beta": report()})
        rows = {r["target"]: r for r in self.section(s, "alfa")["rows"]}
        self.assertEqual(rows["300"]["watched_by"], ["runs"])
        self.assertEqual(rows["500"]["watched_by"], [])
        out = io.StringIO()
        with redirect_stdout(out):
            alarms = self.fw.report(s)
        self.assertTrue(alarms)
        self.assertIn("LIVE WORK WITH NO WATCHER", out.getvalue())
        self.assertIn("fleetregister runs alfa 500", out.getvalue())

    def test_all_quiet_only_when_every_cluster_answered(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(self.fw.report(self.survey({"alfa": report(), "beta": report()})), 0)
        self.assertIn("Every cluster answered", out.getvalue())


class Watchers(Base):
    def test_a_dead_watcher_on_live_work(self):
        self.reg("runs", "alfa", "300", alive=False)
        sec = self.section(self.survey({"alfa": report(
            jobs=["300|300|RUNNING|None|/c/agents/claude/runs/a"]), "beta": report()}), "alfa")
        self.assertEqual([g["target"] for g in sec["dead"]], ["300"])

    def test_finished_needs_sacct_to_prove_the_end(self):
        self.reg("runs", "alfa", "300", alive=False)
        self.reg("runs", "alfa", "301", alive=False)
        sec = self.section(self.survey({"alfa": report(finals={"300": "COMPLETED,"}),
                                        "beta": report()}), "alfa")
        self.assertEqual([g["target"] for g in sec["finished"]], ["300"])
        self.assertEqual([g["target"] for g in sec["dead"]], ["301"])   # sacct silent: alarm
        self.assertEqual(sorted(self.asked["alfa"]), ["300", "301"])

    def test_a_live_watcher_on_ended_work_is_stale(self):
        self.reg("runs", "alfa", "300")
        sec = self.section(self.survey({"alfa": report(finals={"300": "FAILED,"}),
                                        "beta": report()}), "alfa")
        self.assertEqual([g["target"] for g in sec["stale"]], ["300"])

    def test_a_build_whose_pid_was_reused_has_ended(self):
        self.reg("spack", "alfa", "build:10", alive=False, host="login1", remote_start="500")
        sec = self.section(self.survey({"alfa": report(
            procs=["10|1|777|900|/c/agents/claude/other|something else"]), "beta": report()}), "alfa")
        self.assertEqual([g["target"] for g in sec["finished"]], ["build:10"])
        row = next(r for r in sec["rows"] if r["target"] == "build:10")
        self.assertEqual(row["watched_by"], [])        # and the new process is unwatched

    def test_a_young_registered_build_is_live_and_watched(self):
        # mendieta, 2026-10-04: registered right after starting, read as "process gone"
        self.reg("mendieta", "alfa", "build:10", host="login1", remote_start="500")
        sec = self.section(self.survey({"alfa": report(
            procs=["10|1|500|40|/c/agents/claude/mendieta|bash chain.sh"]), "beta": report()}), "alfa")
        self.assertEqual(sec["finished"] + sec["dead"] + sec["stale"], [])
        row = next(r for r in sec["rows"] if r["target"] == "build:10")
        self.assertEqual(row["watched_by"], ["mendieta"])

    def test_a_registered_inner_process_watches_its_whole_tree(self):
        self.reg("mendieta", "alfa", "build:11", host="login1", remote_start="501")
        sec = self.section(self.survey({"alfa": report(
            procs=["10|1|500|900|/c/agents/claude/mendieta|bash -c chain",
                   "11|10|501|899|/c/agents/claude/mendieta|bash chain.sh",
                   "12|11|502|800|/c/agents/claude/mendieta|spack install"]), "beta": report()}), "alfa")
        self.assertEqual(sec["finished"] + sec["dead"] + sec["stale"], [])
        self.assertEqual([(r["target"], r["watched_by"]) for r in sec["rows"]],
                         [("build:10", ["mendieta"])])

    def test_a_build_on_another_login_node_cannot_be_judged(self):
        self.reg("spack", "alfa", "build:10", alive=False, host="login2", remote_start="500")
        sec = self.section(self.survey({"alfa": report(host="login1"), "beta": report()}), "alfa")
        self.assertEqual([g["target"] for g in sec["dead"]], ["build:10"])
        self.assertIn("cannot tell", sec["dead"][0]["_why"])
        self.assertEqual(sec["finished"], [])

    def test_an_unreachable_cluster_is_not_nothing_running(self):
        self.reg("runs", "beta", "300", alive=False)
        s = self.survey({"alfa": report(), "beta": report(end=False)})
        sec = self.section(s, "beta")
        self.assertFalse(sec["ok"])
        self.assertEqual([g["target"] for g in sec["unjudged"]], ["300"])
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertTrue(self.fw.report(s))
        self.assertIn("COULD NOT ASK THE CLUSTER", out.getvalue())
        self.assertNotIn("nothing running.", out.getvalue().split("== beta")[1])

    def test_a_registration_without_a_cluster_reads_as_an_orphan(self):
        with open(os.path.join(self.watch, "old.json"), "w") as f:
            json.dump({"session": "runs", "job": "300", "pid": 1, "starttime": "1"}, f)
        s = self.survey({"alfa": report(), "beta": report()})
        self.assertEqual(len(s["orphans"]), 1)

    def test_the_session_filter(self):
        self.reg("runs", "alfa", "300")
        s = self.survey({"alfa": report(jobs=["300|300|RUNNING|None|/c/agents/claude/runs/a",
                                              "500|500|RUNNING|None|/c/agents/claude/other/b"]),
                         "beta": report()}, only="runs")
        self.assertEqual([r["target"] for r in self.section(s, "alfa")["rows"]], ["300"])

if __name__ == "__main__":
    unittest.main()
