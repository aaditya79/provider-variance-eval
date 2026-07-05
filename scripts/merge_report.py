#!/usr/bin/env python3
"""Merge a re-run patch into a source JSONL (patch wins per cell) and print the tables.

General over benchmarks (unlike analyze_gsm8k which prints GSM8K-specific final tables).
No API calls.

Usage:
  python scripts/merge_report.py <source.jsonl> --patch <patch.jsonl> --title "HumanEval/70B (recovered)"
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv import report as REPORT  # noqa: E402


def _key(r):
    return (r["benchmark"], r["item_id"], r["provider_label"], r["repeat"])


def merge(source: str, patch: str) -> str:
    rows = {}
    for line in open(source):
        if line.strip():
            r = json.loads(line); rows[_key(r)] = r
    n = 0
    for line in open(patch):
        if line.strip():
            r = json.loads(line); rows[_key(r)] = r; n += 1
    out = Path(tempfile.mkstemp(suffix="_merged.jsonl")[1])
    with open(out, "w") as f:
        for r in rows.values():
            f.write(json.dumps(r) + "\n")
    print(f"[merge] overlaid {n} patch rows -> {len(rows)} cells -> {out}")
    return str(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--patch", required=True)
    ap.add_argument("--title", default="MERGED RESULTS")
    args = ap.parse_args()
    merged = merge(args.source, args.patch)
    REPORT.print_table(merged, title=args.title)
    REPORT.print_reliability_stored(merged)
    REPORT.print_invalid_breakdown(merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
