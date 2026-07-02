#!/usr/bin/env python3
"""Consolidated length-vs-truncation view across all runs (no API calls).

Scans run JSONLs (default: ~/pv_runs/**/raw/*.jsonl) and, per (benchmark, model, provider),
reports avg completion tokens vs truncation rate — to test the length-dependence hypothesis
(PREREGISTRATION §27). Highlights Cloudflare across every cell.

Usage:
  python scripts/reliability_matrix.py [glob ...]     # default globs ~/pv_runs full_* runs
"""

from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict

DEFAULT_GLOB = os.path.expanduser("~/pv_runs/full_*/raw/*.jsonl")


def cell_stats(path: str) -> dict:
    rows = [json.loads(l) for l in open(path) if l.strip()]
    if not rows:
        return {}
    benchmark = rows[0].get("benchmark")
    model = rows[0].get("model_slug")
    per_prov = defaultdict(lambda: {"n": 0, "ct": 0, "ctn": 0, "trunc": 0,
                                    "overt": 0, "silent": 0})
    allct, allctn = 0, 0
    for r in rows:
        p = per_prov[r["provider_label"]]
        p["n"] += 1
        if r.get("valid"):
            if r.get("completion_tokens"):
                p["ct"] += r["completion_tokens"]; p["ctn"] += 1
                allct += r["completion_tokens"]; allctn += 1
        elif r.get("invalid_reason") == "generation_error":
            p["trunc"] += 1
            sub = r.get("invalid_subtype")
            if sub == "silent_truncation":
                p["silent"] += 1
            else:
                p["overt"] += 1  # overt or legacy pre-subtype (finish=error)
    return {"benchmark": benchmark, "model": model, "per_prov": per_prov,
            "avg_ct": (allct / allctn if allctn else 0), "n_rows": len(rows)}


def main() -> int:
    globs = sys.argv[1:] or [DEFAULT_GLOB]
    paths = sorted({p for g in globs for p in glob.glob(g)})
    if not paths:
        print(f"No run JSONLs found under: {globs}", file=sys.stderr)
        return 1

    cells = [cell_stats(p) for p in paths]
    cells = [c for c in cells if c]

    print("=" * 92)
    print("LENGTH vs TRUNCATION — per (benchmark x model), overall avg output tokens")
    print("=" * 92)
    print(f"{'benchmark':<12}{'model':<34}{'rows':>7}{'avg_ct':>9}")
    for c in sorted(cells, key=lambda x: (x["benchmark"], x["model"])):
        print(f"{c['benchmark']:<12}{c['model']:<34}{c['n_rows']:>7}{c['avg_ct']:>9.0f}")

    print("\n" + "=" * 92)
    print("CLOUDFLARE across cells — avg output tokens vs truncation rate (tests §27 hypothesis)")
    print("=" * 92)
    print(f"{'benchmark':<12}{'model':<28}{'CF avg_ct':>11}{'CF trunc%':>11}{'overt':>7}{'silent':>8}")
    for c in sorted(cells, key=lambda x: (x["benchmark"], x["model"])):
        p = c["per_prov"].get("cloudflare/fp8")
        if not p:
            continue
        avg = p["ct"] / p["ctn"] if p["ctn"] else 0
        rate = p["trunc"] / p["n"] * 100 if p["n"] else 0
        print(f"{c['benchmark']:<12}{c['model']:<28}{avg:>11.0f}{rate:>10.1f}%{p['overt']:>7}{p['silent']:>8}")

    print("\n(hypothesis: CF trunc% rises with avg output tokens; ~0 on short-output cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
