# ARCHITECTURE.md — System Architecture

Document only what has been **verified in code**. Mark planned items as `(planned, DEC-NNN)`.

Last verified: 2026-11-03 (session 5, against code). Full description: `docs/architecture.md`.

## Components / modules
- `reproproof/core/controller.py`: SQLite state machine. Sole path to `passes_frozen_test` is `run_verification()` (runs the verifier itself, checks provenance). Approval is bound to the stored reproduced test. `HOST_EXECUTION_FLAG` gates LIVE_MODEL patch execution.
- `core/verifier.py`: fresh-copy verifier. Returns `VerificationResult` (no status). Also `tree_sha256`, `sha256_*`.
- `core/evidence.py`: `create_bundle_from_run` only; re-hashes artifacts and sets `evidence_valid`.
- `core/model_adapter.py`: live client, plus a mock limited to `MOCK_SCRIPTED_REPORT`.
- `core/planner.py`: `load_manifest` (allowlist), classifier. `core/compiler.py`: data-driven Playwright driver with a runtime same-origin check, and `extract_plan`.
- `core/patcher.py`: path boundary + `git apply`. `core/proc_utils.py`: ports, scrubbed env, process-tree kill, `force_rmtree`.
- `worker/runner.py`: reproduction/repair orchestration. Reads report and mode from the run record.
- `ui/app.py`: Streamlit. Reads everything from the controller.

## Data flow
create_run(mode, report) → record_plan (RECEIVED) → REPRODUCING → record_reproduction (test, hash, tree hash, screenshot hash) → AWAITING_TEST_APPROVAL → record_human_approval → PATCHING → record_patch → VERIFYING → run_verification → PASSES_FROZEN_TEST | PATCHING | UNRESOLVED.

## Database schema
`runs` (one row per run; see `_EXTRA_COLUMNS` for migrated columns) and `transitions` (audit trail).

## External services and infrastructure
Meta AI OpenAI-compatible endpoint (live mode only). Node + Playwright Chromium locally. **No sandbox.**
