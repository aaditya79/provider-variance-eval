#!/usr/bin/env python3
"""GATE: prove provider pinning + read-back on ONE live call before building anything else.

What it does (plan §4, "Start here" step 3):
  1. Enumerate providers for the chosen model (live).
  2. Pin EXACTLY one provider (order=[slug], allow_fallbacks=false, require_parameters=true).
  3. Make ONE real chat call with a trivial prompt.
  4. Read back the served provider and ASSERT it matches the pin.
  5. Print the full record (pinned vs returned, tokens, cost, latency, raw completion).

Exit code 0 only if the read-back matches. Optionally also probes a second provider and
the ':floor' route for a fuller picture.

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  python scripts/probe_pinning.py --model meta-llama/llama-3.3-70b-instruct
  python scripts/probe_pinning.py --model <slug> --provider deepinfra
  python scripts/probe_pinning.py --model <slug> --all-providers   # one call per provider
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.config import load_config, require_api_key  # noqa: E402
from pv.openrouter import OpenRouterClient, normalize_provider  # noqa: E402

PROMPT = [{"role": "user", "content": "What is 2 + 2? Reply with only the number."}]


def _candidate_slugs(client: OpenRouterClient, model_slug: str) -> list[tuple[str, str]]:
    """Return [(display_name, normalized_slug)] for the model's providers."""
    raw = client.list_endpoints(model_slug)
    eps = (raw.get("data") or {}).get("endpoints") or []
    out = []
    for ep in eps:
        name = ep.get("provider_name") or ep.get("name")
        if name:
            out.append((name, ep.get("tag") or normalize_provider(name)))
    return out


def _probe_one(client: OpenRouterClient, model_slug: str, provider: str) -> bool:
    print(f"\n--- pinning provider: {provider!r} ---")
    res = client.chat_completion(
        model_slug=model_slug,
        messages=PROMPT,
        max_tokens=16,
        temperature=0.0,
        top_p=1.0,
        pinned_provider=provider,
        route_mode="pinned",
    )
    d = res.to_jsonl_dict()
    # Print the salient fields, then the full record.
    print(f"  pinned_provider   : {res.pinned_provider}")
    print(f"  returned_provider : {res.returned_provider}  (norm: {res.returned_provider_slug})")
    print(f"  provider_match    : {res.provider_match}")
    print(f"  valid             : {res.valid}   invalid_reason: {res.invalid_reason}")
    print(f"  finish_reason     : {res.finish_reason}")
    print(f"  completion        : {res.completion_text!r}")
    print(f"  tokens (p/c/t)    : {res.prompt_tokens}/{res.completion_tokens}/{res.total_tokens}")
    print(f"  cost_usd          : {res.cost_usd}")
    print(f"  latency_s         : {res.latency_s}")
    print(f"  attempts          : {res.attempts}   http_status: {res.http_status}")
    if res.error:
        print(f"  ERROR             : {res.error}")
    print("  full record:")
    print("    " + json.dumps(d, indent=2).replace("\n", "\n    "))
    return bool(res.provider_match)


def _probe_floor(client: OpenRouterClient, model_slug: str) -> None:
    print("\n--- :floor route (cheapest; provider is whatever resolves) ---")
    res = client.chat_completion(
        model_slug=model_slug,
        messages=PROMPT,
        max_tokens=16,
        temperature=0.0,
        top_p=1.0,
        route_mode="floor",
    )
    print(f"  returned_provider : {res.returned_provider}")
    print(f"  cost_usd          : {res.cost_usd}   completion: {res.completion_text!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="model slug, e.g. meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--provider", help="provider slug to pin; default = first enumerated")
    ap.add_argument("--all-providers", action="store_true", help="probe every provider once")
    ap.add_argument("--floor", action="store_true", help="also probe the :floor route")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    try:
        api_key = require_api_key()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2

    with OpenRouterClient(
        api_key,
        timeout_s=cfg["run"]["request_timeout_s"],
        max_attempts=cfg["retry"]["max_attempts"],
        backoff_base_s=cfg["retry"]["backoff_base_s"],
        backoff_cap_s=cfg["retry"]["backoff_cap_s"],
        retry_on_status=tuple(cfg["retry"]["retry_on_status"]),
    ) as client:
        cands = _candidate_slugs(client, args.model)
        print(f"Model {args.model} is served by {len(cands)} provider(s):")
        for name, slug in cands:
            print(f"  - {name}  (pin as: {slug})")

        if not cands:
            print("No providers found — cannot probe.", file=sys.stderr)
            return 2

        if args.all_providers:
            targets = [slug for _, slug in cands]
        elif args.provider:
            targets = [args.provider]
        else:
            targets = [cands[0][1]]

        results = [_probe_one(client, args.model, t) for t in targets]

        if args.floor:
            _probe_floor(client, args.model)

    ok = all(results)
    print("\n" + ("=" * 60))
    if ok:
        print(f"GATE PASS: read-back matched the pin for all {len(results)} probe(s).")
    else:
        n_fail = sum(1 for r in results if not r)
        print(f"GATE FAIL: {n_fail}/{len(results)} probe(s) had a provider read-back mismatch.")
        print("Do NOT proceed — investigate before collecting data.")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
