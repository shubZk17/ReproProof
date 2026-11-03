# 🛡️ ReproProof

> **Bug reproduction as a frozen browser test, a human approval gate, source-only repair, and fresh-copy checking.**
> Built for the **Meta Global AI Developer Hackathon (Indie Developer Track)**. Hackathon MVP, **not production software**.

---

## 💡 The Core Idea

AI code models usually change code without proving the bug exists or that the fix works. ReproProof puts a controller between the model and the codebase:

1. **Constrained reproduction:** a plan (from the model, or a hand-written template in mock mode) is compiled into a data-driven Playwright test and run in real Chromium against the app.
2. **Human approval freeze:** a human approves the exact test that ran. The controller binds approval to that stored test and its SHA-256; nothing else can be approved. No patch is requested before approval.
3. **Source-only repair:** patches may touch only the manifest's allowed source paths (no tests, configs, manifests; ≤200 lines, ≤5 files), applied with `git apply`.
4. **Fresh-copy check (`passes_frozen_test`):** the controller itself runs the verifier on a fresh copy of the app with the stored patch, runs the byte-identical frozen test and the protected regression suite, and checks the result's provenance (run id, test hash, patch hash, source-tree hash). `passes_frozen_test` requires frozen test `PASSED` **and** regression `PASSED`. There is no API that accepts a caller-supplied success flag.
5. **Evidence bundle:** built only from the stored run record and on-disk artifacts, each re-hashed. Missing or tampered artifacts are reported as `MISSING` / `FAILED` / `CORRUPTED` and the bundle is marked `evidence_valid: false`.

```
[ 1. Report ] ──► [ 2. Reproduce ] ──► [ Human Approval ] ──► [ 3. Repair ] ──► [ 4. Check ]
                  real Chromium run     freezes stored test     git apply on      frozen test + regression
                                        (SHA-256 bound)          fresh copy        suite, provenance checked
```

State machine and transitions: [docs/architecture.md](docs/architecture.md).

---

## ⚠️ What this demo does and does not prove

| | Status |
|---|---|
| Real Chromium (Playwright) reproduction and checking on ephemeral ports | **Genuinely executed** (tests + demo) |
| `git apply` on a fresh temporary app copy; protected regression suite | **Genuinely executed** |
| Controller rejects forged approval / verification / foreign evidence | **Tested** (`tests/test_controller_invariants.py`) |
| Evidence bundle flags tampered or missing artifacts | **Tested** (`tests/test_remediation_evidence.py`) |
| AI-generated plans or patches | **NOT demonstrated.** No live-model run has been recorded. |
| Repair rate of an AI model | **NOT measured** |
| False-success rate | **NOT measured** (hidden checks in `evals/hidden/` are never executed) |
| Sandboxing | **None.** See execution boundary below. |
| Second allowlisted app (`todo-app`) and 5 of 8 eval cases | **NOT run** |

### Mock mode (default without `MODEL_API_KEY`)
- **`MOCK_MODEL` is not an AI model.** It returns a **hand-written plan and a hand-written patch** (`reproproof/core/model_adapter.py`) for exactly one scripted report on `inventory-demo` (eval case DEV-01): *"Clicking Delete Widget B removes Widget A instead of Widget B."*
- Any other report is refused with `clarification_required` and an explicit "not analysed" reason, so mock mode cannot produce a plausible success for an unrelated report.
- The mode is stored on every run, shown as a badge and banner in the UI, written into every evidence bundle with a disclosure, and labelled in eval results. The UI locks the report box in mock mode.

### Execution boundary (no sandbox)
- Patched apps and tests run **as the logged-in OS user**, with that user's filesystem and network access. The temporary copy, ephemeral port and scrubbed environment (`MODEL_API_KEY` and token-like variables removed) are **not** a sandbox.
- So only trusted, allowlisted demo apps (`apps/manifests/`) are run, and in mock mode only the hand-written patch runs.
- **Model-generated (`LIVE_MODEL`) patches are not executed** on the host: the run ends `unresolved` with the patch recorded for human review. An operator can opt in on a disposable machine with `REPROPROOF_ALLOW_UNSANDBOXED_HOST_EXECUTION=1`. Don't do this on a machine with credentials or sensitive files.
- Navigation is limited to same-origin relative paths (schema validation plus a runtime origin check in the test driver).

---

## 🚀 Quick Start

Requirements: Python ≥ 3.11, Node.js ≥ 18, npm.

```bash
pip install -r requirements.txt
npm install
npx playwright install chromium

# Optional, live model planning (patches still not executed, see above):
# set MODEL_API_KEY in the environment

streamlit run reproproof/ui/app.py      # http://localhost:8501
```

Demo script (mock mode): **Start Reproduction** → review the test and the failing assertion → **Approve Test** → **Generate Patch & Verify on Clean Copy** → download the evidence bundle.

---

## 📊 Evaluation

```bash
python evals/run_eval.py     # writes evals/results/latest_run.json
```

Last run (2026-11-03, `MOCK_MODEL`): 3 of 8 cases executed, 5 `NOT RUN`.

| Case | Input | Result |
|---|---|---|
| DEV-01 | hand-written plan + hand-written patch | `passes_frozen_test` (real Chromium, git apply, regression suite) |
| DEV-05 (ambiguous) | hand-written clarification plan from the harness | `clarification_required` (shows only that the controller halts) |
| HELD-03 (false report) | hand-written plan | `not_reproduced` (real Chromium run; test passes) |

Reproduction and repair rates are reported as `NOT_MEASURED` in mock mode. Details: [docs/evaluation.md](docs/evaluation.md).

---

## 🧪 Tests

```bash
python -m pytest tests/ -v
```
98 tests (97 pass, 1 skipped: the symlink-escape test needs symlink permission on Windows). `tests/test_e2e_workflow.py` uses real Chromium and a real Node server. Controller-logic tests in `tests/test_controller_invariants.py` and `tests/test_remediation_regression.py` replace browser execution with a scripted verifier stub, so they are **not** evidence of browser execution.

---

## 📦 Allowlisted Applications

1. **Warehouse Inventory Demo (`inventory-demo`)**: seeded wrong-row deletion bug. Manifest `apps/manifests/inventory-demo.yaml`. The only app exercised by the demo and tests.
2. **Pinned TodoMVC (`todo-app`)**: MIT licensed (see `THIRD_PARTY_NOTICES.md`). Manifest present; **not run**, and it has no regression suite configured.

---

## 📜 Attribution & Third-Party Notices

See [docs/hackathon-contributions.md](docs/hackathon-contributions.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
