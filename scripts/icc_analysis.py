#!/usr/bin/env python3
"""Failure Consistency Coefficient — ICC(1,1) for Provider C (Cloudflare) truncation.

Pure re-analysis of the canonical result files (PREREGISTRATION §35); NO new API calls.
Quantifies the §40 "truncation is item-specific / reproducible" finding with a standard
one-way random-effects intraclass correlation.

For each cell it builds Provider C's item×repeat binary truncation matrix
(1 = truncated [overt finish=error OR audit-confirmed silent], 0 = clean completion),
computes ICC(1,1) via the manual ANOVA formula:

    ICC(1,1) = (MSB - MSW) / (MSB + (k-1)*MSW)
    MSB = SSB/(n-1)              # mean square BETWEEN items
    MSW = SSW/(n*(k-1))          # mean square WITHIN items (residual)
    k   = repeats (3)

and a 95% CI by item-level bootstrap (10,000 resamples, seed 20260629). A clean PEER
provider per cell is computed as a degenerate-baseline sanity check (zero truncations =>
zero variance => ICC undefined), confirming the metric distinguishes Provider C from
normal providers.

Data source: the canonical JSONLs. By default reads the working copies under ~/pv_runs
(byte-identical to archive/canonical_results_v1.tar.gz). To run from the archive instead:
    tar -xzf archive/canonical_results_v1.tar.gz
    python scripts/icc_analysis.py --data-root canonical_results
(the script auto-detects either layout).

Deps: numpy only (pingouin/scipy optional; if pingouin is importable it is used to
cross-validate the manual ICC, otherwise an independent SS-decomposition check is printed).
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

HOME = os.path.expanduser("~")

# (cell -> (pv_runs relative jsonl, archive relative jsonl, Provider C, clean peer))
CELLS = {
    "GSM8K/70B": (
        f"{HOME}/pv_runs/full_gsm8k_20260630T164925Z_nogit/raw/gsm8k.jsonl",
        "canonical_results/gsm8k_llama-3.3-70b/gsm8k.jsonl",
        "cloudflare/fp8", "nebius/fp8",
    ),
    "HumanEval/70B": (
        f"{HOME}/pv_runs/final_humaneval_llama-3.3-70b_recovered/raw/humaneval.jsonl",
        "canonical_results/humaneval_llama-3.3-70b_recovered/humaneval.jsonl",
        "cloudflare/fp8", "akashml/fp8",
    ),
    "MMLU/8B": (
        f"{HOME}/pv_runs/full_mmlu_llama-3.1-8b_20260702T010240Z_nogit/raw/mmlu.jsonl",
        "canonical_results/mmlu_llama-3.1-8b/mmlu.jsonl",
        "cloudflare/fp8", "deepinfra/fp8",
    ),
}
K_REPEATS = 3
N_BOOT = 10_000
SEED = 20260629


def resolve(pv_path: str, archive_rel: str, data_root: str | None) -> str:
    """Locate the canonical JSONL: explicit --data-root (archive layout) wins, else ~/pv_runs."""
    if data_root:
        p = Path(data_root) / archive_rel
        if p.exists():
            return str(p)
        # allow --data-root pointing directly at an extracted canonical_results dir
        p2 = Path(data_root) / Path(archive_rel).relative_to("canonical_results")
        if p2.exists():
            return str(p2)
    return pv_path


def truncation_outcome(r: dict) -> int | None:
    """1 = truncated (overt finish=error OR audited silent; both stored as generation_error),
    0 = clean valid completion, None = other invalid (req_failed/empty_response/mismatch) ->
    excluded (not a truncation, not a clean completion)."""
    if r.get("invalid_reason") == "generation_error":
        return 1
    if r.get("valid"):
        return 0
    return None


def build_matrix(path: str, provider: str):
    """Return (X[n_items x k] binary, k_repeats, n_dropped_incomplete)."""
    cell = defaultdict(dict)
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r["provider_label"] != provider:
                continue
            cell[r["item_id"]][r["repeat"]] = truncation_outcome(r)
    reps = sorted({rp for d in cell.values() for rp in d})
    rows, dropped = [], 0
    for _, d in cell.items():
        vals = [d.get(rp) for rp in reps]
        if len(vals) != len(reps) or any(v is None for v in vals):
            dropped += 1
            continue
        rows.append(vals)
    return np.array(rows, dtype=float), len(reps), dropped


def icc_1_1(X: np.ndarray) -> float:
    """One-way random-effects ICC(1,1) via ANOVA. NaN if degenerate (zero total variance)."""
    n, k = X.shape
    if n < 2:
        return float("nan")
    grand = X.mean()
    row = X.mean(axis=1)
    ssb = k * ((row - grand) ** 2).sum()
    ssw = ((X - row[:, None]) ** 2).sum()
    msb = ssb / (n - 1)
    msw = ssw / (n * (k - 1))
    denom = msb + (k - 1) * msw
    if denom == 0:
        return float("nan")  # no variance at all (e.g. zero truncations) -> ICC undefined
    return (msb - msw) / denom


def bootstrap_ci(X: np.ndarray, b: int = N_BOOT, seed: int = SEED):
    """Item-level bootstrap 95% CI. Returns (lo, hi, n_valid_resamples)."""
    n = X.shape[0]
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(b):
        idx = rng.integers(0, n, n)
        v = icc_1_1(X[idx])
        if not np.isnan(v):
            vals.append(v)
    if not vals:
        return float("nan"), float("nan"), 0
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)), len(vals)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", help="extracted archive dir (contains canonical_results/); "
                                        "default reads ~/pv_runs")
    args = ap.parse_args()

    try:
        import pingouin  # noqa: F401
        have_pingouin = True
    except Exception:  # noqa: BLE001
        have_pingouin = False

    print(f"{'cell':<14}{'who':<20}{'n':>5}{'k':>3}{'#trunc':>8}{'ICC(1,1)':>11}   95% CI (bootstrap 10k)")
    print("-" * 94)
    for cell, (pv, arc, prov_c, peer) in CELLS.items():
        path = resolve(pv, arc, args.data_root)
        for label, prov in (("C:" + prov_c.split("/")[0], prov_c), ("peer:" + peer.split("/")[0], peer)):
            X, k, dropped = build_matrix(path, prov)
            n, ntr = X.shape[0], int(X.sum())
            icc = icc_1_1(X)
            if np.isnan(icc):
                print(f"{cell:<14}{label:<20}{n:>5}{k:>3}{ntr:>8}{'undefined':>11}   "
                      f"DEGENERATE (zero truncation variance) -> ICC undefined")
            else:
                lo, hi, nb = bootstrap_ci(X)
                extra = f"  (dropped {dropped} incomplete)" if dropped else ""
                print(f"{cell:<14}{label:<20}{n:>5}{k:>3}{ntr:>8}{icc:>11.3f}   [{lo:.3f}, {hi:.3f}]{extra}")

    # cross-validation of the manual ANOVA on GSM8K/70B Provider C
    pv, arc, prov_c, _ = CELLS["GSM8K/70B"]
    X, k, _ = build_matrix(resolve(pv, arc, args.data_root), prov_c)
    n = X.shape[0]
    grand, row = X.mean(), X.mean(axis=1)
    sst = ((X - grand) ** 2).sum()
    ssb = k * ((row - grand) ** 2).sum()
    ssw = sst - ssb
    msb, msw = ssb / (n - 1), ssw / (n * (k - 1))
    print(f"\ncross-check GSM8K/70B C: SST {sst:.1f} = SSB {ssb:.1f} + SSW {ssw:.1f}  "
          f"ICC {(msb - msw) / (msb + (k - 1) * msw):.4f}")
    if have_pingouin:
        import pandas as pd
        import pingouin as pg
        long = pd.DataFrame(
            [(i, j, X[i, j]) for i in range(n) for j in range(k)],
            columns=["item", "repeat", "trunc"])
        r = pg.intraclass_corr(data=long, targets="item", raters="repeat", ratings="trunc")
        icc1 = r.loc[r["Type"] == "ICC1", "ICC"].values[0]
        print(f"pingouin ICC1 cross-check: {icc1:.4f}")
    else:
        print("(pingouin not installed; used independent SS-decomposition cross-check above)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
