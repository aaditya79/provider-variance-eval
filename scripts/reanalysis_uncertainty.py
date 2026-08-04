#!/usr/bin/env python3
"""Re-analysis for reviewer-raised uncertainty questions. NO new API calls.

Pure re-analysis of the canonical result files (PREREGISTRATION §35), i.e. the same
JSONLs archived in archive/canonical_results_v1.tar.gz (checksummed).

Three tasks:

  1. TOST / minimum-detectable-effect for the accuracy comparison, per benchmark.
     The paper claims "provider-invariant" from a failure to reject. This computes
     what the design could actually have detected, and what equivalence margin the
     data DOES support.

  2. Paired bootstrap on the accuracy gaps. The design is paired (frozen item sets
     reused across providers) but the paper analyses it as unpaired (Wilson intervals
     on independent proportions). This recovers the pairing.

  3. Peer FCC on MMLU/8B cap-hits. §5.4 attributes the highest FCC (0.935) to
     "cap-hit failures where the same difficult items consistently exceed the token
     budget", but §3.3 defines budget-cap as an artifact of our own configuration.
     If peers show comparable item-level determinism on their own cap-hits, the
     0.935 is largely item difficulty, not a Provider C property.

Deps: numpy only. Normal quantiles hardcoded (no scipy).

    python scripts/reanalysis_uncertainty.py [--data-root <extracted canonical_results parent>]
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

HOME = os.path.expanduser("~")

Z_975 = 1.959963985  # two-sided alpha=0.05
Z_95 = 1.644853627  # one-sided alpha=0.05 (TOST / 90% CI)
Z_80 = 0.841621234  # 80% power

N_BOOT = 10_000
SEED = 20260629
PROVIDER_C = "cloudflare/fp8"

# Exclusion rules implementing the paper's Sec 3.3 taxonomy on the canonical files.
#
# invalid rows (generation_error / request_failed / readback_mismatch) are always
# excluded. In addition, some truncation classes remain valid=True in the canonical
# JSONLs and must be excluded explicitly (PREREGISTRATION Sec 19-21):
#
#   GSM8K  -- parse.path == "delimiter_missing_flagged" covers BOTH google-vertex's
#             silent truncations (finish=stop, #### never emitted) and peers'
#             finish=length budget-cap hits. Sec 19 verifies 34/34 google-vertex
#             flags are genuine truncations; excluding them takes google-vertex
#             92.4% -> 96.1% and collapses the spread 4.67pp -> ~1.6pp.
#   MMLU   -- parse.path == "unparseable": the 64-token cap was hit before a letter
#             was emitted. Sec 3.3 says budget-cap cells are excluded uniformly.
#   HumanEval -- finish_reason == "length" (the only cap signal; graded by unit test).
#
# Providers: canonical endpoints only. ":floor" is a variant/aggregator route
# (Sec 4.2) and sambanova/bf16 went dead mid-study (Sec 18, zero valid rows).
NON_CANONICAL = {":floor", "sambanova/bf16"}


def excl_gsm8k(r):
    return (r.get("parse") or {}).get("path") == "delimiter_missing_flagged"


def excl_mmlu(r):
    return (r.get("parse") or {}).get("path") == "unparseable"


def excl_humaneval(r):
    return r.get("finish_reason") == "length"


# cell -> (pv_runs path, archive-relative path, extra-exclusion predicate)
CELLS = {
    "GSM8K/70B": (
        f"{HOME}/pv_runs/full_gsm8k_20260630T164925Z_nogit/raw/gsm8k.jsonl",
        "canonical_results/gsm8k_llama-3.3-70b/gsm8k.jsonl",
        excl_gsm8k,
    ),
    "MMLU/70B": (
        f"{HOME}/pv_runs/full_mmlu_llama-3.3-70b_20260701T232233Z_nogit/raw/mmlu.jsonl",
        "canonical_results/mmlu_llama-3.3-70b/mmlu.jsonl",
        excl_mmlu,
    ),
    "HumanEval/70B": (
        f"{HOME}/pv_runs/final_humaneval_llama-3.3-70b_recovered/raw/humaneval.jsonl",
        "canonical_results/humaneval_llama-3.3-70b_recovered/humaneval.jsonl",
        excl_humaneval,
    ),
    "MMLU/8B": (
        f"{HOME}/pv_runs/full_mmlu_llama-3.1-8b_20260702T010240Z_nogit/raw/mmlu.jsonl",
        "canonical_results/mmlu_llama-3.1-8b/mmlu.jsonl",
        excl_mmlu,
    ),
}


def resolve(pv_path: str, archive_rel: str, data_root: str | None) -> str:
    if data_root:
        p = Path(data_root) / archive_rel
        if p.exists():
            return str(p)
        p2 = Path(data_root) / Path(archive_rel).relative_to("canonical_results")
        if p2.exists():
            return str(p2)
    return pv_path


def load(path: str) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# --------------------------------------------------------------------------
# Task 1 + 2: accuracy, paired
# --------------------------------------------------------------------------

def item_provider_matrix(rows: list[dict], extra_excl=None):
    """Per-item, per-provider clean-completion accuracy.

    Returns (items, providers, ACC[n_items x n_prov], NVALID[n_items x n_prov]).
    ACC = mean(correct) over CLEAN repeats only -- invalid rows and the extra
    truncation/cap classes are removed from numerator and denominator alike, per
    the Sec 3.3 taxonomy. NaN where a provider has zero clean repeats on an item.
    """
    acc = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["provider_label"] in NON_CANONICAL:
            continue
        if not r.get("valid"):
            continue  # overt/silent truncations, request failures, readback mismatches
        if extra_excl is not None and extra_excl(r):
            continue  # budget-cap + flagged-truncation classes still marked valid
        acc[r["item_id"]][r["provider_label"]].append(1.0 if r.get("correct") else 0.0)

    items = sorted(acc)
    providers = sorted({p for d in acc.values() for p in d})
    A = np.full((len(items), len(providers)), np.nan)
    N = np.zeros((len(items), len(providers)))
    for i, it in enumerate(items):
        for j, pv in enumerate(providers):
            v = acc[it].get(pv)
            if v:
                A[i, j] = float(np.mean(v))
                N[i, j] = len(v)
    return items, providers, A, N


def provider_accuracy(A, N):
    """Call-weighted accuracy per provider (matches paper's c_j / n_j)."""
    num = np.nansum(np.where(np.isnan(A), 0.0, A) * N, axis=0)
    den = N.sum(axis=0)
    return num / np.maximum(den, 1), den


def wilson(p, n, z=Z_975):
    if n <= 0:
        return (np.nan, np.nan)
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def paired_bootstrap_gap(A, N, ja, jb, b=N_BOOT, seed=SEED):
    """Item-level paired bootstrap of (acc_a - acc_b), resampling ITEMS.

    Accuracy recomputed call-weighted within each resample, so this preserves both
    the pairing and the fact that repeats are nested within items.
    """
    n = A.shape[0]
    rng = np.random.default_rng(seed)
    Aa = np.where(np.isnan(A[:, ja]), 0.0, A[:, ja]) * N[:, ja]
    Ab = np.where(np.isnan(A[:, jb]), 0.0, A[:, jb]) * N[:, jb]
    Na, Nb = N[:, ja], N[:, jb]
    out = np.empty(b)
    for t in range(b):
        idx = rng.integers(0, n, n)
        da, db = Na[idx].sum(), Nb[idx].sum()
        out[t] = (Aa[idx].sum() / da if da else np.nan) - (Ab[idx].sum() / db if db else np.nan)
    return out[~np.isnan(out)]


def task1_and_2(cell: str, rows: list[dict], extra_excl=None):
    items, providers, A, N = item_provider_matrix(rows, extra_excl)
    accs, dens = provider_accuracy(A, N)
    order = np.argsort(-accs)
    jmax, jmin = order[0], order[-1]
    spread = accs[jmax] - accs[jmin]

    print(f"\n{'='*78}\n{cell}   ({len(items)} items, {len(providers)} providers)\n{'='*78}")
    print(f"{'provider':<22}{'acc':>8}{'n_calls':>9}   95% Wilson (n=calls)   95% Wilson (n=items)")
    for j in np.argsort(-accs):
        lo_c, hi_c = wilson(accs[j], dens[j])
        n_items_j = int((N[:, j] > 0).sum())
        lo_i, hi_i = wilson(accs[j], n_items_j)
        star = "  <-- Provider C" if providers[j] == PROVIDER_C else ""
        print(f"{providers[j]:<22}{accs[j]*100:7.2f}%{int(dens[j]):9d}   "
              f"[{lo_c*100:5.2f}, {hi_c*100:5.2f}]        [{lo_i*100:5.2f}, {hi_i*100:5.2f}]{star}")

    print(f"\nobserved max-min spread: {spread*100:.2f} pp "
          f"({providers[jmax]} vs {providers[jmin]})")

    # ---- paired bootstrap on the extreme pair (Task 2)
    boot = paired_bootstrap_gap(A, N, jmax, jmin)
    lo95, hi95 = np.percentile(boot, [2.5, 97.5])
    lo90, hi90 = np.percentile(boot, [5.0, 95.0])
    se_paired = float(boot.std(ddof=1))

    # unpaired SE for the same pair, as the paper effectively assumes
    pa, pb = accs[jmax], accs[jmin]
    na, nb = dens[jmax], dens[jmin]
    se_unpaired = float(np.sqrt(pa * (1 - pa) / na + pb * (1 - pb) / nb))

    print(f"\n-- Task 2: paired item-level bootstrap on the extreme pair (10k resamples)")
    print(f"   gap = {spread*100:.2f} pp")
    print(f"   95% CI [{lo95*100:6.2f}, {hi95*100:6.2f}] pp   -> "
          f"{'EXCLUDES 0 (separated)' if lo95 > 0 or hi95 < 0 else 'includes 0 (not separated)'}")
    print(f"   90% CI [{lo90*100:6.2f}, {hi90*100:6.2f}] pp")
    print(f"   SE paired   = {se_paired*100:.3f} pp")
    print(f"   SE unpaired = {se_unpaired*100:.3f} pp   "
          f"(ratio paired/unpaired = {se_paired/se_unpaired:.2f})")

    # ---- TOST + MDE (Task 1)
    achieved = max(abs(lo90), abs(hi90))
    print(f"\n-- Task 1: TOST / minimum detectable effect")
    for delta in (0.03, 0.05):
        ok = (lo90 > -delta) and (hi90 < delta)
        print(f"   TOST @ margin {delta*100:.0f} pp: "
              f"{'EQUIVALENCE ESTABLISHED' if ok else 'NOT established'} "
              f"(90% CI within +/-{delta*100:.0f} pp? {'yes' if ok else 'no'})")
    print(f"   smallest margin the data supports: +/-{achieved*100:.2f} pp")
    print(f"     -> we can rule out extreme-pair differences larger than "
          f"{achieved*100:.2f} pp, and no smaller.")

    mde_paired = (Z_975 + Z_80) * se_paired
    mde_unpaired = (Z_975 + Z_80) * se_unpaired
    print(f"   MDE @80% power, alpha=.05 (paired)   = {mde_paired*100:.2f} pp")
    print(f"   MDE @80% power, alpha=.05 (unpaired) = {mde_unpaired*100:.2f} pp")

    # effective sample size / design effect
    n_items = int((N[:, jmax] > 0).sum())
    n_calls = int(dens[jmax])
    deff = (se_paired / se_unpaired) ** 2
    print(f"\n   n_calls={n_calls}, n_items={n_items} (ratio {n_calls/n_items:.1f}x); "
          f"design effect on the gap = {deff:.2f}")
    return {"cell": cell, "spread": spread, "achieved": achieved,
            "mde_paired": mde_paired, "ci95": (lo95, hi95)}


# --------------------------------------------------------------------------
# Task 3: peer FCC on MMLU/8B cap-hits
# --------------------------------------------------------------------------

def icc_1_1(X: np.ndarray) -> float:
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
        return float("nan")
    return (msb - msw) / denom


def boot_icc(X, b=N_BOOT, seed=SEED):
    n = X.shape[0]
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(b):
        v = icc_1_1(X[rng.integers(0, n, n)])
        if not np.isnan(v):
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def event_matrix(rows, provider, fn):
    cell = defaultdict(dict)
    for r in rows:
        if r["provider_label"] != provider:
            continue
        cell[r["item_id"]][r["repeat"]] = fn(r)
    reps = sorted({rp for d in cell.values() for rp in d})
    out = []
    for _, d in cell.items():
        vals = [d.get(rp) for rp in reps]
        if len(vals) == len(reps) and not any(v is None for v in vals):
            out.append(vals)
    return np.array(out, dtype=float)


def task3(rows: list[dict]):
    print(f"\n{'='*78}\nTASK 3: MMLU/8B -- is the 0.935 FCC a Provider C property or item difficulty?\n{'='*78}")

    CAP = 64

    def is_caphit(r):
        ct = r.get("completion_tokens")
        return None if ct is None else float(ct >= CAP)

    def is_unparseable(r):
        p = r.get("parse") or {}
        return float(p.get("path") == "unparseable" or p.get("parsed") is None)

    def is_caphit_unparseable(r):
        c = is_caphit(r)
        return None if c is None else float(c > 0 and is_unparseable(r) > 0)

    defs = [
        ("cap-hit (completion_tokens>=64)", is_caphit),
        ("unparseable answer", is_unparseable),
        ("cap-hit AND unparseable", is_caphit_unparseable),
    ]

    providers = sorted({r["provider_label"] for r in rows})
    for label, fn in defs:
        print(f"\n--- event: {label}")
        print(f"{'provider':<22}{'rate':>8}{'n_items':>9}{'FCC':>10}   95% CI")
        for pv in providers:
            X = event_matrix(rows, pv, fn)
            if X.size == 0:
                print(f"{pv:<22}{'--':>8}{0:>9}{'n/a':>10}")
                continue
            rate = X.mean()
            v = icc_1_1(X)
            if np.isnan(v):
                ci = "undefined (zero variance)"
                vs = "undefined"
            else:
                lo, hi = boot_icc(X)
                ci = f"[{lo:.3f}, {hi:.3f}]"
                vs = f"{v:.3f}"
            star = "  <-- Provider C" if pv == PROVIDER_C else ""
            print(f"{pv:<22}{rate*100:7.1f}%{X.shape[0]:9d}{vs:>10}   {ci}{star}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root")
    args = ap.parse_args()

    print("Re-analysis of canonical results (no new API calls)")
    print(f"bootstrap: {N_BOOT} resamples, seed {SEED}")

    for cell, (pv, arc, excl) in CELLS.items():
        path = resolve(pv, arc, args.data_root)
        if not Path(path).exists():
            print(f"\n!! MISSING {cell}: {path}")
            continue
        rows = load(path)
        task1_and_2(cell, rows, excl)
        if cell == "MMLU/8B":
            task3(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
