import unittest

from core.risk import (LEVELS, LEVEL_LABELS, OPENCODE_LEVELS, worst,
                       parse_verdict, summary_of)


class RiskTests(unittest.TestCase):
    def test_worst_picks_higher(self):
        self.assertEqual(worst("LOW", "HIGH"), "HIGH")
        self.assertEqual(worst("MEDIUM", "LOW"), "MEDIUM")
        self.assertEqual(worst("LOW", "LOW"), "LOW")

    def test_parse_verdict_level(self):
        text = "CLASSIFICACAO: PERIGOSO\nRECOMENDACAO: NAO RECOMENDADO"
        level, rec = parse_verdict(text)
        self.assertEqual(level, "HIGH")
        self.assertEqual(rec, "NAO RECOMENDADO")

    def test_parse_verdict_secure(self):
        text = "Classificação: SEGURO\nRecomendação: PARECER SEGURO"
        level, rec = parse_verdict(text)
        self.assertEqual(level, "LOW")
        self.assertEqual(rec, "PARECER SEGURO")

    def test_parse_verdict_empty(self):
        self.assertEqual(parse_verdict(""), (None, None))
        self.assertEqual(parse_verdict(None), (None, None))

    def test_summary_of(self):
        report = {"reasons": ["a", "b"], "blocked_ext": ["x.exe"]}
        s = summary_of(report)
        self.assertIn("- a", s)
        self.assertIn("x.exe", s)

    def test_summary_of_empty(self):
        self.assertEqual(summary_of(None), "")
        self.assertEqual(summary_of({}), "")

    def test_levels_tuple(self):
        self.assertEqual(LEVELS, ("LOW", "MEDIUM", "HIGH"))


if __name__ == "__main__":
    unittest.main()
