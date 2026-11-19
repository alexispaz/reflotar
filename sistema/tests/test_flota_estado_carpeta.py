"""flota estado <carpeta>: your copy of a project against the fleet's. Real git repos
in a temporary folder stand for your clone and the agent's; a loose file is any file
outside .git and outside what git follows on either side.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import time
import unittest
from unittest import mock

FLOTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flota")
USUARIOS = {"claude": {}, "pensadero": {"roles": ["maestro"]}}


def cargar():
    l = importlib.machinery.SourceFileLoader("flota_mod", FLOTA)
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader("flota_mod", l))
    l.exec_module(m)
    return m


def git(*args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def escribir(ruta, texto="x", hace=0):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w") as f:
        f.write(texto)
    if hace:
        t = time.time() - hace
        os.utime(ruta, (t, t))


class EstadoCarpeta(unittest.TestCase):
    def setUp(self):
        self.flota = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name
        self.casas, self.agents = os.path.join(t, "home"), os.path.join(t, "agents")
        for u in USUARIOS:
            os.makedirs(os.path.join(self.casas, u, "work"))
        # the project: a repo (code) and loose folders, in pensadero and in your ~/agents
        self.suya = os.path.join(self.casas, "pensadero", "work", "proy")
        self.mia = os.path.join(self.agents, "proy")
        codigo = os.path.join(self.suya, "codigo")
        git("init", "-q", "-b", "main", codigo)
        escribir(os.path.join(codigo, "a.py"))
        git("-C", codigo, "add", ".")
        git("-C", codigo, "commit", "-qm", "a")
        git("clone", "-q", codigo, os.path.join(self.mia, "codigo"))
        mi = os.path.join(self.mia, "codigo")
        git("-C", mi, "remote", "rename", "origin", "pensadero")
        git("-C", mi, "config", "remote.pensadero.pushurl", self.flota.PUSHURL)
        git("-C", codigo, "checkout", "-qb", "pensadero/nuevo")
        escribir(os.path.join(codigo, "b.py"))                     # tracked in its branch only
        git("-C", codigo, "add", ".")
        git("-C", codigo, "commit", "-qm", "b")
        escribir(os.path.join(codigo, "datos", "ignorado.dat"))      # untracked, inside the repo
        escribir(os.path.join(self.suya, "notas", "n.md"), "suyo, más nuevo")
        escribir(os.path.join(self.mia, "notas", "n.md"), "mío", hace=3600)
        escribir(os.path.join(self.mia, "notas", "solo-mio.md"))
        escribir(os.path.join(self.suya, "codigo", "a.py"), "cambiado en su repo")  # tracked: not loose
        for p in [mock.patch.object(self.flota, "CASAS", self.casas),
                  mock.patch.object(self.flota, "CLONES", self.agents),
                  mock.patch.object(self.flota, "instalado", lambda: {"ai_users": USUARIOS})]:
            p.start()
            self.addCleanup(p.stop)

    def test_the_fleet_is_deduced_from_your_folder(self):
        self.assertEqual(self.flota.par(self.mia)[0], "pensadero")
        self.assertEqual(self.flota.par("pensadero:proy")[1], self.mia)

    def test_two_fleets_with_one_project_stop(self):
        os.makedirs(os.path.join(self.casas, "claude", "work", "proy"))
        with self.assertRaises(SystemExit) as fin:
            self.flota.par(self.mia)
        self.assertIn("one fleet", str(fin.exception.code))

    def test_repos_by_git_and_loose_files_outside_git(self):
        u, mia, suya, filas, d, sin_clon = self.flota.estado_carpeta(self.mia)
        (nombre, ramas, falta, nota), = filas
        self.assertEqual((nombre, nota, falta), ("codigo", None, 0))
        self.assertEqual([(r, n) for r, n in ramas], [("pensadero/pensadero/nuevo", 1)])
        self.assertEqual([r for r, _ in d["solo_aca"]], ["notas/solo-mio.md"])
        self.assertEqual([r for r, _ in d["nuevo_alla"]], ["notas/n.md"])
        self.assertEqual([r for r, _ in d["solo_alla"]], ["codigo/datos/ignorado.dat"])
        todos = [r for k in ("solo_aca", "solo_alla", "nuevo_aca", "nuevo_alla") for r, _ in d[k]]
        self.assertNotIn("codigo/a.py", todos)        # tracked in main
        self.assertNotIn("codigo/b.py", todos)        # tracked in its fetched branch
        self.assertFalse(any(".git" in r.split("/") for r in todos))

    def test_your_main_ahead_is_counted(self):
        mi = os.path.join(self.mia, "codigo")
        escribir(os.path.join(mi, "c.py"))
        git("-C", mi, "add", ".")
        git("-C", mi, "commit", "-qm", "c")
        _, _, _, filas, _, _ = self.flota.estado_carpeta(self.mia)
        self.assertEqual(filas[0][2], 1)


if __name__ == "__main__":
    unittest.main()


class PasarProyecto(EstadoCarpeta):
    """flota pasar <origin> alone: the project to its one fleet, or back to ~/agents;
    repos by git, loose files by rsync, never a tracked file nor over a newer one."""
    def setUp(self):
        super().setUp()
        self.llamadas = []
        real = subprocess.run
        def run(args, *a, **k):
            if os.path.basename(str(args[0])) in ("entregar-repo", "instalar"):
                self.llamadas.append(args)
                return mock.Mock(returncode=0)
            return real(args, *a, **k)
        for p in [mock.patch.object(self.flota.subprocess, "run", run),
                  mock.patch.object(self.flota, "si", lambda *a, **k: True),
                  mock.patch.object(self.flota, "revisar", lambda *a, **k: None),
                  mock.patch.dict(os.environ, {"FLOTA_RSH_DIRECTO": "1"})]:
            p.start()
            self.addCleanup(p.stop)

    def leer(self, *p):
        with open(os.path.join(*p)) as f:
            return f.read()

    def test_from_the_fleet_to_you(self):
        self.flota.pasar_proyecto("pensadero:proy")
        mi = os.path.join(self.mia, "codigo")
        self.assertTrue(os.path.isfile(os.path.join(mi, "b.py")))              # its branch, merged
        self.assertEqual(self.leer(self.mia, "notas", "n.md"), "suyo, más nuevo")
        self.assertTrue(os.path.isfile(os.path.join(mi, "datos", "ignorado.dat")))
        self.assertTrue(os.path.isfile(os.path.join(self.mia, "notas", "solo-mio.md")))  # nothing deleted
        self.assertEqual(self.leer(mi, "a.py"), "x")                          # a tracked file: git's

    def test_from_you_to_the_fleet(self):
        escribir(os.path.join(self.mia, "notas", "nuevo.md"), "nuevo")
        self.flota.pasar_proyecto(self.mia)
        self.assertEqual(self.leer(self.suya, "notas", "nuevo.md"), "nuevo")
        self.assertTrue(os.path.isfile(os.path.join(self.suya, "notas", "solo-mio.md")))
        self.assertEqual(self.leer(self.suya, "notas", "n.md"), "suyo, más nuevo")    # newer there
        self.assertEqual(self.leer(self.suya, "codigo", "a.py"), "cambiado en su repo")  # git's
        self.assertEqual(self.llamadas, [])            # the fleet has your main: no repo to hand

    def test_your_main_ahead_is_handed_by_git(self):
        mi = os.path.join(self.mia, "codigo")
        escribir(os.path.join(mi, "c.py"))
        git("-C", mi, "add", ".")
        git("-C", mi, "commit", "-qm", "c")
        self.flota.pasar_proyecto(self.mia)
        (llamada,) = self.llamadas
        self.assertEqual(llamada[1:4], ["pensadero", mi, "--name"])
        self.assertFalse(os.path.exists(os.path.join(self.suya, "codigo", "c.py")))   # not by rsync


class PuntoYTodo(PasarProyecto):
    """`.` inside a repo means the repo; flota entregar with nothing hands every clone
    whose main its fleet lacks to that fleet, and nothing else."""
    def test_a_folder_inside_a_repo_is_the_repo(self):
        mi = os.path.join(self.mia, "codigo")
        os.makedirs(os.path.join(mi, "src", "sub"))
        self.assertEqual(self.flota.raiz_de(os.path.join(mi, "src", "sub")), mi)
        self.assertEqual(self.flota.raiz_de(os.path.join(self.mia, "notas")),
                         os.path.join(self.mia, "notas"))       # not in a repo: itself
        self.assertEqual(self.flota.par(os.path.join(mi, "src"))[1], os.path.join(mi, "src"))  # pasar: itself

    def test_entregar_everything_only_what_its_fleet_lacks(self):
        with mock.patch.object(self.flota, "clones", lambda c=None: [os.path.join(self.mia, "codigo")]):
            self.flota.entregar_todo()
            self.assertEqual(self.llamadas, [])                 # its fleet has your main
            mi = os.path.join(self.mia, "codigo")
            escribir(os.path.join(mi, "c.py"))
            git("-C", mi, "add", ".")
            git("-C", mi, "commit", "-qm", "c")
            self.flota.entregar_todo()
        (llamada,) = self.llamadas
        self.assertEqual(llamada[1:], ["pensadero", os.path.join(self.mia, "codigo"), "--name", "proy/codigo", "--go"])


class TraerSinClon(PasarProyecto):
    """flota traer of a project you have no clone of: the fleet that has it is found,
    and each of its repos is cloned safely (clonar.py), not refused."""
    def test_a_project_only_in_its_fleet_is_cloned(self):
        nuevo = os.path.join(self.casas, "pensadero", "work", "ensayo")
        git("init", "-q", "-b", "pensadero/inicio", nuevo)
        clonados = []
        with mock.patch.object(self.flota, "clonar_uno", lambda a: clonados.append(a) or 0):
            self.flota.traer_sin_clon(os.path.join(self.agents, "ensayo"))
        self.assertEqual(clonados, [["pensadero", "ensayo", os.path.join(self.agents, "ensayo")]])

    def test_nowhere_says_so(self):
        with self.assertRaises(SystemExit) as fin:
            self.flota.traer_sin_clon(os.path.join(self.agents, "nada"))
        self.assertIn("any fleet", str(fin.exception.code))


class NadaPeroAlReves(PasarProyecto):
    """Nothing to send one way, but a branch waits the other way: it says so, with the
    command, instead of "already the same"."""
    def test_it_points_to_the_other_direction(self):
        import io, contextlib
        os.remove(os.path.join(self.mia, "notas", "solo-mio.md"))
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.flota.pasar_proyecto(self.mia)
        texto = salida.getvalue()
        self.assertIn("nada que pasar", texto)
        self.assertIn("en la otra dirección sí hay: codigo", texto)
        self.assertIn("flota pasar pensadero proy", texto)


class DosLados(EstadoCarpeta):
    """flota pasar takes both sides, always; a bare fleet name is the same path there."""
    def test_the_two_copies_of_a_project(self):
        f = self.flota.como_proyecto
        self.assertEqual(f(self.mia, "pensadero"), (self.mia, "pensadero"))
        self.assertEqual(f("pensadero", self.mia), ("pensadero:proy", "pensadero"))
        self.assertEqual(f("pensadero:proy", self.mia), ("pensadero:proy", "pensadero"))
        self.assertEqual(f(os.path.join(self.mia, "codigo", "x"), "pensadero"),
                         (os.path.join(self.mia, "codigo", "x"), "pensadero"))  # a subfolder: itself
        self.assertIsNone(f(self.mia, "pensadero:otra"))                    # another path: not the pair
        self.assertIsNone(f("/tmp", "pensadero"))                           # not under ~/agents

    def test_another_fleet_than_its_own_is_refused(self):
        with self.assertRaises(SystemExit) as fin:
            self.flota.pasar_proyecto(self.mia, flota_pedida="claude")
        self.assertIn("flota mover pensadero:proy claude", str(fin.exception.code))


class Subcarpeta(PasarProyecto):
    """A subfolder of a project goes to the same path in its fleet, made there if new;
    what git follows in the repo around it stays out (that is entregar / traer)."""
    def test_a_subfolder_of_a_repo(self):
        mi = os.path.join(self.mia, "codigo")
        escribir(os.path.join(mi, "doc", "seguido.md"))
        git("-C", mi, "add", ".")
        git("-C", mi, "commit", "-qm", "doc")
        escribir(os.path.join(mi, "doc", "suelto.md"), "suelto")
        sub = os.path.join(mi, "doc")
        self.assertEqual(self.flota.par(sub)[0], "pensadero")         # new there: from the folder above
        self.flota.pasar_proyecto(sub, flota_pedida="pensadero")
        alla = os.path.join(self.suya, "codigo", "doc")
        self.assertEqual(self.leer(alla, "suelto.md"), "suelto")
        self.assertFalse(os.path.exists(os.path.join(alla, "seguido.md")))   # git's, not rsync's
        self.assertEqual(self.llamadas, [])                                 # the repo is not handed


class Direccion(PasarProyecto):
    """pasar says where things go in its first line, and does not claim to use the repo
    around a subfolder it passes on its own."""
    def test_the_header_has_the_direction_and_no_repo_notice(self):
        import io, contextlib
        sub = os.path.join(self.mia, "codigo", "doc")
        escribir(os.path.join(sub, "x.md"))
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.flota.pasar_proyecto(sub, flota_pedida="pensadero")
        texto = salida.getvalue()
        self.assertIn("→  pensadero:proy/codigo/doc", texto.splitlines()[0])
        self.assertIn("de vos a pensadero", texto.splitlines()[0])
        self.assertNotIn("uso el repo", texto)


class Legible(PasarProyecto):
    """A file of yours kept 600 reaches the fleet readable by its group; a session's lock
    under .claude/ is neither listed nor passed."""
    def test_a_closed_file_arrives_readable_and_locks_stay(self):
        cerrado = os.path.join(self.mia, "notas", "cerrado.md")
        escribir(cerrado, "c")
        os.chmod(cerrado, 0o600)
        escribir(os.path.join(self.suya, ".claude", "scheduled_tasks.lock"))
        _, _, _, _, d, _ = self.flota.estado_carpeta(self.mia)
        self.assertNotIn(".claude/scheduled_tasks.lock", [r for k in d if k != "ilegibles" for r, _ in d[k]])
        self.flota.pasar_proyecto(self.mia)
        alla = os.path.join(self.suya, "notas", "cerrado.md")
        self.assertTrue(os.stat(alla).st_mode & 0o040, oct(os.stat(alla).st_mode))


class UnArchivo(PasarProyecto):
    """One file of a project, both sides given: it goes to the same folder there, and
    back, as a plain pasar."""
    def test_one_file_both_ways(self):
        f = os.path.join(self.mia, "notas", "temas", "RHCD#1.pdf")
        escribir(f, "pdf")
        self.assertEqual(self.flota.archivo_de_proyecto(f, "pensadero"),
                         (f, "pensadero:proy/notas/temas/"))
        alla = os.path.join(self.suya, "notas", "n.md")
        self.assertEqual(self.flota.archivo_de_proyecto("pensadero:proy/notas/n.md", "pensadero"),
                         ("pensadero:proy/notas/n.md", os.path.join(self.agents, "proy", "notas") + "/"))
        self.assertIsNone(self.flota.archivo_de_proyecto(self.mia, "pensadero"))
        with self.assertRaises(SystemExit) as fin:
            self.flota.pasar(*self.flota.archivo_de_proyecto(f, "pensadero"))
        self.assertEqual(fin.exception.code, 0)
        self.assertEqual(self.leer(self.suya, "notas", "temas", "RHCD#1.pdf"), "pdf")


class Borrar(PasarProyecto):
    """--borrar in a folder without repos (inside a repo is fine): the loose files only
    the destination has are deleted, and nothing else; with repos in it, refused."""
    def test_a_folder_without_repos_deletes_what_only_the_destination_has(self):
        mi, alla = os.path.join(self.mia, "codigo", "res"), os.path.join(self.suya, "codigo", "res")
        escribir(os.path.join(mi, "viejo.dat"))
        escribir(os.path.join(alla, "nuevo.dat"), "nuevo")
        self.flota.pasar_proyecto("pensadero:proy/codigo/res", borrar=True)
        self.assertFalse(os.path.exists(os.path.join(mi, "viejo.dat")))
        self.assertEqual(self.leer(mi, "nuevo.dat"), "nuevo")
        self.assertEqual(self.leer(self.mia, "codigo", "a.py"), "x")          # the repo around: untouched
        escribir(os.path.join(alla, "otro.dat"))
        escribir(os.path.join(alla, "umbrella", "phi_180", "w.dat"))       # folders only there
        os.makedirs(os.path.join(alla, "umbrella", "vacia"))
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.flota.pasar_proyecto(mi, borrar=True)                        # and the other way
        self.assertFalse(os.path.exists(os.path.join(alla, "otro.dat")))
        self.assertFalse(os.path.exists(os.path.join(alla, "umbrella")))      # emptied: gone too
        self.assertTrue(os.path.exists(os.path.join(alla, "nuevo.dat")))
        self.assertNotIn("vanished", err.getvalue())

    def test_a_folder_with_a_file_not_on_the_list_stays(self):
        mi, alla = os.path.join(self.mia, "codigo", "res"), os.path.join(self.suya, "codigo", "res")
        escribir(os.path.join(mi, "a.dat"))
        escribir(os.path.join(alla, "a.dat"))
        escribir(os.path.join(alla, "d", "x.dat"))
        escribir(os.path.join(alla, "d", "y.dat"))
        self.assertEqual(self.flota.carpetas_que_sobran(mi, alla, [("d/x.dat", 1)]), [])
        self.assertEqual(self.flota.carpetas_que_sobran(mi, alla, [("d/x.dat", 1), ("d/y.dat", 1)]), ["d"])

    def test_with_repos_in_it_it_is_refused(self):
        with self.assertRaises(SystemExit) as fin:
            self.flota.pasar_proyecto("pensadero:proy", borrar=True)
        self.assertIn("sin repos", str(fin.exception.code))
        self.assertTrue(os.path.isfile(os.path.join(self.mia, "notas", "solo-mio.md")))


class ProyectoNuevo(PasarProyecto):
    """A project no fleet has yet, with a repo and files beside it: flota pasar . <fleet>
    hands the repo by git and copies the rest; with repos and another path, it says how."""
    def test_a_new_project_goes_to_the_fleet_you_name(self):
        nuevo = os.path.join(self.agents, "proyecto_b")
        git("init", "-q", "-b", "main", os.path.join(nuevo, "codigo"))
        escribir(os.path.join(nuevo, "codigo", "m.py"))
        git("-C", os.path.join(nuevo, "codigo"), "add", ".")
        git("-C", os.path.join(nuevo, "codigo"), "commit", "-qm", "m")
        escribir(os.path.join(nuevo, "datos", "d.dat"), "d")
        self.assertEqual(self.flota.como_proyecto(nuevo, "pensadero"), (nuevo, "pensadero"))
        self.flota.pasar_proyecto(nuevo, flota_pedida="pensadero")
        (llamada,) = self.llamadas
        self.assertIn("proyecto_b/codigo", llamada)
        self.assertEqual(self.leer(self.casas, "pensadero", "work", "proyecto_b", "datos", "d.dat"), "d")

    def test_repos_outside_agents_say_where_a_project_lives(self):
        fuera = os.path.join(self.tmp.name, "current", "proyecto_b")
        git("init", "-q", "-b", "main", os.path.join(fuera, "codigo"))
        with self.assertRaises(SystemExit) as fin:
            self.flota.pasar(fuera, "pensadero:proyecto_b")
        self.assertIn("flota pasar . pensadero", str(fin.exception.code))
        self.assertNotIn("sin destino", str(fin.exception.code))
