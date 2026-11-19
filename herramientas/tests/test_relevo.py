"""Tests for bin/relevo. Stdlib only; reads only transcripts written here, in a fake HOME."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "bin", "relevo")


def load():
    loader = importlib.machinery.SourceFileLoader("relevo_under_test", TOOL)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    mod.FLEET_TOML = "/nonexistent/fleet.toml"     # never the real one
    return mod


def escribir(ruta, filas):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w") as f:
        for fila in filas:
            f.write(json.dumps(fila) + "\n")


def claude(tipo, contenido, **extra):
    return {"type": tipo, "timestamp": "2026-10-08T22:00:00Z",
            "message": {"role": tipo, "content": contenido}, **extra}


def codex(tipo, payload):
    return {"timestamp": "2026-10-08T22:00:00Z", "type": tipo, "payload": payload}


class RelevoTest(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        self.tmp = tempfile.mkdtemp(prefix="relevo-test-")
        os.environ["HOME"] = os.path.join(self.tmp, "home")
        os.environ.pop("CODEX_HOME", None)
        self.carpeta = os.path.join(self.tmp, "home")
        os.makedirs(self.carpeta)
        self.r = load()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def correr(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.r.main(list(args) + ["--carpeta", self.carpeta])
        return out.getvalue()

    def sesion_claude(self, filas, nombre="s1"):
        ruta = os.path.join(self.tmp, "home", ".claude", "projects",
                            self.r.slug(self.carpeta), f"{nombre}.jsonl")
        escribir(ruta, filas)
        return ruta

    def test_claude_keeps_the_conversation_and_drops_the_rest(self):
        self.sesion_claude([
            claude("user", "antes del resumen"),
            claude("user", "RESUMEN-VIEJO", isCompactSummary=True),
            claude("user", "pregunta del humano <system-reminder>RECORDATORIO</system-reminder>"),
            claude("user", "META", isMeta=True),
            claude("assistant", [{"type": "thinking", "thinking": "PENSANDO"},
                                 {"type": "text", "text": "respuesta del agente"},
                                 {"type": "tool_use", "name": "Bash", "input": {"command": "LLAMADA"}}]),
            claude("user", [{"type": "tool_result", "content": "SALIDA"}]),
            claude("assistant", [{"type": "text", "text": "SUBAGENTE"}], isSidechain=True),
            claude("user", "[Request interrupted by user]"),
            {"type": "attachment", "timestamp": "2026-10-08T22:00:00Z"},
        ])
        out = self.correr("claude")
        self.assertIn("RESUMEN-VIEJO", out)
        self.assertIn("pregunta del humano", out)
        self.assertIn("respuesta del agente", out)
        for fuera in ("antes del resumen", "RECORDATORIO", "META", "PENSANDO", "LLAMADA",
                      "SALIDA", "SUBAGENTE", "Request interrupted"):
            self.assertNotIn(fuera, out, fuera)
        self.assertLess(out.index("pregunta del humano"), out.index("respuesta del agente"))

    def test_claude_takes_the_newest_session_of_the_folder(self):
        vieja = self.sesion_claude([claude("user", "SESION-VIEJA")], "vieja")
        self.sesion_claude([claude("user", "SESION-NUEVA")], "nueva")
        os.utime(vieja, (1, 1))
        out = self.correr("claude")
        self.assertIn("SESION-NUEVA", out)
        self.assertNotIn("SESION-VIEJA", out)

    def test_limit_keeps_the_newest_messages(self):
        self.sesion_claude([claude("user", f"mensaje-{i:02d} " + "x" * 200) for i in range(30)])
        out = self.correr("claude", "--max", "1000")
        self.assertIn("mensaje-29", out)
        self.assertNotIn("mensaje-00", out)
        self.assertIn("más viejos no entran", out)

    def sesion_codex(self, carpeta, filas, nombre):
        ruta = os.path.join(self.tmp, "home", ".codex", "sessions", "2026", "10", "08",
                            f"rollout-{nombre}.jsonl")
        escribir(ruta, [codex("session_meta", {"id": nombre, "cwd": carpeta})] + filas)
        return ruta

    def test_codex_reads_the_session_of_this_folder(self):
        self.sesion_codex(self.carpeta, [
            codex("response_item", {"type": "message", "role": "user",
                                    "content": [{"type": "input_text", "text": "# AGENTS.md instructions BRIEF"}]}),
            codex("compacted", {"message": "RESUMEN-CODEX"}),
            codex("event_msg", {"type": "user_message", "message": "pregunta en codex"}),
            codex("response_item", {"type": "function_call", "name": "shell", "arguments": "LLAMADA"}),
            codex("event_msg", {"type": "agent_message", "message": "respuesta de codex"}),
        ], "aca")
        otra = self.sesion_codex("/otra/carpeta", [
            codex("event_msg", {"type": "user_message", "message": "OTRA-CARPETA"})], "otra")
        os.utime(otra, None)
        out = self.correr("codex")
        self.assertIn("RESUMEN-CODEX", out)
        self.assertIn("pregunta en codex", out)
        self.assertIn("respuesta de codex", out)
        for fuera in ("BRIEF", "LLAMADA", "OTRA-CARPETA"):
            self.assertNotIn(fuera, out, fuera)

    def test_codex_without_events_falls_back_to_messages(self):
        self.sesion_codex(self.carpeta, [
            codex("response_item", {"type": "message", "role": "user",
                                    "content": [{"type": "input_text", "text": "<environment_context>ENTORNO"}]}),
            codex("response_item", {"type": "message", "role": "user",
                                    "content": [{"type": "input_text", "text": "hola codex"}]}),
            codex("response_item", {"type": "message", "role": "assistant",
                                    "content": [{"type": "output_text", "text": "hola humano"}]}),
        ], "solo-items")
        out = self.correr("codex")
        self.assertIn("hola codex", out)
        self.assertIn("hola humano", out)
        self.assertNotIn("ENTORNO", out)

    def test_no_session_is_an_error(self):
        with self.assertRaises(SystemExit) as e:
            self.correr("codex")
        self.assertIn("no codex session", str(e.exception.code))

    def test_file_is_private_even_if_it_existed(self):
        self.sesion_claude([claude("user", "confidencial")])
        archivo = os.path.join(self.tmp, "relevo.md")
        with open(archivo, "w") as f:
            f.write("viejo")
        os.chmod(archivo, 0o644)
        self.correr("claude", "-o", archivo)
        self.assertEqual(stat.S_IMODE(os.stat(archivo).st_mode), 0o600)
        with open(archivo) as f:
            self.assertIn("confidencial", f.read())


if __name__ == "__main__":
    unittest.main()
