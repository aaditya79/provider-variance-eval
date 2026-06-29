#!/usr/bin/env python3
"""Enumerate + snapshot providers for the configured models.

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  python scripts/snapshot_providers.py [--phase start|end] [--config config.yaml]

Prints a human-readable table of each model's providers (name, quantization, context,
price) and writes the full timestamped JSON to data/snapshots/. Use this output to fill
the `providers:` lists in config.yaml.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.config import git_sha, load_config, require_api_key  # noqa: E402
from pv.openrouter import OpenRouterClient  # noqa: E402
from pv.snapshot import take_snapshot  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["start", "end"], default="start")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    model_slugs = [m["slug"] for m in cfg["models"]]
    try:
        api_key = require_api_key()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2

    with OpenRouterClient(api_key, timeout_s=cfg["run"]["request_timeout_s"]) as client:
        path = take_snapshot(
            client, model_slugs, phase=args.phase, git_sha=git_sha(short=True)
        )

    import json

    snap = json.loads(path.read_text())
    print(f"\nSnapshot written: {path}\n")
    for model in snap["models"]:
        print(f"=== {model['model_slug']}  ({model['n_endpoints']} providers) ===")
        hdr = f"{'provider':<22}{'quant':<10}{'ctx':<10}{'$/Mtok in':<12}{'$/Mtok out':<12}"
        print(hdr)
        print("-" * len(hdr))
        for ep in model["endpoints"]:
            pin = ep.get("price_prompt_per_token")
            pout = ep.get("price_completion_per_token")
            pin_m = f"{float(pin) * 1e6:.3f}" if pin not in (None, "") else "?"
            pout_m = f"{float(pout) * 1e6:.3f}" if pout not in (None, "") else "?"
            print(
                f"{str(ep.get('provider_name')):<22}"
                f"{str(ep.get('quantization')):<10}"
                f"{str(ep.get('context_length')):<10}"
                f"{pin_m:<12}{pout_m:<12}"
            )
        print()
    print("Fill the `providers:` lists in config.yaml using the provider names above")
    print("(normalized to slugs). Re-run with --phase end after data collection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
