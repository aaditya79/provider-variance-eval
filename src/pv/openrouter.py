"""OpenRouter client wrapper.

Responsibilities (plan §3, §4; PREREGISTRATION §10.7):
  * Pin EXACTLY one provider per call: provider={order:[slug], allow_fallbacks:false,
    require_parameters:true}.  (Schema verified against current OpenRouter docs 2026-06-29.)
  * Read back which provider served the response and assert it matches the pin; on mismatch
    the record is marked invalid (valid=False) and logged — never silently kept.
  * Retry with exponential backoff + jitter on 429/5xx/network; honor Retry-After.
  * Capture for every call: raw completion, token counts, latency, returned provider, cost.

Nothing here hardcodes the API key; it is read from OPENROUTER_API_KEY via config.require_api_key.
"""

from __future__ import annotations

import dataclasses
import random
import re
import time
from typing import Any

import httpx

from .config import utc_now_iso

API_BASE = "https://openrouter.ai/api/v1"
CHAT_URL = f"{API_BASE}/chat/completions"
GENERATION_URL = f"{API_BASE}/generation"

# Identifies the harness to OpenRouter (optional but courteous; not auth).
_HEADERS_EXTRA = {
    "HTTP-Referer": "https://github.com/provider-variance-study",
    "X-Title": "provider-variance-study",
}


def normalize_provider(name: str) -> str:
    """Canonicalize a provider slug or display name for comparison.

    OpenRouter's `order` array takes slugs ("deepinfra") while the response may report a
    display name ("DeepInfra", "Inference.net"). Strip case and non-alphanumerics so the
    read-back assertion compares apples to apples. The snapshot's authoritative name<->slug
    map is the preferred source; this is the robust fallback.
    """
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def provider_base_key(name: str) -> str:
    """Base provider identity used for the read-back MATCH comparison.

    A pinned slug can carry a variant sub-tag after '/', e.g. 'deepinfra/turbo' or
    'novita/bf16'. The API's served-provider field reports only the BASE provider name
    ('DeepInfra'). So the match must compare base-to-base: drop everything after the first
    '/', then normalize. This ONLY removes the variant sub-tag; distinct base names stay
    distinct (it never merges 'deepinfra' with 'novita'). The verbatim served string is kept
    separately (see returned_provider) — only the comparison is base-keyed.
    """
    base = (name or "").split("/", 1)[0]
    return normalize_provider(base)


@dataclasses.dataclass
class CallResult:
    """One row per call — serialized to JSONL by the runner."""

    # identity / request
    request_utc: str
    model_slug: str
    pinned_provider: str | None          # slug we pinned, or None for ':floor'/auto
    route_mode: str                      # "pinned" | "floor"
    request_provider_block: dict[str, Any] | None  # EXACT provider routing sent (audit)
    # response
    valid: bool                          # False => provider read-back failed or hard error
    invalid_reason: str | None
    returned_provider: str | None        # as reported by OpenRouter (display name)
    returned_provider_slug: str | None   # normalized
    provider_match: bool | None          # did read-back match the pin? (None for floor)
    generation_id: str | None
    finish_reason: str | None
    completion_text: str | None          # RAW model output (audit trail)
    # accounting
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost_usd: float | None               # OpenRouter-reported actual cost (ground truth)
    # timing / retries
    latency_s: float | None
    attempts: int
    http_status: int | None
    error: str | None                    # transport/error detail if the call failed outright
    attempt_log: list[dict[str, Any]]    # per-attempt status for auditing retries

    def to_jsonl_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class BudgetExceeded(RuntimeError):
    """Raised when cumulative spend would exceed the configured hard cap."""


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        *,
        timeout_s: float = 120.0,
        max_attempts: int = 5,
        backoff_base_s: float = 1.0,
        backoff_cap_s: float = 60.0,
        retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504),
        rng: random.Random | None = None,
    ) -> None:
        self._api_key = api_key
        self.max_attempts = max_attempts
        self.backoff_base_s = backoff_base_s
        self.backoff_cap_s = backoff_cap_s
        self.retry_on_status = tuple(retry_on_status)
        self._rng = rng or random.Random()
        self._client = httpx.Client(
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {api_key}", **_HEADERS_EXTRA},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OpenRouterClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- provider enumeration / snapshot -------------------------------------------------

    def list_endpoints(self, model_slug: str) -> dict[str, Any]:
        """GET the providers/endpoints serving a model, with quantization/price/context.

        Endpoint: /api/v1/models/{author}/{slug}/endpoints
        Returned shape is recorded verbatim by the snapshot tool (it is time-varying).
        """
        url = f"{API_BASE}/models/{model_slug}/endpoints"
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp.json()

    def get_generation(self, generation_id: str) -> dict[str, Any] | None:
        """Fetch canonical generation stats (provider_name, cost, tokens) by id.

        Used as the authoritative read-back / cost source when the inline response is
        ambiguous. Returns None if unavailable (it can lag briefly after the call).
        """
        try:
            resp = self._client.get(GENERATION_URL, params={"id": generation_id})
            if resp.status_code != 200:
                return None
            return resp.json().get("data")
        except httpx.HTTPError:
            return None

    # ---- chat completion -----------------------------------------------------------------

    def chat_completion(
        self,
        *,
        model_slug: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
        pinned_provider: str | None = None,
        route_mode: str = "pinned",
        send_seed: bool = False,
        seed: int | None = None,
    ) -> CallResult:
        """Make one pinned (or :floor) chat call, with retries and provider read-back.

        route_mode="pinned": pin `pinned_provider` with no fallback.
        route_mode="floor":  use the ':floor' suffix (cheapest); provider is whatever resolves.
        """
        body: dict[str, Any] = {
            "model": model_slug if route_mode != "floor" else f"{model_slug}:floor",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "usage": {"include": True},  # ask OpenRouter to include actual cost in usage
        }
        if route_mode == "pinned":
            if not pinned_provider:
                raise ValueError("pinned route requires pinned_provider")
            # The exact pinning contract from the plan, schema-verified 2026-06-29.
            body["provider"] = {
                "order": [pinned_provider],
                "allow_fallbacks": False,
                "require_parameters": True,
            }
        request_provider_block = body.get("provider")  # exact routing sent (None for floor)
        if send_seed and seed is not None:
            body["seed"] = seed  # deliberately OFF by default (RQ3); see PREREGISTRATION §10.4

        attempt_log: list[dict[str, Any]] = []
        request_utc = utc_now_iso()
        last_error: str | None = None
        last_status: int | None = None

        for attempt in range(1, self.max_attempts + 1):
            t0 = time.monotonic()
            try:
                resp = self._client.post(CHAT_URL, json=body)
                latency = time.monotonic() - t0
                last_status = resp.status_code
                if resp.status_code == 200:
                    return self._parse_success(
                        resp.json(),
                        model_slug=model_slug,
                        pinned_provider=pinned_provider,
                        route_mode=route_mode,
                        request_provider_block=request_provider_block,
                        request_utc=request_utc,
                        latency_s=latency,
                        attempts=attempt,
                        attempt_log=attempt_log,
                    )
                # non-200
                body_snippet = resp.text[:500]
                attempt_log.append(
                    {"attempt": attempt, "status": resp.status_code, "body": body_snippet}
                )
                last_error = f"HTTP {resp.status_code}: {body_snippet}"
                if resp.status_code in self.retry_on_status and attempt < self.max_attempts:
                    self._sleep_backoff(attempt, resp)
                    continue
                # non-retryable (e.g. 4xx other than 429) — give up
                break
            except httpx.HTTPError as e:
                latency = time.monotonic() - t0
                attempt_log.append(
                    {"attempt": attempt, "status": None, "error": repr(e)}
                )
                last_error = repr(e)
                if attempt < self.max_attempts:
                    self._sleep_backoff(attempt, None)
                    continue
                break

        # exhausted / non-retryable
        return CallResult(
            request_utc=request_utc,
            model_slug=model_slug,
            pinned_provider=pinned_provider,
            route_mode=route_mode,
            request_provider_block=request_provider_block,
            valid=False,
            invalid_reason="request_failed",
            returned_provider=None,
            returned_provider_slug=None,
            provider_match=None,
            generation_id=None,
            finish_reason=None,
            completion_text=None,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            cost_usd=None,
            latency_s=None,
            attempts=len(attempt_log),
            http_status=last_status,
            error=last_error,
            attempt_log=attempt_log,
        )

    # ---- internals -----------------------------------------------------------------------

    def _sleep_backoff(self, attempt: int, resp: httpx.Response | None) -> None:
        """Exponential backoff with jitter; honor Retry-After if present."""
        delay = min(self.backoff_cap_s, self.backoff_base_s * (2 ** (attempt - 1)))
        if resp is not None:
            ra = resp.headers.get("Retry-After")
            if ra:
                try:
                    delay = max(delay, float(ra))
                except ValueError:
                    pass
        delay += self._rng.uniform(0, self.backoff_base_s)  # full-ish jitter
        time.sleep(delay)

    def _parse_success(
        self,
        data: dict[str, Any],
        *,
        model_slug: str,
        pinned_provider: str | None,
        route_mode: str,
        request_utc: str,
        latency_s: float,
        attempts: int,
        attempt_log: list[dict[str, Any]],
        request_provider_block: dict[str, Any] | None = None,
    ) -> CallResult:
        gen_id = data.get("id")
        # top-level provider display name (empirically present); fall back to generation lookup
        returned_provider = data.get("provider")
        choices = data.get("choices") or [{}]
        msg = (choices[0] or {}).get("message") or {}
        completion_text = msg.get("content")
        finish_reason = (choices[0] or {}).get("finish_reason")

        usage = data.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        cost_usd = usage.get("cost")

        # If provider/cost missing inline, consult the canonical generation stats.
        if (returned_provider is None or cost_usd is None) and gen_id:
            gen = self.get_generation(gen_id)
            if gen:
                returned_provider = returned_provider or gen.get("provider_name")
                if cost_usd is None:
                    cost_usd = gen.get("total_cost")

        returned_slug = normalize_provider(returned_provider) if returned_provider else None

        if route_mode == "pinned":
            # Compare BASE provider identity: the pin may carry a variant sub-tag
            # ('deepinfra/turbo') that the served-provider field never reports.
            match = (
                returned_provider is not None
                and provider_base_key(pinned_provider or "") == provider_base_key(returned_provider)
            )
            valid = bool(match)
            invalid_reason = None if valid else "provider_readback_mismatch"
        else:
            match = None
            valid = True
            invalid_reason = None

        return CallResult(
            request_utc=request_utc,
            model_slug=model_slug,
            pinned_provider=pinned_provider,
            route_mode=route_mode,
            request_provider_block=request_provider_block,
            valid=valid,
            invalid_reason=invalid_reason,
            returned_provider=returned_provider,
            returned_provider_slug=returned_slug,
            provider_match=match,
            generation_id=gen_id,
            finish_reason=finish_reason,
            completion_text=completion_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_s=latency_s,
            attempts=attempts,
            http_status=200,
            error=None,
            attempt_log=attempt_log,
        )
