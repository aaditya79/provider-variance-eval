"""Offline unit tests for the provider read-back logic (no network / no API key)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.openrouter import OpenRouterClient, normalize_provider, provider_base_key


def test_provider_base_key_strips_subtag():
    # pin carries a variant sub-tag; served field reports base name only
    assert provider_base_key("deepinfra/turbo") == "deepinfra"
    assert provider_base_key("novita/bf16") == "novita"
    assert provider_base_key("DeepInfra") == "deepinfra"
    # distinct base names must NOT collide
    assert provider_base_key("deepinfra/turbo") != provider_base_key("novita/bf16")


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
        "choices": [{"message": {"content": "reasoning...\n#### 4"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11, "cost": 0.0001},
    }
    res = c._parse_success(
        data, model_slug="m", pinned_provider="deepinfra", route_mode="pinned",
        request_utc="t", latency_s=0.1, attempts=1, attempt_log=[],
    )
    assert res.provider_match is True
    assert res.valid is True
    assert res.cost_usd == 0.0001
    assert res.completion_text == "reasoning...\n#### 4"
    c.close()


def test_readback_mismatch_marks_invalid():
    c = _client()
    data = {
        "id": "gen-2",
        "provider": "Novita",  # we pinned deepinfra but got novita
        "choices": [{"message": {"content": "reasoning...\n#### 4"}, "finish_reason": "stop"}],
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


def test_pinned_subtag_matches_base_served_name():
    """The exact failing run: pin 'deepinfra/turbo', API serves 'DeepInfra' -> must match."""
    c = _client()
    data = {
        "id": "gen-st",
        "provider": "DeepInfra",
        "choices": [{"message": {"content": "reasoning...\n#### 4"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
    }
    res = c._parse_success(
        data, model_slug="m", pinned_provider="deepinfra/turbo", route_mode="pinned",
        request_utc="t", latency_s=0.1, attempts=1, attempt_log=[],
    )
    assert res.provider_match is True
    assert res.valid is True
    assert res.returned_provider == "DeepInfra"  # served_raw kept verbatim
    c.close()


def test_subtag_fix_does_not_merge_distinct_providers():
    """Pinning 'deepinfra/turbo' but being served 'Novita' must still be a mismatch."""
    c = _client()
    data = {
        "id": "gen-st2",
        "provider": "Novita",
        "choices": [{"message": {"content": "reasoning...\n#### 4"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
    }
    res = c._parse_success(
        data, model_slug="m", pinned_provider="deepinfra/turbo", route_mode="pinned",
        request_utc="t", latency_s=0.1, attempts=1, attempt_log=[],
    )
    assert res.provider_match is False
    assert res.invalid_reason == "provider_readback_mismatch"
    c.close()


def test_expected_served_name_matches_disclosed_name():
    """Slug 'google-vertex' is disclosed as 'Google'; served 'Google' must match via the map."""
    c = _client()
    data = {
        "id": "gen-gv",
        "provider": "Google",
        "choices": [{"message": {"content": "reasoning...\n#### 4"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
    }
    res = c._parse_success(
        data, model_slug="m", pinned_provider="google-vertex", route_mode="pinned",
        request_utc="t", latency_s=0.1, attempts=1, attempt_log=[],
        expected_served_name="Google",
    )
    assert res.provider_match is True
    assert res.valid is True
    assert res.returned_provider == "Google"  # served_raw kept verbatim
    c.close()


def test_expected_name_does_not_mask_a_real_reroute():
    """Even with an expected name, a genuinely different served provider must mismatch."""
    c = _client()
    data = {
        "id": "gen-gv2",
        "provider": "Novita",  # we expected Google
        "choices": [{"message": {"content": "reasoning...\n#### 4"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
    }
    res = c._parse_success(
        data, model_slug="m", pinned_provider="google-vertex", route_mode="pinned",
        request_utc="t", latency_s=0.1, attempts=1, attempt_log=[],
        expected_served_name="Google",
    )
    assert res.provider_match is False
    c.close()


def test_request_provider_block_is_recorded():
    """The exact routing sent must be captured so the gate can prove allow_fallbacks:false."""
    c = _client()
    data = {
        "id": "gen-x",
        "provider": "DeepInfra",
        "choices": [{"message": {"content": "reasoning...\n#### 4"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
    }
    block = {"order": ["deepinfra"], "allow_fallbacks": False, "require_parameters": True}
    res = c._parse_success(
        data, model_slug="m", pinned_provider="deepinfra", route_mode="pinned",
        request_utc="t", latency_s=0.1, attempts=1, attempt_log=[],
        request_provider_block=block,
    )
    assert res.request_provider_block == block
    assert res.request_provider_block["allow_fallbacks"] is False
    c.close()


def test_silent_truncation_detection():
    """finish=stop but no #### and ends mid-sentence -> generation_error/silent_truncation."""
    from pv.openrouter import is_silent_truncation
    # truncated: no ####, ends mid-clause
    assert is_silent_truncation("stop", "so 2 * 30 =") is True
    assert is_silent_truncation("stop", "") is True                 # empty stop
    # NOT truncated: has the #### answer
    assert is_silent_truncation("stop", "reasoning\n#### 42") is False
    # NOT truncated: complete sentence ending in terminal punctuation (genuine no-#### answer)
    assert is_silent_truncation("stop", "The answer is 42.") is False
    # not a stop finish -> handled elsewhere
    assert is_silent_truncation("length", "cut off here") is False


def test_silent_truncation_marks_invalid_subtype():
    c = _client()
    data = {
        "id": "gen-silent",
        "provider": "Google",
        "choices": [{"message": {"content": "Timothy has three times the number of"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 52, "total_tokens": 952, "cost": 0.0006},
    }
    from pv.benchmarks import gsm8k
    res = c._parse_success(
        data, model_slug="m", pinned_provider="google-vertex", route_mode="pinned",
        request_utc="t", latency_s=0.1, attempts=1, attempt_log=[],
        expected_served_name="Google", completeness_check=gsm8k.is_complete,
    )
    assert res.provider_match is True                 # read-back matched
    assert res.valid is False                         # ...but silently truncated
    assert res.invalid_reason == "generation_error"
    assert res.invalid_subtype == "silent_truncation"
    c.close()


def test_generation_error_is_third_outcome_class():
    """HTTP 200 with finish_reason 'error' -> valid=False, invalid_reason='generation_error',
    even though the provider read-back matched. Must not be graded as correct/incorrect."""
    c = _client()
    data = {
        "id": "gen-err",
        "provider": "Cloudflare",
        "choices": [{"message": {"content": "...truncated mid-sent"}, "finish_reason": "error"}],
        "usage": {"prompt_tokens": 900, "completion_tokens": None, "total_tokens": None,
                  "cost": 0.0003},
    }
    res = c._parse_success(
        data, model_slug="m", pinned_provider="cloudflare/fp8", route_mode="pinned",
        request_utc="t", latency_s=0.1, attempts=1, attempt_log=[],
        expected_served_name="Cloudflare",
    )
    assert res.provider_match is True          # read-back DID match
    assert res.valid is False                  # ...but the call is unusable
    assert res.invalid_reason == "generation_error"
    assert res.invalid_subtype == "overt_truncation"
    c.close()


def test_floor_route_has_no_match_requirement():
    c = _client()
    data = {
        "id": "gen-3",
        "provider": "SomeCheapProvider",
        "choices": [{"message": {"content": "reasoning...\n#### 4"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11, "cost": 0.00001},
    }
    res = c._parse_success(
        data, model_slug="m", pinned_provider=None, route_mode="floor",
        request_utc="t", latency_s=0.1, attempts=1, attempt_log=[],
    )
    assert res.provider_match is None
    assert res.valid is True
    c.close()
