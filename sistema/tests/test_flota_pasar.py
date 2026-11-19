"""flota pasar creates the folders the destination needs inside the AI user's ~/work,
as cp does not. A fake rsh runs the other side's rsync locally, in a temporary folder
that stands for the agents' homes.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

FLOTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flota")
USUARIOS = {"claude": {}, "codex": {}}


def cargar():
    l = importlib.machinery.SourceFileLoader("flota_mod", FLOTA)
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader("flota_mod", l))
    l.exec_module(m)
    return m


class Pasar(unittest.TestCase):
    def setUp(self):
        self.flota = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.casas = os.path.join(t, "home")
        self.work = os.path.join(self.casas, "claude", "work")
        os.makedirs(self.work)
        self.mio = os.path.join(t, "mio")
        os.makedirs(os.path.join(self.mio, "ideas", "sub"))
        with open(os.path.join(self.mio, "ideas", "sub", "a.md"), "w") as f:
            f.write("a\n")
        with open(os.path.join(self.mio, "nota.txt"), "w") as f:
            f.write("n\n")
        rsh = os.path.join(t, "rsh")
        with open(rsh, "w") as f:
            f.write('#!/bin/sh\nshift\nexec "$@"\n')        # drop the host, run the rest here
        os.chmod(rsh, 0o755)
        for p in [mock.patch.object(self.flota, "CASAS", self.casas),
                  mock.patch.object(self.flota, "RSH", rsh),
                  mock.patch.object(self.flota, "instalado", lambda: {"ai_users": USUARIOS}),
                  mock.patch.object(self.flota, "si", return_value=True)]:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def pasar(self, origen, destino):
        with self.assertRaises(SystemExit) as fin:
            self.flota.pasar(os.path.join(self.mio, origen), destino)
        self.assertEqual(fin.exception.code, 0)

    def test_a_folder_to_a_path_that_does_not_exist_yet(self):
        self.pasar("ideas", "claude:proyecto/docs/ideas")
        self.assertTrue(os.path.isfile(os.path.join(self.work, "proyecto/docs/ideas/sub/a.md")))

    def test_a_trailing_slash_puts_it_inside_a_new_folder(self):
        self.pasar("ideas", "claude:proyecto/docs/")
        self.assertTrue(os.path.isfile(os.path.join(self.work, "proyecto/docs/ideas/sub/a.md")))

    def test_a_file_to_a_new_folder(self):
        self.pasar("nota.txt", "claude:proyecto/notas")
        self.assertTrue(os.path.isfile(os.path.join(self.work, "proyecto/notas/nota.txt")))

    def test_an_existing_folder_still_gets_it_inside(self):
        os.makedirs(os.path.join(self.work, "proyecto"))
        self.pasar("ideas", "claude:proyecto")
        self.assertTrue(os.path.isfile(os.path.join(self.work, "proyecto/ideas/sub/a.md")))

    def varios(self, origenes, destino, arbol=None):
        with self.assertRaises(SystemExit) as fin:
            self.flota.pasar([os.path.join(self.mio, o) for o in origenes], destino,
                             arbol=arbol and os.path.join(self.mio, arbol))
        return fin.exception.code

    def test_several_origins_go_inside(self):
        self.assertEqual(self.varios(["ideas", "nota.txt"], "claude:proyecto"), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.work, "proyecto/ideas/sub/a.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.work, "proyecto/nota.txt")))

    def test_two_origins_with_one_name_ask_for_arbol(self):
        os.makedirs(os.path.join(self.mio, "otro", "ideas"))
        self.assertIn("--arbol", self.varios(["ideas", "otro/ideas"], "claude:proyecto"))

    def test_arbol_keeps_each_folder_at_its_point_of_the_tree(self):
        for d in ["gd/a/b/uno", "gd/c/dos", "gd/c/otra"]:
            os.makedirs(os.path.join(self.mio, d))
            with open(os.path.join(self.mio, d, "f"), "w") as f:
                f.write(d)
        self.assertEqual(self.varios(["gd/a/b/uno", "gd/c/dos"], "claude:gd", arbol="gd"), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.work, "gd/a/b/uno/f")))
        self.assertTrue(os.path.isfile(os.path.join(self.work, "gd/c/dos/f")))
        self.assertFalse(os.path.exists(os.path.join(self.work, "gd/c/otra")))

    def test_arbol_takes_only_what_is_inside_it(self):
        self.assertIn("inside --arbol", self.varios(["ideas"], "claude:gd", arbol="gd"))

    def test_nothing_outside_its_work(self):
        with self.assertRaises(SystemExit) as fin:
            self.flota.pasar(os.path.join(self.mio, "ideas"), "claude:../afuera")
        self.assertIn("..", str(fin.exception.code))
        self.assertFalse(os.path.exists(os.path.join(self.casas, "claude", "afuera")))


if __name__ == "__main__":
    unittest.main()


class Ilegibles(Pasar):
    """A file rsync cannot read (an agent's 600 file, say) does not stop the rest: its
    own error lines are shown, not only its last 'see previous errors'."""
    def test_what_cannot_be_read_is_named_and_the_rest_goes(self):
        if os.geteuid() == 0:
            self.skipTest("root reads everything")
        src = os.path.join(self.work, "notas")
        os.makedirs(src)
        for n in ("ok.md", "cerrado.md"):
            with open(os.path.join(src, n), "w") as f:
                f.write(n)
        os.chmod(os.path.join(src, "cerrado.md"), 0)
        destino = os.path.join(self.tmp.name, "aca")
        os.makedirs(destino)
        import io, contextlib
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), self.assertRaises(SystemExit) as fin:
            self.flota.pasar("claude:notas", destino)
        self.assertEqual(fin.exception.code, 23)                 # not all of it: said so
        self.assertIn("cerrado.md", salida.getvalue())
        self.assertIn("pasó lo demás", salida.getvalue())
        self.assertTrue(os.path.isfile(os.path.join(destino, "notas", "ok.md")))

    def test_a_folder_it_cannot_open_is_named_before_the_question(self):
        if os.geteuid() == 0:
            self.skipTest("root reads everything")
        src = os.path.join(self.work, "notas")
        os.makedirs(os.path.join(src, "privado"))
        with open(os.path.join(src, "ok.md"), "w") as f:
            f.write("ok")
        os.chmod(os.path.join(src, "privado"), 0)
        self.addCleanup(os.chmod, os.path.join(src, "privado"), 0o755)
        destino = os.path.join(self.tmp.name, "aca")
        os.makedirs(destino)
        import io, contextlib
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), self.assertRaises(SystemExit):
            self.flota.pasar("claude:notas", destino)
        self.assertIn("privado", salida.getvalue().split("ok.md")[0])     # before the list
        self.assertTrue(os.path.isfile(os.path.join(destino, "notas", "ok.md")))


class ComoCp(Pasar):
    """`flota pasar pensadero:x .` standing in the folder that holds your copy of x is the
    project form, as `flota pasar pensadero:x x` is."""
    def test_into_the_folder_that_holds_your_copy(self):
        agents = os.path.join(self.tmp.name, "agents")
        os.makedirs(os.path.join(agents, "notas"))
        with mock.patch.object(self.flota, "CLONES", agents):
            self.assertEqual(self.flota.como_proyecto("claude:notas", agents), ("claude:notas", "claude"))
            self.assertIsNone(self.flota.como_proyecto("claude:notas", self.mio))
            self.assertIsNone(self.flota.como_proyecto("claude:otra/notas", agents))

