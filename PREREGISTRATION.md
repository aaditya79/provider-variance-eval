# PREREGISTRATION — Locked Study Parameters

**Status:** Frozen before data collection. Open choices resolved by author 2026-06-29 (see §10).
**Source of truth:** [`provider_variance_paper_plan.md`](./provider_variance_paper_plan.md), committed untouched as the pre-registration record (commit 1).
**Purpose:** Extract and lock the exact decision values from the plan so they cannot drift once harness coding begins. The plan left some choices open; these were resolved by the author before any pilot and are recorded in §10. No previously **PENDING** value remains unresolved.

---

## 1. Hypotheses (verbatim from plan §1)

- **H1:** Cross-provider accuracy spread exceeds within-provider noise for at least one model+benchmark.
- **H2:** There exists at least one (benchmark, model-pair) where the sign of (acc_A − acc_B) depends on which providers serve A and B.
- **H3:** Repeated identical calls to one provider at temp 0 produce non-identical outputs and non-zero accuracy variance.
- **H4:** Accuracy correlates with disclosed quantization; some providers underperform their disclosed precision tier.

Each hypothesis is pre-registered as two-sided: a null result is reported as an informative finding (provider-robustness / no ranking flips / determinism / disclosed-precision-predicts-accuracy), per the plan's "both outcomes are publishable" design principle.

---

## 2. Decision thresholds (verbatim from plan §1)

- **Meaningful spread:** max−min provider accuracy ≥ **3 percentage points** AND the gap's bootstrap **95% CI excludes 0**. Both conditions required.
- **Ranking flip:** sign of (acc_A − acc_B) differs across provider assignments, with each direction's gap CI excluding 0 in at least one configuration. A flip where both directions are within noise is reported as **"ranking indeterminate,"** itself a registered finding.

---

## 3. Models under test (plan §3)

- **Llama 3.3 70B Instruct**
- **Qwen2.5 72B Instruct**

Run-time condition: confirm ≥4 providers each at snapshot time; substitute a comparable 70B-class open model only if this condition fails (substitution, if any, is logged and dated).

### Ranking-flip model-pair (RQ2)

- **Llama 3.3 70B Instruct  vs  Qwen2.5 72B Instruct** — the sole pair (two models under test). This is the (model-pair) used for the H2 / RQ2 ranking-flip analysis across all provider assignment combinations, per benchmark.

---

## 4. Providers (plan §3, §4)

- **Target: 4–6 distinct providers pinned per model.**
- Exact provider **slugs are NOT frozen here** — provider availability is time-varying. Slugs, disclosed quantization, context length, and price are captured by the snapshot tool at run start AND run end (UTC-timestamped JSON), per plan §4/§11.
- Pinning contract (plan §4): `provider: { order: ["<slug>"], allow_fallbacks: false, require_parameters: true }`.
- Provider read-back: the response `provider` field is asserted to equal the pinned slug on every call; mismatches are marked invalid and logged, never silently kept.
- `:floor` (cheapest routing) is additionally run for the cost-accuracy frontier; the resolved provider is recorded per call.

---

## 5. Benchmarks and item counts (plan §3)

| Benchmark | Item count | Grading |
|-----------|-----------|---------|
| GSM8K     | **300** (uniform sample, `openai/gsm8k` main/test, seed 20260629) | exact-match final answer |
| MMLU slice | **300** (stratified: fixed items per subject across all 57, ~5–6 each, `cais/mmlu` test, seed 20260629) | letter match |
| HumanEval | **164** (all, `openai/humaneval`) | unit tests in sandboxed subprocess |

- **MMLU is stratified**, not uniform-pooled: a fixed number of items is drawn per subject across all 57 subjects (target ≈ 300 total ⇒ ~5–6 per subject); the exact per-subject counts are logged in the frozen item file.
- **Paired design:** item sets are frozen to `data/items/` exactly once and reloaded for every (model, provider, repeat). Items are never re-sampled.
- Graders are byte-for-byte identical across all providers and models. Every parse is logged for manual audit of disagreements (plan §5, §8).

---

## 6. Run parameters (plan §3)

| Parameter | Value |
|-----------|-------|
| temperature | **0** |
| top_p | **1** |
| repeats per (model, provider, benchmark, item) | **3** |
| seed | **none** — deliberately NOT sent (see §10.4) |
| max_tokens (GSM8K) | **512** |
| max_tokens (MMLU) | **16** |
| max_tokens (HumanEval) | **1024** |
| prompt templates | locked per benchmark (see §10.2) |

---

## 7. Statistical methods (plan §1, §5)

- **Per-provider accuracy CIs:** Wilson 95% confidence intervals.
- **Cross-provider spread (max−min):** paired bootstrap over items, **10,000 resamples**, 95% CI.
- **Ranking-flip:** acc_A−acc_B across all provider combinations; fraction of combos where the winner differs from the default; McNemar's test on the default configuration; paired bootstrap per combo.
- **Nondeterminism (RQ3):** exact-match output agreement + accuracy SD across the 3 temp-0 repeats.
- **Quantization audit (RQ4):** regress accuracy on disclosed precision tier; flag providers ≥1 noise-band below same-precision peers (factual, snapshot-dated, no intent claims).

---

## 8. Budget and pilot gate (plan §6, §7)

- **Hard budget cap:** default **$30 USD** (configurable). The run aborts if cumulative estimated spend exceeds the cap. Token usage and cost are tracked per call. Plan estimate: $10–30 for the full ~27k-call run.
- **Pilot gate (mandatory, plan §6):** 50 items of ONE benchmark, across ALL providers, for ONE model, **1 repeat**. The pilot confirms per-call cost + extrapolation, verifies pinning + read-back, and sanity-checks grading.
- **Full-run lock:** the full ~300×3 run **must refuse to start** until a pilot has been run and the author has explicitly confirmed (projected cost ≤ budget and harness clean).

---

## 9. Reproducibility (plan §11)

Each run directory records the resolved config, the git commit hash, and UTC timestamps. Public artifacts: harness, frozen item lists, pinned configs, raw completions (JSONL), grading scripts, notebooks, start/end provider+quant snapshot JSON, and the reporting checklist.

---

---

## 10. Resolved open choices (author, 2026-06-29, pre-pilot)

The plan left the following open. Resolved before any data collection. Defaults from the open-questions list were accepted except where overridden below.

### 10.1 Item selection
- **GSM8K:** `openai/gsm8k` (`main`, `test`), uniform sample of 300, seed **20260629**.
- **MMLU:** `cais/mmlu` (`test`), **stratified** — fixed number of items per subject across all **57** subjects (~5–6 each, ≈300 total). Per-subject counts logged in the frozen item file. Seed **20260629**.
- **HumanEval:** all **164**, no sampling.
- Single shared sampling seed **20260629**, recorded in each frozen item file.

### 10.2 Prompt templates (identical per benchmark across all providers/models; frozen with the item set)
- **GSM8K:** standard **8-shot chain-of-thought** using the **Wei et al. exemplars**, with a `####` final-answer delimiter. The 8 exemplars are **frozen in the GSM8K item file**.
- **MMLU:** **5-shot**, options labeled A–D, instruction "answer with the single letter." (5-shot exemplars drawn per the standard MMLU dev-set convention; frozen with the item set.)
- **HumanEval:** **raw function-signature completion** (standard harness) — NOT instruction-wrapped.
- **System prompt:** none (user message only), identical across providers.

### 10.3 Decoding
- `max_tokens`: GSM8K **512**, MMLU **16**, HumanEval **1024**.
- temperature **0**, top_p **1**.

### 10.4 Seed parameter — deliberate RQ3 decision
- The OpenRouter `seed` parameter is **deliberately NOT sent.** RQ3 measures provider nondeterminism at temperature 0; pinning a seed would mask exactly the effect H3 is designed to detect. This is a pre-registered measurement decision, not an oversight.

### 10.5 Grading / parsing (identical parser across providers; every parse logged for audit)
- **GSM8K:** take the number after `####`; fall back to the last number in the text; normalize commas / `$` / trailing `.0`. The path taken is logged per call.
- **MMLU:** first standalone A–D (case-insensitive regex); unparseable ⇒ incorrect AND flagged.
- **HumanEval:** extract code from the first fenced block (or whole text if none); append the official `check(candidate)`; run in sandbox.
- **Truncated / empty / refused** outputs ⇒ incorrect AND flagged.

### 10.6 Code-execution sandbox (HumanEval)
- Fresh **subprocess** per candidate (no Docker), temp cwd, process-group kill, **10s** wall-clock timeout per problem.

### 10.7 OpenRouter client / budget
- **Cost ground truth:** OpenRouter-returned per-response cost drives the running total; snapshot prices used only for pre-flight projection.
- **Retry/backoff:** retry on 429 + 5xx + network/timeout; max 5 attempts; exponential backoff w/ jitter (base 1s, cap 60s); honor `Retry-After`; 4xx (except 429) not retried; each attempt logged.
- **Invalid records** (provider mismatch / exhausted retries): marked invalid + logged, re-queued once at end of run; persistent failures left as a logged gap.
- **Per-call request timeout:** 120s.

### 10.8 Pilot
- 50 items of **GSM8K** on **Llama 3.3 70B Instruct**, all pinned providers + `:floor`, **1 repeat**.

### 10.9 Tooling
- `uv` + `pyproject.toml`. Run dirs: `runs/<UTC-timestamp>_<git-sha>/` with a copy of the resolved config; raw JSONL under `data/raw/`.

---

## 11. Provider taxonomy & scope (amendment, 2026-06-29, post-snapshot, pre-pilot)

The start snapshot (`data/snapshots/providers_start_20260629T181444Z.json`) enumerated **13
endpoints** for `meta-llama/llama-3.3-70b-instruct`. We classify each endpoint **neutrally**
as **CANONICAL** (a distinct provider's plain/base endpoint, optionally carrying a per-quant
tag like `/fp8`) or **VARIANT/SKU** (a vendor-*optimized* or *region*-pinned endpoint, e.g.
`*-turbo`, `*/us-central1`). **This is a naming/topology distinction, not a quality judgment.**

A per-quant tag (`/fp8`, `/bf16`, `/fp16`) is part of the CANONICAL slug — it is the provider's
disclosed precision, not an "optimization SKU." Only optimization (`turbo`) and region tags
make an endpoint a VARIANT.

### Primary provider set — CANONICAL endpoints (the primary study, RQ1–RQ4)

One canonical endpoint per distinct provider; the two SambaNova and two Google entries are
deduped to their plain base endpoint.

| # | Provider | Pin slug | Disclosed quant | Context |
|---|----------|----------|-----------------|---------|
| 1 | Nebius | `nebius/fp8` | fp8 | 131072 |
| 2 | AkashML | `akashml/fp8` | fp8 | 131072 |
| 3 | Novita | `novita/bf16` | bf16 | 131072 |
| 4 | Parasail | `parasail/fp8` | fp8 | 131072 |
| 5 | Cloudflare | `cloudflare/fp8` | fp8 | 24000 |
| 6 | Groq | `groq` | unknown | 131072 |
| 7 | SambaNova | `sambanova/bf16` | bf16 | 131072 |
| 8 | WandB | `wandb/fp16` | fp16 | 128000 |
| 9 | Google (Vertex) | `google-vertex` | unknown | 128000 |
| 10 | Together | `together/fp8` | fp8 | 131072 |

**10 canonical providers.** Quant spread: fp8 ×6, bf16 ×2, fp16 ×1, unknown ×2.

### Secondary set — VARIANT/SKU endpoints (secondary analysis only)

Measured *separately* for whether they differ from their canonical sibling, with **no prior
assumption about direction** (faster, slower, more accurate, or less — all open empirical
questions answered by data).

| Endpoint | Quant | Type | Canonical sibling |
|----------|-------|------|-------------------|
| `deepinfra/turbo` | fp8 | optimized SKU | none currently listed (DeepInfra exposes only the turbo endpoint for this model) |
| `sambanova-turbo` | bf16 | optimized SKU | `sambanova/bf16` |
| `google-vertex/us-central1` | unknown | region-pinned | `google-vertex` |

13 endpoints = 10 canonical + 3 variant. The variant set is **not** mixed into primary
per-provider accuracy.

## 12. Lesson recorded — never interpret content from non-clean responses

A completion's CONTENT is interpreted **only** if the call was a clean HTTP 200 with valid
auth. An earlier "garbage backslash output" attributed to `deepinfra/turbo` came from a run
with a **bogus key (HTTP 401)** and was **void**; with a valid key that endpoint returns a
clean answer identical to its peers. The harness already marks any non-200/auth-failed call
`valid=false` and stores its body only as an error string; analysis must filter on
`valid=true` before reading `completion_text`. (See also `LESSONS.md`.)

## 13. TODO before the FULL run (not a pilot blocker) — second model

`qwen/qwen-2.5-72b-instruct` showed only **2 providers** in the snapshot — too thin to be the
sole second model for RQ2 (ranking flips need provider breadth on both models). Before the
full run: snapshot 2–3 candidate second models and pick one with **≥5 canonical providers**.
Record the chosen model + its canonical set as a further amendment. The pilot proceeds on
Llama 3.3 70B alone.

---

*Further amendments after the pilot are made as separate, dated commits so the pre-registration history stays auditable.*
