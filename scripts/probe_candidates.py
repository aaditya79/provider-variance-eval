#!/usr/bin/env python3
"""Snapshot + LIVENESS-probe candidate second models (PREREGISTRATION §13, §23).

For each candidate model: enumerate its provider endpoints (slug/tag, canonical?, disclosed quant,
ctx, price) AND do a 1-call pinned liveness probe per endpoint (so we don't pick a model with dead
endpoints, as sambanova/bf16 just 404'd). Reports per-model count of CANONICAL providers that are
actually ALIVE; we want a second model with >= 5.

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  python scripts/probe_candidates.py           # default candidate list
  python scripts/probe_candidates.py meta-llama/llama-3.1-70b-instruct qwen/qwen-2.5-72b-instruct
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.config import load_config, require_api_key  # noqa: E402
from pv.openrouter import OpenRouterClient  # noqa: E402

DEFAULT_CANDIDATES = [
    "meta-llama/llama-3.1-70b-instruct",
    "mistralai/mixtral-8x7b-instruct",
    "qwen/qwen-2.5-72b-instruct",          # known ~2 providers — confirm
    "meta-llama/llama-3.1-8b-instruct",    # very widely multi-provider-served (coverage safety)
]

_QUANTS = {"fp4", "fp6", "fp8", "fp16", "bf16", "int4", "int8", "fp32", "fp8-dynamic"}
PROBE = [{"role": "user", "content": "What is 2 + 2? Reply with only the number."}]


def is_canonical(tag: str) -> bool:
    """Canonical = base provider, optionally with a QUANT suffix. Variant = turbo/free/region tag."""
    low = tag.lower()
    if "turbo" in low or "free" in low:
        return False
    parts = tag.split("/")
    if len(parts) == 1:
        return True
    return parts[1] in _QUANTS  # quant suffix = canonical; anything else (region etc.) = variant


def main() -> int:
    cands = sys.argv[1:] or DEFAULT_CANDIDATES
    cfg = load_config("config.yaml")
    try:
        api_key = require_api_key()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2

    summary = []
    with OpenRouterClient(
        api_key, timeout_s=cfg["run"]["request_timeout_s"],
        max_attempts=cfg["retry"]["max_attempts"],
        backoff_base_s=cfg["retry"]["backoff_base_s"],
        backoff_cap_s=cfg["retry"]["backoff_cap_s"],
        retry_on_status=tuple(cfg["retry"]["retry_on_status"]),
    ) as client:
        for model in cands:
            print("\n" + "=" * 100)
            print(f"CANDIDATE: {model}")
            print("=" * 100)
            try:
                raw = client.list_endpoints(model)
            except Exception as e:  # noqa: BLE001
                print(f"  ENUMERATION FAILED ({e!r}) — model slug may be wrong or unavailable.")
                summary.append((model, 0, 0, "enumeration failed"))
                continue
            eps = (raw.get("data") or {}).get("endpoints") or []
            hdr = (f"{'slug/tag':<26}{'canon':>6}{'quant':>9}{'ctx':>9}"
                   f"{'in$/M':>9}{'out$/M':>9}  {'LIVE':<6}{'served':<16}{'finish'}")
            print(hdr); print("-" * len(hdr))
            canon_total = canon_alive = 0
            for ep in eps:
                tag = ep.get("tag") or ep.get("provider_name")
                name = ep.get("provider_name")
                canon = is_canonical(tag or "")
                canon_total += canon
                pr = ep.get("pricing") or {}
                def perM(x):
                    return f"{float(x)*1e6:.2f}" if x not in (None, "") else "?"
                # 1-call liveness probe, pinned, read-back against disclosed provider_name
                res = client.chat_completion(
                    model_slug=model, messages=PROBE, max_tokens=16, temperature=0.0, top_p=1.0,
                    pinned_provider=tag, route_mode="pinned", expected_served_name=name,
                )
                live = res.valid and res.completion_text
                if canon and live:
                    canon_alive += 1
                live_s = "OK" if live else (f"x{res.http_status}" if res.http_status else "xERR")
                print(f"{str(tag):<26}{('Y' if canon else '-'):>6}{str(ep.get('quantization')):>9}"
                      f"{str(ep.get('context_length')):>9}{perM(pr.get('prompt')):>9}"
                      f"{perM(pr.get('completion')):>9}  {live_s:<6}{str(res.returned_provider):<16}"
                      f"{res.finish_reason or (res.invalid_reason or '')}")
            print(f"\n  canonical providers: {canon_total} total, {canon_alive} ALIVE "
                  f"({'MEETS' if canon_alive >= 5 else 'below'} >=5 target)")
            summary.append((model, canon_total, canon_alive,
                            "OK" if canon_alive >= 5 else "insufficient"))

    print("\n" + "=" * 100)
    print("SUMMARY — second-model candidates (want >=5 canonical ALIVE)")
    print("=" * 100)
    print(f"{'model':<42}{'canon_total':>12}{'canon_alive':>12}  verdict")
    for m, ct, ca, v in summary:
        print(f"{m:<42}{ct:>12}{ca:>12}  {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
