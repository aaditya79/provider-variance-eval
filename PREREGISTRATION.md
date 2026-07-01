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

## 14. Read-back resolution & granularity caveat (amendment, post-pilot, 2026-06-29)

The GSM8K pilot surfaced that `google-vertex` got 50/50 `provider_readback_mismatch` despite
all 50 calls being clean HTTP 200, `finish=stop`, real CoT (90% accuracy when graded). Raw
strings: pinned slug `google-vertex`, served display name **`Google`** (verbatim, every call).
This is a **normalization gap (case a), not a reroute** — the calls succeeded; only the label
format differed.

**Fix (not a coercion):** the read-back now matches the served display name against the slug's
**disclosed `provider_name` from the snapshot** (authoritative `{slug -> provider_name}` map),
not a string-munged slug. `google-vertex` is disclosed as `Google`, so served `Google` matches.
`google-vertex` is **KEPT in the primary set.** Distinct providers still mismatch (tested:
expecting `Google` but served `Novita` ⇒ invalid).

**Granularity caveat (documented, not hidden):** two provider families expose >1 endpoint that
share one display name:
- `google-vertex` and `google-vertex/us-central1` both disclose `Google`.
- `sambanova/bf16` and `sambanova-turbo` both disclose `SambaNova`.

So for these families the read-back confirms identity at **family granularity** (a Google /
SambaNova endpoint served the call), not the exact sub-endpoint. **Exact-endpoint routing
integrity still holds** because we pin by slug with `allow_fallbacks:false` (OpenRouter routes
to the pinned endpoint or errors — it cannot silently swap to the sibling). Only the primary
canonical endpoint of each family is in the primary set; its variant sibling is secondary, so
within the primary set there is no within-family ambiguity.

## 15. DECIDED (author, 2026-06-29) — `finish_reason == "error"` is a third outcome class

**Principle (author):** `finish_reason == "error"` is a provider-side *serving* failure, not the
model producing a wrong answer. Conflating the two corrupts the central measurement. It is its
own outcome class:
- Marked `valid=false`, `invalid_reason="generation_error"` (distinct from `provider_readback_
  mismatch` and from a clean wrong answer). **Excluded from accuracy numerator AND denominator.**
- **Retried** with the standard bounded backoff (transient serving fault). A successful retry
  yields a clean gradeable call.
- If it still errors after max retries, logged as a **persistent gap** (runner handles missing
  cells) — never coerced to "incorrect."
- **Per-provider error rate is reported as a first-class reliability metric** alongside accuracy
  (relevant to RQ3), not buried inside it.

Implemented: client marks + retries `generation_error`; pilot/analysis report `gen_err` rate
per provider. `finish_reason == "length"` (hit `max_tokens`) remains a separate case, graded
as-is unless separately flagged.

### Original framing (kept for the record):

Cloudflare's pilot accuracy looked low (66%) but the raw completions show **16/50 calls returned
`finish_reason == "error"`**: HTTP 200 with a completion **truncated mid-sentence** (`ctok=None`),
i.e. a provider-side generation failure, not a wrong answer. The parser's last-number fallback
then grabbed an intermediate value and mis-graded it. **Excluding the 16 errored calls,
Cloudflare is 33/34 = 97.1%** — in line with the 94–98% pack (only 1 genuine wrong-with-
`finish=stop`).

Current harness behavior counts these as wrong (they are `valid=true` because read-back matched).
**Proposed (pending author sign-off):** treat `finish_reason == "error"` as a **failed call**
(`valid=false`, `invalid_reason="generation_error"`), exclude from accuracy, and **retry** it like
a transient error; report per-provider error rate separately as a reliability finding (relevant
to RQ3). This conflates-reliability-with-accuracy fix is a grading-semantics change and is
therefore recorded here for explicit approval before the full run. `finish_reason == "length"`
(hit `max_tokens`) is a separate case and remains graded as-is unless also flagged.

## 16. FINAL primary provider set & two outcome axes (author, 2026-06-29, post-pilot)

**Primary set = all 10 canonical providers** (PREREGISTRATION §11), confirmed after pilot review:

- **`google-vertex` KEPT.** Benign normalization gap: 50/50 clean `finish=stop` completions
  reporting display name `Google`, which matches OpenRouter's disclosed `provider_name` for the
  slug. Read-back uses the authoritative disclosed-name map (not a munged slug). Caveat: the
  `Google` label confirms *family*, not exact endpoint, but the exact endpoint is guaranteed by
  the slug pin + `allow_fallbacks:false`; `google-vertex/us-central1` is *secondary*, so the
  primary set holds exactly one canonical Google endpoint. No ambiguity within primary.
- **`cloudflare/fp8` KEPT.** Its low pilot accuracy was a **serving-reliability artifact, not bad
  reasoning**: 16/50 calls truncated mid-generation (`finish=error`) with correct reasoning up to
  the cut. Clean-completion accuracy = 33/34 = 97.1%, in line with peers. Cloudflare is the
  primary exhibit for the reliability axis.

**Two separable PRIMARY outcome axes (both pre-registered as primary results):**
1. **Clean-completion accuracy** — correctness over `valid=true` completions (excludes
   `generation_error` and `provider_readback_mismatch` from numerator AND denominator), with
   Wilson 95% CIs.
2. **Per-provider reliability** — the `generation_error` rate (and, separately, read-back
   mismatch rate). Reported alongside accuracy, never folded into it.

## 17. Parser tightening (author, 2026-06-29, before full run)

A `valid`, `finish=stop` completion that LACKS the `####` delimiter is **flagged for audit**, not
silently graded via the last-number fallback. Parse-path taxonomy (recorded per call):

- `delimiter` — `####` present with a parseable number after it (the intended path).
- `delimiter_missing_flagged` — no `####` in the output; last-number fallback used, **flagged**.
- `delimiter_unusable_flagged` — `####` present but no number after it; last-number fallback
  used, **flagged**.
- `unparseable` — no number anywhere; counts as incorrect, flagged.

The last-number fallback still produces a gradeable value (we do not discard the item), but it is
**never silent**: any non-`delimiter` path is flagged so disagreements can be audited by hand.
Flagged rates are reported per provider in the results table.

## 18. `sambanova/bf16` dropped — became unavailable between snapshot and run (2026-07-01)

In the full GSM8K run, `sambanova/bf16` returned **900/900 HTTP 404**:
`{"error":{"message":"No endpoints found for meta-llama/llama-3.3-70b-instruct.","code":404}}`
($0 billed). It disclosed `bf16` / 131072 ctx at snapshot time but the endpoint was gone at run
time — a real instance of the plan's time-variation threat (§8). **Dropped from the primary set;
primary is now 9 canonical providers.** All accuracy/spread/H1 statistics are computed over the 9
working providers. The 404 evidence is preserved in the raw JSONL and the invalid breakdown.

## 19. google-vertex low accuracy is largely a SERVING-TRUNCATION artifact (2026-07-01, audit)

The parser flag (§17) did its job. Auditing google-vertex's **34** `delimiter_missing_flagged`
completions verbatim: **34/34 graded wrong, and all are TRUNCATED** — cut off mid-sentence with
the `####` answer never emitted, `finish_reason="stop"` (33) at `ctok` 39–191 (far below
`max_tokens=512`). They are NOT format mismatches (google-vertex emits `####` cleanly on its other
866 calls) and NOT genuine reasoning errors — the answer simply never arrived. So google-vertex's
gap is mostly a serving artifact, not the model being worse.

**Impact (excluding flagged truncations as non-answers):**
- google-vertex 92.4% → **96.1%** (832/866) — back in the pack.
- Other providers shift ≤0.9pp (each has 1–9 flagged).
- **Cross-provider spread collapses from 4.67pp (as-collected) to ~1.6pp (truncation-excluded)** —
  which flips the H1 "meaningful spread" read (≥3pp) from YES to NO. **This is decision-critical.**

Two truncation sub-types among the 74 total flagged (67/74 have no `####` and no terminal
punctuation):
- `finish="stop"` but incomplete (34, all google-vertex): a **provider serving truncation** — the
  same category as `generation_error` but mislabeled `stop`, so §15 didn't catch it.
- `finish="length"` (40, spread across providers): hit `max_tokens=512` before reaching `####` — a
  **budget** issue, not a provider fault.

### OPEN DECISION (before finalizing GSM8K numbers)
How to treat flagged truncations — needs author sign-off, analogous to §15:
1. `finish="stop"` + truncated (no `####`, `ctok` << max) → reclassify as a serving failure
   (`invalid_reason="generation_stop_truncated"`), exclude from accuracy, retry, report rate.
2. `finish="length"` → either raise `max_tokens` (pre-reg change) and re-run those cells, or
   exclude uniformly as non-answers.
No reclassification is applied yet; the as-collected AND truncation-excluded numbers are both
reported so the choice is explicit.

## 20. Truncation handling — DECIDED (author, 2026-07-01)

Resolving the §19 open decision. Two provider serving failure modes, reported as **distinct
headline reliability findings** (not footnotes), both excluded from accuracy num+denom and retried:

- **overt_truncation** — `finish_reason=='error'` (Cloudflare). HTTP 200 but the provider broke
  mid-generation with truncated/empty content. Pilot/full rate: Cloudflare **16.2%**.
- **silent_truncation** — `finish_reason=='stop'` but the completion lacks `####` AND ends
  mid-token/mid-sentence (no terminal punctuation) (google-vertex). The provider *claims* a clean
  stop on an incomplete generation. Observed rate: google-vertex **3.6%** (32/900). This is a NEW
  subtype `generation_error/silent_truncation`; detection is `is_silent_truncation()`.

Both are `invalid_reason="generation_error"` with `invalid_subtype` distinguishing them; both are
auto-retried by the client (transient serving faults); residual (post-retry) counts are reported
as per-provider reliability rates alongside accuracy (§16 axis 2).

## 21. `max_tokens` raised 512 -> 1024 for GSM8K (author, 2026-07-01, amendment)

**Rationale:** 40 cells hit `finish_reason=='length'` (the old 512 cap) before emitting `####`.
That is OUR budget cap, not a provider property, so it must not be attributed to any provider.
`max_tokens` is raised to **1024** and ONLY the affected (length-truncated) cells are re-run
(`scripts/rerun_cells.py`), preserving the paired design; the other 9,826 cells are unchanged.
If a cell still hits `length` at 1024 it is excluded uniformly (attributed to no provider). The
silent-truncation cells are retried in the same pass. This is a decoding-parameter amendment,
logged here; all other frozen parameters are unchanged.

## 22. FINAL GSM8K result — H1 NOT met (clean completions, 9 providers, 2026-07-01)

After dropping `sambanova/bf16` (§18) and excluding all truncations (§20-21), over the 9 working
providers on clean completions:

- Per-provider clean accuracy ranges **95.6% (groq) – 97.2% (nebius)**; POOLED **96.3%**
  [95.9, 96.7]. **Spread (max-min) = 1.60 pp < 3 pp threshold => H1 "meaningful spread" NOT met.**
- **After recovering the truncated cells at max_tokens=1024** (§21 re-run, 73 cells merged): POOLED
  **96.2%** [95.8, 96.6], spread **1.45 pp** (nebius 97.1% .. groq 95.7%) — H1 still NOT met, and
  the conclusion is now robust to both dropping AND recovering the truncations.
- **Recoverability nuance (reliability finding):** the silent truncations were **transient** —
  re-running recovered 31/32 of google-vertex's into clean gradeable answers (1 residual turned
  overt). By contrast Cloudflare's **overt** truncations persist (16.2%, already retried at
  collection). So the two failure modes differ not just in labeling but in recoverability:
  silent = transient/retry-recoverable, overt = persistent.
- **Robustness:** the as-collected spread (4.67 pp) was an artifact — 34 of google-vertex's 68
  wrongs were silent truncations, not model errors. Under the pre-registered clean-completion
  policy the spread is 1.60 pp; the H1 = NO conclusion holds under the truncation handling.
  (The pre-registered paired-bootstrap CI on the spread is the confirmatory test in the analysis
  stage; the Wilson non-overlap view shows no provider pair separates once truncations are excluded.)
- **RQ3/reliability (separate axis, both non-null findings):** Cloudflare overt-truncation
  **16.2%**, google-vertex silent-truncation **3.6%**; all other providers ~0. sambanova/bf16
  fully unavailable (404).

Headline: for Llama-3.3-70B on GSM8K, **clean-completion accuracy is provider-robust (no
meaningful spread), but providers differ sharply on serving reliability** (two distinct
truncation failure modes) — the reproducibility risk here is reliability/availability, not accuracy.

## 23. Confirmed paper framing & second-model role (author, 2026-07-01)

Based on the GSM8K result (§22), the paper's framing is updated (the plan pre-registered both
outcomes, §1/§9; this records which obtained):

- **Confirmed headline:** clean-completion **accuracy is provider-robust** for Llama-3.3-70B on
  GSM8K (spread 1.6 pp, H1 not met). Accordingly **RQ2 (ranking flips) is likely UNSUPPORTED on
  accuracy** — providers cluster too tightly to reverse a model-vs-model ranking. This is the
  "reassurance" branch for accuracy.
- **Primary contribution is the RELIABILITY axis:** providers differ sharply and in *kind* —
  **overt truncation** (`finish_reason=='error'`, Cloudflare 16.2%) vs **silent truncation**
  (`finish_reason=='stop'` on an incomplete generation, google-vertex 3.6%) — plus the general
  methodological finding that **`finish_reason` is an unreliable completeness signal** (a provider
  can report a clean stop on a truncated answer, which silently corrupts naive accuracy scoring).
- **Second model's role = REPLICATION of the reliability pattern**, NOT to rescue a ranking flip.
  Success = showing the overt/silent truncation and finish_reason-unreliability phenomena recur on
  an independent open model. Selection criterion is therefore provider COVERAGE + liveness
  (≥5 canonical providers actually serving), not ranking stakes.

## 24. Second model LOCKED — `meta-llama/llama-3.1-8b-instruct` (author, 2026-07-01)

**Second model = `meta-llama/llama-3.1-8b-instruct`**, 6 live canonical providers (liveness-probed):
`deepinfra/fp8`, `novita/fp8`, `deepinfra/bf16`, `groq`, `cloudflare/fp8`, `wandb/bf16`
(quant spread fp8 / bf16 / unknown).

- **Role = RELIABILITY REPLICATION across models**, NOT accuracy. The serving-reliability axis
  (overt/silent truncation, `finish_reason` reliability) is an **infrastructure property of the
  provider deployment**, so the 8B-vs-70B size gap is irrelevant to it. **Cross-model ACCURACY
  comparison is explicitly NOT claimed** (different model sizes; accuracy is only compared
  across providers *within* a model).
- **Cloudflare serves BOTH models** (`cloudflare/fp8` on Llama-3.3-70B and Llama-3.1-8B) — a
  **direct test of whether its overt-truncation pathology (16.2% on GSM8K/70B) is a provider
  property that generalizes across models.** Flagged as a key comparison. (Other overlaps:
  deepinfra, novita, wandb, groq also serve both.)
- **Ecosystem finding (reportable result + selection rationale):** of **8** probed open models,
  only **2** have ≥5 live canonical providers — wide multi-provider serving concentrates on a few
  popular models. This is *why* Llama-3.3-70B (13) and Llama-3.1-8B (6) were selected, and is
  itself a finding about the API-marketplace: "same model, many providers" is the exception, not
  the norm.

## 25. MMLU `max_tokens` raised 16 -> 64 (author, 2026-07-01, amendment)

**Rationale:** the 16-token MMLU pilots showed the cap was measuring PARSER FAILURE, not accuracy.
On Llama-3.1-8B at 16 tokens, `finish=='length'` fired on ~49/50 calls for most providers and
unparseable rates hit 22–36/50 (accuracy 16–36%) — the chatty 8B model reasons before the letter
and gets cut off. Raised to **64**. Only the MMLU pilots are re-run (paired design); the full run
uses 64. If a cell still hits `length` at 64 it is handled as an our-cap exclusion (as GSM8K §21),
attributed to no provider.

**Key disambiguation this sets up (RQ3 headline):** at 16 tokens the providers split cleanly —
every provider EXCEPT Cloudflare reported `finish=='length'` (honest "I hit the cap") on cut-off
calls, while **Cloudflare alone reported `finish=='stop'` with a truncated, letter-less output
(silent_truncation, 26/50)**. So even at the tight cap, Cloudflare's `finish_reason` is
*mislabeled* relative to every peer under identical conditions — direct evidence for the
"`finish_reason` is an unreliable completeness signal" finding. The 64-token re-run tests whether
Cloudflare *also truncates earlier than peers* (real serving pathology, headline) or merely
mislabels the same cap-hit (lesser but still real finding); the reported metric is Cloudflare's
silent_truncation rate on 8B-MMLU at 64 tokens.

## 26. Cloudflare truncation REPLICATES across benchmarks and models (author, 2026-07-01, pilots)

Cloudflare exhibits truncation pathology on every (benchmark × model) cell where it serves, in a
provider-specific way peers do not:

| cell | Cloudflare truncation | peers |
|------|----------------------|-------|
| GSM8K / 70B (full) | overt 16.2% (finish=error) | ~0 |
| HumanEval / 70B (pilot) | overt 12% (finish=error) | ~0 |
| HumanEval / 8B (pilot) | 0 | ~0 |
| MMLU / 8B (pilot, 16 tok) | **silent 52%** (finish=stop, uniquely) | others finish=length |

This is the pre-registered **reliability replication** (§24): the pathology is a property of the
Cloudflare *deployment*, recurring across a different benchmark and a different model, and it
manifests as BOTH failure modes (overt on GSM8K/HumanEval-70B, silent on MMLU-8B). HumanEval-8B is
the one clean cell so far (to be confirmed at scale).

### DISAMBIGUATION CONFIRMED (64-token MMLU/8B re-run)

At `max_tokens=64` on MMLU/8B, Cloudflare silent-truncates **10/50 (20%)** while **all 6 peers are
at 0% AND emit clean letters** (unparseables collapsed). This **rules out mere cap-mislabeling**:
under peer-clean conditions Cloudflare still truncates → **real Cloudflare serving pathology**, not
our cap. The rate fell **52% → 20%** from 16→64 tokens: part was cap-driven, but a **20% residual
persists** when every peer is clean. Full Cloudflare-across-conditions table:

| cell | Cloudflare truncation | peers |
|------|----------------------|-------|
| GSM8K / 70B (full) | overt 16.2% (finish=error) | ~0 |
| HumanEval / 70B (pilot) | overt 12% (finish=error) | ~0 |
| HumanEval / 8B (pilot) | 0 | ~0 |
| MMLU / 8B (pilot, 16 tok) | silent 52% (finish=stop) | others finish=length |
| MMLU / 8B (pilot, 64 tok) | **silent 20% (residual, real)** | **0% and clean letters** |

### CAVEAT — 8B MMLU accuracy is NOT a provider effect

The Llama-3.1-8B MMLU accuracy spread (~30–48%) is **parser / small-model formatting noise**
(elevated unparseable rates on novita/groq from the 8B's chatty formatting), **not** provider
accuracy variance. Per §24, the 8B's role is the **RELIABILITY axis only**; **8B accuracy is not
reported as a provider effect.** Cross-provider accuracy claims are made only for Llama-3.3-70B.

---

*Further amendments after the pilot are made as separate, dated commits so the pre-registration history stays auditable.*
