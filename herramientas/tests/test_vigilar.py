"""vigilar: the one watcher. Fixed query, 5 minutes at least, gives up after 3 failed
asks, registers itself and clears on the way out."""
import getpass, io, os, unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock
from tests.support import FakeConfig, load_tool

TOML = """
[paths]
state = "{state}"

[cluster.alfa]
box = {{ %(agent)s = "/c/agents/%(agent)s" }}
"""


def estado(jobs=(), procs=(), finals=None, end=True, host="login1"):
    from fleet import clusters
    t = f"host|{host}\n" + "".join(f"proc|{p}\n" for p in procs) + \
        "".join(f"job|{j}\n" for j in jobs) + "squeue|ok\n" + \
        "".join(f"final|{k}|{v}\n" for k, v in (finals or {}).items()) + ("end|\n" if end else "")
    r = clusters.parse(t)
    if not r["complete"]:
        r["error"] = "ssh: connect to host alfa: Connection refused"
    return r


class Vigilar(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig(TOML % {"agent": getpass.getuser()})
        self.v = load_tool("vigilar")
        self.registros, self.dormido, self.avisos = [], [], []

    def tearDown(self):
        self.cfg.close()

    def correr(self, respuestas, target="123", cada=5, buzon=False):
        it = iter(respuestas)
        out = io.StringIO()
        reg = lambda *a: self.registros.append(a) or mock.Mock(returncode=0, stdout="", stderr="")
        with redirect_stdout(out):
            code = self.v.vigilar("runs", "alfa", target, cada, buzon, query=lambda c, ids: next(it),
                                  dormir=self.dormido.append, registrar=reg,
                                  avisar=lambda *a: self.avisos.append(a))
        return code, out.getvalue()

    def test_a_job_that_ends_well(self):
        code, out = self.correr([estado(jobs=["123|123|RUNNING|None|/w"]),
                                 estado(finals={"123": "COMPLETED"})])
        self.assertEqual(code, 0)
        self.assertIn("terminó: 123 en alfa, COMPLETED", out)
        self.assertEqual(self.dormido, [300])
        self.assertEqual(self.registros[0][:3], ("runs", "alfa", "123"))
        self.assertEqual(self.registros[-1], ("--clear", "runs", "alfa", "123"))

    def test_a_job_that_fails_is_named(self):
        code, out = self.correr([estado(finals={"123": "FAILED"})])
        self.assertEqual(code, 1)
        self.assertIn("123=FAILED", out)

    def test_three_failed_asks_end_it_and_never_more(self):
        code, out = self.correr([estado(end=False)] * 3 + [AssertionError("a 4th ask")])
        self.assertEqual(code, 2)
        self.assertIn("no pude preguntar 3 veces", out)
        self.assertEqual(len(self.dormido), 2)

    def test_a_good_answer_resets_the_count(self):
        bien = estado(jobs=["123|123|RUNNING|None|/w"])
        code, _ = self.correr([estado(end=False), estado(end=False), bien,
                               estado(end=False), estado(end=False), estado(finals={"123": "COMPLETED"})])
        self.assertEqual(code, 0)

    def test_a_build_ends_when_its_pid_and_start_are_gone(self):
        vivo = estado(procs=["42|1|777|60|/c/agents/x/b|make"])
        otro = estado(procs=["42|1|999|5|/c/agents/x/b|other"])          # pid reused
        code, out = self.correr([vivo, otro], target="build:42")
        self.assertEqual(code, 0)
        self.assertIn("terminó: build:42", out)

    def test_sacct_lag_is_waited_for(self):
        code, _ = self.correr([estado(), estado(finals={"123": "COMPLETED"})])
        self.assertEqual(code, 0)

    def test_buzon_leaves_the_end_line(self):
        self.correr([estado(finals={"123": "COMPLETED"})], buzon=True)
        self.assertEqual(self.avisos[0][1], "alfa")

    def test_less_than_five_minutes_is_refused(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as fin:
            self.v.main(["runs", "alfa", "123", "--cada", "1"])
        self.assertEqual(fin.exception.code, 2)

    def test_a_target_that_is_not_a_job_or_build_is_refused(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as fin:
            self.v.main(["runs", "alfa", "123; rm -rf ~"])
        self.assertEqual(fin.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
