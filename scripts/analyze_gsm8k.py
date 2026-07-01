#!/usr/bin/env python3
"""Analyze an existing GSM8K run JSONL (no API calls).

Recomputes the per-provider table + POOLED over the WORKING primary providers (dropping
providers flagged unavailable, e.g. sambanova/bf16 -> 900x HTTP 404), shows ':floor' as a
separate routing condition, the invalid breakdown (incl. the 404 evidence), invalid-over-time,
and the H1 quick check.

Usage:
  python scripts/analyze_gsm8k.py <path/to/gsm8k.jsonl> [--drop slugA,slugB]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv import report as REPORT  # noqa: E402
from pv.stats import wilson_ci  # noqa: E402


def _merge_patch(source: str, patch: str) -> str:
    """Overlay patch rows onto source by cell key (patch wins). Returns a temp merged path."""
    def key(r):
        return (r["benchmark"], r["item_id"], r["provider_label"], r["repeat"])
    rows = {}
    for line in open(source):
        line = line.strip()
        if line:
            r = json.loads(line); rows[key(r)] = r
    n_patched = 0
    for line in open(patch):
        line = line.strip()
        if line:
            r = json.loads(line); rows[key(r)] = r; n_patched += 1
    out = Path(tempfile.mkstemp(suffix="_merged.jsonl")[1])
    with open(out, "w") as f:
        for r in rows.values():
            f.write(json.dumps(r) + "\n")
    print(f"[patch] overlaid {n_patched} re-run rows onto {len(rows)} cells -> {out}")
    return str(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("--patch", help="re-run patch JSONL to overlay (from rerun_cells.py)")
    ap.add_argument("--drop", default="sambanova/bf16",
                    help="comma-separated provider slugs to exclude as unavailable")
    args = ap.parse_args()

    if args.patch:
        args.jsonl = _merge_patch(args.jsonl, args.patch)
    dropped = {s for s in args.drop.split(",") if s}
    # The provider table + POOLED + H1 are over the WORKING canonical providers only:
    # exclude the dropped provider(s) AND ':floor' (a routing condition, not a distinct provider).
    exclude = dropped | {":floor"}

    # FINAL table: clean completions only (silent/overt/length truncations excluded).
    REPORT.print_final_table(
        args.jsonl,
        title="FINAL GSM8K — WORKING primary providers (clean completions, Wilson 95% CI)",
        exclude=exclude,
    )
    REPORT.print_reliability_table(args.jsonl, exclude={":floor"})

    # For reference: the as-collected table (before truncation reclassification).
    REPORT.print_table(
        args.jsonl,
        title="(reference) AS-COLLECTED table — before truncation reclassification",
        exclude=exclude,
    )

    # ':floor' shown separately as the cost-frontier routing condition.
    by = REPORT.load_provider_stats(args.jsonl)
    if ":floor" in by:
        p = by[":floor"]
        pt, lo, hi = wilson_ci(p["correct"], p["valid"])
        print(f"\n:floor (cost-frontier routing condition, not a distinct provider): "
              f"acc {pt*100:.1f}% [{lo*100:.1f},{hi*100:.1f}]  n_ok/val {p['correct']}/{p['valid']}"
              f"  cost ${p['cost']:.4f}")
    for d in sorted(dropped):
        if d in by:
            p = by[d]
            print(f"DROPPED {d}: {p['n']} rows, {p['req_failed']} request_failed "
                  f"(see invalid breakdown for HTTP status); excluded from accuracy.")

    REPORT.print_h1_check(args.jsonl, exclude=exclude)
    REPORT.print_invalid_breakdown(args.jsonl)   # includes dropped provider's 404s as evidence
    REPORT.print_invalid_over_time(args.jsonl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
