"""The shell functions the plan defines (HELPERS in plan-agentes.py), run by bash on
scratch files. runuser is a stub that runs the command as the caller, and every
/home/<user> in a helper is redirected to a scratch home. Nothing outside a
temporary folder is touched, and the planner itself is not run.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import ast
import os
import stat
import subprocess
import tempfile
import unittest

PLANNER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plan-agentes.py")


def helpers():
    """HELPERS, read from the planner's source without running it."""
    with open(PLANNER) as f:
        arbol = ast.parse(f.read())
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(getattr(t, "id", None) == "HELPERS" for t in nodo.targets):
            return ast.literal_eval(nodo.value)
    raise AssertionError("no HELPERS in plan-agentes.py")


class Helpers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(self.home, "u", ".codex"))
        self.log = os.path.join(self.tmp.name, "runuser.log")
        texto = "\n\n".join(helpers().values()).replace("/home/$1/", self.home + "/$1/")
        self.lib = os.path.join(self.tmp.name, "helpers.sh")
        with open(self.lib, "w") as f:
            f.write(texto + "\n")

    def tearDown(self):
        for raiz, dirs, archivos in os.walk(self.tmp.name):
            for x in dirs + archivos:
                p = os.path.join(raiz, x)
                if not os.path.islink(p):
                    os.chmod(p, 0o700)
        self.tmp.cleanup()

    def bash(self, script):
        """Run script as the plan runs (set -euo pipefail), after the helpers."""
        cabeza = (f"set -euo pipefail\n"
                  f"runuser() {{ shift 3; echo \"$*\" >> {self.log}; \"$@\"; }}\n"
                  f"chown() {{ :; }}\n. {self.lib}\n")
        return subprocess.run(["bash", "-c", cabeza + script], capture_output=True, text=True)

    def path(self, *p):
        return os.path.join(self.home, *p)

    def leer(self, *p):
        with open(self.path(*p)) as f:
            return f.read()

    def escribir(self, contenido, *p):
        with open(self.path(*p), "w") as f:
            f.write(contenido)

    # ---- tmux_conf: the backup decision -------------------------------------------
    LINEAS = "'set -g @c colour34' 'source-file /etc/x.conf'"
    QUIERO = "set -g @c colour34\nsource-file /etc/x.conf\n"

    def tmux(self, contenido):
        f = self.path("u", ".tmux.conf")
        if contenido is not None:
            self.escribir(contenido, "u", ".tmux.conf")
        return self.bash(f"tmux_conf u {f} {self.LINEAS}"), f

    def test_tmux_missing_is_written_without_backup(self):
        r, f = self.tmux(None)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.leer("u", ".tmux.conf"), self.QUIERO)
        self.assertFalse(os.path.exists(f + ".antes-flota"))

    def test_tmux_empty_is_written_without_backup(self):
        r, f = self.tmux("")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.leer("u", ".tmux.conf"), self.QUIERO)
        self.assertFalse(os.path.exists(f + ".antes-flota"))

    def test_tmux_fleet_lines_are_replaced_without_backup(self):
        r, f = self.tmux("source-file /old\n\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.leer("u", ".tmux.conf"), self.QUIERO)
        self.assertFalse(os.path.exists(f + ".antes-flota"))

    def test_tmux_right_is_left_alone(self):
        r, f = self.tmux(self.QUIERO)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.log), "nothing was run as the user")

    def test_tmux_foreign_config_is_backed_up_once(self):
        r, f = self.tmux("set -g mouse on\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(f + ".antes-flota") as g:
            self.assertEqual(g.read(), "set -g mouse on\n")
        self.escribir("set -g mouse off\n", "u", ".tmux.conf")
        self.bash(f"tmux_conf u {f} {self.LINEAS}")
        with open(f + ".antes-flota") as g:
            self.assertEqual(g.read(), "set -g mouse on\n", "an older backup is never overwritten")

    def test_tmux_unreadable_attempts_the_backup(self):
        self.escribir("set -g mouse on\n", "u", ".tmux.conf")
        f = self.path("u", ".tmux.conf")
        os.chmod(f, 0)
        self.bash(f"tmux_conf u {f} {self.LINEAS}")    # cp fails here (not root): the attempt counts
        with open(self.log) as g:
            self.assertIn("cp -pn", g.read())

    # ---- sandbox_codex --------------------------------------------------------------
    def sandbox(self, *carpetas):
        return self.bash("sandbox_codex u true /buz/u " + " ".join(self.path("u", c) for c in carpetas))

    def test_sandbox_adds_the_block_once(self):
        self.assertEqual(self.sandbox("a", "b").returncode, 0)
        primero = self.leer("u", ".codex", "config.toml")
        self.sandbox("a", "b")
        self.assertEqual(self.leer("u", ".codex", "config.toml"), primero)
        self.assertIn(f'writable_roots = ["/buz/u", "{self.path("u", "a")}", "{self.path("u", "b")}"]', primero)
        self.assertTrue(os.path.isdir(self.path("u", "b")))

    def test_sandbox_rewrites_only_the_fleets_line(self):
        self.escribir('model = "x"\n', "u", ".codex", "config.toml")
        self.sandbox("a")
        self.sandbox("a", "c")
        texto = self.leer("u", ".codex", "config.toml")
        self.assertTrue(texto.startswith('model = "x"\n'))
        self.assertEqual(texto.count("[sandbox_workspace_write]"), 1)
        self.assertIn(self.path("u", "c"), texto)

    def test_sandbox_gives_the_network_and_upgrades_an_older_block(self):
        viejo = ('model = "x"\n\n# flota: what the sandbox may write besides the working folder\n'
                 '[sandbox_workspace_write]\nwritable_roots = ["/buz/u"]\n\n[otro]\nk = 1\n')
        self.escribir(viejo, "u", ".codex", "config.toml")
        self.sandbox("a")
        self.sandbox("a")
        texto = self.leer("u", ".codex", "config.toml")
        self.assertEqual(texto.count("network_access = true"), 1)
        self.assertEqual(texto.count("writable_roots ="), 1)
        self.assertIn(self.path("u", "a"), texto)
        self.assertIn("[otro]\nk = 1\n", texto)

    def test_sandbox_leaves_a_foreign_section_and_warns(self):
        ajeno = '[sandbox_workspace_write]\nwritable_roots = ["/x"]\n'
        self.escribir(ajeno, "u", ".codex", "config.toml")
        r = self.sandbox("a")
        self.assertEqual(self.leer("u", ".codex", "config.toml"), ajeno)
        self.assertIn("has its own [sandbox_workspace_write]", r.stderr)

    def test_sandbox_unreadable_config_warns_and_changes_nothing(self):
        self.escribir('model = "x"\n', "u", ".codex", "config.toml")
        os.chmod(self.path("u", ".codex", "config.toml"), 0)
        r = self.sandbox("a")
        self.assertEqual(r.returncode, 0)
        self.assertIn("was NOT checked", r.stderr)
        self.assertFalse(os.path.exists(self.path("u", "a")))

    # ---- sudoers_flota -------------------------------------------------------------
    def sudoers(self, *lineas):
        f = self.path("sudoers-flota")
        stub = "install() { cp \"${@: -2:1}\" \"${@: -1}\"; echo install >> " + self.log + "; }\n"
        return f, self.bash(stub + "sudoers_flota " + " ".join([f, *(repr(l) for l in lineas)]))

    def test_sudoers_installs_a_rule_visudo_accepts_once(self):
        f, r = self.sudoers("# flota", "alexis ALL=(claude,codex) NOPASSWD: ALL")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.leer("sudoers-flota"), "# flota\nalexis ALL=(claude,codex) NOPASSWD: ALL\n")
        _, r = self.sudoers("# flota", "alexis ALL=(claude,codex) NOPASSWD: ALL")
        with open(self.log) as g:
            self.assertEqual(g.read().count("install"), 1, "the same rule is left alone")

    def test_sudoers_a_rule_visudo_refuses_installs_nothing(self):
        f, r = self.sudoers("alexis ALL=(claude NOPASSWD")
        self.assertEqual(r.returncode, 0)
        self.assertIn("visudo refused", r.stderr)
        self.assertFalse(os.path.exists(f))

    # ---- confiar_codex --------------------------------------------------------------
    def test_trust_appends_missing_entries_once(self):
        self.escribir('[projects."/r/coord"]\ntrust_level = "trusted"\n', "u", ".codex", "config.toml")
        self.bash("confiar_codex u /r/coord /r/aparejador")
        self.bash("confiar_codex u /r/coord /r/aparejador")
        texto = self.leer("u", ".codex", "config.toml")
        self.assertEqual(texto.count('[projects."/r/coord"]'), 1)
        self.assertEqual(texto.count('[projects."/r/aparejador"]'), 1)
        self.assertIn('[projects."/r/aparejador"]\ntrust_level = "trusted"\n', texto)

    def test_trust_leaves_an_existing_entry_as_it_is(self):
        propio = '[projects."/r/coord"]\ntrust_level = "untrusted"\n'
        self.escribir(propio, "u", ".codex", "config.toml")
        self.bash("confiar_codex u /r/coord")
        self.assertEqual(self.leer("u", ".codex", "config.toml"), propio)

    def test_trust_unreadable_config_warns_and_changes_nothing(self):
        self.escribir("", "u", ".codex", "config.toml")
        os.chmod(self.path("u", ".codex", "config.toml"), 0)
        r = self.bash("confiar_codex u /r/coord")
        self.assertEqual(r.returncode, 0)
        self.assertIn("was NOT checked", r.stderr)

    # ---- the others -------------------------------------------------------------------
    def test_linea_adds_once(self):
        f = self.path("u", ".profile")
        self.bash(f"linea u {f} 'umask 002'; linea u {f} 'umask 002'")
        self.assertEqual(self.leer("u", ".profile"), "umask 002\n")

    def test_enlace_fixes_a_link_and_leaves_a_real_file(self):
        l = self.path("u", "d", "AGENTS.md")
        self.assertEqual(self.bash(f"enlace u {l} /etc/brief.md").returncode, 0)
        self.assertEqual(os.readlink(l), "/etc/brief.md")
        real = self.path("u", "real.md")
        self.escribir("mine\n", "u", "real.md")
        r = self.bash(f"enlace u {real} /etc/brief.md")
        self.assertIn("is not a symlink", r.stderr)
        self.assertEqual(self.leer("u", "real.md"), "mine\n")

    def test_carpeta_sets_mode(self):
        d = self.path("u", "nueva")
        self.assertEqual(self.bash(f"carpeta {d} u:u 2770").returncode, 0)
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o2770)

    def test_repo_git_once(self):
        d = self.path("u", "datos")
        os.makedirs(d)
        self.bash(f"repo_git u {d}; repo_git u {d}")
        self.assertTrue(os.path.isdir(os.path.join(d, ".git")))
        with open(self.log) as g:
            self.assertEqual(g.read().count("git init"), 1)

    def test_sin_override_warns(self):
        d = self.path("u")
        self.assertEqual(self.bash(f"sin_override {d} x").stderr, "")
        self.escribir("", "u", "AGENTS.override.md")
        self.assertIn("INSTEAD of its brief", self.bash(f"sin_override {d} 'its brief'").stderr)


if __name__ == "__main__":
    unittest.main()
