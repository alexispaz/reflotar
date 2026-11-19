"""add-cluster: the agent's ssh configuration (its blocks go first, and ssh -G must
agree), and the cluster's authorized_keys (no other key of the agent stays). The
cluster side (REMOTE) runs with bash in a scratch home; nothing else is touched.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import base64
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest

ADD = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   "clusters", "add-cluster")


def cargar():
    l = importlib.machinery.SourceFileLoader("add_cluster", ADD)
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader("add_cluster", l))
    l.exec_module(m)
    return m


AC = cargar()
NUEVA = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINUEVANUEVANUEVANUEVANUEVANUEVANUEVANUEVA1"
VIEJA = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIVIEJAVIEJAVIEJAVIEJAVIEJAVIEJAVIEJAVIEJA1"
MIA = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMIAMIAMIAMIAMIAMIAMIAMIAMIAMIAMIAMIAMIA12"


class Config(unittest.TestCase):
    HAND = "Host helvetios\n    HostName helvetios.example\n    IdentityAgent ~/.ssh/agent.sock\n"

    def test_the_tools_block_goes_above_one_written_by_hand(self):
        out = AC.merge_config(self.HAND, "helvetios", "Host helvetios\n    User usuario\n")
        self.assertLess(out.index("# >>> add-cluster: helvetios"), out.index("IdentityAgent ~/.ssh/agent.sock"))
        again = AC.merge_config(out, "helvetios", "Host helvetios\n    User usuario\n")
        self.assertEqual(again, out)
        self.assertEqual(again.count("# >>> add-cluster: helvetios"), 1)

    def test_a_block_left_below_by_an_older_run_moves_up(self):
        viejo = self.HAND + "\n# >>> add-cluster: helvetios\nHost helvetios\n    User x\n# <<< add-cluster: helvetios\n"
        out = AC.merge_config(viejo, "helvetios", "Host helvetios\n    User usuario\n")
        self.assertTrue(out.startswith("# >>> add-cluster: helvetios"))
        self.assertNotIn("User x", out)
        self.assertIn(self.HAND, out)

    def test_ssh_g_names_what_a_hand_written_block_overrides(self):
        g = ("hostname helvetios.example\nuser usuario\nport 22\nidentitiesonly yes\n"
             "identityfile ~/.ssh/id_ed25519\nidentityagent ~/.ssh/agent.sock\n")
        wrong = AC.config_wrong(g, "/home/claude", "helvetios.example", "usuario", "22")
        self.assertEqual([w[0] for w in wrong], ["identityagent"])
        ok = g.replace("agent.sock", "agente.sock")
        self.assertEqual(AC.config_wrong(ok, "/home/claude", "helvetios.example", "usuario", "22"), [])


class Vpn(unittest.TestCase):
    """With vpn declared, ssh stops on this machine while the interface is missing."""
    def test_the_match_is_written_and_works(self):
        import shutil
        b = AC.host_block("prueba", "192.0.2.1", "nadie", "22", "noexiste*")
        self.assertIn("Match originalhost prueba !exec", b)
        self.assertNotIn("Match", AC.host_block("prueba", "192.0.2.1", "nadie", "22"))
        if not shutil.which("ssh"):
            self.skipTest("no ssh")
        with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as f:
            f.write(b)
        try:
            r = subprocess.run(["ssh", "-F", f.name, "-o", "BatchMode=yes", "prueba", "true"],
                               capture_output=True, text=True, timeout=20)
        finally:
            os.unlink(f.name)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no esta levantada", r.stderr)

    def test_a_bad_interface_is_refused(self):
        with self.assertRaises(SystemExit):
            AC.host_block("prueba", "192.0.2.1", "nadie", "22", "ppp0; rm -rf ~")


class AuthorizedKeys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "usuario")
        os.makedirs(os.path.join(self.home, ".ssh"))
        self.ak = os.path.join(self.home, ".ssh", "authorized_keys")

    def tearDown(self):
        self.tmp.cleanup()

    def remoto(self, go, viejas=""):
        puerta = base64.b64encode(b"#!/bin/sh\n").decode()
        r = subprocess.run(["bash", "-s", "--", "1" if go else "0", "claude", NUEVA, "", puerta,
                            "", "off", "", "", viejas],
                           input=AC.REMOTE, capture_output=True, text=True,
                           env={"HOME": self.home, "PATH": os.environ["PATH"]})
        if "NO BOX" in r.stdout:
            self.skipTest("no user namespaces here")
        return r

    def lineas(self):
        with open(self.ak) as f:
            return f.read().splitlines()

    def test_it_says_whether_there_is_slurm(self):
        r = self.remoto(False)
        hay = subprocess.run(["sh", "-c", "command -v sbatch"], capture_output=True).returncode == 0
        self.assertIn("scheduler: slurm" if hay else "scheduler: none", r.stdout)

    def test_an_authorized_keys_it_cannot_write_says_so(self):
        os.symlink("/nonexistent-flota-test/authorized_keys", self.ak)   # touch cannot make it
        r = self.remoto(True)
        self.assertEqual(r.returncode, 7, r.stdout + r.stderr)
        self.assertIn("AUTHORIZED_KEYS NOT WRITABLE", r.stdout)

    def test_an_older_key_of_the_agent_is_dropped_and_yours_kept(self):
        with open(self.ak, "w") as f:
            f.write(f"{MIA} usuario@portatil\n{VIEJA} claude@maquina\n")
        plan = self.remoto(False, VIEJA.split()[1])
        self.assertIn("would DROP 1 line", plan.stdout)
        self.assertEqual(len(self.lineas()), 2)                       # a plan changes nothing
        r = self.remoto(True, VIEJA.split()[1])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        l = self.lineas()
        self.assertIn(f"{MIA} usuario@portatil", l)
        self.assertFalse(any(VIEJA.split()[1] in x for x in l))
        self.assertTrue(any(NUEVA in x and "agents/puerta claude" in x for x in l))

    def test_a_copy_of_the_key_outside_the_box_goes_even_when_the_boxed_line_is_there(self):
        self.remoto(True)
        with open(self.ak, "a") as f:
            f.write(f"{NUEVA} claude@maquina\n")                  # same key, no puerta
        r = self.remoto(True)
        self.assertNotIn("authorized_keys: unchanged", r.stdout)
        l = self.lineas()
        self.assertEqual(len([x for x in l if NUEVA.split()[1] in x]), 1)
        self.assertIn("agents/puerta claude", "\n".join(l))

    def test_a_line_naming_the_agent_with_an_unknown_key_is_shown_not_dropped(self):
        with open(self.ak, "w") as f:
            f.write(f"{MIA} claude@otra\n")
        r = self.remoto(True)
        self.assertIn("do not go through puerta", r.stdout)
        self.assertIn(f"{MIA} claude@otra", self.lineas())


if __name__ == "__main__":
    unittest.main()
