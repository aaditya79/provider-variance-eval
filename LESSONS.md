# Lessons (operational gotchas worth not relearning)

## L1 — Never interpret completion CONTENT from a non-clean response (2026-06-29)

A response body is only meaningful if the call was a **clean HTTP 200 with valid auth**.

- An early "garbage backslash output" blamed on `deepinfra/turbo` actually came from a run
  with a **bogus API key (HTTP 401)**. Error pages / auth failures can carry arbitrary body
  text that is NOT model output. That evidence was void; with a valid key the same endpoint
  returns a clean answer.
- Compounding trap: `repr()` doubles backslashes (`\` → `\\`), so a non-output string can
  *look* like model garbage on screen.

**Rule:** filter on `valid == true` (HTTP 200 + provider read-back match) before reading
`completion_text`. The harness already sets `valid=false` and stores only an error string for
non-200/auth-failed calls — do not override this in analysis.

**Corollary:** do not pre-register a provider/SKU as "degraded" (or any quality label) from
anything but clean, graded data. Direction of any variant-vs-canonical difference is an
empirical question, not an assumption.

## L2 — Raw run logs must live OFF iCloud, and runs must self-verify persistence (2026-06-29)

The full GSM8K run reported `9900/9900 cells, $3.35` but its JSONL was **0 bytes** with mtime ==
run start (never appended). Data existed nowhere (disk/iCloud/git). The reporter was fine; this
was a **persistence failure**. Cost was spent; results were lost.

Contributing factors: the repo lives under `~/Desktop` (iCloud-synced — can evict/placeholder
large files), and raw JSONL is gitignored (no backup), and the runner trusted in-memory counters
without verifying bytes hit disk.

**Rules now enforced in the runner:**
- `runs_dir` defaults OFF iCloud (`~/pv_runs`); a startup WARNING fires if a run dir is under an
  iCloud path.
- Periodic + final `os.fsync`; a post-run **integrity check** raises `PersistenceError` if rows
  generated ≠ rows on disk; a `manifest_<bench>.json` records counts + bytes; a `[persisted]`
  line prints row count + file size.
- **Never trust a run's printed counters alone** — confirm `[persisted] N rows, M bytes` and the
  manifest before treating a run as complete.
