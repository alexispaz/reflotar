"""What `flota arrancar` runs as each AI user (LLAVE and VENTANA in sistema/flota),
run by bash in a scratch home, with ssh-add, ssh-agent and tmux as stubs that log
their calls; and which fleets it opens, with sudo never run. Nothing outside a
temporary folder is touched.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import ast
import importlib.machinery
import importlib.util
import os
import re
import shlex
import subprocess
import tempfile
import unittest
from unittest import mock

CORRER = subprocess.run          # flota's subprocess.run is mocked below: this one runs bash -n
FLOTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flota")


def literal(nombre):
    with open(FLOTA) as f:
        arbol = ast.parse(f.read())
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(getattr(t, "id", None) == nombre for t in nodo.targets):
            return ast.literal_eval(nodo.value)
    raise AssertionError(f"no {nombre} in sistema/flota")


def arranque():
    """What runs as claude's coordinator user (LLAVE, then VENTANA for its coord), read
    from flota's source without running it."""
    ventana = literal("VENTANA")
    for k, v in {"sesion": "flota", "ventana": "coord", "carpeta": "coord",
                 "orden": shlex.quote('claude -c -n coord "Retomá la flota"')}.items():
        ventana = ventana.replace(f"@{k}@", v)
    return literal("LLAVE") + ventana


STUBS = {
    "ssh-add": 'echo "ssh-add $*" >> "$LOG"; [ "${1:-}" = -l ] && exit 2; exit 0',
    "ssh-agent": 'echo "ssh-agent $*" >> "$LOG"',
    "tmux": 'echo "tmux $*" >> "$LOG"; [ "$1" = has-session ] && exit 1; exit 0',
}


class Arrancar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(self.home, "coord"))
        self.log = os.path.join(self.tmp.name, "llamadas.log")
        rutas = {}
        for nombre, cuerpo in STUBS.items():
            rutas[nombre] = os.path.join(self.tmp.name, nombre)
            with open(rutas[nombre], "w") as f:
                f.write("#!/bin/bash\n" + cuerpo + "\n")
            os.chmod(rutas[nombre], 0o755)
        self.guion = re.sub(r"@([a-z-]+)@", lambda m: rutas[m.group(1)], arranque())

    def tearDown(self):
        self.tmp.cleanup()

    def correr(self):
        r = subprocess.run(["bash", "-c", self.guion], capture_output=True, text=True,
                           env={"HOME": self.home, "LOG": self.log, "PATH": os.environ["PATH"]})
        with open(self.log) as f:
            return r, f.read()

    def test_no_key_starts_coord_without_ssh_agent(self):
        r, llamadas = self.correr()                  # no ~/.ssh at all, as on a new machine
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("ssh-agent", llamadas)
        self.assertNotIn("ssh-add", llamadas)
        self.assertIn("tmux new-session -d -s flota -n coord", llamadas)
        self.assertIn("tmux send-keys -t flota:coord claude -c -n coord", llamadas)
        self.assertIn("arranco sin ssh-agent", r.stdout)

    def test_a_key_starts_the_agent_and_asks_for_it(self):
        os.makedirs(os.path.join(self.home, ".ssh"), mode=0o700)
        open(os.path.join(self.home, ".ssh", "id_ed25519.pub"), "w").close()
        r, llamadas = self.correr()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"ssh-agent -a {self.home}/.ssh/agente.sock", llamadas)
        self.assertRegex(llamadas, r"(?m)^ssh-add $")
        self.assertIn("tmux send-keys -t flota:coord", llamadas)


USUARIOS = {"claude": {"roles": ["coord", "arquitecto"]},
            "codex": {"provider": "codex", "roles": ["coord", "aparejador"]},
            "pensadero": {"providers": ["claude", "codex"], "roles": ["maestro"]}}


def cargar():
    l = importlib.machinery.SourceFileLoader("flota_mod", FLOTA)
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader("flota_mod", l))
    l.exec_module(m)
    return m


class Cuales(unittest.TestCase):
    """Which fleets open, and where you land; sudo is captured, never run."""
    def setUp(self):
        self.flota = cargar()
        self.corridos, self.final = [], None
        for p in [mock.patch.object(self.flota, "instalado", lambda: {"ai_users": USUARIOS}),
                  mock.patch.object(self.flota, "binario", lambda n: f"/usr/bin/{n}"),
                  mock.patch.object(self.flota.subprocess, "run",
                                    lambda args, **k: self.corridos.append(args)),
                  mock.patch.object(self.flota.os, "execvp", lambda prog, args: setattr(self, "final", args))]:
            p.start()
            self.addCleanup(p.stop)

    def guiones(self):
        """{AI user: the script machinectl would run as that user}."""
        return {a[3].split("@")[0]: a[-1] for a in self.corridos}

    def test_all_fleets_by_default_and_you_land_in_the_first(self):
        self.flota.arrancar()
        g = self.guiones()
        self.assertEqual(list(g), ["claude", "codex", "pensadero"])
        self.assertIn("ssh-add", g["codex"])
        self.assertNotIn("ssh-add", g["pensadero"])             # no clusters, no key
        self.assertIn("claude -c -n coord", g["claude"])
        self.assertIn("codex resume --last", g["codex"])
        self.assertIn("buzon despertador >>", g["codex"])          # codex's mailbox waker, in the background
        self.assertIn("pgrep", g["codex"])                          # never a second one
        self.assertNotIn("despertador", g["claude"])
        self.assertIn("-s pensadero -n maestro", g["pensadero"])
        self.assertIn('claude -c -n maestro "Retomá el pensadero"', g["pensadero"])  # in claude
        self.assertEqual(self.final[-3:], ["attach", "-t", "flota:coord"])
        self.assertIn("claude@", self.final)
        for guion in g.values():
            r = CORRER(["bash", "-n", "-c", guion], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_one_named_fleet_only(self):
        self.flota.arrancar(["pensadero"])
        self.assertEqual(list(self.guiones()), ["pensadero"])
        self.assertEqual(self.final[-3:], ["attach", "-t", "pensadero:maestro"])
        self.assertIn("pensadero@", self.final)

    def test_an_unknown_name_stops_before_anything(self):
        with self.assertRaises(SystemExit) as fin:
            self.flota.arrancar(["pensador"])
        self.assertIn("no es un usuario IA", str(fin.exception.code))
        self.assertEqual(self.corridos, [])


if __name__ == "__main__":
    unittest.main()
