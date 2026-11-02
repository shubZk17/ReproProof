# ReproProof Evaluation & Benchmark Results

## Benchmark Design & Protocol
Per PRD §Evaluation, 8 evaluation cases are evaluated against hidden ground truth assertions (`evals/hidden/cases_truth.json`).
- Hidden checks and solutions are strictly isolated from model context.
- All metrics are measured and reported with explicit denominators (Rule 7: Never invent metrics or omit failures).

| Dataset | Total Cases | Composition |
|---|---|---|
| **Development** | 5 | 4 defect cases (including 1 third-party), 1 ambiguous report |
| **Held-Out** | 3 | 2 defect cases (including 1 third-party), 1 false report |

---

## Measured Benchmark Results

Run timestamp: `2026-11-03`  
Harness: `evals/run_eval.py`  
Output Artifact: `evals/results/latest_run.json`

| Metric | Target | Measured Result | Notes |
|---|---|---|---|
| **False Success Rate** | 0.0% | **0 / 1 (0.0%)** | Zero runs achieved `passes_frozen_test` while failing hidden assertions |
| **Control Handling** | 2 / 2 (100%) | **2 / 2 (100.0%)** | Ambiguous case transitioned to `clarification_required`; false report to `not_reproduced` |
| **Reproduction Rate** | ≥ 1 / 1 | **1 / 1 (100.0%)** | Defect case reproduced intended assertion failure via Playwright |
| **Repair Rate** | ≥ 1 / 1 | **1 / 1 (100.0%)** | Defect resolved on fresh copy within budget, passing frozen + regression tests |
| **Unexecuted Scope** | Report | **5 / 8 marked NOT RUN** | 5 cases marked `NOT RUN` (scoped out of hackathon MVP single-app focus) |
| **Median Duration** | Report | **3.58s** | Measured Playwright execution runtime |

---

## Failure & Control Analysis
- **DEV-01 (Supported Defect):** Seeded wrong-row deletion bug reproduced with genuine Playwright test execution on ephemeral port, frozen with SHA-256 upon human approval, patched via `git apply`, and verified against fresh copy running frozen test and regression suite.
- **DEV-05 (Ambiguous):** When given the underspecified report *"The button does something weird when I click it"*, the planner successfully generated a targeted clarification question and paused in `clarification_required`.
- **HELD-03 (False Report):** When given a false bug report on working page title behavior, the browser test passed cleanly, correctly leading the classifier to report `not_reproduced` per PRD Rule 6.
- **Unexecuted Cases (DEV-02, DEV-03, DEV-04, HELD-01, HELD-02):** Explicitly marked `NOT RUN` to avoid fabricated or synthetic metrics.
