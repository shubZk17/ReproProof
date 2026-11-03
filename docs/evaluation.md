# ReproProof Evaluation & Benchmark Results

## Benchmark Design & Protocol
Per PRD §Evaluation, 8 evaluation cases are evaluated against hidden ground truth assertions (`evals/hidden/cases_truth.json`).
- Hidden checks and solutions are strictly isolated from model context.
- All metrics are measured and reported with explicit denominators (Rule 7: Never invent metrics or omit failures).
- Execution mode (LIVE_MODEL vs MOCK_MODEL) is explicitly tracked and disclosed.

| Dataset | Total Cases | Composition |
|---|---|---|
| **Development** | 5 | 4 defect cases (including 1 third-party), 1 ambiguous report |
| **Held-Out** | 3 | 2 defect cases (including 1 third-party), 1 false report |

---

## Measured Benchmark Results

Run: `2026-11-03`, harness `evals/run_eval.py`, output `evals/results/latest_run.json`.
**Execution mode: `MOCK_MODEL`. No AI model was called.**

> **Disclosure:** DEV-01 uses a **hand-written plan and a hand-written patch** (`reproproof/core/model_adapter.py`).
> DEV-05 and HELD-03 use **hand-written plans supplied by the harness**. Browser execution (Chromium via
> Playwright), `git apply`, the fresh-copy check and the protected regression suite were really executed.
> These results show that the pipeline's controls work. They say **nothing** about AI repair ability.

| Metric | Measured | Notes |
|---|---|---|
| Executed cases | **3 / 8** | 5 cases `NOT RUN` (outside single-app MVP scope) |
| Reproduction rate | **NOT_MEASURED** (mock) | hand-written plan reproduced DEV-01 (1 / 1) |
| Repair rate | **NOT_MEASURED** (mock) | hand-written patch reached `passes_frozen_test` (1 / 1) |
| Control handling | **2 / 2** | both control inputs were hand-written plans |
| False success rate | **NOT_MEASURED** | hidden checks (`evals/hidden/`) are never executed |
| Median duration | ~5.7 s | per executed case, this machine |

## Regression Status Semantics (Priority 3)
ReproProof enforces four explicit regression outcome states:
- **`PASSED`**: The regression test suite was executed and exited with code 0.
- **`FAILED`**: The regression test suite was executed and reported one or more test failures.
- **`NOT_RUN`**: The regression test suite was skipped (e.g. because the frozen defect test failed, or no regression suite is configured).
- **`ERROR`**: An execution error or subprocess exception occurred while running the regression suite.

**Controller Invariant:** `passes_frozen_test` is granted **only** when the byte-identical frozen test passes **AND** the regression status is explicitly `PASSED`.

---

## Failure & Control Analysis
- **DEV-01 (Supported Defect):** the hand-written plan reproduced the seeded wrong-row deletion bug in real Chromium; the harness approved the test (SHA-256 frozen); the hand-written patch was applied with `git apply` to a fresh copy, and the frozen test and the regression suite both passed.
- **DEV-05 (Ambiguous):** the harness supplies a hand-written clarification plan, so this only shows that the controller halts in `clarification_required`. No model asked the question.
- **HELD-03 (False Report):** When given a false bug report on working page title behavior, the browser test passed cleanly, correctly leading the classifier to report `not_reproduced` per PRD Rule 6.
- **Unexecuted Cases (DEV-02, DEV-03, DEV-04, HELD-01, HELD-02):** Explicitly marked `NOT RUN` to avoid fabricated or synthetic metrics.
