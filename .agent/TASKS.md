# TASKS.md — Task Board

Format: `- [ ] TASK-NNN [P1-P3] description. Done when: <criterion>. (deps: …)`
Search for an existing task before adding one. When a task is done, move it to Completed with its date.

## In Progress
_(none)_

## Pending
_(none — hackathon MVP objectives fully met and verified)_

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
