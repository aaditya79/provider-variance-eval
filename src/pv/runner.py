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
import os
import shutil
from pathlib import Path
from typing import Any, Callable

import yaml

from .benchmarks import gsm8k as gsm8k_mod
from .benchmarks import humaneval as he_mod
from .benchmarks import mmlu as mmlu_mod
from .config import RunProvenance, utc_now_iso
from .openrouter import BudgetExceeded, CallResult, OpenRouterClient

# A benchmark adapter = how to build the prompt, grade, and check completeness for a benchmark.
PromptFn = Callable[[dict, dict], list[dict[str, str]]]   # (item, frozen) -> messages
GradeFn = Callable[[str | None, dict], tuple[bool, dict]]  # (completion, item) -> (correct, parse)
CompleteFn = Callable[[str], bool]                         # completion -> is_complete (for silent-trunc)


def _gsm8k_prompt(item: dict, frozen: dict) -> list[dict[str, str]]:
    return gsm8k_mod.build_prompt(item["question"], frozen["exemplars"])


def _gsm8k_grade(completion: str | None, item: dict) -> tuple[bool, dict]:
    correct, pr = gsm8k_mod.grade(completion, item["gold_raw"])
    return correct, dataclasses.asdict(pr)


def _mmlu_prompt(item: dict, frozen: dict) -> list[dict[str, str]]:
    return mmlu_mod.build_prompt(item, frozen["dev_exemplars"][item["subject"]])


def _mmlu_grade(completion: str | None, item: dict) -> tuple[bool, dict]:
    return mmlu_mod.grade(completion, item["gold"])


def _he_prompt(item: dict, frozen: dict) -> list[dict[str, str]]:
    return he_mod.build_prompt(item["prompt"])


def _he_grade(completion: str | None, item: dict) -> tuple[bool, dict]:
    return he_mod.grade(completion, item)


@dataclasses.dataclass
class Adapter:
    prompt_fn: PromptFn
    grade_fn: GradeFn
    complete_fn: CompleteFn | None   # None => no silent-truncation detection (e.g. code)


ADAPTERS: dict[str, Adapter] = {
    "gsm8k": Adapter(_gsm8k_prompt, _gsm8k_grade, gsm8k_mod.is_complete),
    "mmlu": Adapter(_mmlu_prompt, _mmlu_grade, mmlu_mod.is_complete),
    "humaneval": Adapter(_he_prompt, _he_grade, he_mod.is_complete),
}


def _cell_key(benchmark: str, item_id: str, provider_label: str, repeat: int) -> str:
    return f"{benchmark}|{item_id}|{provider_label}|{repeat}"


class PersistenceError(RuntimeError):
    """Raised when rows were generated but did not durably land on disk."""


def _under_icloud(path: Path) -> bool:
    """True if path is inside an iCloud-synced location (Desktop/Documents/Mobile Documents).

    Such locations can evict/placeholder large files and are NOT a safe home for raw run logs
    (which are also gitignored => no backup). Warned about at run start.
    """
    s = str(path.resolve())
    return ("/Library/Mobile Documents/" in s
            or "/Desktop/" in s or "/Documents/" in s)


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path) as f:
        return sum(1 for _ in f)


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
    run_dir = Path(runs_dir).expanduser() / run_id  # expanduser so runs can live off iCloud
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    # provenance + resolved config copy (reproducibility, plan §11)
    prov = RunProvenance.capture(config_path)
    (run_dir / "provenance.json").write_text(json.dumps(prov.as_dict(), indent=2))
    shutil.copy(config_path, run_dir / "config.snapshot.yaml")
    (run_dir / "resolved.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    return run_dir


def run(plan: RunPlan, client: OpenRouterClient, *, cap_usd: float,
        temperature: float = 0.0, top_p: float = 1.0,
        send_seed: bool = False, seed: int | None = None,
        name_map: dict[str, str] | None = None) -> dict[str, Any]:
    """Execute the plan, append rows to JSONL, enforce the budget cap, support resume."""
    jsonl = plan.run_dir / "raw" / f"{plan.benchmark}.jsonl"
    if _under_icloud(jsonl):
        print(f"WARNING: run dir is inside an iCloud-synced path:\n  {jsonl.resolve()}\n"
              "  iCloud can evict/placeholder large files and raw logs are gitignored (no backup).\n"
              "  Strongly consider moving `runs_dir` outside iCloud (e.g. ~/pv_runs).")

    done, cum_cost, n_existing = _load_completed(jsonl)
    if n_existing:
        print(f"[resume] {n_existing} rows already present; ${cum_cost:.4f} spent; "
              f"{len(done)} cells complete — skipping those.")

    adapter = ADAPTERS[plan.benchmark]
    prompt_fn, grade_fn, complete_fn = adapter.prompt_fn, adapter.grade_fn, adapter.complete_fn
    name_map = name_map or {}
    total_cells = len(plan.provider_labels) * len(plan.items) * plan.repeats
    n_done = 0
    n_invalid = 0
    n_written = 0  # rows this process actually wrote (excludes resumed/skipped cells)

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
                        expected_served_name=name_map.get(provider_label),
                        completeness_check=complete_fn,
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
                    n_written += 1
                    if n_written % 200 == 0:
                        os.fsync(out.fileno())  # force durability periodically (crash-safe resume)
                    if call.cost_usd:
                        cum_cost += float(call.cost_usd)
                    n_done += 1
                    if n_done % 25 == 0:
                        print(f"  ... {n_done}/{total_cells} cells, ${cum_cost:.4f} spent, "
                              f"{n_invalid} invalid")
        out.flush()
        os.fsync(out.fileno())  # final durability barrier before close

    # ---- integrity check: rows generated this process MUST be on disk ---------------------
    lines_on_disk = _count_lines(jsonl)
    expected_on_disk = n_existing + n_written
    bytes_on_disk = jsonl.stat().st_size if jsonl.exists() else 0
    manifest = {
        "run_id": plan.run_id,
        "benchmark": plan.benchmark,
        "cells_processed": n_done,
        "rows_written_this_process": n_written,
        "rows_resumed": n_existing,
        "rows_on_disk": lines_on_disk,
        "jsonl_bytes": bytes_on_disk,
        "invalid": n_invalid,
        "cost_usd": cum_cost,
        "jsonl": str(jsonl),
    }
    (plan.run_dir / f"manifest_{plan.benchmark}.json").write_text(json.dumps(manifest, indent=2))

    if n_written > 0 and lines_on_disk != expected_on_disk:
        raise PersistenceError(
            f"DATA LOSS: generated {n_written} new rows (resumed {n_existing}) but the JSONL holds "
            f"{lines_on_disk} lines ({bytes_on_disk} bytes). Expected {expected_on_disk}. "
            f"File: {jsonl}. Do NOT trust this run."
        )
    print(f"[done] {n_done}/{total_cells} cells; ${cum_cost:.4f} spent; {n_invalid} invalid.")
    print(f"[persisted] {lines_on_disk} rows, {bytes_on_disk} bytes -> {jsonl}")
    return {"jsonl": str(jsonl), "cost_usd": cum_cost, "cells": n_done,
            "invalid": n_invalid, "rows_on_disk": lines_on_disk}


# The frozen item set is attached to the plan lazily so prompt_fn can read exemplars.
_FROZEN_CACHE: dict[str, dict] = {}


def attach_frozen(plan: RunPlan, frozen: dict) -> None:
    _FROZEN_CACHE[plan.run_id] = frozen


def plan_frozen(plan: RunPlan) -> dict:
    return _FROZEN_CACHE[plan.run_id]
