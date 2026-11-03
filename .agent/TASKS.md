# TASKS.md — Task Board

Format: `- [ ] TASK-NNN [P1-P3] description. Done when: <criterion>. (deps: …)`
Search for an existing task before adding one. When a task is done, move it to Completed with its date.

## In Progress
_(none)_

## Pending
- [ ] TASK-026 [P2] Live-model run with a real `MODEL_API_KEY` (planning only unless the host-execution opt-in is set on a disposable machine). Done when: a LIVE_MODEL run is recorded with its outcome, success or failure.
- [ ] TASK-027 [P3] Real sandbox (container/VM) for patched-app execution so the LIVE_MODEL host-execution gate can be removed. Done when: execution runs without host FS/network/credential access.
- [ ] TASK-028 [P3] Execute hidden checks in evals so the false-success rate can be measured; run the todo-app and other NOT RUN cases.
- [ ] TASK-029 [P3] Classifier (H-10) still treats any failed `expect(...)` as the intended assertion, even when the locator itself is wrong. Human approval is the only guard.

## Blocked
_(none)_

## Completed
- [x] TASK-000 [P1] Set up the `.agent/` memory and governance system and wire it into `CLAUDE.md`. Done 2026-11-02.
- [x] TASK-001 [P2] Initialize git repository and commit initial baseline. Done 2026-11-02.
- [x] TASK-002 [P1] Learn the project's objective, stack, and requirements from PRD.md. Done 2026-11-02.
- [x] TASK-003 [P0] Build `reproproof.core.model_adapter` supporting Meta API client (`base_url=https://api.meta.ai/v1`, models `muse-spark-1.3`, `muse-wonder-1.0`) with offline deterministic mock mode. Done 2026-11-02.
- [x] TASK-004 [P0] Build seeded demo app (`apps/demo-app`) with a deterministic defect, manifest (`apps/manifests/inventory-demo.yaml`), and protected regression tests. Done 2026-11-02.
- [x] TASK-005 [P0] Build Pydantic schemas, SQLite run store, and strict state machine controller (`reproproof.core.schemas`, `controller`, `limits`). Done 2026-11-02.
- [x] TASK-006 [P0] Build Playwright action compiler (`reproproof.core.compiler`). Done 2026-11-02.
- [x] TASK-007 [P0] Build reproduction planner and failure classifier (`reproproof.core.planner`, Gate G1). Done 2026-11-02.
- [x] TASK-008 [P0] Build test freeze, source-only patch validator, and fresh-copy verifier (`reproproof.core.patcher`, `verifier`, Gate G2). Done 2026-11-02.
- [x] TASK-009 [P0] Build evidence bundle exporter (`reproproof.core.evidence`). Done 2026-11-02.
- [x] TASK-010 [P0] Add pinned permissively-licensed third-party app with manifest (`apps/third-party/`, R12). Done 2026-11-02.
- [x] TASK-011 [P0] Build Streamlit interface (`reproproof/ui/app.py`). Done 2026-11-02.
- [x] TASK-012 [P0] Build evaluation harness and run benchmarks (`evals/run_eval.py`, Gate G3). Done 2026-11-02.
- [x] TASK-013 [P0] Remediate Prompt-Injection-to-RCE vulnerability in test compiler: safe JSON serialization with `STATIC_TEST_DRIVER`, ARIA role validation, and relative path constraints. Add `tests/test_security_injection.py`. Done 2026-11-03.
- [x] TASK-014 [P0] Replace unsafe line-deletion patch heuristic with `git apply --check` and `git apply`. Enforce path safety against `..`, absolute paths, symlinks, and protected files. Add `tests/test_patch_application.py`. Done 2026-11-03.
- [x] TASK-015 [P0] Enforce controller-owned state transitions in SQLite: bind human approval to test SHA-256 hash, reject duplicate approval, require verified evidence before transitioning to `passes_frozen_test`. Add `tests/test_controller_invariants.py`. Done 2026-11-03.
- [x] TASK-016 [P0] Implement genuine Playwright test execution environment: package configuration, ephemeral port allocation, process tree termination, runner environment sanitization (scrub `MODEL_API_KEY`). Add full end-to-end integration test `tests/test_e2e_workflow.py`. Done 2026-11-03.
- [x] TASK-017 [P0] Eliminate fabricated benchmark metrics: refactor `evals/run_eval.py` to execute real reproduction and clean verification with Playwright; report honest results with explicit denominators; mark out-of-scope cases `NOT RUN`; update UI and docs. Done 2026-11-03.
- [x] TASK-018 [P0] (partly ineffective, superseded by TASK-025) Eliminate fabricated evidence bundle: refactor `EvidenceExporter.create_bundle_from_run` and `app.py` to derive all evidence directly from controller run records, frozen test SHA-256, and verified patch output. Add `tests/test_remediation_evidence.py`. Done 2026-11-03.
- [x] TASK-019 [P0] Implement explicit model-mode tracking (`LIVE_MODEL` vs `MOCK_MODEL`): persist in `RunRecord`, display prominent badge and warning banner in UI, disclose deterministic template in evaluation, docs, and README. Done 2026-11-03.
- [x] TASK-020 [P0] Correct regression result semantics with explicit `RegressionStatus` enum (`PASSED`, `FAILED`, `NOT_RUN`, `ERROR`): ensure skipped suites are NOT_RUN, errors are ERROR, only actual successes are PASSED. Add `tests/test_remediation_regression.py`. Done 2026-11-03.
- [x] TASK-021 [P0] Eliminate controller verification bypass (`_internal_evidence_verified` removed): require atomic evidence verification in `record_verification_result`, validate test hash and patch hash match, reject mutated approvals and placeholder hashes. Add `tests/test_remediation_security.py`. Done 2026-11-03.
- [x] TASK-022 [P0] Fix allowed-path prefix bypass (`srcX/evil.js`, `src_evil/`) in `patcher.py` and protocol-relative navigation (`//evil.com`, `/\\evil.com`, `\\evil.com`) in `ActionStep.validate_path`. Add adversarial tests in `tests/test_remediation_security.py`. Done 2026-11-03.
- [x] TASK-023 [P0] Preserve screenshot evidence: ensure reproduction before-screenshot is backed up and never overwritten by verification Playwright execution; maintain distinct paths and timestamps for both screenshots. Done 2026-11-03.
- [x] TASK-024 [P0] ~~(claims partly wrong, see TASK-025)~~ Cleanup: prevent `runs/` from test discovery via `playwright.config.js` and `PLAYWRIGHT_ALLOW_RUNS`, clean up temporary verify files, fix temp dir leaks on patch validation failures, remove debug prints, and document execution boundaries. Done 2026-11-03.
- [x] TASK-025 [P0] Final hackathon remediation (DEC-005): controller-executed verification + provenance, approval bound to stored test, live-patch host-execution gate, scripted-only mock, re-hashed evidence incl. screenshots, working screenshot preservation, tab-stripping nav bypass, temp-dir leak (read-only git objects), honest eval metrics, docs. Done 2026-11-03 (97 passed, 1 skipped; real E2E + UI drive).
