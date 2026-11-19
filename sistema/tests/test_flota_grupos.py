"""flota stops before traer, entregar and clonar when the login does not carry a group
the human was added to (the plan adds them; a group applies only to a new login).
The system's groups are stubs; nothing is run.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import collections
import importlib.machinery
import importlib.util
import os
import unittest
from unittest import mock

FLOTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flota")


def cargar():
    l = importlib.machinery.SourceFileLoader("flota_mod", FLOTA)
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader("flota_mod", l))
    l.exec_module(m)
    return m


Grupo = collections.namedtuple("Grupo", "gr_name gr_gid gr_mem")
GRUPOS = [Grupo("ana", 1000, []), Grupo("claude", 1003, ["ana"]),
          Grupo("buzon", 1010, ["ana", "claude"]), Grupo("otros", 1020, ["bob"])]


class Grupos(unittest.TestCase):
    def setUp(self):
        self.flota = cargar()

    def con(self, activos):
        return mock.patch.multiple(self.flota.os, getgroups=lambda: activos), \
               mock.patch.object(self.flota.grp, "getgrall", lambda: GRUPOS), \
               mock.patch.object(self.flota.getpass, "getuser", lambda: "ana")

    def test_lists_only_your_groups_this_login_lacks(self):
        a, b, c = self.con([1000, 1003])
        with a, b, c:
            self.assertEqual(self.flota.grupos_sin_activar(), ["buzon"])

    def test_entregar_stops_and_says_what_to_do(self):
        a, b, c = self.con([1000])
        with a, b, c, mock.patch.object(self.flota.sys, "argv", ["flota", "entregar", "claude", "/x"]), \
                mock.patch.object(self.flota, "entregar_a") as entregar:
            with self.assertRaises(SystemExit) as fin:
                self.flota.main()
        entregar.assert_not_called()
        self.assertIn("buzon, claude", str(fin.exception.code))
        self.assertIn("exec su -l $USER", str(fin.exception.code))

    def test_with_every_group_active_entregar_runs(self):
        a, b, c = self.con([1000, 1003, 1010])
        with a, b, c, mock.patch.object(self.flota.sys, "argv", ["flota", "entregar", "claude", "/x"]), \
                mock.patch.object(self.flota, "entregar_a") as entregar:
            self.flota.main()
        entregar.assert_called_once_with("claude", "/x")



class Clusters(unittest.TestCase):
    CFG = {"ai_users": {"claude": {"roles": ["coord"]}, "codex": {"provider": "codex", "roles": ["coord"]},
                        "pensadero": {"roles": ["pensadero"]}},
           "cluster": {"serafin": {"box": {"claude": "/h/agents/claude"}}}}

    def setUp(self):
        self.flota = cargar()

    def test_a_working_ai_user_with_no_box_anywhere_is_named(self):
        with mock.patch.object(self.flota, "instalado", lambda: self.CFG):
            self.assertEqual(self.flota.sin_box(), ["codex"])

    def test_arrancar_unlocks_each_working_users_key_before_its_session(self):
        llamadas = []
        with mock.patch.object(self.flota, "instalado", lambda: self.CFG), \
                mock.patch.object(self.flota, "binario", lambda n: "/usr/bin/" + n), \
                mock.patch.object(self.flota.subprocess, "run", lambda a, **k: llamadas.append(a)), \
                mock.patch.object(self.flota.os, "execvp", lambda p, a: llamadas.append(a)):
            self.flota.arrancar()
        self.assertEqual([a[3] for a in llamadas], ["claude@", "codex@", "pensadero@", "claude@"])
        for a in llamadas[:2]:                        # each working user: its key, then its coord
            self.assertLess(a[-1].index("ssh-add"), a[-1].index("send-keys -t flota:coord"))
        self.assertIn("codex resume --last", llamadas[1][-1])
        self.assertNotIn("ssh-add", llamadas[2][-1])                    # the pensadero has no key
        self.assertEqual(llamadas[3][-3:], ["attach", "-t", "flota:coord"])

    def test_cluster_runs_add_cluster_for_each_box_plan_first(self):
        llamadas = []
        with mock.patch.object(self.flota, "instalado", lambda: self.CFG), \
                mock.patch.object(self.flota, "banda", lambda *a: None), \
                mock.patch.object(self.flota, "si", lambda *a, **k: True), \
                mock.patch.object(self.flota.subprocess, "run",
                                  lambda a, **k: llamadas.append(a[1:]) or mock.Mock(returncode=0)):
            with self.assertRaises(SystemExit) as fin:
                self.flota.cluster("serafin", [])
        self.assertEqual(fin.exception.code, 0)
        self.assertEqual(llamadas, [["serafin", "claude"], ["serafin", "claude", "--go"]])


class Scp(unittest.TestCase):
    CFG = {"ai_users": {"claude": {"roles": ["coord"]}, "pensadero": {"roles": ["maestro"]}}}

    def setUp(self):
        import tempfile
        self.flota = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        self.flota.CASAS = self.tmp.name
        os.makedirs(os.path.join(self.tmp.name, "claude", "work", "proyecto_a"))
        os.makedirs(os.path.join(self.tmp.name, "pensadero", "work", "linea_a"))
        self.p = mock.patch.object(self.flota, "instalado", lambda: self.CFG)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_places_as_scp_writes_them(self):
        t = self.tmp.name
        self.assertEqual(self.flota.lugar("claude:proyecto_a")[::2], ("claude", f"{t}/claude/work/proyecto_a"))
        self.assertEqual(self.flota.lugar("pensadero")[::2], ("pensadero", f"{t}/pensadero/work"))
        self.assertEqual(self.flota.lugar("claude:")[2], f"{t}/claude/work")
        self.assertIsNone(self.flota.lugar("/tmp")[0])
        with self.assertRaises(SystemExit):
            self.flota.lugar("claude:../x")

    def entregar(self, origen, destino):
        llamadas = []
        with mock.patch.object(self.flota.subprocess, "run",
                               lambda a, **k: llamadas.append(a) or mock.Mock(returncode=0)):
            with self.assertRaises(SystemExit):
                self.flota.entregar_a(origen, destino)
        return llamadas[0] if llamadas else None

    def test_entregar_is_for_repositories_only(self):
        mia = os.path.join(self.tmp.name, "mia")
        os.makedirs(mia)
        self.assertIsNone(self.entregar("claude", mia))      # the old order, no repository
        self.assertIsNone(self.entregar(mia, "claude"))


class Estado(unittest.TestCase):
    def test_each_ai_user_with_its_sessions_folders_and_mail(self):
        import io, contextlib, time
        flota = cargar()
        cfg = {"ai_users": {"codex": {"provider": "codex", "roles": ["coord"]},
                            "pensadero": {"providers": ["claude", "codex"], "roles": ["maestro"]}},
               "cluster": {"serafin": {"box": {"codex": "/x"}}}}
        ahora = int(time.time())
        respuestas = {
            "codex": f"S|10|codex|/home/codex/coord|120\nF|/home/codex/work/rc|{ahora - 7200}|grupo\nC|{ahora - 300}\n",
            "pensadero": f"F|/home/pensadero/work/ideas|{ahora - 60}|\n",
        }
        def como(u, *cmd):
            return (1, "", "") if "fleetcontext" in cmd[0] else (0, respuestas[u], "")
        buzon = "* 1-a\n    claude/arquitecto -> codex/aparejador [pedido] x\n"
        out = io.StringIO()
        with mock.patch.object(flota, "instalado", lambda: cfg), mock.patch.object(flota, "como", como), \
                mock.patch.object(flota, "correr", lambda c, **k: (0, buzon, "")), contextlib.redirect_stdout(out):
            flota.estado()
        t = out.getvalue()
        self.assertIn("clusters: serafin", t)
        self.assertIn("~/coord", t)
        self.assertIn("rc", t)
        self.assertIn("2 h", t)
        self.assertIn("grupo", t)
        self.assertIn("contexto", t)                           # a header, not words per row
        self.assertIn("última actividad hace 5 min", t)
        self.assertIn("carpetas en ~/work: 1", t)
        self.assertIn("buzón: 1 pedido", t)



class Pasar(unittest.TestCase):
    """flota pasar with real rsync on scratch folders; rsh-agente runs without sudo."""
    CFG = {"ai_users": {"claude": {"roles": ["coord"]}, "pensadero": {"roles": ["maestro"]}}}

    def setUp(self):
        import tempfile
        self.flota = cargar()
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.flota.CASAS = t
        os.makedirs(os.path.join(t, "claude", "work", "proyecto_a", "sub"))
        with open(os.path.join(t, "claude", "work", "proyecto_a", "sub", "a.md"), "w") as f:
            f.write("uno\n")
        os.makedirs(os.path.join(t, "pensadero", "work", "linea_a"))
        os.makedirs(os.path.join(t, "mio"))
        self.parches = [mock.patch.object(self.flota, "instalado", lambda: self.CFG),
                        mock.patch.dict(os.environ, {"FLOTA_RSH_DIRECTO": "1"})]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()
        self.tmp.cleanup()

    def pasar(self, origen, destino, si=True, borrar=False):
        with mock.patch.object(self.flota, "si", lambda *a, **k: si):
            try:
                self.flota.pasar(origen, destino, borrar=borrar)
            except SystemExit as e:
                return e.code
        return 0

    def ruta(self, *p):
        return os.path.join(self.tmp.name, *p)

    def test_a_folder_with_a_repo_never_goes_between_fleets(self):
        os.makedirs(self.ruta("claude", "work", "proyecto_a", "codigo", ".git"))
        codigo = self.pasar("claude:proyecto_a", "pensadero")
        self.assertIn("flota mover", str(codigo))
        self.assertFalse(os.path.exists(self.ruta("pensadero", "work", "proyecto_a")))
        self.assertIn("flota pasar claude:proyecto_a ", str(self.pasar("claude:proyecto_a", self.ruta("mio"))))

    def test_between_fleets_and_again_to_update(self):
        self.assertEqual(self.pasar("claude:proyecto_a", "pensadero"), 0)
        self.assertTrue(os.path.isfile(self.ruta("pensadero", "work", "proyecto_a", "sub", "a.md")))
        with open(self.ruta("claude", "work", "proyecto_a", "sub", "a.md"), "w") as f:
            f.write("dos, más largo\n")
        self.assertEqual(self.pasar("claude:proyecto_a", "pensadero:proyecto_a"), 0)   # same name: updated
        with open(self.ruta("pensadero", "work", "proyecto_a", "sub", "a.md")) as f:
            self.assertEqual(f.read(), "dos, más largo\n")
        self.assertFalse(os.path.exists(self.ruta("pensadero", "work", "proyecto_a", "proyecto_a")))

    def test_back_to_you_deletes_nothing_unless_asked(self):
        self.assertEqual(self.pasar("claude:proyecto_a", self.ruta("mio")), 0)
        open(self.ruta("mio", "proyecto_a", "propio.md"), "w").close()
        self.pasar("claude:proyecto_a", self.ruta("mio"))
        self.assertTrue(os.path.exists(self.ruta("mio", "proyecto_a", "propio.md")))
        self.pasar("claude:proyecto_a", self.ruta("mio"), borrar=True)
        self.assertFalse(os.path.exists(self.ruta("mio", "proyecto_a", "propio.md")))

    def test_out_of_the_pensadero_it_asks(self):
        os.makedirs(self.ruta("pensadero", "work", "secreta"))
        self.assertNotEqual(self.pasar("pensadero:secreta", "claude", si=False), 0)
        self.assertFalse(os.path.exists(self.ruta("claude", "work", "secreta")))

    def test_a_file_keeps_its_name(self):
        f = self.ruta("informe.pdf")
        open(f, "w").close()
        self.assertEqual(self.pasar(f, "pensadero:linea_a"), 0)
        self.assertTrue(os.path.isfile(self.ruta("pensadero", "work", "linea_a", "informe.pdf")))


if __name__ == "__main__":
    unittest.main()
