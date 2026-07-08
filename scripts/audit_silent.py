#!/usr/bin/env python3
"""Audit silent_truncation flags: REAL truncation vs FALSE POSITIVE (complete answer, wrong format).

The GSM8K completeness screen (is_complete = has #### OR ends in terminal punctuation) FALSE-POSITIVES
on complete answers that state the result without #### and end in a digit (e.g. "The final answer is:
109"). This audit re-classifies each silent-flagged completion:
  * LIKELY-COMPLETE (false positive): contains a stated final answer near the end.
  * LIKELY-TRUNCATED (real): ends mid-clause (operator/word), no stated answer.
So a "second truncator" claim is only credited on LIKELY-TRUNCATED cases.

Usage:  python scripts/audit_silent.py <jsonl> [<jsonl> ...]
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict

# A stated final answer near the end => the model finished, just not in #### format.
# Allow filler ("is:", ":", "= ") between the answer word and the number.
_ANSWER_RE = re.compile(
    r"((final\s+)?answer\b[^0-9\n]{0,15}|=\s*)\$?-?[\d,]+\.?\d*\s*[.)]?\s*$", re.I)
# Ends mid-clause: trailing operator / equals / open word (no number) => genuinely cut off.
_TRUNC_TAIL_RE = re.compile(r"[=+\-*/(]\s*$")


def classify(text: str | None) -> str:
    t = (text or "").rstrip()
    if not t:
        return "empty"
    tail = t[-80:]
    if _ANSWER_RE.search(tail):
        return "likely_complete"      # false positive
    if _TRUNC_TAIL_RE.search(t):
        return "likely_truncated"     # real
    # ends with a bare number but no concluding phrase -> ambiguous, lean truncated (mid-calc)
    return "ambiguous"


def main() -> int:
    paths = sys.argv[1:]
    if not paths:
        print("usage: audit_silent.py <jsonl> ...", file=sys.stderr); return 2
    by = defaultdict(lambda: defaultdict(int))
    examples = defaultdict(list)
    for p in paths:
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("invalid_subtype") != "silent_truncation":
                continue
            model = (r.get("sweep_model") or r.get("model_slug") or "?").split("/")[-1]
            key = f"{model} | {r['provider_label']}"
            cls = classify(r.get("completion_text"))
            by[key][cls] += 1
            if len(examples[key]) < 2:
                examples[key].append((cls, (r.get("completion_text") or "")[-90:]))

    print("SILENT-FLAG AUDIT — real truncation vs false positive (complete answer, non-#### format)")
    print("=" * 92)
    for key in sorted(by):
        d = by[key]
        real = d.get("likely_truncated", 0) + d.get("ambiguous", 0)
        fp = d.get("likely_complete", 0)
        print(f"{key:<44} real~{real:<4} false_pos={fp:<4} {dict(d)}")
        for cls, ex in examples[key]:
            print(f"    [{cls}] ...{ex!r}")
    print("\nOnly LIKELY-TRUNCATED (+ audited ambiguous) count as genuine truncation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
