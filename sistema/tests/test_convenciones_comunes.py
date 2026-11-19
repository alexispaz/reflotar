"""Rules that hold for every fleet are written three times, once per conventions file
(claude, codex, the pensadero's in Spanish): nothing shares the text. Each such rule
carries a marker, `<!-- comun: <name> -->`, and a marker in one file must be in all
three, so a rule added to one fleet and forgotten in another fails here.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sistema/tests
"""
import os
import re
import unittest

REGLAS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                      "reglas")
ARCHIVOS = ["conventions.md", "conventions-codex.md", "conventions-pensadero.md"]
MARCA = re.compile(r"<!-- comun: ([a-z0-9-]+) -->")


def marcas(nombre):
    with open(os.path.join(REGLAS, nombre)) as f:
        return MARCA.findall(f.read())


class Comunes(unittest.TestCase):
    def test_every_shared_rule_is_in_every_fleet(self):
        todas = {n: marcas(n) for n in ARCHIVOS}
        union = set().union(*map(set, todas.values()))
        self.assertTrue(union, "no shared-rule markers at all")
        for n, ms in todas.items():
            self.assertEqual(sorted(set(union) - set(ms)), [], f"{n} lacks these shared rules")

    def test_each_marker_once_per_file(self):
        for n in ARCHIVOS:
            ms = marcas(n)
            self.assertEqual(len(ms), len(set(ms)), f"{n} repeats a marker")


if __name__ == "__main__":
    unittest.main()
