# ReproProof Architecture Specification

## Mission & Core Invariant
ReproProof turns a bug report into:
1. A failing browser test tied directly to the report.
2. A source-only patch restoring expected behavior.
3. An evidence bundle, built from the stored run record and re-hashed artifacts, showing whether the byte-identical test and the regression suite pass after the patch.

**Core Invariant:** The test is frozen after human approval; only product code may change.

---

## State Machine

```
received ───────► clarification_required ───────► received
   │
   ▼
reproducing ────┬──► awaiting_test_approval (intended assertion failed)
                ├──► not_reproduced         (assertion passed or locator/timeout error)
                └──► environment_error      (setup, connection or server crash)

awaiting_test_approval ──┬──► test_rejected  (operator rejects test)
                         └──► patching       (operator approves; freezes SHA-256 test)

patching ───────┬──► verifying
                └──► unresolved              (no valid patch generated within attempt budget)

verifying ──────┬──► passes_frozen_test      (only via RunController.run_verification: frozen test PASSED
                │                             and regression PASSED, provenance matches the run)
                ├──► patching                (attempt 2 only, escalating to muse-wonder-1.0)
                └──► unresolved              (2 attempts exhausted)

any active state ──► budget_exceeded         (step, time, or monetary limit reached)
```

**Hard Rule:** Any other state transition is rejected in code by `RunController`.

---

## Component Layout

```
reproproof/
├── ui/                  # Streamlit web interface
│   └── app.py
├── core/
│   ├── controller.py    # State machine engine, transitions & SQLite persistence
│   ├── model_adapter.py # Meta AI OpenAI-compatible client (muse-spark-1.3, muse-wonder-1.0)
│   ├── schemas.py       # Pydantic v2 schemas for runs, steps, patches, bundles
│   ├── planner.py       # Intake, expected-behavior inference, failure classification
│   ├── compiler.py      # Action plan to Playwright test compiler & SHA-256 hasher
│   ├── patcher.py       # Source-only patch proposal, path boundary, and diff validator
│   ├── verifier.py      # Isolated fresh-copy verification engine
│   ├── evidence.py      # SHA-256 evidence bundle exporter (ZIP & JSON)
│   └── limits.py        # Budget and step enforcement
├── worker/
│   └── runner.py        # Subprocess runner and orchestrator
├── apps/
│   ├── manifests/       # YAML definitions of allowlisted applications
│   ├── demo-app/        # Seeded demo web app with off-by-one row deletion bug
│   └── third-party/     # Pinned TodoMVC app (MIT License) with filter defect
├── protected-tests/     # Regression checks inaccessible to patch models
├── evals/               # Evaluation benchmark suite (8 cases)
└── docs/                # Architectural, evaluation, and hackathon documentation
```

---

## Isolation & Security Boundaries
- **Temp-Copy Execution:** Verification occurs inside an isolated temporary copy (`tempfile.mkdtemp`), copying only source files and executing the byte-identical frozen test.
- **NOT a sandbox:** patched apps and tests run as the host user with full filesystem/network access. Only trusted allowlisted apps run; `LIVE_MODEL` patches are not executed unless `REPROPROOF_ALLOW_UNSANDBOXED_HOST_EXECUTION=1` (README "Execution boundary").
- **Controller-owned verification:** `run_verification(run_id)` reads the frozen test and patch from SQLite, loads the allowlisted manifest, runs `FreshCopyVerifier`, and rejects results whose run id, test hash, patch hash or source-tree hash don't match. There is no public method accepting caller-supplied pass/fail.
- **Approval binding:** approval requires the reproduced test stored during `REPRODUCING`, a 64-hex hash equal to its hash, and an approver id. `record_reproduction` / `record_patch` are rejected outside their own states.
- **Screenshots:** the reproduction capture is copied to `runs/repro_<run_id>.png` (hashed at capture); verification captures go to `runs/verify_<run_id>_<patch>.png`. The evidence exporter re-hashes both.
- **Model Credentials:** `MODEL_API_KEY` is loaded strictly via environment variables, never committed to git, logged, or passed to subprocess environments.
- **Path Whitelisting:** Patches are restricted strictly to `allowed_source_paths` defined in the manifest. Edits to `package.json`, tests, lockfiles, or configurations are automatically rejected.
