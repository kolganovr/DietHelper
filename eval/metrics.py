"""Метрики eval вердиктов. Без сети и Django, тесты в eval/tests.py.

Запись результата: dict с ключами id, expected, predicted (None, если ответ не прошёл
схему или вердикт не распознан), repeat (номер повтора), latency (секунды, может быть None)."""
from collections import defaultdict

LABELS = ("Можно", "Нельзя", "С осторожностью")
INVALID = "невалидный"


def _first_repeat(records):
    """Одна запись на кейс: повтор 0 (или минимальный), чтобы повторы не раздували точность."""
    best = {}
    for r in records:
        if r["id"] not in best or r.get("repeat", 0) < best[r["id"]].get("repeat", 0):
            best[r["id"]] = r
    return list(best.values())


def confusion(records):
    """matrix[expected][predicted], predicted включает INVALID."""
    matrix = {e: {p: 0 for p in LABELS + (INVALID,)} for e in LABELS}
    for r in records:
        matrix[r["expected"]][r["predicted"] or INVALID] += 1
    return matrix


def per_class(records):
    out = {}
    for label in LABELS:
        tp = sum(1 for r in records if r["expected"] == label and r["predicted"] == label)
        pred = sum(1 for r in records if r["predicted"] == label)
        true = sum(1 for r in records if r["expected"] == label)
        precision = tp / pred if pred else 0.0
        recall = tp / true if true else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        out[label] = {"precision": precision, "recall": recall, "f1": f1, "support": true}
    return out


def percentile(values, q):
    """Перцентиль с линейной интерполяцией (как numpy по умолчанию)."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    pos = (len(values) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def stability(records):
    """Доля кейсов, где все повторы дали один и тот же вердикт (только кейсы с 2+ повторами)."""
    by_case = defaultdict(list)
    for r in records:
        by_case[r["id"]].append(r["predicted"])
    multi = [v for v in by_case.values() if len(v) >= 2]
    if not multi:
        return None, 0
    same = sum(1 for v in multi if len(set(v)) == 1)
    return same / len(multi), len(multi)


def summarize(records):
    """Сводка по всем метрикам. Точность и F1 считаются по первому повтору каждого кейса,
    стабильность и латентность по всем записям."""
    first = _first_repeat(records)
    n = len(first)
    classes = per_class(first)
    must_not = [r for r in first if r["expected"] == "Нельзя"]
    dangerous = [r for r in must_not if r["predicted"] == "Можно"]
    stab, stab_n = stability(records)
    latencies = [r.get("latency") for r in records]
    return {
        "n": n,
        "accuracy": sum(1 for r in first if r["predicted"] == r["expected"]) / n if n else 0.0,
        "macro_f1": sum(c["f1"] for c in classes.values()) / len(LABELS),
        "per_class": classes,
        "confusion": confusion(first),
        "dangerous_rate": len(dangerous) / len(must_not) if must_not else 0.0,
        "dangerous_n": len(dangerous),
        "dangerous_ids": sorted(r["id"] for r in dangerous),
        "must_not_n": len(must_not),
        "schema_ok": sum(1 for r in first if r["predicted"] is not None) / n if n else 0.0,
        "stability": stab,
        "stability_n": stab_n,
        "latency_p50": percentile(latencies, 0.5),
        "latency_p95": percentile(latencies, 0.95),
    }
