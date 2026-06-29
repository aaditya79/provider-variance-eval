#!/usr/bin/env python3
"""PILOT runner (plan §6; PREREGISTRATION §8, §10.8).

Runs the pilot slice for ONE model on the PRIMARY canonical provider set:
  50 GSM8K items, 1 repeat, all primary providers + ':floor', frozen 8-shot CoT, locked parser.
Then prints per-provider accuracy + projected full-run cost and STOPS. Does NOT run the full
study. Writes a pilot summary and a confirmation stub the full runner will later require.

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  python scripts/freeze_items.py --benchmark gsm8k      # once
  python scripts/run_pilot.py                            # the pilot
  python scripts/run_pilot.py --resume <run_id>          # continue an interrupted pilot
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.config import git_sha, load_config, require_api_key, utc_now_iso  # noqa: E402
from pv.openrouter import BudgetExceeded, OpenRouterClient  # noqa: E402
from pv.snapshot import build_name_map, load_latest_snapshot  # noqa: E402
from pv import runner as R  # noqa: E402

ITEMS_DIR = Path("data/items")


def _run_id(cfg: dict) -> str:
    ts = utc_now_iso().replace(":", "").replace("-", "")
    sha = git_sha(short=True) or "nogit"
    return f"pilot_{ts}_{sha}"


def _summarize(jsonl: Path, full_items: int, full_repeats: int) -> None:
    """Per-provider accuracy (valid calls only) + full-run GSM8K cost projection."""
    by_prov = defaultdict(lambda: {"n": 0, "valid": 0, "correct": 0, "cost": 0.0,
                                    "ptok": 0, "ctok": 0, "invalid_reasons": defaultdict(int),
                                    "parse_paths": defaultdict(int)})
    pilot_items = set()
    for line in open(jsonl):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        p = by_prov[r["provider_label"]]
        p["n"] += 1
        pilot_items.add(r["item_id"])
        if r.get("cost_usd"):
            p["cost"] += float(r["cost_usd"])
        if r["valid"]:
            p["valid"] += 1
            if r.get("correct"):
                p["correct"] += 1
            if r.get("prompt_tokens"):
                p["ptok"] += r["prompt_tokens"]
            if r.get("completion_tokens"):
                p["ctok"] += r["completion_tokens"]
            if r.get("parse"):
                p["parse_paths"][r["parse"]["path"]] += 1
        else:
            p["invalid_reasons"][r.get("invalid_reason") or "?"] += 1

    n_pilot_items = len(pilot_items)
    print("\n" + "=" * 78)
    print(f"PILOT SUMMARY — GSM8K, {n_pilot_items} items x 1 repeat")
    print("=" * 78)
    hdr = (f"{'provider':<24}{'acc':>8}{'n_ok/n':>10}{'gen_err':>9}{'mismatch':>9}"
           f"{'$pilot':>10}{'$/call':>10}{'avg_ctok':>9}")
    print(hdr)
    print("  (acc = correct/valid, excludes gen_err + mismatch from num AND denom)")
    print("-" * len(hdr))

    grand_pilot_cost = 0.0
    grand_full_cost = 0.0
    for prov in sorted(by_prov):
        p = by_prov[prov]
        acc = (p["correct"] / p["valid"]) if p["valid"] else float("nan")
        per_call = (p["cost"] / p["n"]) if p["n"] else 0.0
        avg_ctok = (p["ctok"] / p["valid"]) if p["valid"] else 0.0
        # Full GSM8K projection for this provider: avg $/call * full_items * full_repeats.
        full_cost = per_call * full_items * full_repeats
        grand_pilot_cost += p["cost"]
        grand_full_cost += full_cost
        acc_s = f"{acc*100:.1f}%" if p["valid"] else "n/a"
        ratio = f"{p['correct']}/{p['valid']}"
        n_err = p["invalid_reasons"].get("generation_error", 0)
        n_mis = p["invalid_reasons"].get("provider_readback_mismatch", 0)
        err_s = f"{n_err}/{p['n']}"
        mis_s = f"{n_mis}/{p['n']}"
        print(f"{prov:<24}{acc_s:>8}{ratio:>10}{err_s:>9}{mis_s:>9}"
              f"{p['cost']:>10.4f}{per_call:>10.5f}{avg_ctok:>9.0f}")
        if p["parse_paths"]:
            print(f"    parse paths: {dict(p['parse_paths'])}")

    print("-" * len(hdr))
    print(f"{'TOTAL (pilot)':<24}{'':>8}{'':>10}{grand_pilot_cost:>10.4f}")
    print("\nPROJECTED FULL-RUN COST")
    print(f"  GSM8K full ({full_items} items x {full_repeats} repeats, this model, "
          f"{len(by_prov)} provider-routes): ${grand_full_cost:.2f}")
    print(f"  Rough all-3-benchmarks, 2-models estimate (very approximate; HumanEval emits")
    print(f"  many more tokens, MMLU far fewer) ~ GSM8K_full x 2 models x ~2.0 benchmark factor")
    print(f"     ≈ ${grand_full_cost * 2 * 2.0:.2f}  (refine after MMLU/HumanEval pilots)")
    print("=" * 78)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--resume", help="existing pilot run_id to continue")
    args = ap.parse_args()

    cfg = load_config(args.config)
    pcfg = cfg["pilot"]
    model = next(m for m in cfg["models"] if m["key"] == pcfg["model"])
    benchmark = pcfg["benchmark"]
    if benchmark != "gsm8k":
        print("Only the gsm8k pilot is wired up so far.", file=sys.stderr)
        return 2

    frozen_path = ITEMS_DIR / f"{benchmark}.json"
    if not frozen_path.exists():
        print(f"Frozen items missing: {frozen_path}\n"
              f"Run: python scripts/freeze_items.py --benchmark {benchmark}", file=sys.stderr)
        return 2
    frozen = json.loads(frozen_path.read_text())
    pilot_items = frozen["items"][: pcfg["n_items"]]  # first N of the frozen set (subset, paired)

    provider_labels = list(model["providers"])
    if pcfg.get("include_floor"):
        provider_labels.append(":floor")

    try:
        api_key = require_api_key()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2

    # Authoritative slug -> disclosed provider_name map for the read-back match.
    snap = load_latest_snapshot("start")
    name_map = build_name_map(snap) if snap else {}
    if not name_map:
        print("WARNING: no provider snapshot found; read-back falls back to slug base-key.",
              file=sys.stderr)

    run_id = args.resume or _run_id(cfg)
    run_dir = R.make_run_dir(cfg["run"]["runs_dir"], run_id, cfg, args.config)

    plan = R.RunPlan(
        run_id=run_id, run_dir=run_dir, benchmark=benchmark,
        model_key=model["key"], model_slug=model["slug"],
        provider_labels=provider_labels, items=pilot_items,
        repeats=pcfg["repeats"], max_tokens=cfg["benchmarks"][benchmark]["max_tokens"],
        is_pilot=True,
    )
    R.attach_frozen(plan, frozen)

    print(f"PILOT run_id={run_id}")
    print(f"  model={model['slug']}")
    print(f"  providers ({len(provider_labels)}): {provider_labels}")
    print(f"  items={len(pilot_items)}  repeats={plan.repeats}  max_tokens={plan.max_tokens}")
    print(f"  budget cap=${cfg['budget']['cap_usd']:.2f}  run_dir={run_dir}")

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
            return 3

    jsonl = Path(res["jsonl"])
    _summarize(jsonl, cfg["benchmarks"][benchmark]["n_items"], cfg["repeats"])

    # Pilot confirmation stub — the full runner refuses to start until you sign this off.
    confirm = run_dir / "PILOT_REVIEW_REQUIRED.md"
    confirm.write_text(
        "# Pilot review gate\n\n"
        f"Pilot {run_id} completed at {utc_now_iso()}.\n\n"
        "The FULL run is BLOCKED until a human reviews per-provider accuracy + projected cost\n"
        "above and confirms (projected cost <= budget, parsing sane). To confirm, this file is\n"
        "replaced by `PILOT_CONFIRMED.md` (the full runner will check for it).\n"
    )
    print(f"\nPilot complete. Review the summary above. Full run is GATED until you confirm.")
    print(f"Artifacts in: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
