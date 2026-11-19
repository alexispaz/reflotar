"""./install copies the selected tools into a prefix, for the claude user to run."""
import grp, os, subprocess, sys, tempfile, unittest
from tests.support import APP

INSTALL = os.path.join(APP, "install")

class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prefix = os.path.join(self.tmp.name, "agents")
        os.makedirs(self.prefix)
        # installed by the planner; install reads it there
        os.makedirs(os.path.join(self.prefix, "etc", "fleet"))
        self.config = os.path.join(self.prefix, "etc", "fleet", "fleet.toml")
        # any group the test user is in stands for claude and buzon
        g = grp.getgrgid(os.getgid()).gr_name
        self.groups = f"agents={g},buzon={g}"
        self.select(["fleetlog"])

    def tearDown(self):
        self.tmp.cleanup()

    def select(self, tools, skills=()):
        with open(self.config, "w") as f:
            f.write("[messages]\nreport_after = 4\n[install]\n"
                    f"tools = {list(tools)!r}\nskills = {list(skills)!r}\n".replace("'", '"'))

    def run_install(self, *extra):
        return subprocess.run([sys.executable, INSTALL, "--prefix", self.prefix,
                               "--groups", self.groups, *extra],
                              capture_output=True, text=True)

    def p(self, *parts):
        return os.path.join(self.prefix, *parts)

    def test_the_plan_changes_nothing(self):
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("install", r.stdout)
        self.assertEqual(sorted(os.listdir(self.prefix)), ["etc"])

    def test_go_installs_the_tool_and_its_wrapper_then_has_nothing_to_do(self):
        self.assertEqual(self.run_install("--go").returncode, 0)
        self.assertTrue(os.path.isfile(self.p("lib", "fleet", "bin", "fleetlog")))
        self.assertTrue(os.path.isfile(self.p("lib", "fleet", "fleet", "config.py")))
        with open(self.p("bin", "fleetlog")) as f:
            self.assertIn(f"FLEET_CONFIG={self.p('etc', 'fleet')}", f.read())
        self.assertIn("nothing to do", self.run_install().stdout)

    def test_the_wrapper_runs_the_tool_against_the_installed_config(self):
        self.run_install("--go")
        work = os.path.join(self.tmp.name, "nowhere")
        r = subprocess.run([self.p("bin", "fleetlog"), "since-human", "--dir", work],
                           capture_output=True, text=True,
                           env=dict(os.environ, FLEET_CONFIG="/nonexistent"))
        # exit 2: no transcript for that directory -- it got past loading the config
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_the_code_goes_to_the_group_named_agents(self):
        # claude and codex both run the tools: the group is agents, not claude
        r = self.run_install()
        self.assertIn("(agents, 2750)", r.stdout)
        self.assertNotIn("(claude,", r.stdout)

    def test_the_installed_code_is_not_writable_by_the_group(self):
        self.run_install("--go")
        for path in (self.p("lib", "fleet", "bin", "fleetlog"), self.p("bin", "fleetlog"),
                     self.p("lib", "fleet", "bin")):
            self.assertFalse(os.stat(path).st_mode & 0o022, path)

    def test_a_dropped_tool_loses_its_copy_and_wrapper(self):
        self.select(["fleetlog", "fleetregister"])
        self.run_install("--go")
        self.select(["fleetlog"])
        self.run_install("--go")
        self.assertFalse(os.path.exists(self.p("lib", "fleet", "bin", "fleetregister")))
        self.assertFalse(os.path.exists(self.p("bin", "fleetregister")))
        self.assertTrue(os.path.exists(self.p("bin", "fleetlog")))

    def test_a_file_in_bin_that_is_not_our_wrapper_is_never_removed(self):
        self.select(["fleetlog", "fleetregister"])
        self.run_install("--go")
        with open(self.p("bin", "fleetregister"), "w") as f:
            f.write("#!/bin/sh\necho someone else's\n")
        self.select(["fleetlog"])
        self.run_install("--go")
        self.assertTrue(os.path.exists(self.p("bin", "fleetregister")))

    def test_the_config_is_read_never_written_and_code_diffs_only_on_request(self):
        before = open(self.config).read()
        out = self.run_install("--go").stdout
        self.assertEqual(open(self.config).read(), before)
        self.assertNotIn("fleet.toml", out.split("MODE")[1])
        self.assertNotIn("+import", out)
        os.remove(self.p("lib", "fleet", "bin", "fleetlog"))
        self.assertIn("+import", self.run_install("--diff").stdout)

    def test_without_an_installed_config_it_says_to_run_the_planner(self):
        os.remove(self.config)
        r = self.run_install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("planner", r.stderr)

    def test_a_symlinked_config_is_refused(self):
        real = os.path.join(self.tmp.name, "elsewhere.toml")
        os.rename(self.config, real)
        os.symlink(real, self.config)
        r = self.run_install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing", r.stderr)

    def test_skills_and_unknown_tools_are_refused(self):
        self.select(["fleetlog"], skills=["waiting"])
        self.assertIn("skills", self.run_install().stderr)
        self.select(["fleetnope"])
        self.assertIn("no such tool", self.run_install().stderr)

if __name__ == "__main__":
    unittest.main()
