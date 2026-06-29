"""Offline unit tests for the provider read-back logic (no network / no API key)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.openrouter import OpenRouterClient, normalize_provider


def test_normalize_handles_case_and_punctuation():
    assert normalize_provider("DeepInfra") == "deepinfra"
    assert normalize_provider("deepinfra") == "deepinfra"
    assert normalize_provider("Inference.net") == "inferencenet"
    assert normalize_provider("inference-net") == "inferencenet"
    assert normalize_provider("Together AI") == "togetherai"
    assert normalize_provider(None) == ""


def _client() -> OpenRouterClient:
    # No network call is made by _parse_success; a dummy key is fine.
    return OpenRouterClient("sk-or-test", timeout_s=1)


def test_readback_match_marks_valid():
    c = _client()
    data = {
        "id": "gen-1",
        "provider": "DeepInfra",
        "choices": [{"message": {"content": "4"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11, "cost": 0.0001},
    }
    res = c._parse_success(
        data, model_slug="m", pinned_provider="deepinfra", route_mode="pinned",
        request_utc="t", latency_s=0.1, attempts=1, attempt_log=[],
    )
    assert res.provider_match is True
    assert res.valid is True
    assert res.cost_usd == 0.0001
    assert res.completion_text == "4"
    c.close()


def test_readback_mismatch_marks_invalid():
    c = _client()
    data = {
        "id": "gen-2",
        "provider": "Novita",  # we pinned deepinfra but got novita
        "choices": [{"message": {"content": "4"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11, "cost": 0.0001},
    }
    res = c._parse_success(
        data, model_slug="m", pinned_provider="deepinfra", route_mode="pinned",
        request_utc="t", latency_s=0.1, attempts=1, attempt_log=[],
    )
    assert res.provider_match is False
    assert res.valid is False
    assert res.invalid_reason == "provider_readback_mismatch"
    c.close()


def test_floor_route_has_no_match_requirement():
    c = _client()
    data = {
        "id": "gen-3",
        "provider": "SomeCheapProvider",
        "choices": [{"message": {"content": "4"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11, "cost": 0.00001},
    }
    res = c._parse_success(
        data, model_slug="m", pinned_provider=None, route_mode="floor",
        request_utc="t", latency_s=0.1, attempts=1, attempt_log=[],
    )
    assert res.provider_match is None
    assert res.valid is True
    c.close()
