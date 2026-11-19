"""flota entregar CLON, without a destination, goes to the AI user that already has the
clone; to anyone else it asks first, since that is a second copy. Real git repos in a
temporary folder stand for your clones and the agents' homes; entregar-repo is a stub.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest
from unittest import mock

FLOTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flota")
USUARIOS = {"claude": {}, "codex": {}, "pensadero": {"roles": ["maestro"]}}


def cargar():
    l = importlib.machinery.SourceFileLoader("flota_mod", FLOTA)
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader("flota_mod", l))
    l.exec_module(m)
    return m


def git(*args):
    subprocess.run(["git", *args], check=True, capture_output=True)


class Entregar(unittest.TestCase):
    def setUp(self):
        self.flota = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.casas = os.path.join(t, "home")
        self.clones = os.path.join(t, "agents")
        os.makedirs(self.clones)
        for u in USUARIOS:
            os.makedirs(os.path.join(self.casas, u, "work"))
        for p in [mock.patch.object(self.flota, "CASAS", self.casas),
                  mock.patch.object(self.flota, "instalado", lambda: {"ai_users": USUARIOS}),
                  mock.patch.object(self.flota, "entregar")]:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def clon(self, nombre, remotos, grupo=None):
        """A clone of yours with a fetch-only remote per AI user, to its ~/work/<rel>;
        a rel of None leaves that folder missing (a remote gone stale)."""
        carpeta = os.path.join(self.clones, *([grupo] if grupo else []), nombre)
        os.makedirs(carpeta)
        git("init", "-q", carpeta)
        for u, rel in remotos.items():
            dest = os.path.join(self.casas, u, "work", rel or nombre)
            if rel is not None:
                os.makedirs(dest, exist_ok=True)
            git("-C", carpeta, "remote", "add", u, dest)
            git("-C", carpeta, "config", f"remote.{u}.pushurl", self.flota.PUSHURL)
        return carpeta

    def test_without_destination_it_goes_to_the_one_that_has_it(self):
        c = self.clon("clases", {"pensadero": "lineas/clases"})
        self.flota.entregar_a(c)
        self.flota.entregar.assert_called_once_with("pensadero", c, "lineas/clases")

    def test_a_remote_whose_folder_is_gone_does_not_count(self):
        c = self.clon("clases", {"pensadero": "clases", "claude": None})
        self.flota.entregar_a(c)
        self.flota.entregar.assert_called_once_with("pensadero", c, "clases")

    def test_nobody_has_it_yet_asks_for_a_destination(self):
        c = self.clon("nuevo", {})
        with self.assertRaises(SystemExit) as fin:
            self.flota.entregar_a(c)
        self.assertIn("decí a quién", str(fin.exception.code))
        self.flota.entregar.assert_not_called()

    def test_two_have_it_asks_which(self):
        c = self.clon("rc", {"claude": "rc", "codex": "rc"})
        with self.assertRaises(SystemExit) as fin:
            self.flota.entregar_a(c)
        self.assertIn("decí a cuál", str(fin.exception.code))
        self.flota.entregar.assert_not_called()

    def test_another_fleet_is_refused_a_project_lives_in_one(self):
        c = self.clon("clases", {"pensadero": "clases"})
        with self.assertRaises(SystemExit) as fin:
            self.flota.entregar_a(c, "claude")
        self.assertIn("flota mover pensadero:clases claude", str(fin.exception.code))
        self.flota.entregar.assert_not_called()

    def test_the_one_that_has_it_is_not_asked(self):
        c = self.clon("clases", {"pensadero": "clases"})
        with mock.patch.object(self.flota, "si") as si:
            self.flota.entregar_a(c, "pensadero")
        si.assert_not_called()
        self.flota.entregar.assert_called_once_with("pensadero", c, "clases")

    def test_a_group_goes_to_its_group_folder(self):
        a = self.clon("a", {"claude": "rc/a"}, grupo="rc")
        self.clon("b", {"claude": "rc/b"}, grupo="rc")
        grupo = os.path.dirname(a)
        self.flota.entregar_a(grupo)
        self.flota.entregar.assert_called_once_with("claude", grupo, "rc")

    def test_the_old_order_still_works(self):
        c = self.clon("clases", {"claude": "clases"})
        self.flota.entregar_a("claude", c)
        self.flota.entregar.assert_called_once_with("claude", c, "clases")


if __name__ == "__main__":
    unittest.main()
