"""Shared per-provider results table (used by the pilot and full runners).

Two outcome axes (PREREGISTRATION §16), reported side by side, never conflated:
  1. clean-completion accuracy (over valid calls) with Wilson 95% CI
  2. reliability: generation_error rate and read-back mismatch rate
Plus the parse-path distribution (delimiter vs flagged fallbacks; PREREGISTRATION §17) and cost.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .stats import wilson_ci


def _blank() -> dict:
    return {
        "n": 0, "valid": 0, "correct": 0, "cost": 0.0, "ctok": 0,
        "gen_err": 0, "mismatch": 0, "req_failed": 0,
        "parse_paths": defaultdict(int),
    }


def load_provider_stats(jsonl: str | Path) -> dict[str, dict]:
    """Aggregate one JSONL into per-provider stats."""
    by = defaultdict(_blank)
    for line in open(jsonl):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        p = by[r["provider_label"]]
        p["n"] += 1
        if r.get("cost_usd"):
            p["cost"] += float(r["cost_usd"])
        reason = r.get("invalid_reason")
        if r["valid"]:
            p["valid"] += 1
            if r.get("correct"):
                p["correct"] += 1
            if r.get("completion_tokens"):
                p["ctok"] += r["completion_tokens"]
            if r.get("parse"):
                p["parse_paths"][r["parse"]["path"]] += 1
        elif reason == "generation_error":
            p["gen_err"] += 1
        elif reason == "provider_readback_mismatch":
            p["mismatch"] += 1
        else:
            p["req_failed"] += 1
    return by


def print_table(jsonl: str | Path, *, title: str) -> dict:
    by = load_provider_stats(jsonl)
    print("\n" + "=" * 104)
    print(title)
    print("=" * 104)
    hdr = (f"{'provider':<22}{'acc':>7}{'95% Wilson CI':>18}{'n_ok':>6}"
           f"{'gen_err':>9}{'mism':>7}{'flag':>6}{'avg_ct':>8}{'$':>9}")
    print(hdr)
    print("  acc = correct/valid (excludes gen_err + mismatch from num AND denom); "
          "flag = flagged parse paths")
    print("-" * len(hdr))
    total_cost = 0.0
    total_correct = total_valid = 0
    for prov in sorted(by):
        p = by[prov]
        pt, lo, hi = wilson_ci(p["correct"], p["valid"])
        acc_s = f"{pt*100:.1f}%" if p["valid"] else "n/a"
        ci_s = f"[{lo*100:.1f},{hi*100:.1f}]" if p["valid"] else "-"
        flagged = sum(v for k, v in p["parse_paths"].items() if k.endswith("_flagged"))
        avg_ct = (p["ctok"] / p["valid"]) if p["valid"] else 0.0
        err_s = f"{p['gen_err']}/{p['n']}"
        total_cost += p["cost"]
        total_correct += p["correct"]
        total_valid += p["valid"]
        print(f"{prov:<22}{acc_s:>7}{ci_s:>18}{p['valid']:>6}"
              f"{err_s:>9}{p['mismatch']:>7}{flagged:>6}{avg_ct:>8.0f}{p['cost']:>9.4f}")
    print("-" * len(hdr))
    print(f"{'POOLED':<22}{'':>7}{'':>18}{total_valid:>6}{'':>9}{'':>7}{'':>6}"
          f"{'':>8}{total_cost:>9.4f}")
    # Parse-path detail (audit trail) under the table.
    print("\nparse-path distribution per provider (flagged = needs manual audit):")
    for prov in sorted(by):
        pp = dict(by[prov]["parse_paths"])
        if pp:
            print(f"  {prov:<22} {pp}")
    return by
