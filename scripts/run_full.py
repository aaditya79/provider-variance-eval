#!/usr/bin/env python3
"""FULL GSM8K run (plan §3; PREREGISTRATION §6, §16, §17).

Refuses to start unless the pilot has been confirmed (a PILOT_CONFIRMED.md exists at repo
root). Runs 300 items x 3 repeats x 10 primary providers (+ ':floor' as its own routing
condition) for Llama 3.3 70B, with the generation_error retry policy and the authoritative
read-back active. Resumable. Enforces the hard budget cap. Prints progress and the full
per-provider results table (clean accuracy + Wilson CI, generation_error rate, parse-path
distribution, cost).

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  python scripts/run_full.py --benchmark gsm8k
  python scripts/run_full.py --benchmark gsm8k --resume <run_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.config import git_sha, load_config, require_api_key, utc_now_iso  # noqa: E402
from pv.openrouter import BudgetExceeded, OpenRouterClient  # noqa: E402
from pv.snapshot import build_name_map, load_latest_snapshot  # noqa: E402
from pv import report as REPORT  # noqa: E402
from pv import runner as R  # noqa: E402

ITEMS_DIR = Path("data/items")
CONFIRM_FILE = Path("PILOT_CONFIRMED.md")


def _run_id(benchmark: str) -> str:
    ts = utc_now_iso().replace(":", "").replace("-", "")
    sha = git_sha(short=True) or "nogit"
    return f"full_{benchmark}_{ts}_{sha}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", default="gsm8k", choices=["gsm8k"])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--resume", help="existing full run_id to continue")
    args = ap.parse_args()

    # ---- UNLOCK GATE: full run blocked until the pilot is confirmed ----------------------
    if not CONFIRM_FILE.exists():
        print(f"BLOCKED: {CONFIRM_FILE} not found. The full run requires a confirmed pilot.\n"
              "Review a pilot's per-provider accuracy + projected cost, then create "
              f"{CONFIRM_FILE} to unlock.", file=sys.stderr)
        return 4

    cfg = load_config(args.config)
    bcfg = cfg["benchmarks"][args.benchmark]
    if not bcfg.get("enabled", True):
        print(f"{args.benchmark} is disabled in config.", file=sys.stderr)
        return 2

    # Pilot was Llama-only; the full GSM8K run here uses the pilot model's primary set.
    model = next(m for m in cfg["models"] if m["key"] == cfg["pilot"]["model"])
    frozen_path = ITEMS_DIR / f"{args.benchmark}.json"
    if not frozen_path.exists():
        print(f"Frozen items missing: {frozen_path}\n"
              f"Run: python scripts/freeze_items.py --benchmark {args.benchmark}", file=sys.stderr)
        return 2
    frozen = json.loads(frozen_path.read_text())
    items = frozen["items"]  # ALL frozen items (paired design)

    provider_labels = list(model["providers"])
    if cfg.get("include_floor"):
        provider_labels.append(":floor")

    try:
        api_key = require_api_key()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2

    snap = load_latest_snapshot("start")
    name_map = build_name_map(snap) if snap else {}
    if not name_map:
        print("WARNING: no provider snapshot found; read-back falls back to slug base-key.",
              file=sys.stderr)

    run_id = args.resume or _run_id(args.benchmark)
    run_dir = R.make_run_dir(cfg["run"]["runs_dir"], run_id, cfg, args.config)

    plan = R.RunPlan(
        run_id=run_id, run_dir=run_dir, benchmark=args.benchmark,
        model_key=model["key"], model_slug=model["slug"],
        provider_labels=provider_labels, items=items,
        repeats=cfg["repeats"], max_tokens=bcfg["max_tokens"], is_pilot=False,
    )
    R.attach_frozen(plan, frozen)

    total_cells = len(provider_labels) * len(items) * cfg["repeats"]
    print(f"FULL run_id={run_id}")
    print(f"  model={model['slug']}")
    print(f"  routes ({len(provider_labels)}): {provider_labels}")
    print(f"  items={len(items)}  repeats={cfg['repeats']}  -> {total_cells} cells")
    print(f"  max_tokens={plan.max_tokens}  budget cap=${cfg['budget']['cap_usd']:.2f}")
    print(f"  run_dir={run_dir}\n")

    with OpenRouterClient(
        api_key,
        timeout_s=cfg["run"]["request_timeout_s"],
        max_attempts=cfg["retry"]["max_attempts"],
        backoff_base_s=cfg["retry"]["backoff_base_s"],
        backoff_cap_s=cfg["retry"]["backoff_cap_s"],
        retry_on_status=tuple(cfg["retry"]["retry_on_status"]),
    ) as client:
        try:
            res = R.run(
                plan, client,
                cap_usd=cfg["budget"]["cap_usd"],
                temperature=cfg["decoding"]["temperature"],
                top_p=cfg["decoding"]["top_p"],
                send_seed=cfg["decoding"]["send_seed"],
                seed=cfg["run"]["seed"],
                name_map=name_map,
            )
        except BudgetExceeded as e:
            print(f"\nBUDGET ABORT: {e}", file=sys.stderr)
            print("Partial results are saved and resumable with --resume "
                  f"{run_id}", file=sys.stderr)
            return 3

    REPORT.print_table(
        res["jsonl"],
        title=f"FULL GSM8K RESULTS — {model['slug']} — {len(items)} items x "
              f"{cfg['repeats']} repeats  (run {run_id})",
    )
    print(f"\nTotal spend: ${res['cost_usd']:.4f}  |  invalid cells: {res['invalid']}")
    print(f"Raw JSONL: {res['jsonl']}")
    print("\nFull GSM8K done. STOP — review before MMLU/HumanEval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
