"""clonar.py's choice of the branch a clone starts from, on scratch repositories:
when the AI user's repository has no main yet (conventions rule 12), its only
branch, the one that holds all the others, or the one --rama names. Only temporary folders are touched.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest

CLONAR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "clonar.py")


def cargar():
    l = importlib.machinery.SourceFileLoader("clonar", CLONAR)
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader("clonar", l))
    l.exec_module(m)
    return m


class ElegirRama(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = cargar()

    def tearDown(self):
        self.tmp.cleanup()

    def repo(self, *ramas, empaquetar=False):
        r = os.path.join(self.tmp.name, "repo")
        git = lambda *a: subprocess.run(["git", "-C", r, *a], check=True, capture_output=True)
        subprocess.run(["git", "init", "-q", "-b", ramas[0], r], check=True)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
        for rama in ramas[1:]:
            git("branch", rama)
        if empaquetar:
            git("pack-refs", "--all")
        return r

    def test_ramas_de_reads_loose_refs(self):
        self.assertEqual(self.m.ramas_de(self.repo("ia/init", "ia/dos", "otra"), "ia"), ["ia/dos", "ia/init"])

    def test_ramas_de_reads_packed_refs(self):
        r = self.repo("ia/init", "ia/dos", empaquetar=True)
        self.assertFalse(os.path.exists(os.path.join(r, ".git/refs/heads/ia/init")))
        self.assertEqual(self.m.ramas_de(r, "ia"), ["ia/dos", "ia/init"])

    def test_main_wins(self):
        self.assertEqual(self.m.elegir_rama(self.repo("main", "ia/init"), "ia"), ("main", False))

    def test_new_repo_with_one_branch_starts_from_it(self):
        self.assertEqual(self.m.elegir_rama(self.repo("ia/init"), "ia"), ("ia/init", True))

    def historia(self, apiladas, divergente=None, gc=False):
        """A new repo whose branches stack in order (each one commit on the last), plus
        optionally one branch off the first; gc packs every object."""
        r = os.path.join(self.tmp.name, "hist")
        git = lambda *a: subprocess.run(["git", "-C", r, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                        check=True, capture_output=True)
        subprocess.run(["git", "init", "-q", "-b", apiladas[0], r], check=True)
        for i, rama in enumerate(apiladas):
            if i:
                git("switch", "-q", "-c", rama)
            git("commit", "-q", "--allow-empty", "-m", rama)
        if divergente:
            git("switch", "-q", "-c", divergente, apiladas[0])
            git("commit", "-q", "--allow-empty", "-m", divergente)
        if gc:
            git("gc", "-q")
        return r

    def test_stacked_branches_start_from_the_one_that_holds_the_others(self):
        r = self.historia(["ia/uno", "ia/dos", "ia/tres"])
        self.assertEqual(self.m.elegir_rama(r, "ia"), ("ia/tres", True))

    def test_diverging_branches_ask_for_rama(self):
        with self.assertRaises(SystemExit) as e:
            self.m.elegir_rama(self.historia(["ia/a", "ia/b"], divergente="ia/c"), "ia")
        self.assertIn("--rama", str(e.exception.code))

    def test_packed_history_cannot_be_read_and_asks_for_rama(self):
        r = self.historia(["ia/a", "ia/b"], gc=True)
        self.assertIsNone(self.m.rama_tope(r, ["ia/a", "ia/b"]))
        with self.assertRaises(SystemExit) as e:
            self.m.elegir_rama(r, "ia")
        self.assertIn("--rama", str(e.exception.code))

    def test_rama_names_one(self):
        self.assertEqual(self.m.elegir_rama(self.repo("ia/init", "ia/dos"), "ia", "ia/dos"), ("ia/dos", True))

    def test_rama_that_does_not_exist_stops(self):
        with self.assertRaises(SystemExit) as e:
            self.m.elegir_rama(self.repo("ia/init"), "ia", "ia/otra")
        self.assertIn("ia/init", str(e.exception.code))


if __name__ == "__main__":
    unittest.main()
