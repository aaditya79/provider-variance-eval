# Pilot confirmed — full GSM8K run unlocked

**Confirmed:** 2026-06-29 (author).
**Pilot run:** `pilot_20260629T200007Z_nogit` (50 GSM8K items × 1 repeat × 10 primary providers + `:floor`).

## Basis for confirmation

- Projected full GSM8K cost ≈ $4.10 — far under the $30 hard cap.
- Read-back verified discriminating; `google-vertex` normalization gap fixed via the
  authoritative disclosed-name map (50/50 clean, kept).
- `cloudflare/fp8` low pilot accuracy traced to serving truncation (`finish_reason==error`),
  not bad reasoning; clean-completion accuracy 97.1%; kept as the reliability exhibit.
- `generation_error` handled as a third outcome class (excluded from accuracy, retried,
  error-rate reported) — PREREGISTRATION §15.
- Parser tightened: missing/unusable `####` delimiter is flagged, never silently graded
  — PREREGISTRATION §17.

## Locked for the full run

- Primary set = all 10 canonical providers + `:floor` (PREREGISTRATION §16).
- 300 items × 3 repeats, temp 0, top_p 1, no seed, max_tokens 512.
- Two primary outcome axes: clean-completion accuracy (Wilson CI) and reliability
  (`generation_error` rate).

Deleting this file re-locks the full runner.
