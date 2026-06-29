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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", required=True, choices=["gsm8k"])  # mmlu/humaneval later
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
    else:
        raise NotImplementedError(args.benchmark)

    with open(out, "w") as f:
        json.dump(frozen, f, indent=2)
    print(f"Froze {frozen['n_items']} {args.benchmark} items -> {out}")
    print(f"  seed={seed}  source={frozen['source']}/{frozen['split']} "
          f"(of {frozen['source_size']})  exemplars={len(frozen['exemplars'])}")
    print(f"  first item id={frozen['items'][0]['id']} gold={frozen['items'][0]['gold']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
