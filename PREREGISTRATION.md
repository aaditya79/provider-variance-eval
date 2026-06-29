# PREREGISTRATION — Locked Study Parameters

**Status:** Frozen before data collection.
**Source of truth:** [`provider_variance_paper_plan.md`](./provider_variance_paper_plan.md), committed untouched as the pre-registration record (commit 1).
**Purpose:** Extract and lock the exact decision values from the plan so they cannot drift once harness coding begins. Values marked **PENDING** are choices the plan leaves open; they are NOT picked here and will be locked (in a follow-up amendment commit) only after the author answers the open-questions list — before any pilot runs.

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
| GSM8K     | **300** (sampled) | exact-match final answer |
| MMLU slice | **300** (sampled) | letter match |
| HumanEval | **164** (all) | unit tests in sandboxed subprocess |

- **Paired design:** item sets are frozen to `data/items/` exactly once and reloaded for every (model, provider, repeat). Items are never re-sampled.
- Graders are byte-for-byte identical across all providers and models. Every parse is logged for manual audit of disagreements (plan §5, §8).

---

## 6. Run parameters (plan §3)

| Parameter | Value |
|-----------|-------|
| temperature | **0** |
| top_p | **1** |
| repeats per (model, provider, benchmark, item) | **3** |
| max_tokens | **PENDING** — plan says "fixed max_tokens" but specifies no value; see open question. To be locked per-benchmark before pilot. |
| prompt template per benchmark | **PENDING** — plan requires "identical prompt template per benchmark" but does not give the text; see open question. To be locked before pilot. |

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

*Amendments to this file after the pilot (e.g., locking the PENDING values) are made as separate, dated commits so the pre-registration history is auditable.*
