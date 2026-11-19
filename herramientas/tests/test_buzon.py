"""Tests for bin/buzon. Stdlib only; never touches the real /srv/buzon or ~/.local/state.

    python3 -m unittest discover -s tests -t .
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import pwd
import stat
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "bin", "buzon")
ME = pwd.getpwuid(os.geteuid()).pw_name


def load(tmp):
    os.environ["BUZON_DIR"] = os.path.join(tmp, "buzon")
    os.environ["HOME"] = os.path.join(tmp, "home")       # READ_LOG lands here
    loader = importlib.machinery.SourceFileLoader("buzon_under_test", TOOL)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class BuzonTest(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        self.tmp = tempfile.mkdtemp(prefix="buzon-test-")
        self.b = load(self.tmp)
        self.b.FLEET_TOML = os.path.join(self.tmp, "fleet.toml")   # none: not the installed one
        self.box = os.path.join(self.tmp, "buzon", ME)
        os.makedirs(self.box)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        for root, dirs, files in os.walk(self.tmp, topdown=False):
            for f in files:
                p = os.path.join(root, f)
                os.chmod(p, 0o600)
                os.unlink(p)
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self.tmp)

    def run_tool(self, *argv, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if stdin is not None:
                import sys
                old, sys.stdin = sys.stdin, io.StringIO(stdin)
                try:
                    code = self.b.main(list(argv))
                finally:
                    sys.stdin = old
            else:
                code = self.b.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def send(self, *extra, body="hola"):
        code, out, err = self.run_tool("enviar", "--para", "pensadero", "--asunto", "Estado spack",
                                       "-m", body, *extra)
        self.assertEqual(code, 0, err)
        return out.strip()

    def test_send_writes_one_readonly_file_with_header(self):
        mid = self.send("--tipo", "pedido", "--sesion", "coord")
        path = os.path.join(self.box, mid + ".md")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o440)
        head, body = self.b.parse(path)
        self.assertEqual(head["de"], ME)
        self.assertEqual(head["sesion"], "coord")
        self.assertEqual(head["para"], ["pensadero"])
        self.assertEqual(head["tipo"], "pedido")
        self.assertEqual(body, "hola\n")
        self.assertIn(f"_{ME}-coord_a_pensadero_estado-spack", mid)
        self.assertEqual([n for n in os.listdir(self.box)], [mid + ".md"])   # no tmp left

    def test_accents_are_kept_as_letters_in_the_file_name(self):
        self.assertEqual(self.b.slug("Prueba de instalación: ñandú"), "prueba-de-instalacion-nandu")
        self.assertEqual(self.b.slug("¿¡!?"), "sin-asunto")

    def test_same_second_same_subject_does_not_overwrite(self):
        a, b = self.send(body="uno"), self.send(body="dos")
        self.assertNotEqual(a, b)
        self.assertEqual(len(os.listdir(self.box)), 2)

    def test_body_over_limit_is_refused(self):
        code, _, err = self.run_tool("enviar", "--para", "pensadero", "--asunto", "x",
                                     "-m", "a" * (self.b.MAX_BODY + 1))
        self.assertEqual(code, 2)
        self.assertIn("limit", err)
        self.assertEqual(os.listdir(self.box), [])

    def test_bad_recipient_and_multiline_subject_are_refused(self):
        self.assertEqual(self.run_tool("enviar", "--para", "../etc", "--asunto", "x", "-m", "b")[0], 2)
        self.assertEqual(self.run_tool("enviar", "--para", "pensadero", "--asunto", "x\n---", "-m", "b")[0], 2)
        self.assertEqual(os.listdir(self.box), [])

    def test_reply_must_name_an_existing_message(self):
        self.assertEqual(self.run_tool("enviar", "--para", "pensadero", "--asunto", "r",
                                       "--responde", "nope", "-m", "b")[0], 2)
        mid = self.send()
        code, out, _ = self.run_tool("enviar", "--para", "pensadero", "--asunto", "r",
                                     "--responde", mid, "--tipo", "respuesta", "-m", "b")
        self.assertEqual(code, 0)
        head, _ = self.b.parse(os.path.join(self.box, out.strip() + ".md"))
        self.assertEqual(head["en-respuesta-a"], mid)

    def test_body_from_stdin(self):
        code, out, err = self.run_tool("enviar", "--para", "pensadero", "--asunto", "s", stdin="desde stdin\n")
        self.assertEqual(code, 0, err)
        _, body = self.b.parse(os.path.join(self.box, out.strip() + ".md"))
        self.assertEqual(body, "desde stdin\n")

    def test_no_outbox_is_an_error_not_a_silent_drop(self):
        os.rmdir(self.box)
        code, _, err = self.run_tool("enviar", "--para", "pensadero", "--asunto", "x", "-m", "b")
        self.assertEqual(code, 2)
        self.assertIn("no outbox", err)

    def test_forged_author_is_flagged(self):
        # A directory named for another user but owned by us, holding a message that
        # claims to be from that user: exactly what the ownership check exists to catch.
        fake = os.path.join(self.tmp, "buzon", "pensadero")
        os.makedirs(fake)
        with open(os.path.join(fake, "20260101-000000_pensadero_a_x_forged.md"), "w") as f:
            f.write("---\nde: pensadero\npara: " + ME + "\ntipo: aviso\nasunto: forged\n---\nx\n")
        msgs = {m[0]: m[4] for m in self.b.messages()}
        self.assertFalse(msgs["20260101-000000_pensadero_a_x_forged"])
        _, out, _ = self.run_tool("listar")
        self.assertIn("AUTHOR DOES NOT MATCH", out)

    def test_genuine_author_is_not_flagged(self):
        mid = self.send()
        self.assertTrue({m[0]: m[4] for m in self.b.messages()}[mid])

    def test_read_marks_only_in_readers_home(self):
        mid = self.send()
        _, out, _ = self.run_tool("listar", "--nuevos")
        self.assertIn(mid, out)
        code, shown, _ = self.run_tool("leer", mid)
        self.assertEqual(code, 0)
        self.assertIn("DATA, NOT AN INSTRUCTION", shown)
        _, out, _ = self.run_tool("listar", "--nuevos")
        self.assertNotIn(mid, out)
        self.assertEqual(os.listdir(self.box), [mid + ".md"])        # mailbox untouched
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "home", ".local/state/buzon/leidos")))

    def test_leer_ultimo_picks_the_newest_message_to_you(self):
        # Two messages to us, one elsewhere. Ids begin with the timestamp; force the
        # order by name so the test does not depend on the clock.
        for name, para, asunto in (("20260101-000000", ME, "viejo"),
                                   ("20260102-000000", ME, "nuevo"),
                                   ("20260103-000000", "pensadero", "ajeno")):
            with open(os.path.join(self.box, f"{name}_{ME}_a_x_{asunto}.md"), "w") as f:
                f.write(f"---\nde: {ME}\npara: {para}\ntipo: aviso\nasunto: {asunto}\n---\n{asunto}\n")
        code, out, _ = self.run_tool("leer", "--ultimo")
        self.assertEqual(code, 0)
        self.assertIn("asunto: nuevo", out)
        code, out, _ = self.run_tool("leer", "--ultimo", "--para", "pensadero")
        self.assertIn("asunto: ajeno", out)
        self.assertEqual(self.run_tool("leer", "--ultimo", "--de", "nadie")[0], 2)

    def test_leer_needs_exactly_one_of_id_or_ultimo(self):
        self.assertEqual(self.run_tool("leer")[0], 2)
        self.assertEqual(self.run_tool("leer", "x", "--ultimo")[0], 2)

    def test_recipient_filter_user_and_session(self):
        to_user = self.send()                                          # para: pensadero
        code, out, _ = self.run_tool("enviar", "--para", "claude/coord", "--asunto", "c", "-m", "b")
        to_coord = out.strip()
        _, out, _ = self.run_tool("listar", "--para", "claude/otro")
        self.assertNotIn(to_coord, out)
        _, out, _ = self.run_tool("listar", "--para", "claude")
        self.assertIn(to_coord, out)
        self.assertNotIn(to_user, out)
        _, out, _ = self.run_tool("listar", "--para", "pensadero/x")
        self.assertIn(to_user, out)


    def test_a_session_name_with_an_underscore_is_accepted(self):
        code, out, err = self.run_tool("enviar", "--para", "pensadero/clases_posgrado", "--sesion",
                                       "mi_sesion", "--asunto", "c", "-m", "b")
        self.assertEqual(code, 0, err)
        mid = out.strip()
        self.assertIn(f"_{ME}-mi-sesion_a_pensadero-clases-posgrado_c", mid)
        head, _ = self.b.parse(os.path.join(self.box, mid + ".md"))
        self.assertEqual(head["para"], ["pensadero/clases_posgrado"])
        self.assertEqual(head["sesion"], "mi_sesion")
        _, out, _ = self.run_tool("listar", "--para", "pensadero/clases_posgrado")
        self.assertIn(mid, out)
        _, out, _ = self.run_tool("listar", "--para", "pensadero/clases-posgrado")
        self.assertNotIn(mid, out)

    def test_proposals_are_listed_until_answered(self):
        code, out, err = self.run_tool("enviar", "--para", "claude/arquitecto", "--tipo", "propuesta",
                                       "--asunto", "regla 5", "-m", "ver propuestas/x.md")
        self.assertEqual(code, 0, err)
        prop = out.strip()
        other = self.send()                                  # an aviso, not a proposal
        _, out, _ = self.run_tool("listar", "--tipo", "propuesta", "--sin-respuesta")
        self.assertIn(prop, out)
        self.assertNotIn(other, out)
        self.run_tool("enviar", "--para", "claude/coord", "--tipo", "respuesta", "--responde", prop,
                      "--asunto", "aceptada", "-m", "en claude/x")
        _, out, _ = self.run_tool("listar", "--tipo", "propuesta", "--sin-respuesta")
        self.assertNotIn(prop, out)
        _, out, _ = self.run_tool("listar", "--tipo", "propuesta")
        self.assertIn(prop, out)

    def test_only_requests_and_proposals_wait_for_an_answer(self):
        ids = {}
        for tipo in ("pedido", "propuesta", "aviso", "respuesta"):
            code, out, err = self.run_tool("enviar", "--para", "claude/arquitecto", "--tipo", tipo,
                                           "--asunto", tipo, "-m", "b")
            self.assertEqual(code, 0, err)
            ids[tipo] = out.strip()
        _, out, _ = self.run_tool("listar", "--sin-respuesta")
        self.assertIn(ids["pedido"], out)
        self.assertIn(ids["propuesta"], out)
        self.assertNotIn(ids["aviso"], out)
        self.assertNotIn(ids["respuesta"], out)
        self.run_tool("marcar", ids["pedido"], "hecha")
        _, out, _ = self.run_tool("listar", "--sin-respuesta")
        self.assertNotIn(ids["pedido"], out)

    def test_mark_is_a_reply_to_the_author_shown_in_listar(self):
        code, out, err = self.run_tool("enviar", "--para", "claude/arquitecto", "--tipo", "propuesta",
                                       "--sesion", "coord", "--asunto", "menos tokens", "-m", "ver x.md")
        self.assertEqual(code, 0, err)
        prop = out.strip()
        code, out, err = self.run_tool("marcar", prop, "aceptada", "--nota", "en claude/tokens")
        self.assertEqual(code, 0, err)
        with open(os.path.join(self.box, out.strip() + ".md")) as f:
            text = f.read()
        self.assertIn(f"para: {ME}/coord", text)
        self.assertIn(f"en-respuesta-a: {prop}", text)
        self.assertIn("estado: aceptada", text)
        self.assertIn("asunto: aceptada: menos tokens", text)
        _, out, _ = self.run_tool("listar", "--tipo", "propuesta")
        self.assertIn("-> ACEPTADA", out)
        _, out, _ = self.run_tool("listar", "--tipo", "propuesta", "--sin-respuesta")
        self.assertNotIn(prop, out)
        code, _, err = self.run_tool("marcar", "nope", "hecha")
        self.assertEqual(code, 2)
        self.assertIn("no message", err)

    # ---- esperar ---------------------------------------------------------------------
    def test_wait_is_only_for_your_own_mail(self):
        code, _, err = self.run_tool("esperar", "--para", "otro/arquitecto", "--hasta", "0")
        self.assertEqual(code, 2)
        code, _, err = self.run_tool("esperar", "--para", ME, "--hasta", "0")
        self.assertEqual(code, 2, "one session, not a whole user")

    def test_wait_returns_the_unread_message_and_not_its_own(self):
        code, out, _ = self.run_tool("esperar", "--para", f"{ME}/arquitecto", "--hasta", "0")
        self.assertEqual((code, out.strip()), (1, "(nada nuevo)"))
        self.run_tool("enviar", "--para", ME, "--sesion", "arquitecto", "--asunto", "a", "-m", "b")
        code, _, _ = self.run_tool("esperar", "--para", f"{ME}/arquitecto", "--hasta", "0")
        self.assertEqual(code, 1, "its own message does not wake it")
        _, mid, _ = self.run_tool("enviar", "--para", f"{ME}/arquitecto", "--sesion", "aparejador",
                                  "--asunto", "a", "-m", "b")
        code, out, _ = self.run_tool("esperar", "--para", f"{ME}/arquitecto", "--hasta", "0")
        self.assertEqual((code, out.strip()), (0, mid.strip()))
        self.run_tool("leer", mid.strip())
        code, _, _ = self.run_tool("esperar", "--para", f"{ME}/arquitecto", "--hasta", "0")
        self.assertEqual(code, 1, "once read, it waits again")

    def test_wait_never_outlasts_the_humans_limit(self):
        f = os.path.join(self.tmp, "fleet.toml")
        with open(f, "w") as g:
            g.write("[buzon]\natento_minutos = 0.02\n")              # about a second
        self.b.FLEET_TOML = f
        import time
        t = time.monotonic()
        code, out, _ = self.run_tool("esperar", "--para", f"{ME}/arquitecto", "--hasta", "3600", "--cada", "1")
        self.assertEqual((code, out.strip()), (1, "(nada nuevo)"))
        self.assertLess(time.monotonic() - t, 5)

    def test_a_role_of_another_user_is_refused(self):
        f = os.path.join(self.tmp, "fleet.toml")
        with open(f, "w") as g:
            g.write('[ai_users]\nclaude = { roles = ["coord", "arquitecto"] }\n'
                    'codex = { roles = ["coord", "aparejador"] }\n')
        self.b.FLEET_TOML = f
        code, _, err = self.run_tool("enviar", "--para", "claude/aparejador", "--asunto", "x", "-m", "y")
        self.assertNotEqual(code, 0)
        self.assertIn("--para codex/aparejador", err)
        self.assertEqual(os.listdir(self.box), [], "nothing written")
        for ok in ("codex/aparejador", "claude/coord", "codex/mdsim", "claude"):
            code, _, err = self.run_tool("enviar", "--para", ok, "--asunto", "x", "-m", "y")
            self.assertEqual(code, 0, f"{ok}: {err}")

if __name__ == "__main__":
    unittest.main()


class Despertador(BuzonTest):
    """atento leaves a mark; the despertador queues the marked codex thread a fixed note
    with the new ids (never the content), once per message, and drops expired marks."""
    def setUp(self):
        super().setUp()
        self.log = os.path.join(self.tmp, "codex.log")
        self.codex = os.path.join(self.tmp, "codex")
        with open(self.codex, "w") as f:
            f.write(f'#!/bin/sh\nprintf "%s\\n" "$@" >> {self.log}\necho "---" >> {self.log}\n')
        os.chmod(self.codex, 0o755)
        self.yo = f"{ME}/aparejador"

    def llamadas(self):
        try:
            with open(self.log) as f:
                return [c for c in f.read().split("---\n") if c.strip()]
        except OSError:
            return []

    def test_no_mark_no_wake(self):
        self.run_tool("enviar", "--para", self.yo, "--asunto", "hola", "-m", "x")
        self.assertEqual(self.b.despertar_una_vez(self.codex), 0)
        self.assertEqual(self.llamadas(), [])

    def test_a_marked_session_is_woken_once_with_ids_not_content(self):
        self.run_tool("atento", "--para", self.yo, "--thread", "01a1bb12-2e8a")
        self.run_tool("enviar", "--para", self.yo, "--asunto", "revision", "-m", "CONTENIDO SECRETO")
        self.assertEqual(self.b.despertar_una_vez(self.codex), 1)
        (llamada,) = self.llamadas()
        args = llamada.splitlines()
        self.assertEqual(args[:3], ["queue", "--thread", "01a1bb12-2e8a"])
        self.assertIn("buzon leer ", args[4])
        self.assertNotIn("CONTENIDO SECRETO", llamada)
        self.assertEqual(self.b.despertar_una_vez(self.codex), 0)        # told once
        self.run_tool("enviar", "--para", self.yo, "--asunto", "otra", "-m", "y")
        self.assertEqual(self.b.despertar_una_vez(self.codex), 1)        # a new one wakes it again

    def test_fin_and_expiry_end_it(self):
        import json, time
        self.run_tool("atento", "--para", self.yo, "--thread", "t1")
        self.run_tool("atento", "--para", self.yo, "--fin")
        self.run_tool("enviar", "--para", self.yo, "--asunto", "hola", "-m", "x")
        self.assertEqual(self.b.despertar_una_vez(self.codex), 0)
        self.run_tool("atento", "--para", self.yo, "--thread", "t1")
        path = os.path.join(self.b.ATENTO_DIR, "aparejador.json")
        with open(path) as f:
            m = json.load(f)
        m["hasta"] = time.time() - 1
        with open(path, "w") as f:
            json.dump(m, f)
        self.assertEqual(self.b.despertar_una_vez(self.codex), 0)
        self.assertFalse(os.path.exists(path))

    def test_only_your_own_session_and_a_plain_thread_id(self):
        code, _, err = self.run_tool("atento", "--para", "otro/aparejador", "--thread", "t1")
        self.assertNotEqual(code, 0)
        code, _, err = self.run_tool("atento", "--para", self.yo, "--thread", "a; rm -rf ~")
        self.assertNotEqual(code, 0)


class DespertadorFirme(Despertador):
    """A mark written by hand from the sandbox, and a codex in a writable folder, are
    refused: the despertador runs outside the sandbox and trusts neither."""
    def test_a_hand_written_mark_with_text_or_another_name_is_ignored(self):
        import json
        os.makedirs(self.b.ATENTO_DIR, exist_ok=True)
        for nombre, marca in (("aparejador.json", {"para": self.yo, "thread": "--algo", "hasta": 9e12}),
                              ("otra.json", {"para": self.yo, "thread": "t1", "hasta": 9e12})):
            with open(os.path.join(self.b.ATENTO_DIR, nombre), "w") as f:
                json.dump(marca, f)
        self.run_tool("enviar", "--para", self.yo, "--asunto", "hola", "-m", "x")
        self.assertEqual(self.b.despertar_una_vez(self.codex), 0)
        self.assertEqual(self.llamadas(), [])

    def test_only_a_codex_where_flota_installs_it_runs(self):
        def poner(rel):
            ruta = os.path.join(os.environ["HOME"], rel)
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with open(ruta, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(ruta, 0o755)
            return ruta
        for rel in (".local/state/codex", "aparejador/codex", "work/x/codex", ".codex/tmp/codex"):
            code, _, err = self.run_tool("despertador", "--una-vez", "--codex", poner(rel))
            self.assertNotEqual(code, 0, rel)                    # a session's folder, or any other
            self.assertIn("~/.codex/packages", err)
        bueno = poner(".codex/packages/standalone/current/bin/codex")
        code, _, err = self.run_tool("despertador", "--una-vez", "--codex", bueno)
        self.assertEqual(code, 0, err)
