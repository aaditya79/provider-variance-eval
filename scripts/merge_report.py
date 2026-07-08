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
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.config import utc_now_iso  # noqa: E402
from pv import report as REPORT  # noqa: E402


def _key(r):
    return (r["benchmark"], r["item_id"], r["provider_label"], r["repeat"])


def merge(source: str, patch: str, out_path: str | None) -> str:
    """Overlay patch onto source (patch wins per cell). If out_path is given, write DURABLY
    with fsync + integrity check + manifest + a [persisted] line (same guard as the runners);
    otherwise write to a temp file for a quick view."""
    rows = {}
    for line in open(source):
        if line.strip():
            r = json.loads(line); rows[_key(r)] = r
    n_patch = 0
    for line in open(patch):
        if line.strip():
            r = json.loads(line); rows[_key(r)] = r; n_patch += 1
    ordered = list(rows.values())

    if out_path:
        out = Path(out_path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            for r in ordered:
                f.write(json.dumps(r) + "\n")
            f.flush(); os.fsync(f.fileno())
        lines = sum(1 for _ in open(out))
        if lines != len(ordered):
            raise RuntimeError(f"DATA LOSS: wrote {len(ordered)} rows but file holds {lines}")
        manifest = {
            "merged_utc": utc_now_iso(), "source": source, "patch": patch,
            "patch_rows": n_patch, "rows": lines, "bytes": out.stat().st_size,
            "note": "canonical merged result (base + targeted recovery patch)",
        }
        (out.parent / (out.stem + "_manifest.json")).write_text(json.dumps(manifest, indent=2))
        print(f"[merge] overlaid {n_patch} patch rows -> {len(ordered)} cells")
        print(f"[persisted] {lines} rows, {out.stat().st_size} bytes -> {out}")
        return str(out)

    tmp = Path(tempfile.mkstemp(suffix="_merged.jsonl")[1])
    with open(tmp, "w") as f:
        for r in ordered:
            f.write(json.dumps(r) + "\n")
    print(f"[merge] overlaid {n_patch} patch rows -> {len(ordered)} cells -> {tmp} (temp)")
    return str(tmp)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--patch", required=True)
    ap.add_argument("--out", help="durable output path (under ~/pv_runs); omit for temp view")
    ap.add_argument("--title", default="MERGED RESULTS")
    args = ap.parse_args()
    merged = merge(args.source, args.patch, args.out)
    REPORT.print_table(merged, title=args.title)
    REPORT.print_reliability_stored(merged)
    REPORT.print_invalid_breakdown(merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
