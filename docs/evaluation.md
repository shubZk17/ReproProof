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

Run timestamp: `2026-11-02`  
Harness: `evals/run_eval.py`  
Output Artifact: `evals/results/latest_run.json`

| Metric | Target | Measured Result | Notes |
|---|---|---|---|
| **False Success Rate** | 0.0% | **0 / 4 (0.0%)** | Zero runs achieved `passes_frozen_test` while failing hidden assertions |
| **Control Handling** | 2 / 2 (100%) | **2 / 2 (100.0%)** | Ambiguous case transitioned to `clarification_required`; false report to `not_reproduced` |
| **Reproduction Rate** | ≥ 4 / 6 | **6 / 6 (100.0%)** | All 6 defect cases reproduced intended assertion failure |
| **Repair Rate** | ≥ 3 / 6 | **4 / 6 (66.7%)** | 4 out of 6 defect cases resolved on fresh copy within 2 attempts |
| **Median Duration** | Report | **0.04s** (mock) / ~18s (live runner) | Measured runtime per test run |

---

## Failure Analysis
- **DEV-04 & HELD-02:** Intentionally configured to simulate complex multi-step state mutations that exhaust the 2-attempt budget, correctly verifying that the system ends in honest `unresolved` rather than reporting an unverified fix.
- **DEV-05 (Ambiguous):** When given the underspecified report *"The button does something weird when I click it"*, the planner successfully generated a targeted clarification question and paused in `clarification_required`.
- **HELD-03 (False Report):** When given a false bug report on working page title behavior, the browser test passed cleanly, correctly leading the classifier to report `not_reproduced`.
