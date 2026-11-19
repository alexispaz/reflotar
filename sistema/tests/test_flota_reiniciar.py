"""flota reiniciar walks every AI user (coord's user first), or those named: its claude
sessions from fleetcontext (from ps and their transcripts for the pensadero, which has
not the fleet's tools), its codex sessions from ps and their rollouts (the newest
whose cwd is the session's). fleetcontext, ps, the rollouts and tmux are faked per
user; nothing is typed anywhere.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import importlib.machinery
import importlib.util
import json
import os
import unittest
from unittest import mock

FLOTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flota")
USUARIOS = {"claude": {"roles": ["coord"]}, "codex": {"provider": "codex", "roles": ["coord"]},
            "pensadero": {"providers": ["claude", "codex"], "roles": ["maestro"]}}
SESIONES = {"claude": ["coord", "rc"], "pensadero": ["maestro", "escritor"]}
VENTANA = {3000 + i: n for i, n in enumerate(SESIONES["pensadero"])}   # the pensadero's, by pid
PROGRAMADAS = []                     # session folders with scheduled tasks, per test
CODEX = {"codex": [(2001, "/home/codex/coord", "01a1-coord"), (2002, "/home/codex/aparejador", "01a1-apar")]}


def cargar():
    l = importlib.machinery.SourceFileLoader("flota_mod", FLOTA)
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader("flota_mod", l))
    l.exec_module(m)
    return m


class Reiniciar(unittest.TestCase):
    def setUp(self):
        self.flota = cargar()
        self.preguntas, self.consultados = [], []
        for p in [mock.patch.object(self.flota, "instalado", lambda: {"ai_users": USUARIOS}),
                  mock.patch.object(self.flota, "como", self.como),
                  mock.patch.object(self.flota, "usa_fleetcontext", lambda u: u != "pensadero"),
                  mock.patch.object(self.flota, "tmux", lambda u, *a: (0, "", "")),
                  mock.patch.object(self.flota, "si", self.si)]:
            p.start()
            self.addCleanup(p.stop)

    def como(self, u, *cmd):
        if cmd[0] == "sh" and "scheduled_tasks" in cmd[-1]:           # its scheduled tasks
            return 0, "\n".join(f"/x/.claude/scheduled_tasks.json" for c in [1]
                                if any(f"/{n}'" in cmd[-1] or f"/{n}/" in cmd[-1] for n in PROGRAMADAS)), ""
        claude_sh = cmd[0] == "sh" and cmd[-1] == self.flota.CLAUDE_SH
        self.consultados.append((u, "codex" if cmd[0] == "sh" and not claude_sh else "claude"))
        if claude_sh:                                         # the pensadero's, without fleetcontext
            return 0, "\n".join(f"C|{pid}|{'0' * 8}-0000-0000-0000-{pid:012d}|1|/home/{u}/{n}"
                                for pid, n in VENTANA.items()), ""
        if cmd[0] == "sh":                                    # CODEX_SH
            lineas = []
            for pid, cwd, tid in CODEX.get(u, []):
                lineas.append(f"S|{pid}|{cwd}|300")
            for pid, cwd, tid in CODEX.get(u, []):
                lineas.append("R|1|" + json.dumps({"type": "session_meta", "payload": {"id": tid, "cwd": cwd}}))
            return 0, "\n".join(lineas), ""
        return 0, json.dumps([{"session": n, "pid": 10 ** 6 + i, "tokens": 0, "idle_minutes": 30,
                               "watchers": 0, "uuid": None, "cwd": "/"}
                              for i, n in enumerate(SESIONES.get(u, []))]), ""

    def si(self, pregunta, defecto=False):
        self.preguntas.append(pregunta)
        return False                                  # never restart: only who is asked

    def test_every_claude_user_coord_first(self):
        with mock.patch.object(self.flota, "panel_de", lambda pid, p: ("%1", "x:" + VENTANA.get(pid, "1"))), \
                mock.patch.object(self.flota, "borrador", lambda u, p, prompt=None: None):
            self.flota.reiniciar([])
        self.assertEqual(self.consultados, [("claude", "claude"), ("codex", "codex"),
                                            ("pensadero", "claude"), ("pensadero", "codex")])
        self.assertEqual([q.split("¿Reinicio ")[1].rstrip("?") for q in self.preguntas],
                         ["coord", "rc", "1", "1", "maestro", "escritor"])   # codex's by window: x:1

    def test_one_user_named(self):
        with mock.patch.object(self.flota, "panel_de", lambda pid, p: ("%1", "x:" + VENTANA.get(pid, "1"))), \
                mock.patch.object(self.flota, "borrador", lambda u, p, prompt=None: None):
            self.flota.reiniciar(["pensadero"])
        self.assertEqual([u for u, _ in self.consultados], ["pensadero", "pensadero"])

    def test_a_session_by_name_in_any_fleet(self):
        with mock.patch.object(self.flota, "panel_de", lambda pid, p: ("%1", "x:" + VENTANA.get(pid, "1"))), \
                mock.patch.object(self.flota, "borrador", lambda u, p, prompt=None: None):
            self.flota.reiniciar(["escritor"])
        self.assertEqual(len(self.preguntas), 1)
        self.assertIn("escritor", self.preguntas[0])

    def test_an_unknown_session_says_so(self):
        with self.assertRaises(SystemExit) as fin:
            self.flota.reiniciar(["nadie"])
        self.assertIn("nadie", str(fin.exception.code))

    def test_a_codex_session_is_resumed_by_its_thread(self):
        enviados = []
        with mock.patch.object(self.flota, "panel_de", lambda pid, p: ("%9", f"flota:{'coord' if pid == 2001 else 'aparejador'}")), \
                mock.patch.object(self.flota, "borrador", lambda u, p, prompt=None: None), \
                mock.patch.object(self.flota, "tmux", lambda u, *a: enviados.append(a) or (0, "", "")), \
                mock.patch.object(self.flota, "si", lambda *a, **k: True), \
                mock.patch.object(self.flota.os.path, "exists", lambda p: False), \
                mock.patch.object(self.flota.time, "time", lambda: 1 + 30 * 60):
            self.flota.reiniciar_codex("codex", ["aparejador"], seguir=True, forzar=False)
        tecleado = [a[-1] for a in enviados if a[0] == "send-keys" and "-l" in a]
        self.assertEqual(tecleado[0], "/exit")
        self.assertIn("codex resume 01a1-apar", tecleado[1])

    def test_two_codex_sessions_in_one_folder_get_no_thread(self):
        CODEX["otro"] = [(3001, "/w", "t1"), (3002, "/w", "t2")]
        try:
            ses = self.flota.sesiones_codex("otro")
        finally:
            del CODEX["otro"]
        self.assertEqual([s["thread"] for s in ses], [None, None])


    def test_a_codex_session_is_found_by_its_name_even_beside_another(self):
        CODEX["otro"] = [(3001, "/w", "t1"), (3002, "/w", "t2")]
        indice = [{"id": "t1", "thread_name": "Revisa el campo de fuerzas", "updated_at": "1"},
                  {"id": "t2", "thread_name": "build", "updated_at": "1"},
                  {"id": "t1", "thread_name": "bench", "updated_at": "2"}]      # renamed: the last wins
        como = self.como
        def con_indice(u, *cmd):
            rc, out, err = como(u, *cmd)
            return rc, out + "".join("\nN|" + json.dumps(e) for e in indice), err
        paneles = {3001: ["%1", "flota:bench"], 3002: ["%2", "flota:build"]}
        try:
            with mock.patch.object(self.flota, "como", con_indice), \
                    mock.patch.object(self.flota, "ppid", lambda pid: 1):
                ses = self.flota.sesiones_codex("otro", paneles)
                sin_ventana = self.flota.sesiones_codex("otro")
        finally:
            del CODEX["otro"]
        self.assertEqual([s["thread"] for s in ses], ["t1", "t2"])
        self.assertEqual([s["thread"] for s in sin_ventana], [None, None])   # by folder: ambiguous


    def test_the_pensadero_is_asked_without_the_fleet_tools(self):
        with mock.patch.object(self.flota, "panel_de", lambda pid, p: ("%1", "x:" + VENTANA.get(pid, "1"))), \
                mock.patch.object(self.flota.time, "time", lambda: 1 + 30 * 60):
            ses = self.flota.sesiones_claude("pensadero")
        self.assertEqual([(x["session"], x["idle_minutes"]) for x in ses], [("maestro", 30), ("escritor", 30)])
        self.assertTrue(all(x["uuid"] for x in ses))

    def test_nothing_running_points_to_arrancar(self):
        import io, contextlib
        salida = io.StringIO()
        with mock.patch.object(self.flota, "tmux", lambda u, *a: (1, "", "no server running")), \
                contextlib.redirect_stdout(salida):
            self.flota.sin_sesiones("pensadero", "claude")
        self.assertIn("flota arrancar", salida.getvalue())


    def test_a_session_with_scheduled_tasks_is_left_unasked(self):
        PROGRAMADAS.append("maestro")
        try:
            with mock.patch.object(self.flota, "panel_de", lambda pid, p: ("%1", "x:" + VENTANA.get(pid, "1"))), \
                    mock.patch.object(self.flota, "borrador", lambda u, p, prompt=None: None):
                self.flota.reiniciar(["pensadero"])
        finally:
            PROGRAMADAS.clear()
        self.assertEqual([q.split("¿Reinicio ")[1].rstrip("?") for q in self.preguntas], ["escritor"])


if __name__ == "__main__":
    unittest.main()
