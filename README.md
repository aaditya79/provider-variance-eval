# Same Model, Different Answer — Harness

Measures provider-induced variance in API-based LLM evaluation through OpenRouter.

- **Study design (frozen):** [`provider_variance_paper_plan.md`](./provider_variance_paper_plan.md)
- **Locked parameters (pre-registration):** [`PREREGISTRATION.md`](./PREREGISTRATION.md)

The plan and pre-registration are committed *before* any data collection. Do not change
frozen parameters without a separate, dated amendment commit.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # or: uv pip install -r requirements.txt
export OPENROUTER_API_KEY=sk-or-...       # never hardcoded; read only from this env var
```

## Build/run gates (do NOT skip ahead)

The harness is built and validated in gates; each must pass before the next:

1. **Snapshot providers** — enumerate who serves each model + their disclosures:
   ```bash
   python scripts/snapshot_providers.py --phase start
   ```
   Use the printed table to fill `providers:` in `config.yaml`.

2. **GATE — pinning + read-back on ONE live call:**
   ```bash
   python scripts/probe_pinning.py --model meta-llama/llama-3.3-70b-instruct
   ```
   Confirms the pinned provider equals the served provider. Exit 0 = pass.

3. **GSM8K pilot** (built after gate 2 passes) — 50 items, all providers, 1 repeat;
   prints projected full-run cost, then stops. *(Coming next.)*

4. **Full run** — refuses to start until a pilot has run and been confirmed. *(Coming.)*

## Layout

```
config.yaml              operational config (agrees with PREREGISTRATION.md)
src/pv/                  package: config, openrouter client, snapshot, (benchmarks/runner TBD)
scripts/                 snapshot_providers.py, probe_pinning.py, (runner TBD)
data/items/              frozen benchmark item sets (paired design)
data/raw/                per-call JSONL logs
data/snapshots/          provider metadata JSON (start/end, UTC-timestamped)
results/                 analysis outputs + figures
runs/                    per-run dirs: resolved config + git sha + timestamps
```

## Correctness invariants

- Exactly one provider pinned per call (`order=[slug]`, `allow_fallbacks=false`,
  `require_parameters=true`).
- Provider **read-back** asserted on every call; mismatches marked `valid=false` and logged.
- temp=0, top_p=1, fixed max_tokens, identical prompt template per benchmark.
- Item sets frozen once to `data/items/` and reused across all (model, provider, repeat).
- Hard budget cap (default $30); cumulative cost tracked per call.
