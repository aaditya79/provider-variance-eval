"""Benchmark runner: iterate (model x provider x item x repeat), grade, log, respect budget.

Properties (plan §3, §5, §6; PREREGISTRATION §8):
  * One JSONL row per call (raw completion + grade + accounting + provenance).
  * Hard budget cap: abort before a call once cumulative OpenRouter-reported cost would
    exceed the cap.
  * Resumable: completed (item, provider, repeat) cells are detected from the existing JSONL
    and skipped, so a crash neither loses progress nor re-spends.
  * Pilot mode: runs the small pilot slice, prints per-provider accuracy + projected full-run
    cost, and STOPS. The full run refuses to start until a pilot has been confirmed.

Currently wired for GSM8K (the first end-to-end benchmark); MMLU/HumanEval slot in via the
same row schema and a per-benchmark prompt/grade pair.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path
from typing import Any, Callable

import yaml

from .benchmarks import gsm8k as gsm8k_mod
from .config import RunProvenance, utc_now_iso
from .openrouter import BudgetExceeded, CallResult, OpenRouterClient

# A benchmark adapter = how to build the prompt and grade, given a frozen item set.
PromptFn = Callable[[dict, dict], list[dict[str, str]]]   # (item, frozen) -> messages
GradeFn = Callable[[str | None, dict], tuple[bool, dict]]  # (completion, item) -> (correct, parse)


def _gsm8k_prompt(item: dict, frozen: dict) -> list[dict[str, str]]:
    return gsm8k_mod.build_prompt(item["question"], frozen["exemplars"])


def _gsm8k_grade(completion: str | None, item: dict) -> tuple[bool, dict]:
    correct, pr = gsm8k_mod.grade(completion, item["gold_raw"])
    return correct, dataclasses.asdict(pr)


ADAPTERS: dict[str, tuple[PromptFn, GradeFn, int]] = {
    # benchmark -> (prompt_fn, grade_fn, max_tokens)  [max_tokens filled from config at runtime]
    "gsm8k": (_gsm8k_prompt, _gsm8k_grade, 512),
}


def _cell_key(benchmark: str, item_id: str, provider_label: str, repeat: int) -> str:
    return f"{benchmark}|{item_id}|{provider_label}|{repeat}"


def _load_completed(jsonl_path: Path) -> tuple[set[str], float, int]:
    """Return (completed cell keys, cumulative valid cost, n rows) from an existing JSONL."""
    done: set[str] = set()
    cost = 0.0
    n = 0
    if not jsonl_path.exists():
        return done, cost, n
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            n += 1
            done.add(
                _cell_key(row["benchmark"], row["item_id"], row["provider_label"], row["repeat"])
            )
            if row.get("cost_usd"):
                cost += float(row["cost_usd"])
    return done, cost, n


def _row(call: CallResult, *, benchmark: str, item: dict, repeat: int,
         provider_label: str, route_mode: str, correct: bool | None,
         parse: dict | None, run_id: str) -> dict[str, Any]:
    d = call.to_jsonl_dict()
    d.update(
        {
            "run_id": run_id,
            "benchmark": benchmark,
            "item_id": item["id"],
            "dataset_index": item.get("dataset_index"),
            "repeat": repeat,
            "provider_label": provider_label,   # the pin (or ':floor'); resume/group key
            "route_mode": route_mode,
            "gold": item.get("gold"),
            "correct": correct,
            "parse": parse,
            "graded_utc": utc_now_iso(),
        }
    )
    return d


@dataclasses.dataclass
class RunPlan:
    run_id: str
    run_dir: Path
    benchmark: str
    model_key: str
    model_slug: str
    provider_labels: list[str]   # pinned providers; ':floor' appended if include_floor
    items: list[dict]
    repeats: int
    max_tokens: int
    is_pilot: bool


def make_run_dir(runs_dir: str | Path, run_id: str, cfg: dict, config_path: str) -> Path:
    run_dir = Path(runs_dir) / run_id
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    # provenance + resolved config copy (reproducibility, plan §11)
    prov = RunProvenance.capture(config_path)
    (run_dir / "provenance.json").write_text(json.dumps(prov.as_dict(), indent=2))
    shutil.copy(config_path, run_dir / "config.snapshot.yaml")
    (run_dir / "resolved.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    return run_dir


def run(plan: RunPlan, client: OpenRouterClient, *, cap_usd: float,
        temperature: float = 0.0, top_p: float = 1.0,
        send_seed: bool = False, seed: int | None = None) -> dict[str, Any]:
    """Execute the plan, append rows to JSONL, enforce the budget cap, support resume."""
    jsonl = plan.run_dir / "raw" / f"{plan.benchmark}.jsonl"
    done, cum_cost, n_existing = _load_completed(jsonl)
    if n_existing:
        print(f"[resume] {n_existing} rows already present; ${cum_cost:.4f} spent; "
              f"{len(done)} cells complete — skipping those.")

    prompt_fn, grade_fn, _ = ADAPTERS[plan.benchmark]
    total_cells = len(plan.provider_labels) * len(plan.items) * plan.repeats
    n_done = 0
    n_invalid = 0

    with open(jsonl, "a") as out:
        for provider_label in plan.provider_labels:
            route_mode = "floor" if provider_label == ":floor" else "pinned"
            pinned = None if route_mode == "floor" else provider_label
            for item in plan.items:
                for rep in range(plan.repeats):
                    key = _cell_key(plan.benchmark, item["id"], provider_label, rep)
                    if key in done:
                        n_done += 1
                        continue
                    # Budget guard: stop BEFORE spending if we're already at the cap.
                    if cum_cost >= cap_usd:
                        raise BudgetExceeded(
                            f"cumulative cost ${cum_cost:.4f} >= cap ${cap_usd:.2f}; "
                            f"aborting before further spend ({n_done}/{total_cells} cells done)."
                        )
                    messages = prompt_fn(item, plan_frozen(plan))
                    call = client.chat_completion(
                        model_slug=plan.model_slug,
                        messages=messages,
                        max_tokens=plan.max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        pinned_provider=pinned,
                        route_mode=route_mode,
                        send_seed=send_seed,
                        seed=seed,
                    )
                    # Grade only clean responses (LESSONS L1: never read content of invalid calls).
                    if call.valid:
                        correct, parse = grade_fn(call.completion_text, item)
                    else:
                        correct, parse = None, None
                        n_invalid += 1
                    row = _row(call, benchmark=plan.benchmark, item=item, repeat=rep,
                               provider_label=provider_label, route_mode=route_mode,
                               correct=correct, parse=parse, run_id=plan.run_id)
                    out.write(json.dumps(row) + "\n")
                    out.flush()
                    if call.cost_usd:
                        cum_cost += float(call.cost_usd)
                    n_done += 1
                    if n_done % 25 == 0:
                        print(f"  ... {n_done}/{total_cells} cells, ${cum_cost:.4f} spent, "
                              f"{n_invalid} invalid")

    print(f"[done] {n_done}/{total_cells} cells; ${cum_cost:.4f} spent; {n_invalid} invalid.")
    return {"jsonl": str(jsonl), "cost_usd": cum_cost, "cells": n_done, "invalid": n_invalid}


# The frozen item set is attached to the plan lazily so prompt_fn can read exemplars.
_FROZEN_CACHE: dict[str, dict] = {}


def attach_frozen(plan: RunPlan, frozen: dict) -> None:
    _FROZEN_CACHE[plan.run_id] = frozen


def plan_frozen(plan: RunPlan) -> dict:
    return _FROZEN_CACHE[plan.run_id]
