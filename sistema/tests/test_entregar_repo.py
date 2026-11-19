"""entregar-repo refuses a clone it cannot hand over, and says why. It runs with its
test stand-ins (--as-agent, --agent-work) on scratch repositories, without --go:
nothing is handed over.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import getpass
import os
import subprocess
import tempfile
import unittest

ENTREGAR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "entregar-repo")


class Entregar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clon = os.path.join(self.tmp.name, "flota-ana")
        self.work = os.path.join(self.tmp.name, "work")
        os.makedirs(self.work)
        subprocess.run(["git", "init", "-q", "-b", "main", self.clon], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def entregar(self):
        return subprocess.run([ENTREGAR, "agente", self.clon, "--as-agent", "env",
                               "--agent-work", self.work], capture_output=True, text=True)

    def test_a_repo_with_no_commit_says_commit_first(self):
        r = self.entregar()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("has no commit yet", r.stderr + r.stdout)

    def test_a_committed_main_is_planned(self):
        with open(os.path.join(self.clon, "fleet.toml"), "w") as f:
            f.write("[human]\n")
        git = ["git", "-C", self.clon, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(git + ["add", "fleet.toml"], check=True)
        subprocess.run(git + ["commit", "-qm", "x"], check=True)
        r = self.entregar()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)


    def test_the_agent_runs_from_root_not_from_your_folder(self):
        # the stand-in for `sudo -u AGENT` fails as the agent would in a folder it
        # cannot enter: anywhere but "/"
        agente = os.path.join(self.tmp.name, "como-agente")
        with open(agente, "w") as f:
            f.write('#!/bin/sh\n[ "$(pwd)" = / ] || { echo "Invalid path $(pwd)" >&2; exit 1; }\nexec "$@"\n')
        os.chmod(agente, 0o755)
        with open(os.path.join(self.clon, "fleet.toml"), "w") as f:
            f.write("[human]\n")
        git = ["git", "-C", self.clon, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(git + ["add", "fleet.toml"], check=True)
        subprocess.run(git + ["commit", "-qm", "x"], check=True)
        r = subprocess.run([ENTREGAR, "agente", self.clon, "--as-agent", agente,
                            "--agent-work", self.work, "--go"],
                           capture_output=True, text=True, cwd=self.clon)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.work, "flota-ana", "fleet.toml")))

    def test_the_upstream_your_main_tracks_goes_too(self):
        # the group's repository, which the agent cannot reach, and your clone of it
        G = ["-c", "user.name=t", "-c", "user.email=t@t"]
        grupo = os.path.join(self.tmp.name, "grupo.git")
        otro = os.path.join(self.tmp.name, "otro")
        clon = os.path.join(self.tmp.name, "flota")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", grupo], check=True)
        subprocess.run(["git", "clone", "-q", grupo, otro], check=True, capture_output=True)

        def commit(repo, msg):
            subprocess.run(["git", "-C", repo, *G, "commit", "-q", "--allow-empty", "-m", msg], check=True)

        def entregar():
            r = subprocess.run([ENTREGAR, "agente", clon, "--as-agent", "env",
                                "--agent-work", self.work, "--go"], capture_output=True, text=True, cwd="/")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

        def suyo(ref):
            return subprocess.run(["git", "-C", os.path.join(self.work, "flota"), "rev-parse", ref],
                                  capture_output=True, text=True).stdout.strip()

        def de(repo, ref):
            return subprocess.run(["git", "-C", repo, "rev-parse", ref], capture_output=True, text=True).stdout.strip()

        commit(otro, "grupo 1")
        subprocess.run(["git", "-C", otro, "push", "-q", "origin", "main"], check=True)
        subprocess.run(["git", "clone", "-q", grupo, clon], check=True)
        commit(clon, "mío")                                   # your main diverges
        entregar()                                            # first delivery
        yo = getpass.getuser()
        self.assertEqual(suyo(f"refs/remotes/{yo}/origin/main"), de(grupo, "main"))
        commit(otro, "grupo 2")                               # the group moves on
        subprocess.run(["git", "-C", otro, "push", "-q", "origin", "main"], check=True)
        subprocess.run(["git", "-C", clon, "fetch", "-q", "origin"], check=True)
        entregar()                                            # a later delivery
        self.assertEqual(suyo(f"refs/remotes/{yo}/origin/main"), de(grupo, "main"))
        self.assertEqual(suyo(f"refs/remotes/{yo}/main"), de(clon, "main"))

if __name__ == "__main__":
    unittest.main()
