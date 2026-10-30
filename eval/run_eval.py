"""Прогон eval вердиктов Gemini через прод-код (diet.gemini.get_verdict).

Примеры (из корня репозитория):
    python -X utf8 -m eval.run_eval --dry-run
    python -X utf8 -m eval.run_eval --models gemini-3.1-flash-lite --prompts v1
    python -X utf8 -m eval.run_eval --subset eval/subset30.txt --repeats 3
    python -X utf8 -m eval.run_eval --subset eval/subset30.txt --models gemini-2.5-flash --prompts v1,v2

Ответы кэшируются в eval/.cache/<модель>/<хэш промпта>/<id>_<повтор>.json, повторный
запуск без запросов. Ключ: GEMINI_API_KEY из окружения или из --env-file / .env.
Сводка пишется в eval/results/<модель>__<промпт>__<набор>.json."""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diet.gemini import MODEL, GeminiError, get_verdict  # noqa: E402
from eval.metrics import summarize  # noqa: E402
from eval.prompts import PROMPTS  # noqa: E402

EVAL_DIR = ROOT / "eval"
CACHE_DIR = EVAL_DIR / ".cache"
RESULTS_DIR = EVAL_DIR / "results"
REQUEST_LOG = CACHE_DIR / "requests.log"

QUOTA_WAIT = 60          # пауза после 429, секунд
MAX_QUOTA_IN_ROW = 3     # после стольких 429 подряд прогон модели прекращается
MAX_RETRIES = 3          # повторы при временных сбоях (сеть, 5xx)


def load_cases(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_subset(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        return [line.split("#")[0].strip() for line in f if line.split("#")[0].strip()]


def prompt_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def cache_path(model, prompt_text, case_id, repeat):
    return CACHE_DIR / model / prompt_hash(prompt_text) / f"{case_id}_{repeat}.json"


def read_cache(path, case):
    """Запись из кэша, если она есть и сделана для тех же диеты и блюда."""
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("diet") != case["diet"] or data.get("product") != case["product"]:
        return None
    return data


def api_key(env_file):
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    from dotenv import dotenv_values
    for candidate in filter(None, [env_file, ROOT / ".env"]):
        key = dotenv_values(candidate).get("GEMINI_API_KEY")
        if key:
            return key
    sys.exit("GEMINI_API_KEY не найден: задайте переменную окружения или --env-file")


class Limiter:
    """Не чаще одного запроса в interval секунд (бесплатная квота считает RPM)."""

    def __init__(self, interval):
        self.interval = interval
        self.last = 0.0

    def wait(self):
        delay = self.last + self.interval - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.last = time.monotonic()


def log_request(model, case_id, outcome):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(REQUEST_LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()}\t{model}\t{case_id}\t{outcome}\n")


def ask(case, model, prompt_text, key, limiter):
    """Один кейс с повторами. Вернуть запись для кэша, None если сдались (не кэшируем),
    или "quota", если квота кончилась."""
    quota_in_row, retries = 0, 0
    while True:
        limiter.wait()
        started = time.monotonic()
        try:
            answer = get_verdict(case["product"], case["diet"], key, model=model, system_instruction=prompt_text)
        except GeminiError as e:
            latency = time.monotonic() - started
            log_request(model, case["id"], e.kind)
            if e.kind == "quota":
                quota_in_row += 1
                if quota_in_row >= MAX_QUOTA_IN_ROW:
                    return "quota"
                print(f"  429, жду {QUOTA_WAIT} с ({quota_in_row}/{MAX_QUOTA_IN_ROW})", flush=True)
                time.sleep(QUOTA_WAIT)
                continue
            if e.title.startswith("Не удалось разобрать"):
                # ответ пришёл, но не прошёл схему или вердикт не распознан: это результат модели
                return {"predicted": None, "error": e.message, "latency": latency}
            if e.kind == "key":
                sys.exit(f"Ключ отклонён: {e.message}")
            retries += 1
            if retries >= MAX_RETRIES:
                print(f"  {case['id']}: сбой {e.kind} {MAX_RETRIES} раза, пропускаю", flush=True)
                return None
            time.sleep(10 * retries)
            continue
        latency = time.monotonic() - started
        log_request(model, case["id"], "ok")
        return {"predicted": answer["verdict"], "answer": answer, "latency": latency}


def run(models, prompts, cases, repeats, key, interval, budget):
    """Прогнать все сочетания, вернуть {(model, prompt): [records]} и число запросов к API."""
    limiter = Limiter(interval)
    made = 0
    results = {}
    for model in models:
        for prompt_name in prompts:
            prompt_text = PROMPTS[prompt_name]
            records, stopped = [], False
            for repeat in range(repeats):
                for case in cases:
                    path = cache_path(model, prompt_text, case["id"], repeat)
                    data = read_cache(path, case)
                    if data is None and not stopped:
                        if budget is not None and made >= budget:
                            print(f"Бюджет {budget} запросов исчерпан, остальное не прогоняю", flush=True)
                            stopped = True
                        else:
                            outcome = ask(case, model, prompt_text, key, limiter)
                            made += 1
                            if outcome == "quota":
                                print(f"{model}: {MAX_QUOTA_IN_ROW} раза 429 подряд, прогон модели прекращён", flush=True)
                                stopped = True
                            elif outcome is not None:
                                data = {"id": case["id"], "diet": case["diet"], "product": case["product"],
                                        "model": model, "prompt": prompt_name, "repeat": repeat, **outcome}
                                path.parent.mkdir(parents=True, exist_ok=True)
                                path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                                print(f"  {model} {prompt_name} r{repeat} {case['id']}: "
                                      f"{data['predicted']} (ожид. {case['expected']})", flush=True)
                    if data is not None:
                        records.append({"id": case["id"], "expected": case["expected"], "predicted": data["predicted"],
                                        "repeat": repeat, "latency": data.get("latency"),
                                        "disputed": case["disputed"]})
            results[(model, prompt_name)] = records
    return results, made


def fmt(x, pct=True):
    if x is None:
        return "-"
    return f"{x * 100:.1f}%" if pct else f"{x:.2f}"


def print_summary(name, s):
    print(f"\n== {name}: n={s['n']}")
    print(f"accuracy {fmt(s['accuracy'])}, macro-F1 {fmt(s['macro_f1'], False)}, "
          f"опасные {s['dangerous_n']}/{s['must_not_n']} ({fmt(s['dangerous_rate'])}) {s['dangerous_ids']}, "
          f"схема {fmt(s['schema_ok'])}, стабильность {fmt(s['stability'])} на {s['stability_n']}, "
          f"латентность p50 {fmt(s['latency_p50'], False)} с, p95 {fmt(s['latency_p95'], False)} с")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cases", default=str(EVAL_DIR / "cases.jsonl"))
    p.add_argument("--models", default=MODEL, help="через запятую")
    p.add_argument("--prompts", default="v1", help=f"через запятую из {sorted(PROMPTS)}")
    p.add_argument("--subset", help="файл со списком id (по одному в строке)")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--interval", type=float, default=4.5, help="секунд между запросами")
    p.add_argument("--budget", type=int, help="не больше стольких запросов за запуск")
    p.add_argument("--env-file", help="файл .env с GEMINI_API_KEY")
    p.add_argument("--dry-run", action="store_true", help="только посчитать, сколько запросов нужно")
    args = p.parse_args(argv)

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    prompts = [x.strip() for x in args.prompts.split(",") if x.strip()]
    unknown = set(prompts) - set(PROMPTS)
    if unknown:
        sys.exit(f"Неизвестные версии промпта: {sorted(unknown)}")
    cases = load_cases(args.cases)
    subset = load_subset(args.subset)
    if subset is not None:
        by_id = {c["id"]: c for c in cases}
        missing = [i for i in subset if i not in by_id]
        if missing:
            sys.exit(f"В наборе нет id: {missing}")
        cases = [by_id[i] for i in subset]
    set_name = Path(args.subset).stem if args.subset else "full"

    need = 0
    for model in models:
        for prompt_name in prompts:
            for repeat in range(args.repeats):
                need += sum(1 for c in cases
                            if read_cache(cache_path(model, PROMPTS[prompt_name], c["id"], repeat), c) is None)
    print(f"Кейсов {len(cases)}, моделей {len(models)}, промптов {len(prompts)}, повторов {args.repeats}: "
          f"нужно запросов к API {need} (остальное в кэше)")
    if args.dry_run:
        return 0

    key = api_key(args.env_file) if need else None
    results, made = run(models, prompts, cases, args.repeats, key, args.interval, args.budget)
    print(f"\nЗапросов к API за запуск: {made}")

    RESULTS_DIR.mkdir(exist_ok=True)
    for (model, prompt_name), records in results.items():
        if not records:
            continue
        summary = {
            "model": model, "prompt": prompt_name, "set": set_name, "repeats": args.repeats,
            "all": summarize(records),
            "no_disputed": summarize([r for r in records if not r["disputed"]]),
            "records": records,
        }
        print_summary(f"{model} {prompt_name} {set_name}", summary["all"])
        print_summary(f"{model} {prompt_name} {set_name} без disputed", summary["no_disputed"])
        out = RESULTS_DIR / f"{model}__{prompt_name}__{set_name}_r{args.repeats}.json"
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
