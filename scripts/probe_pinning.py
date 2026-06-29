#!/usr/bin/env python3
"""GATE: prove provider pinning + read-back DISCRIMINATION on live calls.

A single matching call only shows the label agrees with itself. The real test is whether
the served-provider label actually TRACKS the pin. So this gate pins TWO different providers
for the same model and requires:

  (a) pinned == served on BOTH calls, AND
  (b) the served-provider field DIFFERS between the two pins.

If the served field is identical regardless of which provider we pin, that is a GATE FAIL:
the provider labels cannot be trusted and the whole study is compromised. It is flagged loudly.

Each call also prints the EXACT provider routing block sent, so you can verify
allow_fallbacks:false was present on both requests (no silent rerouting).

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  # auto-pick the first two enumerated providers:
  python scripts/probe_pinning.py --model meta-llama/llama-3.3-70b-instruct
  # or name them explicitly:
  python scripts/probe_pinning.py --model <slug> --providers deepinfra novita
  python scripts/probe_pinning.py --model <slug> --providers deepinfra novita --floor
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.config import load_config, require_api_key  # noqa: E402
from pv.openrouter import (  # noqa: E402
    CallResult,
    OpenRouterClient,
    normalize_provider,
    provider_base_key,
)

PROMPT = [{"role": "user", "content": "What is 2 + 2? Reply with only the number."}]


def _completion_diagnostics(text: str | None) -> None:
    """Print repr + exact byte-level facts so a garbage completion can be told apart
    from a display/escaping artifact. repr() escapes backslashes (each '\\' shows as
    '\\\\'); the byte view below is the ground truth of what the API actually returned."""
    t = text or ""
    b = t.encode("utf-8")
    uniq = sorted(set(t))
    print(f"  completion.repr       : {t!r}")
    print(f"  completion.len_chars  : {len(t)}")
    print(f"  completion.len_bytes  : {len(b)}")
    print(f"  completion.first32_hex: {b[:32].hex(' ')}")
    print(f"  completion.uniq_chars : {uniq!r}"
          + ("  [single repeated char]" if len(uniq) == 1 and len(t) > 1 else ""))


def _candidate_slugs(client: OpenRouterClient, model_slug: str) -> list[tuple[str, str]]:
    """Return [(display_name, slug_to_pin)] for the model's providers."""
    raw = client.list_endpoints(model_slug)
    eps = (raw.get("data") or {}).get("endpoints") or []
    out = []
    for ep in eps:
        name = ep.get("provider_name") or ep.get("name")
        if name:
            out.append((name, ep.get("tag") or normalize_provider(name)))
    return out


def _probe_one(client: OpenRouterClient, model_slug: str, provider: str) -> CallResult:
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
    # Show the EXACT routing block sent — proves allow_fallbacks:false was present.
    print(f"  request.provider sent : {json.dumps(res.request_provider_block)}")
    fb = (res.request_provider_block or {}).get("allow_fallbacks")
    print(f"  allow_fallbacks       : {fb}  "
          f"{'[OK: no fallback possible]' if fb is False else '[WARNING: fallback not disabled]'}")
    print(f"  pinned_provider       : {res.pinned_provider}")
    print(f"  returned_provider     : {res.returned_provider}  (norm: {res.returned_provider_slug})")
    print(f"  provider_match        : {res.provider_match}")
    print(f"  valid                 : {res.valid}   invalid_reason: {res.invalid_reason}")
    print(f"  finish_reason         : {res.finish_reason}")
    _completion_diagnostics(res.completion_text)
    print(f"  tokens (p/c/t)        : {res.prompt_tokens}/{res.completion_tokens}/{res.total_tokens}")
    print(f"  cost_usd              : {res.cost_usd}")
    print(f"  latency_s             : {res.latency_s}   attempts: {res.attempts}   http: {res.http_status}")
    if res.error:
        print(f"  ERROR                 : {res.error}")
    return res


def _probe_floor(client: OpenRouterClient, model_slug: str) -> CallResult:
    print("\n--- :floor route (cheapest; provider is whatever resolves) ---")
    res = client.chat_completion(
        model_slug=model_slug, messages=PROMPT, max_tokens=16,
        temperature=0.0, top_p=1.0, route_mode="floor",
    )
    print(f"  returned_provider : {res.returned_provider}")
    print(f"  cost_usd          : {res.cost_usd}   completion: {res.completion_text!r}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="model slug")
    ap.add_argument("--providers", nargs=2, metavar=("P1", "P2"),
                    help="two provider slugs to pin; default = first two enumerated")
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

        if args.providers:
            p1, p2 = args.providers
        else:
            if len(cands) < 2:
                print("\nGATE FAIL: discrimination needs >=2 providers; "
                      f"only {len(cands)} available for this model.", file=sys.stderr)
                return 1
            p1, p2 = cands[0][1], cands[1][1]

        if normalize_provider(p1) == normalize_provider(p2):
            print(f"\nGATE FAIL: the two pins are the same provider ({p1!r}). "
                  "Choose two distinct providers.", file=sys.stderr)
            return 1

        print(f"\nDiscrimination gate: pinning {p1!r} then {p2!r} for the SAME model.")
        print("Exact prompt sent on every probe call (messages array):")
        print("  " + json.dumps(PROMPT))
        print(f"  decoding: max_tokens=16, temperature=0.0, top_p=1.0")
        r1 = _probe_one(client, args.model, p1)
        r2 = _probe_one(client, args.model, p2)

        floor_res = _probe_floor(client, args.model) if args.floor else None
        enumerated_norms = {normalize_provider(name): name for name, _ in cands}

    # ---- evaluate the gate -----------------------------------------------------------
    both_match = bool(r1.provider_match) and bool(r2.provider_match)
    both_fallbacks_off = (
        (r1.request_provider_block or {}).get("allow_fallbacks") is False
        and (r2.request_provider_block or {}).get("allow_fallbacks") is False
    )
    served_differs = (
        r1.returned_provider_slug is not None
        and r2.returned_provider_slug is not None
        and r1.returned_provider_slug != r2.returned_provider_slug
    )

    print("\n" + "=" * 64)
    print("DISCRIMINATION GATE RESULT")
    print("=" * 64)
    for i, (pin, res) in enumerate(((p1, r1), (p2, r2)), start=1):
        print(f"CALL {i}:")
        print(f"  pinned_raw   : {res.pinned_provider!r}")
        print(f"  served_raw   : {res.returned_provider!r}   "
              "(verbatim from API, sub-tag NOT stripped)")
        print(f"  served_norm  : {res.returned_provider_slug!r}")
        print(f"  compared     : pinned_base {provider_base_key(res.pinned_provider or '')!r}"
              f" == served_base {provider_base_key(res.returned_provider or '')!r}"
              f"  -> {res.provider_match}")
        print(f"  match        : {res.provider_match}")
    print("-" * 64)
    print(f"  (a) pinned == served on both : {both_match}")
    print(f"  (b) served_raw differs       : {served_differs}   "
          f"({r1.returned_provider!r} vs {r2.returned_provider!r})")
    print(f"  allow_fallbacks:false on both: {both_fallbacks_off}")
    if floor_res is not None:
        floor_norm = floor_res.returned_provider_slug
        in_enum = floor_norm in enumerated_norms if floor_norm else False
        which = enumerated_norms.get(floor_norm) if in_enum else None
        print(f"  :floor resolved to           : {floor_res.returned_provider!r} "
              f"(norm {floor_norm!r})")
        print(f"      is it one of the enumerated providers? {in_enum}"
              + (f"  -> {which!r}" if which else "  [NOT in enumerated list]"))
    print("=" * 64)

    if both_match and served_differs and both_fallbacks_off:
        print("GATE PASS: provider labels track the pin and discriminate between providers.")
        return 0

    print("GATE FAIL.")
    if not both_match:
        print("  - A pinned provider did NOT match the served provider (read-back mismatch).")
    if not served_differs:
        print("  - !!! The served-provider field was IDENTICAL despite different pins. !!!")
        print("      Provider labels cannot be trusted; the study is compromised. Investigate")
        print("      before collecting ANY data (possible silent reroute or mislabeling).")
    if not both_fallbacks_off:
        print("  - allow_fallbacks was NOT false on both requests; a call could have been rerouted.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
