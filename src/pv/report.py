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

from .openrouter import is_silent_truncation
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
            pp = r.get("parse") or {}
            # benchmark-defensive: letter/delimiter benchmarks store 'path'; code grading
            # (HumanEval) stores 'exec_status' (pass/fail/timeout/error) and has no 'path'.
            key = pp.get("path") or pp.get("exec_status")
            if key:
                p["parse_paths"][key] += 1
        elif reason == "generation_error":
            p["gen_err"] += 1
        elif reason == "provider_readback_mismatch":
            p["mismatch"] += 1
        else:
            p["req_failed"] += 1
    return by


def print_table(jsonl: str | Path, *, title: str, exclude: set[str] | None = None) -> dict:
    by = load_provider_stats(jsonl)
    exclude = exclude or set()
    print("\n" + "=" * 104)
    print(title)
    if exclude:
        print(f"(excluded from this table: {sorted(exclude)})")
    print("=" * 104)
    hdr = (f"{'provider':<22}{'acc':>7}{'95% Wilson CI':>16}{'n_ok/val':>10}"
           f"{'gen_err(rate)':>15}{'mism':>6}{'flag':>6}{'avg_ct':>8}{'$':>9}")
    print(hdr)
    print("  acc = correct/valid (excludes gen_err + mismatch from num AND denom); "
          "flag = flagged parse paths")
    print("-" * len(hdr))
    total_cost = 0.0
    total_correct = total_valid = total_n = 0
    tot_err = tot_mis = tot_flag = 0
    for prov in sorted(by):
        if prov in exclude:
            continue
        p = by[prov]
        pt, lo, hi = wilson_ci(p["correct"], p["valid"])
        acc_s = f"{pt*100:.1f}%" if p["valid"] else "n/a"
        ci_s = f"[{lo*100:.1f},{hi*100:.1f}]" if p["valid"] else "-"
        flagged = sum(v for k, v in p["parse_paths"].items() if k.endswith("_flagged"))
        avg_ct = (p["ctok"] / p["valid"]) if p["valid"] else 0.0
        err_rate = (p["gen_err"] / p["n"] * 100) if p["n"] else 0.0
        err_s = f"{p['gen_err']}({err_rate:.1f}%)"
        nok_s = f"{p['correct']}/{p['valid']}"
        total_cost += p["cost"]; total_correct += p["correct"]; total_valid += p["valid"]
        total_n += p["n"]; tot_err += p["gen_err"]; tot_mis += p["mismatch"]; tot_flag += flagged
        print(f"{prov:<22}{acc_s:>7}{ci_s:>16}{nok_s:>10}"
              f"{err_s:>15}{p['mismatch']:>6}{flagged:>6}{avg_ct:>8.0f}{p['cost']:>9.4f}")
    print("-" * len(hdr))
    ppt, plo, phi = wilson_ci(total_correct, total_valid)
    pooled_acc = f"{ppt*100:.1f}%" if total_valid else "n/a"
    pooled_ci = f"[{plo*100:.1f},{phi*100:.1f}]" if total_valid else "-"
    pooled_err = f"{tot_err}({tot_err/total_n*100:.1f}%)" if total_n else "0"
    print(f"{'POOLED':<22}{pooled_acc:>7}{pooled_ci:>16}{f'{total_correct}/{total_valid}':>10}"
          f"{pooled_err:>15}{tot_mis:>6}{tot_flag:>6}{'':>8}{total_cost:>9.4f}")
    # Parse-path detail (audit trail) under the table.
    print("\nparse-path distribution per provider (flagged = needs manual audit):")
    for prov in sorted(by):
        pp = dict(by[prov]["parse_paths"])
        if pp:
            print(f"  {prov:<22} {pp}")
    return by


def print_h1_check(jsonl: str | Path, *, exclude: set[str] | None = None,
                   threshold_pp: float = 3.0) -> None:
    """Quick H1 read: clean-accuracy spread + which provider Wilson CIs are non-overlapping.

    NOTE: the pre-registered H1 decision uses the paired-bootstrap CI on the max-min spread
    (10k resamples, PREREGISTRATION §7) — that lives in the analysis stage. This Wilson-CI
    non-overlap view is a fast proxy for the write-up's spread narrative.
    """
    by = load_provider_stats(jsonl)
    exclude = exclude or set()
    rows = []
    for prov in sorted(by):
        if prov in exclude:
            continue
        p = by[prov]
        if p["valid"] == 0:
            continue
        pt, lo, hi = wilson_ci(p["correct"], p["valid"])
        rows.append((prov, pt, lo, hi, p["correct"], p["valid"]))

    print("\n" + "=" * 92)
    print(f"H1 QUICK CHECK — clean-accuracy spread across {len(rows)} providers")
    print("=" * 92)
    if not rows:
        print("(no valid providers)")
        return
    accs = [r[1] for r in rows]
    hi_prov = max(rows, key=lambda r: r[1])
    lo_prov = min(rows, key=lambda r: r[1])
    spread = (max(accs) - min(accs)) * 100
    print(f"  max = {hi_prov[0]} {hi_prov[1]*100:.1f}%   min = {lo_prov[0]} {lo_prov[1]*100:.1f}%")
    print(f"  spread (max-min) = {spread:.2f} pp   (pre-registered 'meaningful' threshold "
          f"= {threshold_pp} pp AND bootstrap CI excludes 0)")
    print(f"  spread >= {threshold_pp}pp? {'YES' if spread >= threshold_pp else 'NO'}  "
          "(bootstrap CI test done in analysis stage)")
    # Pairwise non-overlapping Wilson CIs
    nonoverlap = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            if a[3] < b[2] or b[3] < a[2]:  # a.hi < b.lo or b.hi < a.lo
                nonoverlap.append((a, b))
    print(f"\n  provider pairs with NON-overlapping 95% Wilson CIs: {len(nonoverlap)}")
    for a, b in nonoverlap:
        print(f"    {a[0]} [{a[2]*100:.1f},{a[3]*100:.1f}]  vs  "
              f"{b[0]} [{b[2]*100:.1f},{b[3]*100:.1f}]")
    if not nonoverlap:
        print("    (none — all provider CIs overlap at the Wilson level)")


def final_provider_stats(jsonl: str | Path) -> dict[str, dict]:
    """Reclassify rows under the FINAL truncation policy (PREREGISTRATION §20-21).

    Applies the classification to already-collected rows (which predate silent-truncation
    detection), so the same JSONL yields the final numbers without re-running:
      * overt_truncation  = collected generation_error (finish=='error')
      * silent_truncation = valid finish=='stop' but incomplete (no ####, mid-sentence)
      * length_truncation = valid finish=='length' with no #### (our max_tokens cap; not a
                            provider reliability fault)
      * clean            = everything else that is valid -> graded on `correct`
    Truncations of all three kinds are excluded from accuracy num+denom.
    """
    from collections import defaultdict
    def blank():
        return {"n": 0, "clean": 0, "correct": 0, "silent_trunc": 0, "length_trunc": 0,
                "overt": 0, "mismatch": 0, "req_failed": 0, "cost": 0.0, "ctok": 0}
    by = defaultdict(blank)
    for line in open(jsonl):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        p = by[r["provider_label"]]
        p["n"] += 1
        if r.get("cost_usd"):
            p["cost"] += float(r["cost_usd"])
        if not r.get("valid"):
            reason = r.get("invalid_reason")
            if reason == "generation_error":
                p["overt"] += 1
            elif reason == "provider_readback_mismatch":
                p["mismatch"] += 1
            else:
                p["req_failed"] += 1
            continue
        # stored-valid row: reclassify
        text = r.get("completion_text")
        fin = r.get("finish_reason")
        if is_silent_truncation(fin, text):
            p["silent_trunc"] += 1
        elif fin == "length" and not (text and "####" in text):
            p["length_trunc"] += 1
        else:
            p["clean"] += 1
            if r.get("correct"):
                p["correct"] += 1
            if r.get("completion_tokens"):
                p["ctok"] += r["completion_tokens"]
    return by


def print_final_table(jsonl: str | Path, *, title: str, exclude: set[str] | None = None) -> dict:
    by = final_provider_stats(jsonl)
    exclude = exclude or set()
    print("\n" + "=" * 96)
    print(title)
    print("(clean completions only; silent/overt/length truncations excluded from num AND denom)")
    if exclude:
        print(f"(providers excluded: {sorted(exclude)})")
    print("=" * 96)
    hdr = f"{'provider':<22}{'acc':>7}{'95% Wilson CI':>16}{'correct/clean':>15}{'avg_ct':>8}{'$':>9}"
    print(hdr)
    print("-" * len(hdr))
    tc = tcl = 0
    tcost = 0.0
    accs = []
    for prov in sorted(by):
        if prov in exclude:
            continue
        p = by[prov]
        if p["clean"] == 0:
            continue
        pt, lo, hi = wilson_ci(p["correct"], p["clean"])
        accs.append((prov, pt, lo, hi))
        avg_ct = p["ctok"] / p["clean"]
        tc += p["correct"]; tcl += p["clean"]; tcost += p["cost"]
        ratio = f"{p['correct']}/{p['clean']}"
        ci = f"[{lo*100:.1f},{hi*100:.1f}]"
        print(f"{prov:<22}{pt*100:>6.1f}%{ci:>16}{ratio:>15}{avg_ct:>8.0f}{p['cost']:>9.4f}")
    print("-" * len(hdr))
    ppt, plo, phi = wilson_ci(tc, tcl)
    print(f"{'POOLED':<22}{ppt*100:>6.1f}%{f'[{plo*100:.1f},{phi*100:.1f}]':>16}"
          f"{f'{tc}/{tcl}':>15}{'':>8}{tcost:>9.4f}")
    if accs:
        hi_p = max(accs, key=lambda a: a[1]); lo_p = min(accs, key=lambda a: a[1])
        spread = (hi_p[1] - lo_p[1]) * 100
        print(f"\nspread (max-min) = {spread:.2f} pp  "
              f"[{hi_p[0]} {hi_p[1]*100:.1f}% .. {lo_p[0]} {lo_p[1]*100:.1f}%]  "
              f"=> H1 'meaningful' (>=3pp): {'YES' if spread >= 3 else 'NO'}")
    return by


def print_reliability_table(jsonl: str | Path, *, exclude: set[str] | None = None) -> None:
    """Two provider failure modes side by side (PREREGISTRATION §16 axis 2)."""
    by = final_provider_stats(jsonl)
    exclude = exclude or set()
    print("\n" + "=" * 96)
    print("RELIABILITY — provider failure modes (silent vs overt truncation, + our-cap length)")
    print("=" * 96)
    hdr = (f"{'provider':<22}{'n':>6}{'overt(err)':>13}{'silent(stop)':>14}"
           f"{'length(cap)':>13}{'mism':>6}")
    print(hdr)
    print("  overt = finish=error | silent = finish=stop but truncated | length = hit max_tokens")
    print("-" * len(hdr))
    for prov in sorted(by):
        if prov in exclude:
            continue
        p = by[prov]
        n = p["n"]
        overt = f"{p['overt']}({p['overt']/n*100:.1f}%)" if n else "0"
        silent = f"{p['silent_trunc']}({p['silent_trunc']/n*100:.1f}%)" if n else "0"
        length = f"{p['length_trunc']}({p['length_trunc']/n*100:.1f}%)" if n else "0"
        print(f"{prov:<22}{n:>6}{overt:>13}{silent:>14}{length:>13}{p['mismatch']:>6}")


def print_reliability_stored(jsonl: str | Path) -> None:
    """Reliability from STORED invalid_reason/invalid_subtype (authoritative for runs collected
    under the benchmark-aware client). Shows overt vs silent truncation + request_failed."""
    from collections import defaultdict
    by = defaultdict(lambda: {"n": 0, "overt": 0, "silent": 0, "req_failed": 0, "mism": 0,
                              "ct": 0, "ct_n": 0})
    for line in open(jsonl):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        p = by[r["provider_label"]]
        p["n"] += 1
        if r.get("valid"):
            if r.get("completion_tokens"):
                p["ct"] += r["completion_tokens"]; p["ct_n"] += 1
            continue
        reason, sub = r.get("invalid_reason"), r.get("invalid_subtype")
        if reason == "generation_error" and sub == "overt_truncation":
            p["overt"] += 1
        elif reason == "generation_error" and sub == "silent_truncation":
            p["silent"] += 1
        elif reason == "generation_error":
            p["overt"] += 1   # legacy rows (pre-subtype) = overt (finish=error)
        elif reason == "provider_readback_mismatch":
            p["mism"] += 1
        else:
            p["req_failed"] += 1
    print("\n" + "=" * 94)
    print("RELIABILITY (stored subtypes) — overt vs silent truncation + avg output tokens per provider")
    print("=" * 94)
    hdr = (f"{'provider':<22}{'n':>6}{'avg_ct':>8}{'overt(err)':>13}{'silent(stop)':>14}"
           f"{'req_fail':>10}{'mism':>6}")
    print(hdr); print("-" * len(hdr))
    for prov in sorted(by):
        p = by[prov]
        n = p["n"]
        avg_ct = p["ct"] / p["ct_n"] if p["ct_n"] else 0
        overt = f"{p['overt']}({p['overt']/n*100:.0f}%)" if n else "0"
        silent = f"{p['silent']}({p['silent']/n*100:.0f}%)" if n else "0"
        print(f"{prov:<22}{n:>6}{avg_ct:>8.0f}{overt:>13}{silent:>14}{p['req_failed']:>10}{p['mism']:>6}")


def print_invalid_breakdown(jsonl: str | Path) -> None:
    """Invalid cells by provider x reason. request_failed is sub-split by last HTTP status
    (e.g. 429 rate-limit vs 5xx) so exhausted-retry/rate-limit cases are distinguishable from
    generation_error and read-back mismatch."""
    from collections import defaultdict
    REASONS = ["generation_error", "provider_readback_mismatch", "request_failed",
               "empty_response", "other"]
    by = defaultdict(lambda: {r: 0 for r in REASONS})
    http_for_failed = defaultdict(int)
    totals = {r: 0 for r in REASONS}
    n_rows = 0
    for line in open(jsonl):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        n_rows += 1
        if r.get("valid"):
            continue
        reason = r.get("invalid_reason")
        bucket = reason if reason in REASONS else "other"
        by[r["provider_label"]][bucket] += 1
        totals[bucket] += 1
        if bucket == "request_failed":
            http_for_failed[r.get("http_status")] += 1

    print("\n" + "=" * 92)
    print("INVALID BREAKDOWN  (by provider x reason)")
    print("=" * 92)
    hdr = (f"{'provider':<22}{'gen_error':>11}{'readback_mis':>14}"
           f"{'req_failed':>12}{'empty_200':>10}{'other':>7}{'invalid':>9}")
    print(hdr)
    print("-" * len(hdr))
    for prov in sorted(by):
        d = by[prov]
        tot = sum(d.values())
        print(f"{prov:<22}{d['generation_error']:>11}{d['provider_readback_mismatch']:>14}"
              f"{d['request_failed']:>12}{d['empty_response']:>10}{d['other']:>7}{tot:>9}")
    print("-" * len(hdr))
    grand = sum(totals.values())
    print(f"{'TOTAL':<22}{totals['generation_error']:>11}"
          f"{totals['provider_readback_mismatch']:>14}{totals['request_failed']:>12}"
          f"{totals['empty_response']:>10}{totals['other']:>7}{grand:>9}")
    rate = (grand / n_rows * 100) if n_rows else 0.0
    print(f"\nTotal invalid = {grand}/{n_rows} = {rate:.1f}%  (durable count — supersedes any "
          "earlier counter-based number)")
    if http_for_failed:
        print(f"request_failed by last HTTP status: {dict(http_for_failed)}  "
              "(429 = rate-limit/exhausted-retry; 5xx = provider error)")


def print_invalid_over_time(jsonl: str | Path, n_buckets: int = 10) -> None:
    """Bucket invalids over the run to detect mid-run clustering (rate-limit / outage).
    Buckets by file order (= cell processing order) AND by wall-clock request time."""
    rows = []
    for line in open(jsonl):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    n = len(rows)
    if not n:
        print("\n(no rows to bucket)")
        return

    print("\n" + "=" * 92)
    print(f"INVALID OVER TIME  ({n_buckets} buckets)")
    print("=" * 92)

    # (a) by processing order (index in file)
    print("by processing order (cell index):")
    size = max(1, (n + n_buckets - 1) // n_buckets)
    for b in range(0, n, size):
        chunk = rows[b:b + size]
        inv = sum(1 for r in chunk if not r.get("valid"))
        bar = "#" * round(inv / max(1, len(chunk)) * 40)
        print(f"  cells {b:>5}-{b+len(chunk)-1:<5}  invalid {inv:>4}/{len(chunk):<4} "
              f"{inv/len(chunk)*100:>5.1f}%  {bar}")

    # (b) by wall-clock request time
    times = [r.get("request_utc") for r in rows if r.get("request_utc")]
    if times and min(times) != max(times):
        lo, hi = min(times), max(times)
        # lexicographic ISO-8601 ordering is chronological; bucket by even index slices of sorted time
        order = sorted(range(n), key=lambda i: rows[i].get("request_utc") or "")
        print(f"\nby wall-clock request_utc ({lo} -> {hi}):")
        bsize = max(1, (n + n_buckets - 1) // n_buckets)
        for b in range(0, n, bsize):
            idxs = order[b:b + bsize]
            inv = sum(1 for i in idxs if not rows[i].get("valid"))
            t0 = rows[idxs[0]].get("request_utc")
            t1 = rows[idxs[-1]].get("request_utc")
            bar = "#" * round(inv / max(1, len(idxs)) * 40)
            print(f"  {t0} .. {t1}  invalid {inv:>4}/{len(idxs):<4} "
                  f"{inv/len(idxs)*100:>5.1f}%  {bar}")
