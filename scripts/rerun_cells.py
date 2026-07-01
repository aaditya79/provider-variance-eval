#!/usr/bin/env python3
"""Re-run ONLY truncated cells from an existing GSM8K run (paired design preserved).

Targets (PREREGISTRATION §20-21):
  * length  : valid finish=='length' with no #### (hit the old max_tokens cap) -> re-run at the
              new max_tokens (config, now 1024).
  * silent  : finish=='stop' but truncated (silent_truncation) -> retry (harness auto-retries).
Default re-runs both. Overt generation_error (finish=='error') is NOT re-run here (already
retried at collection; reported as its own reliability rate).

Writes a PATCH JSONL to a new run dir; merge it in analysis with:
  python scripts/analyze_gsm8k.py <original.jsonl> --patch <patch.jsonl>

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  python scripts/rerun_cells.py <original/gsm8k.jsonl> [--which length|silent|both]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.benchmarks import gsm8k as gsm8k_mod  # noqa: E402
from pv.config import git_sha, load_config, require_api_key, utc_now_iso  # noqa: E402
from pv.openrouter import OpenRouterClient, is_silent_truncation  # noqa: E402
from pv.snapshot import build_name_map, load_latest_snapshot  # noqa: E402
from pv import runner as R  # noqa: E402

ITEMS_DIR = Path("data/items")


def _is_length_trunc(r: dict) -> bool:
    t = r.get("completion_text")
    return bool(r.get("valid")) and r.get("finish_reason") == "length" and not (t and "####" in t)


def _is_silent_trunc(r: dict) -> bool:
    return bool(r.get("valid")) and is_silent_truncation(r.get("finish_reason"), r.get("completion_text"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--which", choices=["length", "silent", "both"], default="both")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    frozen = json.loads((ITEMS_DIR / "gsm8k.json").read_text())
    itemmap = {it["id"]: it for it in frozen["items"]}
    max_tokens = cfg["benchmarks"]["gsm8k"]["max_tokens"]

    rows = [json.loads(l) for l in open(args.source) if l.strip()]
    def want(r):
        if args.which == "length":
            return _is_length_trunc(r)
        if args.which == "silent":
            return _is_silent_trunc(r)
        return _is_length_trunc(r) or _is_silent_trunc(r)
    targets = [r for r in rows if want(r)]
    print(f"selected {len(targets)} cells to re-run (which={args.which}, max_tokens={max_tokens})")
    kinds = {"length": sum(_is_length_trunc(r) for r in targets),
             "silent": sum(_is_silent_trunc(r) for r in targets)}
    print(f"  breakdown: {kinds}")
    if not targets:
        print("nothing to re-run.")
        return 0

    try:
        api_key = require_api_key()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2

    name_map = build_name_map(load_latest_snapshot("start")) or {}
    ts = utc_now_iso().replace(":", "").replace("-", "")
    run_id = f"rerun_gsm8k_{ts}_{git_sha(short=True) or 'nogit'}"
    run_dir = R.make_run_dir(cfg["run"]["runs_dir"], run_id, cfg, args.config)
    patch = run_dir / "raw" / "gsm8k_rerun.jsonl"

    recovered = still_bad = 0
    with OpenRouterClient(
        api_key, timeout_s=cfg["run"]["request_timeout_s"],
        max_attempts=cfg["retry"]["max_attempts"],
        backoff_base_s=cfg["retry"]["backoff_base_s"],
        backoff_cap_s=cfg["retry"]["backoff_cap_s"],
        retry_on_status=tuple(cfg["retry"]["retry_on_status"]),
    ) as client, open(patch, "a") as out:
        for i, r in enumerate(targets, 1):
            prov = r["provider_label"]
            route = "floor" if prov == ":floor" else "pinned"
            item = itemmap[r["item_id"]]
            call = client.chat_completion(
                model_slug=r["model_slug"],
                messages=gsm8k_mod.build_prompt(item["question"], frozen["exemplars"]),
                max_tokens=max_tokens, temperature=cfg["decoding"]["temperature"],
                top_p=cfg["decoding"]["top_p"], pinned_provider=None if route == "floor" else prov,
                route_mode=route, send_seed=cfg["decoding"]["send_seed"], seed=cfg["run"]["seed"],
                expected_served_name=name_map.get(prov),
            )
            if call.valid:
                correct, parse = gsm8k_mod.grade(call.completion_text, item["gold_raw"])
                recovered += 1
            else:
                correct, parse = None, None
                still_bad += 1
            row = R._row(call, benchmark="gsm8k", item=item, repeat=r["repeat"],
                         provider_label=prov, route_mode=route, correct=correct,
                         parse=(parse if isinstance(parse, dict) else (parse and parse.__dict__)),
                         run_id=run_id)
            out.write(json.dumps(row) + "\n")
            out.flush()
            if i % 20 == 0:
                os.fsync(out.fileno())
                print(f"  ... {i}/{len(targets)} rerun, {recovered} now-valid, {still_bad} still bad")
        out.flush(); os.fsync(out.fileno())

    print(f"\n[persisted] {sum(1 for _ in open(patch))} patch rows -> {patch}")
    print(f"recovered (now valid/gradeable): {recovered} | still truncated: {still_bad}")
    print(f"\nMerge into the final table:\n  python scripts/analyze_gsm8k.py {args.source} --patch {patch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
