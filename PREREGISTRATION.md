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

## 27. Cloudflare truncation is CONDITIONAL on output length (author, 2026-07-02, reframe)

MMLU/70B full run: accuracy is provider-invariant (75.7–80.2%, overlapping CIs, H1 NO — same as
GSM8K), data clean. Reliability: **Cloudflare only 3/900 = 0.3% on MMLU/70B — a CLEAN cell.**

**Reframe (honest):** Cloudflare's truncation is **conditional, not constant** — it correlates with
**generation length**. Heavy on long-output tasks, near-zero on short-output tasks. Direct evidence
(overall avg completion tokens vs Cloudflare truncation rate):

| cell | avg completion tokens | Cloudflare truncation |
|------|----------------------|----------------------|
| GSM8K / 70B (CoT) | 165 | overt 16.2% |
| HumanEval / 70B (code) | ~390 (pilot) | overt 12% (pilot) |
| MMLU / 70B (letter) | **5** | **0.3% (clean)** |
| MMLU / 8B (letter) | ? (test below) | silent 20% |
| HumanEval / 8B (code) | ~200 (pilot) | 0% (pilot) |

**Length-dependence hypothesis:** Cloudflare's `/fp8` deployment fails to complete long generations
(truncating overtly on 70B, silently on 8B) but serves short generations cleanly. This turns the
finding from "Cloudflare is unreliable" into the sharper, more useful "provider reliability is
**workload-dependent** — the same endpoint that looks perfect on MMLU drops 12–16% of long-form
answers." Reporting checklist implication: a provider's reliability must be characterized on the
OUTPUT-LENGTH regime you actually use.

**Exception to test = MMLU/8B silent 20%.** MMLU output should be short (~2–8 tok), yet 8B shows 20%
silent truncation where 70B shows 0.3%. Need MMLU/8B avg completion tokens: if the 8B runs longer
(chatty pre-letter reasoning) that fits the length hypothesis; if not, it's a model×provider
interaction. The full runs report avg_ct alongside truncation per provider to test this directly.

## 28. Remaining full runs report avg completion tokens (author, 2026-07-02)

The 3 remaining full runs (MMLU/8B, HumanEval/70B, HumanEval/8B) report per-provider avg completion
tokens next to the truncation rate, so the length-dependence hypothesis (§27) is testable across
every (benchmark × model × provider) cell. After these land: writing — no new benchmarks/models.

## 29. MMLU/8B full — Cloudflare silent 13.8% at scale (author, 2026-07-02)

MMLU/8B full (300×3×7): **Cloudflare silent-truncates 124/900 = 13.8%**, peers ~0 (peer max 0.7%).
Confirms the pilot (20% on 50 items) at scale. **8B MMLU accuracy (31–41%) is parser/model
formatting noise, NOT a provider accuracy effect** (unparseable counts: groq 215, novita 146,
wandb 126 — the chatty 8B doesn't emit a clean letter). Per §24/§26, 8B is the **reliability axis
only**; 8B accuracy is not reported as a provider effect.

## 30. HONEST length analysis — reject the single-mechanism claim (author, 2026-07-02)

Correcting the §27 lean-in (which was based on only 2 cells). Across all 5 cells (3 full + 2
HumanEval pilots), Cloudflare truncation vs overall avg output tokens:

| cell | kind | avg_ct | CF trunc% | overt | silent | peer max |
|------|------|--------|-----------|-------|--------|----------|
| MMLU/70B | full | 5 | 0.3% | 0 | 3 | 0.0% |
| MMLU/8B | full | 57 | 13.8% | 0 | 124 | 0.7% |
| GSM8K/70B | full | 165 | 16.2% | 146 | 0 | 0.0% |
| HumanEval/8B | pilot | 206 | 0.0% | 0 | 0 | 0.0% |
| HumanEval/70B | pilot | 397 | 12.0% | 6 | 0 | 0.0% |

**Spearman ρ(avg_ct, CF trunc rate) = −0.10 → NO monotonic length correlation.** HumanEval/8B
(2nd-highest avg_ct, 0%) and MMLU/8B (low avg_ct, 13.8%) break a pure length story. So:

- **ROBUST claims (state as findings):**
  1. **Cloudflare truncates where peers do not** — in every cell with truncation, Cloudflare is
     12–16% while all peers are ≤0.7%. Provider-specific, not benchmark-intrinsic.
  2. **`finish_reason` is an unreliable completeness signal** — Cloudflare's failures on the 8B
     are *silent* (`finish=='stop'` on truncated output), so naive scoring miscounts them.
  3. The overt-vs-silent SPLIT tracks the **model** (70B → overt `finish=error`; 8B → silent
     `finish=stop`), NOT output length.
- **SOFTER / not supported:** "truncation rate rises with generation length" — suggestive *within*
  the 70B model (long GSM8K/HumanEval truncate, short MMLU clean) but contradicted by the 8B cells;
  across all 5 the rank correlation is ~0. **Do NOT claim a single clean length mechanism.** The
  honest statement is that truncation is **provider- and model-conditional**, with output length a
  plausible contributor only within the 70B deployment.

Caveat: HumanEval rows are PILOT-scale (n=50/provider); full HumanEval runs would tighten those two
points. As of this writing the two HumanEval FULL runs are not yet on disk (70B stub, 8B absent).

## 31. Data-collection status (author, 2026-07-02; UPDATED 2026-07-04 → COMPLETE)

All 5 cells now full: GSM8K/70B, MMLU/70B, MMLU/8B, HumanEval/70B, HumanEval/8B.

## 32. novita/bf16 transient OUTAGE on HumanEval/70B — NOT a reliability finding (2026-07-04)

The HumanEval/70B run showed an invalid burst (progress log 13→168, spend flat at $0.24). Traced
entirely to **novita/bf16: 166/492 cells invalid** = **109 empty HTTP-200 responses** (no provider
field, no content, no generation id — labeled `provider_readback_mismatch` by the old client but
really empty responses) + **57 HTTP-429** (rate-limit). All **$0 (unbilled)** → the flat spend.
They span novita's own block (cell-index 986–1474) over an ~8h window → a **transient provider
outage / rate-limit exhaustion**, NOT truncation and NOT a read-back-integrity problem.

- **Do NOT attribute this to a reliability finding.** It is provider *availability*, dated and
  distinct from the truncation axis. novita's truncation rate is 0.
- **n impact:** novita's usable n fell to 326 (vs ~492 peers). Its pass@1 (66.3%) is on reduced n.
  **Targeted re-run recommended** to restore comparable n:
  `python scripts/rerun_cells.py <he70b.jsonl> --benchmark humaneval --which invalid --provider novita/bf16`
- **Harness fix (applied):** empty HTTP-200 responses are now classified `empty_response`
  (retryable), distinct from `provider_readback_mismatch`; both `empty_response` and
  `generation_error` are auto-retried. (The existing data predates this; re-run to apply.)

## 33. HumanEval full results (2026-07-04; HumanEval/70B RECOVERED 2026-07-08)

- **Accuracy provider-invariant** (same as GSM8K/MMLU): 70B pass@1 pooled **63.3%** [61.9, 64.6]
  (recovered file: 63.4% [62.0, 64.8], unchanged), providers 59.8–66.3% (overlapping CIs, H1 NO);
  8B pooled **50.4%**, providers 49–52%. (8B accuracy still not reported as a provider effect per §24.)
- **Cloudflare truncation CONFIRMED at full scale:** HumanEval/70B **overt 39/492 = 7.9%**
  (pilot 12%; same direction, provider-specific, peers 0), avg_ct 415. HumanEval/8B **0%** (clean,
  matches pilot), avg_ct 185.

### HumanEval/70B FINAL (post novita-recovery) — SUPERSEDES the pre-recovery table

novita/bf16's transient outage (§32) was recovered by a targeted re-run of its 166 invalid cells:
- **novita/bf16 n restored 326 → 489**, pass@1 **65.4%** (3 cells still-bad after retries — logged,
  not coerced to incorrect).
- Pooled pass@1 **63.3% [61.9, 64.6]** (unchanged; recovery only restored n).
- Cloudflare **7.9% overt truncation (39/492)**, peers 0.
- **Total invalid 44/4920 = 0.9%** (down from 207/4920 = 4.2% pre-recovery).
- The recovered merged JSONL is the CANONICAL HumanEval/70B result (durably persisted; §35).

## 34b. (numbering note) The anchor table and claims live in §34 above; §35 lists canonical files.

## 35. CANONICAL result files — source of truth per cell (reproducibility, 2026-07-08)

Each cell's authoritative raw JSONL (under `~/pv_runs/`, durably persisted with manifest). Cite
these in the paper's reproducibility section:

| cell | rows | canonical file |
|------|------|----------------|
| GSM8K / 70B | 9900 | `~/pv_runs/full_gsm8k_20260630T164925Z_nogit/raw/gsm8k.jsonl` |
| MMLU / 70B | 9000 | `~/pv_runs/full_mmlu_llama-3.3-70b_20260701T232233Z_nogit/raw/mmlu.jsonl` |
| MMLU / 8B | 6300 | `~/pv_runs/full_mmlu_llama-3.1-8b_20260702T010240Z_nogit/raw/mmlu.jsonl` |
| HumanEval / 70B (recovered) | 4920 | `~/pv_runs/final_humaneval_llama-3.3-70b_recovered/raw/humaneval.jsonl` |
| HumanEval / 8B | 3444 | `~/pv_runs/full_humaneval_llama-3.1-8b_20260703T154157Z_nogit/raw/humaneval.jsonl` |

Notes: HumanEval/70B canonical = base run `full_humaneval_llama-3.3-70b_20260702T053126Z` overlaid
with novita recovery patch `rerun_humaneval_20260705T185858Z` (see the sibling `*_manifest.json`).
GSM8K/70B's own truncation-recovery patch (`rerun_gsm8k_20260701T150826Z`) is documented in §22.
Provider snapshots (start/end) live in the repo under `data/snapshots/`. **Data collection FINAL.**

## 34. ANCHOR TABLE — consolidated 5-cell reliability matrix (2026-07-04, data COMPLETE)

| benchmark | model | avg_ct | Cloudflare trunc | subtype | peer max |
|-----------|-------|--------|------------------|---------|----------|
| MMLU | 70B | 2 | 0.3% | silent | 0.0% |
| GSM8K | 70B | 154 | 16.2% | overt | 0.0% |
| HumanEval | 70B | 415 | 7.9% | overt | 0.0%* |
| MMLU | 8B | 56 | 13.8% | silent | 0.7% |
| HumanEval | 8B | 185 | 0.0% | — | 0.0% |

\* excluding novita/bf16's dated outage (§32), which is availability not reliability.

### Length-dependence hypothesis: REJECTED

**Spearman ρ(avg_ct, Cloudflare truncation) = −0.10 over 5 cells → no relationship.** The decisive
counterexample: **HumanEval/70B (avg_ct 415) truncates LESS (7.9%) than GSM8K/70B (avg_ct 154, 16.2%)**
— higher output length, lower truncation. The earlier 2-cell impression (§27) was spurious. **Do NOT
claim length-dependence anywhere in the paper.**

### FINAL reliability claims (robust only)

(a) **Cloudflare truncates where peers complete** — 4 of 5 cells, 8–16%, while all peers are ~0.
(b) **Failure mode tracks the MODEL:** overt (`finish=error`) on Llama-3.3-70B, silent
    (`finish=stop`) on Llama-3.1-8B.
(c) **Conditional / unexplained:** clean on MMLU/70B (0.3%) and HumanEval/8B (0%); which cells
    truncate is NOT predicted by output length (ρ≈0) — reported as conditional, mechanism open.
(d) **`finish_reason` is an unreliable completeness signal** — the 8B failures are silent
    (`finish=stop` on truncated output), so naive accuracy scoring miscounts them.

Availability (novita §32) and read-back integrity are reported as separate axes, not folded into
(a)–(d). **Data collection COMPLETE. → writing.**

## 36. Truncation token-position mining + HONEST correction to §25/§26 (author, 2026-07-08)

Mined completion length at truncation for every Cloudflare truncated call. The two failure modes
have DIFFERENT signatures, and the mining forces an honest correction of the 8B "silent" claim.

### Overt (finish=error) — 70B only, SCATTERED positions (real serving drops)
- GSM8K/70B: 146 overt truncations, all Cloudflare (peers never `finish=error`); `completion_tokens`
  absent (no usage on error). Completion char-length scatters **93–909 (median 325)** across the
  whole range — no consistent cutoff or fraction of the 512 cap.
- HumanEval/70B: 39 overt, char-length **124–1448 (median 768)** — again scattered, no cutoff.
- **Interpretation (honest, for the paper):** *Cloudflare's overt failures (`finish_reason=error`)
  terminate at widely scattered output lengths with no consistent cutoff or fraction of the token
  budget, consistent with random mid-generation drops rather than a deterministic serving limit
  such as a fixed timeout or KV/batch cap (which would cluster).* Provider-specific: peers complete.

### Silent (finish=stop) on MMLU/8B — CORRECTION: mostly a finish_reason MISLABEL, not "truncation where peers complete"
Mining shows all 124 silent cases sit at exactly `completion_tokens == 64` (the cap). Comparing to
peers on MMLU/8B: **every provider hits the 64-token cap at a similar rate** (~715–762/900), BUT
- peers label cap-hits `finish=length` (finish mix, e.g. length 748 / stop 152), whereas
- **Cloudflare reports `finish=stop` for 900/900 responses — it NEVER emits `finish=length`.**

So Cloudflare's 8B behavior is NOT "it truncates where peers complete." It hits the cap like
everyone else; its distinguishing behaviors are (1) **it never reports `finish=length`** — a clear
finish_reason bug — and (2) it fails to emit a parseable letter in 13.8% of cap-hits where peers
nearly always do (a formatting/answer-emission gap, plausibly fp8-quantization-related). **This
CORRECTS §25/§26**, which framed the 8B silent rate as "real serving pathology, not cap" — the
mining shows the cap IS involved and peers also hit it; the honest 8B finding is finish_reason
unreliability + a formatting gap, not serving-truncation-where-peers-complete.

### Clean cells — cleanliness NOT explained by length
- MMLU/70B: CF avg_ct 2 (bare letter, essentially no generation to drop) — 0.3%.
- HumanEval/8B: CF avg_ct 185, char median 596 (mid-length) — 0.0%.
- The two clean cells differ (one ultra-short, one mid-length), so cleanliness is **not** attributable
  to a single factor (consistent with §34 claim (c): conditional/unexplained).

### Net effect on the FINAL claims (§34)
- (a) holds for the **70B overt** cells (real, provider-specific, scattered drops).
- (b)/(d) hold and are SHARPENED: the model-split is overt-random-drops (70B) vs
  finish_reason-mislabel+formatting-gap (8B); `finish_reason` unreliability is now crisply
  evidenced (Cloudflare never emits `finish=length`).
- Do NOT describe the 8B cell as "truncation where peers complete." Recommended paper framing: the
  8B is a finish_reason-labeling failure (+ answer-formatting gap); the 70B is genuine mid-generation
  dropping. Same provider, two distinct defects.

## 37. Breadth sweep — the "second truncator" is a FALSE POSITIVE (author, 2026-07-08)

The 5-item breadth pilot (26 deployments) flagged `wandb/bf16` on Llama-3.1-8B as a silent
truncator (1/5) — apparently a second, independent truncating provider. **On inspection it is a
FALSE POSITIVE of the GSM8K silent-truncation screen, not a real truncation.** The flagged
completion is a **complete, correct answer**:

> `...Allen's age 10 years from now = 99 + 10 = 109\n\nThe final answer is: 109`

The model answered `109` (correct) but used "The final answer is:" instead of `####` and ended on a
digit. The GSM8K `is_complete` heuristic (`####` present OR ends in terminal punctuation) therefore
misfires — a well-formed answer in non-`####` format is scored as a silent truncation.

- **Do NOT claim WandB (or any provider) as a second truncator on the raw silent count.** The raw
  `silent_truncation` tally on GSM8K over-counts complete-but-differently-formatted answers.
- **Audit required:** `scripts/audit_silent.py` re-classifies each silent flag as LIKELY-COMPLETE
  (false positive: states a final answer) vs LIKELY-TRUNCATED (real: ends mid-clause). Only
  audit-confirmed LIKELY-TRUNCATED cases count as genuine truncation.
- **The "provider truncation is a class of failure" claim is DEFERRED** to the audited n=100 sweep.
  As of the pilot, the only audit-confirmed truncator remains Cloudflare. (Note also §36: the
  detector's imperfections are why manual/audited confirmation is required before any headline.)
- Scope note: this GSM8K false-positive mode did NOT affect the main GSM8K/70B result (its
  truncations were overt `finish=error`, silent=0). MMLU silent detection keys on letter-presence,
  a stricter signal.

## 38. Status: two runs IN PROGRESS (author, 2026-07-08)

At time of writing, the 100-item breadth sweep (just started) and the temporal GSM8K/70B re-run
(~2691/9000 rows) are still being written (no completion manifests). Final breadth table (with
audited silent flags), temporal Cloudflare rate, and the consolidated all-provider truncation
finding will be produced once both complete. **No conclusions drawn from the partial files.**

## 39. Breadth 100-item sweep INVALIDATED by credit exhaustion (author, 2026-07-09)

**Diagnosis: the OpenRouter account ran out of credits mid-run — HTTP 402 "Insufficient credits".**
Not a rate-limit, auth, provider-outage, or model-specific bug. (The 5-item pilot worked because it
was 20× cheaper.)

Sequence (deployments in processing order; 402 onset at global row 1149, ~44% through):
- **Deployments 1–11 (all `llama-3.3-70b`): real data** — 11 providers returned valid≈100. Only
  `cloudflare/fp8` truncated: **20/100 overt (`generation_error`) = 20%**, confirming the ~16–20%
  rate at n=100. (Plus 2 one-off network blips.)
- **Deployment 12 (`llama-3.3-70b | together/fp8`): credits ran out mid-deployment** — 49 valid then
  **51× HTTP 402**. (No truncations; the 51 missing are 402, not drops.)
- **Deployments 13–26 (ALL 5 non-70B models + their 14 providers): 100% HTTP 402, ZERO data.**

**Consequence:** only 12/26 deployments returned data, and 11 are the already-studied `llama-3.3-70b`.
**The breadth question (do OTHER models/providers truncate?) has NO data** — the sweep collected
none for llama-3.1-70b, llama-3.1-8b, qwen-2.5-72b/7b, gemma-2-27b.

**Task-2 unaccounted 70B cells explained:** `together/fp8` 49/100 = the 51 credit-exhaustion 402s;
`deepinfra/turbo` 99/100 = 1 transient network error (`http=None`), not a truncation; `cloudflare`
78/100 = 20 real overt truncations + 2 network blips.

**Do NOT report "0 non-Cloudflare truncators."** That is only true for the 12 deployments that
returned data (11 of which are the known-clean 70B set). The class-of-failure question is
**UNANSWERED pending a re-run with credits.**

**Fix (needs credits added, then API):** re-run only the incomplete deployments —
`python scripts/broad_sweep.py --items 100 --models meta-llama/llama-3.1-70b-instruct
meta-llama/llama-3.1-8b-instruct qwen/qwen-2.5-72b-instruct qwen/qwen-2.5-7b-instruct
google/gemma-2-27b-it` (together/fp8's 49 valid is sufficient n; the rest need full data).
Harness hardened: `broad_sweep.py` now ABORTS on the first HTTP 402 instead of logging thousands of
useless failures.

---

*Further amendments after the pilot are made as separate, dated commits so the pre-registration history stays auditable.*
