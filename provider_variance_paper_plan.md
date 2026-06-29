# Same Model, Different Answer
### Provider-Induced Variance in API-Based LLM Evaluation — Pre-Registered Study Plan

**One-line thesis.** When you evaluate "the same" open model through an API aggregator, you are silently evaluating a mix of provider-specific deployments at different (often undisclosed) quantizations. This study quantifies how much that changes benchmark scores, whether it can reverse model-vs-model conclusions, and which providers serve degraded precision.

**Core design principle.** The paper is framed as a *test of a reproducibility threat*, pre-registered so that **both outcomes are publishable**: a large effect is an alarming confound the field must report; a small effect is the first rigorous reassurance that API-routed evaluation is robust. You are not hostage to the effect size.

---

## 1. Research questions and pre-registered hypotheses

State these before collecting data; freeze them in the repo with a timestamp.

- **RQ1 (variance).** Does provider choice change benchmark accuracy for a fixed model+benchmark?
  - **H1:** Cross-provider accuracy spread exceeds within-provider noise for at least one model+benchmark.
  - *Null result is informative:* if spread ≤ noise, API evaluation is provider-robust for these models.

- **RQ2 (ranking flips) — the headline.** Can the choice of provider reverse a published-style "Model A beats Model B" conclusion?
  - **H2:** There exists at least one (benchmark, model-pair) where the sign of (acc_A − acc_B) depends on which providers serve A and B.
  - *Null result is informative:* if no flips occur, model rankings survive provider variance.

- **RQ3 (nondeterminism).** How reproducible is a single provider at temperature 0?
  - **H3:** Repeated identical calls to one provider at temp 0 produce non-identical outputs and non-zero accuracy variance.

- **RQ4 (quantization audit).** Does disclosed precision predict accuracy, and are there providers whose accuracy implies lower precision than disclosed?
  - **H4:** Accuracy correlates with disclosed quantization; some providers underperform their disclosed precision tier.

**Decision thresholds:**
- "Meaningful spread" = max−min provider accuracy ≥ 3 percentage points AND the gap's bootstrap 95% CI excludes 0.
- "Ranking flip" = sign of (acc_A − acc_B) differs across provider assignments, with each direction's gap CI excluding 0 in at least one configuration (a flip where both directions are within noise is reported as "ranking indeterminate," itself a finding).

---

## 2. Positioning (write this section first — novelty defense)

- **"When Is the Same Model Not the Same Service?" (2026):** measures operational layer (price/latency/throughput/context/protocol), explicitly declines to test quality/accuracy. → You measure the accuracy dimension it leaves open.
- **"LLM Output Drift: Cross-Provider Validation" (ICAIF '25):** cross-provider output consistency/determinism, finance-scoped, output-identity metrics. → You measure benchmark accuracy and ranking flips on general tasks.
- **Quantization-accuracy literature:** establishes the mechanism in controlled settings. → Your novelty is the in-the-wild marketplace demonstration + reproducibility-of-the-literature consequence.
- Framing rule: lead with eval reproducibility, not quantization.

---

## 3. Experimental design

- **Models:** Llama 3.3 70B Instruct and Qwen2.5 72B Instruct (confirm ≥4 providers each at run time; substitute if not). For RQ2, compare model-pairs where a realistic ranking is at stake.
- **Providers:** pin 4–6 distinct providers per model. Record at snapshot time: slug, disclosed quantization, context length, price, timestamp. Provider availability is time-varying.
- **Benchmarks:** ~300 items each — GSM8K (exact-match final answer), MMLU slice (~300 sampled, letter match), code (HumanEval all 164 via unit tests). Fix item sets once; reuse identical items across all providers/models (paired design).
- **Runs:** temperature 0, top_p 1, fixed max_tokens, identical prompt template per benchmark. 3 repeats per (model, provider, benchmark, item). Log raw completions, parsed answers, correctness, latency, tokens, and the returned provider for every call.

---

## 4. OpenRouter provider-pinning (verify against current docs)

Pin one provider, disable fallback:
provider: { order: ["<slug>"], allow_fallbacks: false, require_parameters: true }
- Enumerate providers per model; record quantization.
- Also run `:floor` (cheapest) for the cost-accuracy frontier; record which provider it resolves to.
- Read back the response `provider` field on every call; assert it matches; flag mismatches.
- Snapshot provider list + quant disclosures (JSON) at start and end.

---

## 5. Metrics and analysis (pre-registered)

- **Per-provider accuracy (RQ1):** Wilson 95% CIs; cross-provider spread (max−min) with 10k paired bootstrap CIs; compare to within-provider noise.
- **Ranking-flip (RQ2):** for each (benchmark, model-pair), acc_A−acc_B across all provider combinations; fraction of combos where winner differs from default; McNemar on default; paired bootstrap per combo; band-overlap figure.
- **Nondeterminism (RQ3):** exact-match agreement + accuracy SD across 3 temp-0 repeats.
- **Cost–accuracy frontier (RQ4):** price vs accuracy scatter, Pareto front; `:floor` penalty.
- **Quantization audit (RQ4):** regress accuracy on disclosed precision tier; flag providers ≥1 noise-band below same-precision peers as candidate undisclosed degradation (factual, snapshot-dated, no intent claims).

---

## 6. Pilot protocol (first)
- 50 items of one benchmark across all providers for one model, 1 repeat.
- Confirm per-call cost + extrapolate; verify pinning + read-back; sanity-check grading.
- Gate: only scale to full ~300×3 after projected cost ≤ budget and harness is clean.

---

## 7. Budget
- ~2 models × 5 providers × 3 benchmarks × 300 items × 3 repeats ≈ 27k calls; short outputs; 70B-class.
- Estimated $10–30. Hard cap; pilot makes full-run cost predictable.

---

## 8. Threats to validity
- Time-variation → snapshot + timestamp; dated measurement.
- Parsing artifacts → identical parser across providers; manually audit disagreements.
- Prompt/format coupling → fixed template; optional alternate-template robustness check.
- Generalization → scope claims to the sample.
- Provider identity → allow_fallbacks:false + provider read-back.

---

## 9. Writing it up — both outcomes
- Large/flips: reproducibility alarm — "a benchmark number is a property of model+provider+time."
- Small/no flips: reassurance + first rigorous quantification; temp-0 nondeterminism and `:floor` still warrant disclosure.
- Deliverable either way: a reporting checklist (model slug, provider, quantization, date, fallback policy, repeats).

---

## 10. Timeline
Week 1: freeze hypotheses; build harness; pilot; lock budget.
Week 2: full data collection.
Week 3: analysis + figures.
Week 4: write-up + positioning + release code/logs.

---

## 11. Reproducibility artifacts
Public repo: harness, item lists, pinned configs, raw completions, grading scripts, notebooks. Snapshotted provider/quant JSON with timestamps. The reporting checklist.

---

## 12. Venue
Measurement/eval/reproducibility workshop (AIMS-style if a later cycle opens); realistic: an EMNLP eval workshop or NeurIPS D&B/reproducibility track. Workshop/non-archival first.

### Titles
- Same Model, Different Answer: Provider-Induced Variance in LLM Benchmark Evaluation
- Which Provider Did You Get? Quantifying Hidden Provider Variance in API-Based LLM Evaluation
