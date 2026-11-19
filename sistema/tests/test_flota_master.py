"""flota traer, and the pending list, compare against your clone's own main branch: main,
or master in a repo that keeps the old name (2026-10-20). Before, a master-only
clone answered "nothing new" while an agent's branch waited. Temporary repos only.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest

FLOTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flota")


def cargar():
    l = importlib.machinery.SourceFileLoader("flota_master", FLOTA)
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader("flota_master", l))
    l.exec_module(m)
    return m


def git(repo, *args):
    subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


class Master(unittest.TestCase):
    def setUp(self):
        self.flota = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        self.agente = os.path.join(self.tmp.name, "agente")
        os.makedirs(self.agente)
        git(self.agente, "init", "-q", "-b", "master")
        git(self.agente, "commit", "-q", "--allow-empty", "-m", "uno")
        git(self.agente, "switch", "-q", "-c", "claude/x")
        git(self.agente, "commit", "-q", "--allow-empty", "-m", "dos")
        self.clon = os.path.join(self.tmp.name, "clon")
        subprocess.run(["git", "clone", "-q", "-o", "claude", "-b", "master", self.agente, self.clon],
                       check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_main_branch_of_a_master_only_clone_is_master(self):
        self.assertEqual(self.flota.principal(self.clon), "master")

    def test_an_agents_branch_waits_against_master(self):
        base = self.flota.principal(self.clon)
        self.assertEqual(self.flota.ramas_nuevas(self.clon, "claude", base), ["claude/claude/x"])

    def test_a_clone_with_main_still_uses_main(self):
        git(self.clon, "branch", "main")
        self.assertEqual(self.flota.principal(self.clon), "main")


if __name__ == "__main__":
    unittest.main()
