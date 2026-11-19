"""flota mover: what stops it, and a move of plain files to the pensadero, end to end
(the pensadero's ~/work is like anyone's).
The AI users' homes are folders under a temporary /home; what would run as them with
sudo runs directly, as the test user. No real home, mailbox or fleet is touched.

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
CFG = {"human": {"name": "Ana", "timezone": "America/Argentina/Cordoba"},
       "ai_users": {"claude": {"roles": ["coord"]}, "codex": {"roles": ["coord"]},
                    "pensadero": {"roles": ["maestro"]}}}


def cargar():
    l = importlib.machinery.SourceFileLoader("flota_mover", FLOTA)
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader("flota_mover", l))
    l.exec_module(m)
    return m


def git(repo, *args):
    subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def repo(path):
    os.makedirs(path)
    git(path, "init", "-q", "-b", "main")
    with open(os.path.join(path, "a.tex"), "w") as f:
        f.write("x\n")
    git(path, "add", "a.tex")
    git(path, "commit", "-q", "-m", "uno")


class Mover(unittest.TestCase):
    def setUp(self):
        self.flota = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        self.casas = self.tmp.name
        for d in ("claude/work", "codex/work", "pensadero/work"):
            os.makedirs(os.path.join(self.casas, d))
        directo = lambda agente, *cmd: self.flota.correr(list(cmd), cwd="/")
        self.parches = [mock.patch.object(self.flota, "CASAS", self.casas),
                        mock.patch.object(self.flota, "CLONES", os.path.join(self.casas, "yo", "agents")),
                        mock.patch.object(self.flota, "instalado", lambda: CFG),
                        mock.patch.object(self.flota, "como", directo),
                        mock.patch.dict(os.environ, {"FLOTA_RSH_DIRECTO": "1"})]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()
        self.tmp.cleanup()

    def w(self, *partes):
        return os.path.join(self.casas, "codex", "work", *partes)

    def test_repos_in_a_group_and_what_it_will_not_handle(self):
        repo(self.w("g", "a"))
        repo(self.w("g", "suelto", "hondo"))
        os.makedirs(self.w("g", "notas"))
        repos, raros = self.flota.repos_en(self.w("g"))
        self.assertEqual(repos, [self.w("g", "a")])
        self.assertEqual(len(raros), 1)
        self.assertIn("hondo", raros[0])

    def test_a_clean_repo_on_main_has_no_problems(self):
        repo(self.w("r"))
        self.assertEqual(self.flota.problemas_del_repo("codex", self.w("r")), [])

    def test_uncommitted_work_and_unaccepted_branches_are_problems(self):
        repo(self.w("r"))
        git(self.w("r"), "switch", "-q", "-c", "codex/x")
        git(self.w("r"), "commit", "-q", "--allow-empty", "-m", "dos")
        git(self.w("r"), "switch", "-q", "main")
        with open(self.w("r", "nuevo.tex"), "w") as f:
            f.write("y\n")
        p = self.flota.problemas_del_repo("codex", self.w("r"))
        self.assertTrue(any("sin commitear" in x for x in p), p)
        self.assertTrue(any("codex/x" in x for x in p), p)

    def test_a_repo_without_main_is_a_problem(self):
        os.makedirs(self.w("r"))
        git(self.w("r"), "init", "-q", "-b", "codex/inicio")
        git(self.w("r"), "commit", "-q", "--allow-empty", "-m", "uno")
        self.assertIn("no tiene main", self.flota.problemas_del_repo("codex", self.w("r"))[0])

    def clon(self, nombre):
        """Your clone of codex's repo, as clonar.py leaves it: a fetch-only remote 'codex'."""
        c = os.path.join(self.casas, "yo", "agents", nombre)
        subprocess.run(["git", "clone", "-q", "-o", "codex", "-b", "codex/x", self.w(nombre), c],
                       check=True, capture_output=True)
        git(c, "switch", "-q", "-c", "main")
        git(c, "config", "remote.codex.pushurl", self.flota.PUSHURL)
        return c

    def test_an_agent_without_main_is_fine_when_your_main_has_all_it_has(self):
        os.makedirs(self.w("r"))
        git(self.w("r"), "init", "-q", "-b", "codex/x")
        git(self.w("r"), "commit", "-q", "--allow-empty", "-m", "uno")
        c = self.clon("r")
        self.assertEqual(self.flota.problemas_del_repo("codex", self.w("r"), c), [])
        git(self.w("r"), "commit", "-q", "--allow-empty", "-m", "dos")       # not accepted yet
        git(c, "fetch", "-q", "codex")
        p = self.flota.problemas_del_repo("codex", self.w("r"), c)
        self.assertEqual(len(p), 1)
        self.assertIn("codex/x", p[0])

    def test_a_dirty_repo_stops_the_move_before_anything_changes(self):
        repo(self.w("g", "a"))
        with open(self.w("g", "a", "a.tex"), "a") as f:
            f.write("cambio\n")
        with mock.patch("builtins.input", side_effect=AssertionError("asked")), \
                self.assertRaises(SystemExit):
            self.flota.mover("codex:g", "pensadero")
        self.assertTrue(os.path.isdir(self.w("g", "a")))
        self.assertFalse(os.path.exists(self.w("TRASH")))
        self.assertFalse(os.path.exists(os.path.join(self.casas, "pensadero", "work", "g")))

    def test_a_process_working_there_without_a_terminal_stops_the_move(self):
        os.makedirs(self.w("g"))
        p = subprocess.Popen(["sleep", "30"], cwd=self.w("g"), stdin=subprocess.DEVNULL,
                             start_new_session=True)
        try:
            with mock.patch("builtins.input", side_effect=AssertionError("asked")), \
                    mock.patch("sys.stdout", new_callable=__import__("io").StringIO) as salida, \
                    self.assertRaises(SystemExit):
                self.flota.mover("codex:g", "pensadero")
        finally:
            p.kill()
            p.wait()
        self.assertIn(f"sleep (pid {p.pid})", salida.getvalue())
        self.assertTrue(os.path.isdir(self.w("g")))

    def test_an_existing_destination_stops_the_move(self):
        os.makedirs(self.w("g"))
        os.makedirs(os.path.join(self.casas, "pensadero", "work", "g"))
        with mock.patch("builtins.input", side_effect=AssertionError("asked")), \
                self.assertRaises(SystemExit):
            self.flota.mover("codex:g", "pensadero")
        self.assertTrue(os.path.isdir(self.w("g")))

    def test_plain_files_move_to_the_pensadero_and_the_origin_to_trash(self):
        os.makedirs(self.w("clases", "tema1"))
        with open(self.w("clases", "tema1", "c.tex"), "w") as f:
            f.write("clase\n")
        with mock.patch("builtins.input", side_effect=["s", "son documentos"]):
            self.flota.mover("codex:clases", "pensadero")
        llego = os.path.join(self.casas, "pensadero", "work", "clases", "tema1", "c.tex")
        self.assertTrue(os.path.isfile(llego))
        self.assertFalse(os.path.exists(self.w("clases")))
        papelera = self.w("TRASH")
        movida = [d for d in os.listdir(papelera) if d != "README.md"]
        self.assertEqual(len(movida), 1)
        self.assertTrue(movida[0].endswith("-clases"))
        self.assertTrue(os.path.isfile(os.path.join(papelera, movida[0], "tema1", "c.tex")))
        with open(os.path.join(papelera, "README.md")) as f:
            leeme = f.read()
        self.assertIn("flota mover", leeme)
        self.assertIn("son documentos", leeme)
        self.assertIn("pensadero:clases", leeme)

    def test_a_clean_group_plans_a_clone_per_repo_and_a_no_changes_nothing(self):
        repo(self.w("g", "a"))
        os.makedirs(self.w("g", "notas"))
        with mock.patch("builtins.input", side_effect=["n"]), \
                mock.patch("sys.stdout", new_callable=__import__("io").StringIO) as salida, \
                self.assertRaises(SystemExit):
            self.flota.mover("codex:g", "claude")
        self.assertIn(os.path.join(self.casas, "yo", "agents", "g", "a"), salida.getvalue())
        self.assertIn("le entrego tu main", salida.getvalue())
        self.assertTrue(os.path.isdir(self.w("g", "a", ".git")))
        self.assertFalse(os.path.exists(os.path.join(self.casas, "claude", "work", "g")))
        self.assertFalse(os.path.exists(self.w("TRASH")))

    def test_every_ai_users_trash_is_in_its_work(self):
        self.assertEqual(self.flota.papelera("pensadero"), os.path.join(self.casas, "pensadero", "work", "TRASH"))
        self.assertEqual(self.flota.papelera("codex"), self.w("TRASH"))


if __name__ == "__main__":
    unittest.main()
