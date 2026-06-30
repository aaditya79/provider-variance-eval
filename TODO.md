# Operational TODOs (not study-design; see PREREGISTRATION.md for frozen params)

- [ ] **Move the whole repo off `~/Desktop` (iCloud-synced).** Code + frozen items + snapshots
  are recoverable from git, but iCloud is a poor home for an active research repo (eviction,
  sync races). Run outputs already default to `~/pv_runs` (off iCloud); relocating the repo
  itself is the belt-and-suspenders follow-up. Not a blocker for the GSM8K re-run. (See LESSONS L2.)

- [ ] **Pick the second model with ≥5 canonical providers before the full multi-model run**
  (PREREGISTRATION §13). Qwen2.5-72B had only 2 providers in the snapshot — too thin for the
  RQ2 ranking-flip analysis. Snapshot 2–3 candidates and record the chosen model + its canonical
  set as an amendment.

- [ ] **Wire MMLU + HumanEval** (loaders, prompts, graders, sandbox) — only after GSM8K results
  are reviewed.
