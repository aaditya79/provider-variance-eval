"""Regression test for the data-loss class: rows generated MUST land on disk.

Guards against the full-run failure where counters reported 9900 cells but the JSONL was
empty. Uses a fake client (no network)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from pv import runner as R
from pv.openrouter import CallResult


def _fake_call(provider_label: str, route_mode: str) -> CallResult:
    pinned = None if route_mode == "floor" else provider_label
    return CallResult(
        request_utc="t", model_slug="m", pinned_provider=pinned, route_mode=route_mode,
        request_provider_block=None, valid=True, invalid_reason=None, invalid_subtype=None,
        returned_provider="X", returned_provider_slug="x", provider_match=True,
        generation_id="g", finish_reason="stop", completion_text="reasoning\n#### 7",
        prompt_tokens=10, completion_tokens=5, total_tokens=15, cost_usd=0.0001,
        latency_s=0.01, attempts=1, http_status=200, error=None, attempt_log=[],
    )


class FakeClient:
    def chat_completion(self, *, model_slug, messages, max_tokens, temperature, top_p,
                        pinned_provider, route_mode, send_seed, seed, expected_served_name):
        return _fake_call(pinned_provider or ":floor", route_mode)


def _tiny_plan(tmp_path: Path) -> R.RunPlan:
    run_dir = R.make_run_dir(tmp_path / "runs", "testrun",
                             {"x": 1}, str(Path(__file__)))  # config copy = this file (any path)
    items = [{"id": f"gsm8k-{i:04d}", "question": "q?", "gold_raw": "x\n#### 7", "gold": "7"}
             for i in range(3)]
    plan = R.RunPlan(run_id="testrun", run_dir=run_dir, benchmark="gsm8k",
                     model_key="m", model_slug="m", provider_labels=["a", "b"],
                     items=items, repeats=2, max_tokens=16, is_pilot=False)
    R.attach_frozen(plan, {"exemplars": []})
    return plan


def test_rows_actually_persist(tmp_path):
    plan = _tiny_plan(tmp_path)
    res = R.run(plan, FakeClient(), cap_usd=100.0)
    jsonl = Path(res["jsonl"])
    # 2 providers x 3 items x 2 repeats = 12 cells, all written
    assert res["cells"] == 12
    assert res["rows_on_disk"] == 12
    assert jsonl.stat().st_size > 0
    rows = [json.loads(l) for l in open(jsonl)]
    assert len(rows) == 12
    assert all(r["correct"] is True for r in rows)
    # manifest present and consistent
    man = json.loads((plan.run_dir / "manifest_gsm8k.json").read_text())
    assert man["rows_on_disk"] == 12 and man["jsonl_bytes"] > 0


def test_integrity_check_raises_on_loss(tmp_path, monkeypatch):
    """If something deletes/truncates the file mid-run, the run must FAIL loudly, not pass."""
    plan = _tiny_plan(tmp_path)

    real_open = open

    class TruncatingClient(FakeClient):
        def chat_completion(self, **kw):
            r = super().chat_completion(**kw)
            return r

    # Monkeypatch _count_lines to simulate a file that lost its rows (returns 0).
    monkeypatch.setattr(R, "_count_lines", lambda p: 0)
    with pytest.raises(R.PersistenceError):
        R.run(plan, TruncatingClient(), cap_usd=100.0)
