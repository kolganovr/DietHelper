"""Тесты метрик eval на синтетике, без сети. Запуск: python manage.py test eval"""
from unittest import TestCase

from eval.metrics import INVALID, percentile, stability, summarize

OK, NO, CAU = "Можно", "Нельзя", "С осторожностью"


def rec(case_id, expected, predicted, repeat=0, latency=1.0):
    return {"id": case_id, "expected": expected, "predicted": predicted, "repeat": repeat, "latency": latency}


class SummarizeTests(TestCase):
    def setUp(self):
        self.records = [
            rec("a", OK, OK),
            rec("b", NO, NO),
            rec("c", NO, OK),        # опасная ошибка
            rec("d", CAU, CAU),
            rec("e", CAU, NO),
            rec("f", OK, None),      # ответ не прошёл схему
        ]

    def test_accuracy_and_schema(self):
        s = summarize(self.records)
        self.assertEqual(s["n"], 6)
        self.assertAlmostEqual(s["accuracy"], 3 / 6)
        self.assertAlmostEqual(s["schema_ok"], 5 / 6)

    def test_dangerous_rate(self):
        s = summarize(self.records)
        self.assertEqual(s["must_not_n"], 2)
        self.assertEqual(s["dangerous_n"], 1)
        self.assertEqual(s["dangerous_ids"], ["c"])
        self.assertAlmostEqual(s["dangerous_rate"], 0.5)

    def test_per_class_and_macro_f1(self):
        s = summarize(self.records)
        ok = s["per_class"][OK]
        # предсказано "Можно": a (верно), c (неверно); истинных "Можно": a, f
        self.assertAlmostEqual(ok["precision"], 0.5)
        self.assertAlmostEqual(ok["recall"], 0.5)
        no = s["per_class"][NO]
        # предсказано "Нельзя": b, e; истинных: b, c
        self.assertAlmostEqual(no["precision"], 0.5)
        self.assertAlmostEqual(no["recall"], 0.5)
        cau = s["per_class"][CAU]
        self.assertAlmostEqual(cau["precision"], 1.0)
        self.assertAlmostEqual(cau["recall"], 0.5)
        self.assertAlmostEqual(cau["f1"], 2 / 3)
        self.assertAlmostEqual(s["macro_f1"], (0.5 + 0.5 + 2 / 3) / 3)

    def test_confusion(self):
        m = summarize(self.records)["confusion"]
        self.assertEqual(m[NO][OK], 1)
        self.assertEqual(m[CAU][NO], 1)
        self.assertEqual(m[OK][INVALID], 1)
        self.assertEqual(sum(sum(row.values()) for row in m.values()), 6)

    def test_accuracy_uses_first_repeat_only(self):
        records = [rec("a", OK, OK, 0), rec("a", OK, NO, 1), rec("a", OK, NO, 2)]
        s = summarize(records)
        self.assertEqual(s["n"], 1)
        self.assertAlmostEqual(s["accuracy"], 1.0)

    def test_perfect(self):
        s = summarize([rec("a", OK, OK), rec("b", NO, NO), rec("c", CAU, CAU)])
        self.assertAlmostEqual(s["accuracy"], 1.0)
        self.assertAlmostEqual(s["macro_f1"], 1.0)
        self.assertAlmostEqual(s["dangerous_rate"], 0.0)


class StabilityTests(TestCase):
    def test_stability(self):
        records = [
            rec("a", OK, OK, 0), rec("a", OK, OK, 1), rec("a", OK, OK, 2),
            rec("b", NO, NO, 0), rec("b", NO, CAU, 1), rec("b", NO, NO, 2),
            rec("c", CAU, CAU, 0),  # один повтор, не учитывается
        ]
        value, n = stability(records)
        self.assertEqual(n, 2)
        self.assertAlmostEqual(value, 0.5)

    def test_invalid_counts_as_different(self):
        value, _ = stability([rec("a", OK, OK, 0), rec("a", OK, None, 1)])
        self.assertAlmostEqual(value, 0.0)

    def test_no_repeats(self):
        self.assertEqual(stability([rec("a", OK, OK)]), (None, 0))


class PercentileTests(TestCase):
    def test_percentile(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertAlmostEqual(percentile(values, 0.5), 5.5)
        self.assertAlmostEqual(percentile(values, 0.95), 9.55)

    def test_skips_none_and_empty(self):
        self.assertAlmostEqual(percentile([None, 2.0, None], 0.5), 2.0)
        self.assertIsNone(percentile([None], 0.5))
