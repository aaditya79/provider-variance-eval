#!/usr/bin/env python3
"""Freeze benchmark item sets to disk ONCE (paired design; PREREGISTRATION §5, §10.1).

Downloads the benchmark, samples the frozen count with the frozen seed, embeds the frozen
prompt exemplars, and writes data/items/<benchmark>.json. Refuses to overwrite an existing
frozen file unless --force (you should not re-sample once frozen).

Usage:
  python scripts/freeze_items.py --benchmark gsm8k
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.benchmarks import gsm8k as gsm8k_mod  # noqa: E402
from pv.benchmarks import mmlu as mmlu_mod  # noqa: E402
from pv.config import load_config, utc_now_iso  # noqa: E402

ITEMS_DIR = Path("data/items")


def freeze_gsm8k(seed: int, n_items: int) -> dict:
    from datasets import load_dataset

    ds = load_dataset("openai/gsm8k", "main", split="test")
    n = len(ds)
    idx = sorted(random.Random(seed).sample(range(n), n_items))
    items = []
    for rank, i in enumerate(idx):
        row = ds[i]
        items.append(
            {
                "id": f"gsm8k-{rank:04d}",
                "dataset_index": i,
                "question": row["question"],
                "gold_raw": row["answer"],
                "gold": gsm8k_mod.gold_answer(row["answer"]),
            }
        )
    return {
        "benchmark": "gsm8k",
        "source": "openai/gsm8k",
        "config": "main",
        "split": "test",
        "source_size": n,
        "seed": seed,
        "n_items": n_items,
        "sampling": "uniform",
        "prompt": "8shot_cot",
        "frozen_utc": utc_now_iso(),
        "exemplars": gsm8k_mod.GSM8K_8SHOT_EXEMPLARS,
        "items": items,
    }


def freeze_mmlu(seed: int, n_items: int) -> dict:
    """Stratified across all 57 subjects (~5-6 each). 5-shot exemplars = each subject's dev rows."""
    from datasets import load_dataset

    test = load_dataset("cais/mmlu", "all", split="test")
    dev = load_dataset("cais/mmlu", "all", split="dev")
    subjects = sorted(set(test["subject"]))
    # distribute n_items across subjects: base each, first `rem` subjects get +1 (deterministic)
    base, rem = divmod(n_items, len(subjects))
    per_subject = {s: base + (1 if i < rem else 0) for i, s in enumerate(subjects)}

    by_subj_test: dict[str, list[int]] = {s: [] for s in subjects}
    for i, s in enumerate(test["subject"]):
        by_subj_test[s].append(i)
    rng = random.Random(seed)
    items = []
    counts = {}
    rank = 0
    for s in subjects:
        k = min(per_subject[s], len(by_subj_test[s]))
        chosen = sorted(rng.sample(by_subj_test[s], k))
        counts[s] = k
        for i in chosen:
            row = test[i]
            items.append({
                "id": f"mmlu-{rank:04d}", "dataset_index": i, "subject": row["subject"],
                "question": row["question"], "choices": row["choices"],
                "answer": row["answer"], "gold": mmlu_mod.gold_letter(row["answer"]),
            })
            rank += 1

    dev_exemplars: dict[str, list[dict]] = {s: [] for s in subjects}
    for i, s in enumerate(dev["subject"]):
        r = dev[i]
        dev_exemplars[s].append({"question": r["question"], "choices": r["choices"],
                                 "answer": r["answer"]})

    return {
        "benchmark": "mmlu", "source": "cais/mmlu", "config": "all", "split": "test",
        "seed": seed, "n_items": len(items), "sampling": "stratified_by_subject",
        "prompt": "5shot", "frozen_utc": utc_now_iso(),
        "n_subjects": len(subjects), "per_subject_counts": counts,
        "dev_exemplars": dev_exemplars, "items": items,
    }


HUMANEVAL_URL = "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz"


def freeze_humaneval(seed: int, n_items: int) -> dict:
    """All 164 HumanEval problems (no sampling). Fetched from the official source jsonl.gz
    (the modern datasets lib rejects the legacy single-name HF id)."""
    import gzip
    import urllib.request

    with urllib.request.urlopen(HUMANEVAL_URL) as resp:
        raw = gzip.decompress(resp.read()).decode("utf-8")
    items = []
    for i, line in enumerate(l for l in raw.splitlines() if l.strip()):
        row = json.loads(line)
        items.append({
            "id": row["task_id"], "dataset_index": i, "prompt": row["prompt"],
            "canonical_solution": row["canonical_solution"], "test": row["test"],
            "entry_point": row["entry_point"],
        })
    return {
        "benchmark": "humaneval", "source": HUMANEVAL_URL, "split": "test",
        "seed": seed, "n_items": len(items), "sampling": "all",
        "prompt": "raw_completion", "frozen_utc": utc_now_iso(), "items": items,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", required=True, choices=["gsm8k", "mmlu", "humaneval"])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--force", action="store_true", help="overwrite an existing frozen file")
    args = ap.parse_args()

    cfg = load_config(args.config)
    seed = cfg["run"]["seed"]
    n_items = cfg["benchmarks"][args.benchmark]["n_items"]

    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    out = ITEMS_DIR / f"{args.benchmark}.json"
    if out.exists() and not args.force:
        print(f"REFUSING to overwrite frozen item set {out} (use --force to re-sample).")
        print("Frozen item sets must not change once data collection has begun.")
        return 1

    if args.benchmark == "gsm8k":
        frozen = freeze_gsm8k(seed, n_items)
    elif args.benchmark == "mmlu":
        frozen = freeze_mmlu(seed, n_items)
    elif args.benchmark == "humaneval":
        frozen = freeze_humaneval(seed, n_items)
    else:
        raise NotImplementedError(args.benchmark)

    with open(out, "w") as f:
        json.dump(frozen, f, indent=2)
    print(f"Froze {frozen['n_items']} {args.benchmark} items -> {out}")
    print(f"  seed={seed}  source={frozen['source']}/{frozen['split']}  sampling={frozen['sampling']}")
    if args.benchmark == "mmlu":
        print(f"  subjects={frozen['n_subjects']}  per-subject range="
              f"{min(frozen['per_subject_counts'].values())}-{max(frozen['per_subject_counts'].values())}")
    print(f"  first item id={frozen['items'][0]['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
