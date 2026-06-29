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
