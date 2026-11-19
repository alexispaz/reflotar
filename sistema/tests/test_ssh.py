"""herramientas/bin/ssh: the agents' ssh reads their own ~/.ssh/config, never the
system's (codex's sandbox refuses those files). The real ssh is a stub that prints
its arguments.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import os
import subprocess
import tempfile
import unittest

SSH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   "herramientas", "bin", "ssh")


class Ssh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(self.home, ".ssh"))
        self.real = os.path.join(self.tmp.name, "ssh-real")
        with open(self.real, "w") as f:
            f.write('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        os.chmod(self.real, 0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def ssh(self, *args):
        r = subprocess.run([SSH, *args], capture_output=True, text=True,
                           env={"HOME": self.home, "FLOTA_SSH_REAL": self.real, "PATH": os.environ["PATH"]})
        return r.stdout.split("\n")[:-1]

    def test_your_config_only(self):
        open(os.path.join(self.home, ".ssh", "config"), "w").close()
        self.assertEqual(self.ssh("-G", "helvetios"),
                         ["-F", f"{self.home}/.ssh/config", "-G", "helvetios"])

    def test_no_config_means_none_not_the_systems(self):
        self.assertEqual(self.ssh("helvetios", "true"), ["-F", "/dev/null", "helvetios", "true"])

    def test_an_explicit_F_is_left_alone(self):
        self.assertEqual(self.ssh("-F", "/x", "h"), ["-F", "/x", "h"])
        self.assertEqual(self.ssh("-F/x", "h"), ["-F/x", "h"])


if __name__ == "__main__":
    unittest.main()
