#!/usr/bin/env python3
"""BREADTH SWEEP (Task 1): look for a SECOND truncating provider beyond Cloudflare.

Enumerates ALL live providers for many widely-served open models and runs GSM8K at reduced scale
(breadth over depth) across every distinct (model x provider) deployment. Same truncation/
generation_error policy, read-back, and durable persistence guard.

Pilot first: `--items 5` doubles as a liveness probe + cost projection to the 100-item full sweep;
STOP for approval, then `--items 100`.

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  python scripts/broad_sweep.py --items 5     # pilot: enumerate, project full cost, STOP
  python scripts/broad_sweep.py --items 100   # full breadth sweep (after approval)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.benchmarks import gsm8k as G  # noqa: E402
from pv.config import git_sha, load_config, require_api_key, utc_now_iso  # noqa: E402
from pv.openrouter import OpenRouterClient  # noqa: E402
from pv import runner as R  # noqa: E402

CANDIDATE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct", "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct", "meta-llama/llama-3-70b-instruct",
    "mistralai/mixtral-8x7b-instruct", "mistralai/mistral-7b-instruct",
    "qwen/qwen-2.5-72b-instruct", "qwen/qwen-2.5-7b-instruct",
    "google/gemma-2-9b-it", "google/gemma-2-27b-it",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=int, default=5, help="GSM8K items per deployment (5=pilot, 100=full)")
    ap.add_argument("--models", nargs="*", default=CANDIDATE_MODELS)
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    frozen = json.loads((Path("data/items") / "gsm8k.json").read_text())
    items = frozen["items"][: args.items]
    max_tokens = cfg["benchmarks"]["gsm8k"]["max_tokens"]

    try:
        api_key = require_api_key()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2

    ts = utc_now_iso().replace(":", "").replace("-", "")
    run_id = f"broadsweep_gsm8k_{args.items}items_{ts}_{git_sha(short=True) or 'nogit'}"
    run_dir = R.make_run_dir(cfg["run"]["runs_dir"], run_id, cfg, args.config)
    jsonl = run_dir / "raw" / "broadsweep.jsonl"

    n_written = 0
    stats = defaultdict(lambda: {"n": 0, "valid": 0, "overt": 0, "silent": 0, "cost": 0.0, "ct": 0, "ctn": 0})
    with OpenRouterClient(
        api_key, timeout_s=cfg["run"]["request_timeout_s"],
        max_attempts=cfg["retry"]["max_attempts"], backoff_base_s=cfg["retry"]["backoff_base_s"],
        backoff_cap_s=cfg["retry"]["backoff_cap_s"], retry_on_status=tuple(cfg["retry"]["retry_on_status"]),
    ) as client, open(jsonl, "a") as out:
        aborted = False
        for model in args.models:
            if aborted:
                break
            try:
                raw = client.list_endpoints(model)
            except Exception as e:  # noqa: BLE001
                print(f"  {model}: enumeration failed ({e!r})"); continue
            eps = (raw.get("data") or {}).get("endpoints") or []
            print(f"{model}: {len(eps)} endpoints")
            for ep in eps:
                if aborted:
                    break
                tag = ep.get("tag") or ep.get("provider_name")
                name = ep.get("provider_name")
                key = f"{model}|{tag}"
                for it in items:
                    call = client.chat_completion(
                        model_slug=model, messages=G.build_prompt(it["question"], frozen["exemplars"]),
                        max_tokens=max_tokens, temperature=cfg["decoding"]["temperature"],
                        top_p=cfg["decoding"]["top_p"], pinned_provider=tag, route_mode="pinned",
                        send_seed=False, seed=cfg["run"]["seed"], expected_served_name=name,
                        completeness_check=G.is_complete,
                    )
                    correct, parse = (G.grade(call.completion_text, it["gold_raw"]) if call.valid else (None, None))
                    row = R._row(call, benchmark="gsm8k", item=it, repeat=0, provider_label=tag,
                                 route_mode="pinned", correct=correct,
                                 parse=(parse.__dict__ if parse and not isinstance(parse, dict) else parse),
                                 run_id=run_id)
                    row["sweep_model"] = model
                    out.write(json.dumps(row) + "\n"); out.flush(); n_written += 1
                    if call.http_status == 402:
                        # Account credits exhausted — every further call will 402. Stop now
                        # instead of logging thousands of useless failures (as happened 2026-07-08).
                        print(f"\nABORT: HTTP 402 Insufficient credits at {key}. Stopping sweep.\n"
                              "Add credits at https://openrouter.ai/settings/credits and re-run "
                              "the incomplete deployments (--models ...).", file=sys.stderr)
                        aborted = True
                        break
                    s = stats[key]; s["n"] += 1
                    if call.cost_usd:
                        s["cost"] += call.cost_usd
                    if call.valid:
                        s["valid"] += 1
                        if call.completion_tokens:
                            s["ct"] += call.completion_tokens; s["ctn"] += 1
                    elif call.invalid_subtype == "overt_truncation":
                        s["overt"] += 1
                    elif call.invalid_subtype == "silent_truncation":
                        s["silent"] += 1
                if n_written % 50 == 0:
                    os.fsync(out.fileno())
        out.flush(); os.fsync(out.fileno())

    lines = sum(1 for _ in open(jsonl))
    (run_dir / "manifest.json").write_text(json.dumps(
        {"run_id": run_id, "items_per_deployment": args.items, "rows": lines,
         "bytes": jsonl.stat().st_size, "utc": utc_now_iso()}, indent=2))
    print(f"\n[persisted] {lines} rows, {jsonl.stat().st_size} bytes -> {jsonl}")

    # Report: truncation per deployment; flag any NON-Cloudflare truncator.
    print("\n" + "=" * 92)
    print(f"BREADTH SWEEP — GSM8K {args.items} items/deployment — truncation by (model, provider)")
    print("=" * 92)
    total_cost = 0.0
    truncators = []
    for key in sorted(stats):
        s = stats[key]; total_cost += s["cost"]
        tr = s["overt"] + s["silent"]
        avg_ct = s["ct"] / s["ctn"] if s["ctn"] else 0
        flag = ""
        if tr:
            model, prov = key.split("|", 1)
            is_cf = "cloudflare" in prov.lower()
            flag = "  <-- CLOUDFLARE" if is_cf else "  <-- *** NON-CLOUDFLARE TRUNCATOR ***"
            truncators.append((key, s["overt"], s["silent"], is_cf))
        print(f"  {key:<52} n={s['n']:>3} valid={s['valid']:>3} overt={s['overt']} silent={s['silent']}"
              f" avg_ct={avg_ct:>4.0f}{flag}")

    print(f"\nTOTAL cost this sweep: ${total_cost:.4f}")
    if args.items < 100:
        per_call = total_cost / max(1, n_written)
        n_deploy = len(stats)
        print(f"PROJECTED full sweep (100 items/deployment, {n_deploy} live deployments): "
              f"${per_call * n_deploy * 100:.2f}  (~{n_deploy*100} calls)")
        print("PILOT complete — STOP for approval before running --items 100.")
    non_cf = [t for t in truncators if not t[3]]
    print(f"\nNON-Cloudflare truncators found: {len(non_cf)}"
          + (f" -> {[t[0] for t in non_cf]}" if non_cf else " (only Cloudflare truncates, if any)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
