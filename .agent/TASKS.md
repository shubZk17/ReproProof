# TASKS.md — Task Board

Format: `- [ ] TASK-NNN [P1-P3] description. Done when: <criterion>. (deps: …)`
Search for an existing task before adding one. When a task is done, move it to Completed with its date.

## In Progress
- [ ] TASK-003 [P0] Build `reproproof.core.model_adapter` supporting Meta API client (`base_url=https://api.meta.ai/v1`, models `muse-spark-1.3`, `muse-wonder-1.0`) with offline deterministic mock mode. Done when: unit tests verify API client creation, prompt formatting, tool call handling, and mock fallback.

## Pending
- [ ] TASK-004 [P0] Build seeded demo app (`apps/demo-app`) with a deterministic defect, manifest (`apps/manifests/inventory-demo.yaml`), and protected regression tests. Done when: app runs locally, normal tests pass, and defect is demonstrable.
- [ ] TASK-005 [P0] Build Pydantic schemas, SQLite run store, and strict state machine controller (`reproproof.core.schemas`, `controller`, `limits`). Done when: controller strictly validates and permits only legal state transitions and records audit events.
- [ ] TASK-006 [P0] Build Playwright action compiler (`reproproof.core.compiler`). Done when: valid action plans compile to executable Playwright JavaScript/TypeScript test files with screenshot and trace capture.
- [ ] TASK-007 [P0] Build reproduction planner and failure classifier (`reproproof.core.planner`, Gate G1). Done when: a model-planned test fails on the intended assertion for the seeded defect and environment errors are classified accurately.
- [ ] TASK-008 [P0] Build test freeze, source-only patch validator, and fresh-copy verifier (`reproproof.core.patcher`, `verifier`, Gate G2). Done when: test is frozen with SHA-256, patches changing protected paths are rejected, and clean copy verification passes.
- [ ] TASK-009 [P0] Build evidence bundle exporter (`reproproof.core.evidence`). Done when: bundle zip/json contains report, model IDs, test SHA-256, screenshots, unified diff patch, and run logs.
- [ ] TASK-010 [P0] Add pinned permissively-licensed third-party app with manifest (`apps/third-party/`, R12). Done when: manifest exists, app runs, and third party notices credit license.
- [ ] TASK-011 [P0] Build Streamlit interface (`reproproof/ui/app.py`). Done when: 4-stage UI (Report → Reproduce → Repair → Check) allows report submission, approval/rejection, run monitoring, and evidence bundle download.
- [ ] TASK-012 [P0] Build evaluation harness and run benchmarks (`evals/run_eval.py`, Gate G3). Done when: development and held-out cases run against hidden assertions, metrics are recorded with denominators.
- [ ] TASK-001 [P2] Initialize git repository and commit initial baseline. Done when: `git init` is executed and initial project files committed.

## Completed
- [x] TASK-000 [P1] Set up the `.agent/` memory and governance system and wire it into `CLAUDE.md`. Done 2026-11-02.
- [x] TASK-002 [P1] Learn the project's objective, stack, and requirements from PRD.md. Done 2026-11-02.
