"""fleetregister: a watcher registers its target, checked on the cluster first."""
import glob, io, json, os, subprocess, sys, unittest
from contextlib import redirect_stderr
from tests.support import FakeConfig, load_tool

TOML = """
[paths]
state = "{state}"

[cluster.alfa]
box = {{ %(agent)s = "/c/agents/%(agent)s" }}
"""

def estado(host="login1", procs=(), jobs=(), end=True, finals=None):
    t = f"host|{host}\n" + "".join(f"proc|{p}\n" for p in procs) + \
        "".join(f"job|{j}\n" for j in jobs) + "squeue|ok\n" + \
        "".join(f"final|{k}|{v}\n" for k, v in (finals or {}).items()) + ("end|\n" if end else "")
    return t


class Register(unittest.TestCase):
    def setUp(self):
        import getpass
        self.cfg = FakeConfig(TOML % {"agent": getpass.getuser()})
        self.fr = load_tool("fleetregister")
        from fleet import clusters
        self.cl = clusters
        self.watch = os.path.join(self.cfg.state, "watchers")
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        self.cfg.close()

    def run_tool(self, argv, text=None):
        self.queries = getattr(self, "queries", 0)
        def query(c, ids=()):
            self.queries += 1
            r = self.cl.parse(text or "")
            if not r["complete"]:
                r["error"] = "timed out"
            return r
        try:
            self.fr.main([str(a) for a in argv], query=query)
            return 0
        except SystemExit as e:
            return e.code

    def files(self):
        return glob.glob(self.watch + "/*.json")

    def test_a_job_in_the_queue_is_registered_with_its_cluster(self):
        rep = estado(jobs=["123456|123456_1|RUNNING|None|/c/agents/x/runs"])
        self.assertIn(self.run_tool(["runs", "alfa", 123456, self.proc.pid], rep), (0, None))
        rec = json.load(open(self.files()[0]))
        self.assertEqual((rec["session"], rec["cluster"], rec["target"], rec["pid"]),
                         ("runs", "alfa", "123456", self.proc.pid))
        self.assertTrue(rec["starttime"].isdigit())

    def test_what_cannot_be_verified_is_refused(self):
        rep = estado(jobs=["123456|123456|RUNNING|None|/c/agents/x/runs"])
        self.assertEqual(self.run_tool(["runs", "alfa", 999999, self.proc.pid], rep), 1)  # not queued
        self.assertEqual(self.run_tool(["runs", "alfa", "123456_4", self.proc.pid], rep), 1)  # a task
        self.assertEqual(self.run_tool(["runs", "zeta", 123456, self.proc.pid], rep), 1)  # no cluster
        self.assertEqual(self.run_tool(["runs", "alfa", 123456, self.proc.pid], estado(end=False)), 1)
        self.assertEqual(self.run_tool(["runs", "alfa", 123456, 999999999], rep), 1)      # no watcher
        self.assertEqual(self.files(), [])

    def bench(self):
        return glob.glob(self.watch + "/bench-*.json")

    def test_a_range_registers_every_queued_job_with_one_query(self):
        jobs = [f"{i}|{i}|RUNNING|None|/c/agents/x/b{i}" for i in range(432177, 432272)]
        self.queries = 0
        self.assertIn(self.run_tool(["bench", "alfa", "432177-432271", self.proc.pid], estado(jobs=jobs)),
                      (0, None))
        self.assertEqual(self.queries, 1)
        self.assertEqual(len(self.bench()), 95)
        targets = {json.load(open(p))["target"] for p in self.bench()}
        self.assertEqual(targets, {str(i) for i in range(432177, 432272)})

    def test_a_list_registers_what_is_queued_and_names_the_rest(self):
        rep = estado(jobs=["10|10|RUNNING|None|/w", "12|12|PENDING|None|/w"])
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(self.run_tool(["bench", "alfa", "10,11,12", self.proc.pid], rep), 1)
        self.assertEqual({json.load(open(p))["target"] for p in self.bench()}, {"10", "12"})
        self.assertIn("11", err.getvalue())

    def test_a_bad_range_is_refused(self):
        self.assertEqual(self.run_tool(["bench", "alfa", "20-10", self.proc.pid], estado()), 2)
        self.assertEqual(self.bench(), [])

    def test_an_array_task_id_is_refused_saying_why(self):
        rep = estado(jobs=["123456|123456_4|RUNNING|None|/c/agents/x/runs"])
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(self.run_tool(["runs", "alfa", "123456_4", self.proc.pid], rep), 1)
        self.assertIn("array parent", err.getvalue())

    def test_a_build_is_recorded_with_its_login_node_and_start(self):
        rep = estado(host="login2", procs=["4242|1|7777|900|/c/agents/x/spack|spack install"])
        self.assertIn(self.run_tool(["spack", "alfa", "build:4242", self.proc.pid], rep), (0, None))
        rec = json.load(open(self.files()[0]))
        self.assertEqual((rec["target"], rec["host"], rec["remote_start"]),
                         ("build:4242", "login2", "7777"))
        self.assertEqual(self.run_tool(["spack", "alfa", "build:1", self.proc.pid], rep), 1)

    def test_clear_only_once_the_watcher_has_ended(self):
        rep = estado(jobs=["123456|123456|RUNNING|None|/c/agents/x/runs"])
        self.run_tool(["runs", "alfa", 123456, self.proc.pid], rep)
        self.assertEqual(self.run_tool(["--clear", "runs", "alfa", 123456]), 1)
        self.assertEqual(len(self.files()), 1)
        self.proc.kill(); self.proc.wait()
        self.assertIn(self.run_tool(["--clear", "runs", "alfa", 123456]), (0, None))
        self.assertEqual(self.files(), [])

    def test_clear_takes_the_dead_watcher_and_keeps_the_live_one(self):
        rep = estado(jobs=["123456|123456|RUNNING|None|/c/agents/x/runs"])
        muerto = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.run_tool(["runs", "alfa", 123456, muerto.pid], rep)
        muerto.kill(); muerto.wait()                      # the first loop died, a new one re-armed
        self.run_tool(["runs", "alfa", 123456, self.proc.pid], rep)
        self.assertEqual(len(self.files()), 2)
        self.assertEqual(self.run_tool(["--clear", "runs", "alfa", 123456], rep), 1)   # live: refused
        (queda,) = self.files()
        self.assertEqual(json.load(open(queda))["pid"], self.proc.pid)              # the dead one went


class ClearWhileWatching(Register):
    """One loop watches many jobs: an ended job's registration goes while it runs."""
    # inherited from Register: they assume no registrations at the start
    test_a_job_in_the_queue_is_registered_with_its_cluster = None
    test_what_cannot_be_verified_is_refused = None
    test_an_array_task_id_is_refused_saying_why = None
    test_a_build_is_recorded_with_its_login_node_and_start = None
    test_clear_only_once_the_watcher_has_ended = None
    test_clear_takes_the_dead_watcher_and_keeps_the_live_one = None

    def setUp(self):
        super().setUp()
        q = estado(jobs=[f"{j}|{j}|RUNNING|None|/c/agents/x/runs" for j in (111111, 222222, 333333)])
        for j in (111111, 222222, 333333):
            self.run_tool(["runs", "alfa", j, self.proc.pid], q)

    def test_an_ended_job_clears_with_the_loop_alive(self):
        rep = estado(jobs=["222222|222222|RUNNING|None|/c/agents/x/runs"],
                     finals={"111111": "COMPLETED,"})
        self.assertIn(self.run_tool(["--clear", "runs", "alfa", 111111], rep), (0, None))
        self.assertEqual(len(self.files()), 2)

    def test_a_live_job_or_an_unknown_one_does_not(self):
        rep = estado(jobs=["222222|222222|RUNNING|None|/c/agents/x/runs"])
        self.assertEqual(self.run_tool(["--clear", "runs", "alfa", 222222], rep), 1)   # live
        self.assertEqual(self.run_tool(["--clear", "runs", "alfa", 111111], rep), 1)   # no sacct
        self.assertEqual(self.run_tool(["--clear", "runs", "alfa", 111111], estado(end=False)), 1)
        self.assertEqual(len(self.files()), 3)

    def test_clear_ended_takes_only_ended_work_in_one_query(self):
        self.queries = 0
        rep = estado(jobs=["222222|222222|RUNNING|None|/c/agents/x/runs"],
                     finals={"111111": "COMPLETED,", "333333": "FAILED,"})
        self.assertIn(self.run_tool(["--clear-ended", "runs"], rep), (0, None))
        self.assertEqual(self.queries, 1)
        left = [json.load(open(f))["target"] for f in self.files()]
        self.assertEqual(left, ["222222"])

    def test_clear_ended_clears_nothing_when_the_cluster_cannot_answer(self):
        self.assertIn(self.run_tool(["--clear-ended", "runs"], estado(end=False)), (0, None))
        self.assertEqual(len(self.files()), 3)

if __name__ == "__main__":
    unittest.main()
