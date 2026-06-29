"""Provider enumeration + snapshot (plan §3, §4, §11).

Records, per model, the providers serving it and their disclosed metadata
(slug, display name, quantization, context length, input/output price) with a UTC
timestamp. Provider availability and disclosures are TIME-VARYING, so snapshots are
taken at run start AND end and dumped to data/snapshots/ as JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import utc_now_iso
from .openrouter import OpenRouterClient, normalize_provider


def _endpoint_summary(ep: dict[str, Any]) -> dict[str, Any]:
    """Extract the disclosed fields we care about from one endpoint object.

    We keep the raw object too (see snapshot_model) so nothing is lost if the schema
    has fields we didn't anticipate.
    """
    pricing = ep.get("pricing") or {}
    name = ep.get("provider_name") or ep.get("name")
    return {
        "provider_name": name,
        "provider_slug_normalized": normalize_provider(name) if name else None,
        # The tag/slug used in the `order` array, if the API exposes it directly:
        "tag": ep.get("tag"),
        "quantization": ep.get("quantization"),
        "context_length": ep.get("context_length"),
        "max_completion_tokens": ep.get("max_completion_tokens"),
        "supported_parameters": ep.get("supported_parameters"),
        "price_prompt_per_token": pricing.get("prompt"),
        "price_completion_per_token": pricing.get("completion"),
        "uptime_last_30m": ep.get("uptime_last_30m"),
        "status": ep.get("status"),
    }


def snapshot_model(client: OpenRouterClient, model_slug: str) -> dict[str, Any]:
    """Enumerate providers for one model and summarize their disclosures."""
    raw = client.list_endpoints(model_slug)
    data = raw.get("data") or {}
    endpoints = data.get("endpoints") or []
    return {
        "model_slug": model_slug,
        "model_name": data.get("name"),
        "n_endpoints": len(endpoints),
        "endpoints": [_endpoint_summary(ep) for ep in endpoints],
        "raw": raw,  # full verbatim payload — schema-proof audit trail
    }


def take_snapshot(
    client: OpenRouterClient,
    model_slugs: list[str],
    *,
    phase: str,
    out_dir: str | Path = "data/snapshots",
    git_sha: str | None = None,
) -> Path:
    """Snapshot all models and write a timestamped JSON file.

    phase: "start" or "end" (plan §4 requires both).
    Returns the written path.
    """
    ts = utc_now_iso()
    snapshot = {
        "phase": phase,
        "timestamp_utc": ts,
        "git_sha": git_sha,
        "models": [snapshot_model(client, slug) for slug in model_slugs],
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_ts = ts.replace(":", "").replace("-", "")
    path = out / f"providers_{phase}_{safe_ts}.json"
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)
    return path
