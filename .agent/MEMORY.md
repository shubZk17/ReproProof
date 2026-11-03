# MEMORY.md — Persistent Working Memory

High-signal facts only. Details live in the linked files. Last reviewed: 2026-11-03 (session 5).

## Current State
- Project: **ReproProof** (Meta Global AI Developer Hackathon, Indie Dev track). Hackathon MVP, **not production-ready**.
- Status: DEC-005 remediation implemented in the **uncommitted** working tree (on top of `14690b3`). Validated by 97 passed, 1 skipped (`python -m pytest tests/ -v`), a real eval run, and a headless Streamlit drive. See `PROGRESS.md`.
- Only **MOCK_MODEL** has been exercised: a hand-written plan and patch for one scripted report (DEV-01). No live-model run has ever been recorded. AI repair ability is **unmeasured**.
- **No sandbox.** Patched apps run as the host user. LIVE_MODEL patches are not executed unless `REPROPROOF_ALLOW_UNSANDBOXED_HOST_EXECUTION=1`.
- Key invariants (DEC-005):
  - Only `RunController.run_verification()` can reach `passes_frozen_test`. It runs the verifier itself and checks provenance.
  - Approval is bound to the stored reproduced test.
  - Evidence is built only from the run record and re-hashed artifacts (`evidence_valid`).
  - Regression results are PASSED/FAILED/NOT_RUN/ERROR.
- Earlier "41/41 tests" and "Complete Remediation Verified" claims were wrong (L-006, DEC-005 context).

## Environment
- Windows 11, workspace under `C:\Users\BIT\OneDrive\Desktop\Meta` (OneDrive, L-001). No Docker.
- Python 3.12.1, Node.js v22.14.0, npm.cmd 10.9.2, Playwright with Chromium headless shell.

## Running the Demo
- UI: `streamlit run reproproof/ui/app.py`
- Tests: `python -m pytest tests/ -v` (~90 s; e2e tests launch Chromium)
- Eval: `python evals/run_eval.py` (rewrites tracked `evals/results/latest_run.json`)

## Open items
TASK-026..029 in `TASKS.md` (live run, sandbox, hidden checks, classifier).

## Links
Rules: `AGENTS.md` · Tasks: `TASKS.md` · Decisions: `DECISIONS.md` · Architecture: `ARCHITECTURE.md` · Verification: `VERIFICATION_LOG.md` · Last session: `sessions/2026-11-03_session-5.md`
