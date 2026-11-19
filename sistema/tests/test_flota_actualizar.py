"""flota actualizar: brings only flota and your configuration, then installs, even when
nothing new came; flota traer no longer installs.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import importlib.machinery
import importlib.util
import io
import os
import contextlib
import subprocess
import tempfile
import unittest
from unittest import mock

FLOTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flota")


def cargar():
    l = importlib.machinery.SourceFileLoader("flota_mod", FLOTA)
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader("flota_mod", l))
    l.exec_module(m)
    return m


class Actualizar(unittest.TestCase):
    def setUp(self):
        self.flota = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name
        self.aqui, self.cfg = os.path.join(t, "flota"), os.path.join(t, "flota-ana")
        for r in (self.aqui, self.cfg, os.path.join(t, "proyecto")):
            subprocess.run(["git", "init", "-q", r], check=True)
        open(os.path.join(self.cfg, "fleet.toml"), "w").close()
        self.corridas = []
        for p in [mock.patch.object(self.flota, "AQUI", self.aqui),
                  mock.patch.dict(os.environ, {}, clear=False),
                  mock.patch.object(self.flota.subprocess, "run",
                                    lambda a, *x, **k: self.corridas.append(a) or mock.Mock(returncode=0))]:
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("FLOTA_CONFIG", None)

    def test_only_flota_and_your_configuration(self):
        self.assertEqual(self.flota.repos_de_la_flota(), [self.aqui, self.cfg])

    def test_it_installs_even_with_nothing_new(self):
        traidos = []
        with mock.patch.object(self.flota, "traer", lambda destino=None, lista=None: traidos.append(lista)), \
                mock.patch.object(self.flota, "avisar_proveedores", lambda: None), \
                contextlib.redirect_stdout(io.StringIO()):
            self.flota.actualizar_flota()
        self.assertEqual(traidos, [[self.aqui, self.cfg]])
        self.assertEqual([os.path.basename(c[0]) for c in self.corridas], ["instalar"])
        self.assertEqual(self.corridas[0][1:], ["--go"])

    def test_traer_never_runs_instalar(self):
        with open(self.flota.__file__) as f:
            texto = f.read()
        cuerpo = texto[texto.index("def traer("):texto.index("def repos_de_la_flota(")]
        self.assertNotIn('"instalar"', cuerpo)



class Proveedores(unittest.TestCase):
    def test_versions_compare_as_numbers(self):
        f = cargar()
        self.assertTrue(f.mas_nueva("0.167.0", "0.167.2"))
        self.assertTrue(f.mas_nueva("2.1.99", "2.1.322"))
        self.assertFalse(f.mas_nueva("2.1.322", "2.1.282"))
        self.assertFalse(f.mas_nueva("0.167.2", "0.167.2"))

    def test_a_notice_only(self):
        f = cargar()
        cfg = {"software": {"codex": "0.167.0"},
               "ai_users": {"claude": {"provider": "claude"}, "codex": {"provider": "codex"}}}
        corridas = []
        def run(a, *x, **k):
            corridas.append(a)
            return mock.Mock(returncode=0, stdout="2.1.282 (Claude Code)\n")
        salida = io.StringIO()
        with mock.patch.object(f, "instalado", lambda: cfg), \
                mock.patch.object(f, "ultima_version",
                                  lambda p: {"@openai/codex": "0.167.2", "@anthropic-ai/claude-code": "2.1.322"}[p]), \
                mock.patch.object(f.subprocess, "run", run), contextlib.redirect_stdout(salida):
            f.avisar_proveedores()
        self.assertIn("fijada 0.167.0; hay 0.167.2", salida.getvalue())
        self.assertIn("instalado 2.1.282; hay 2.1.322", salida.getvalue())
        self.assertEqual(corridas, [["claude", "--version"]])        # it only asks

    def test_offline_says_so(self):
        f = cargar()
        cfg = {"software": {"codex": "0.167.0"}, "ai_users": {"codex": {"provider": "codex"}}}
        salida = io.StringIO()
        with mock.patch.object(f, "instalado", lambda: cfg), \
                mock.patch.object(f, "ultima_version", lambda p: None), contextlib.redirect_stdout(salida):
            f.avisar_proveedores()
        self.assertIn("no pude consultar", salida.getvalue())


if __name__ == "__main__":
    unittest.main()
