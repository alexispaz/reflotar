"""Tests for bin/fleetcontext: sizes from transcripts, recommendations, watchers."""
import json, os, tempfile, time, unittest
from unittest import mock
from tests.support import load_tool
from fleet import transcripts as tr

CTX = {"compact_above": 250000, "clear_above": 500000, "idle_minutes": 10,
       "compact_focus": "keep job ids"}


def usage(n):
    return json.dumps({"type": "assistant", "message": {"usage": {
        "input_tokens": 1, "cache_read_input_tokens": n - 1, "cache_creation_input_tokens": 0}}}) + "\n"


class FleetContext(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = os.path.join(self.tmp.name, "projects", "-w")
        os.makedirs(self.proj)
        self.state = os.path.join(self.tmp.name, "state")
        os.makedirs(os.path.join(self.state, "watchers"))
        self.p = mock.patch.object(tr, "PROJECTS", os.path.join(self.tmp.name, "projects"))
        self.p.start()
        self.fc = load_tool("fleetcontext")
        self.now = time.time()

    def tearDown(self):
        self.p.stop(); self.tmp.cleanup()

    def session(self, uuid, name, tokens, idle_min):
        path = os.path.join(self.proj, uuid + ".jsonl")
        with open(path, "w") as f:
            f.write(json.dumps({"type": "agent-name", "agentName": name}) + "\n")
            if tokens is not None:
                f.write(usage(tokens))
        t = self.now - idle_min * 60
        os.utime(path, (t, t))
        return (len(uuid), "/w", ["claude", "-r", uuid, "-n", name])

    def test_recommendations_and_order(self):
        procs = [self.session("aaaa0001", "small", 80000, 300),
                 self.session("aaaa0002", "big-idle", 600000, 30),
                 self.session("aaaa0003", "big-busy", 300000, 2)]
        with open(os.path.join(self.state, "watchers", "x.json"), "w") as f:
            json.dump({"session": "big-idle", "cluster": "c", "target": "1"}, f)
        with mock.patch.object(tr, "process_start", return_value=None):
            rs = self.fc.rows(CTX, self.state, now=self.now, procs=procs)
        got = [(r["session"], r["tokens"], r["recommend"], r["watchers"]) for r in rs]
        self.assertEqual(got, [("big-idle", 600000, "compact", 1),
                               ("big-busy", 300000, "later", 0),
                               ("small", 80000, "ok", 0)])

    def test_aviso_names_only_what_to_compact_and_waits(self):
        procs = [self.session("aaaa0005", "big", 600000, 30),
                 self.session("aaaa0006", "busy", 600000, 1)]
        ctx = dict(CTX, remind_minutes=5)
        rows_fn = lambda c, s, now: self.fc.rows(c, s, now=now, procs=procs)
        with mock.patch.object(tr, "process_start", return_value=None):
            first = self.fc.aviso(ctx, self.state, now=self.now, rows_fn=rows_fn)
            again = self.fc.aviso(ctx, self.state, now=self.now + 240, rows_fn=rows_fn)
            later = self.fc.aviso(ctx, self.state, now=self.now + 360, rows_fn=rows_fn)
        self.assertIn("big (600k", first)
        self.assertNotIn("busy", first)
        self.assertIsNone(again)                      # within 5 minutes: silent
        self.assertIn("big", later)

    def test_aviso_silent_when_nothing_to_compact(self):
        procs = [self.session("aaaa0007", "small", 1000, 30)]
        rows_fn = lambda c, s, now: self.fc.rows(c, s, now=now, procs=procs)
        with mock.patch.object(tr, "process_start", return_value=None):
            self.assertIsNone(self.fc.aviso(dict(CTX, remind_minutes=5), self.state,
                                            now=self.now, rows_fn=rows_fn))

    def test_unknown_size(self):
        procs = [self.session("aaaa0004", "fresh", None, 1)]
        with mock.patch.object(tr, "process_start", return_value=None):
            rs = self.fc.rows(CTX, self.state, now=self.now, procs=procs)
        self.assertEqual((rs[0]["session"], rs[0]["recommend"]), ("fresh", "?"))


if __name__ == "__main__":
    unittest.main()
