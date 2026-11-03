# DECISIONS.md — Decision Log (append-only)

Rules: never edit the substance of an `Accepted` entry. To change one, set its status to `Superseded by DEC-NNN` and append a new entry.
Statuses: Proposed · Accepted · Superseded · Rejected. IDs are sequential.

Template:
```markdown
## DEC-NNN: <title>
Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded by DEC-NNN | Rejected
### Context / Problem
### Options Considered
### Decision
### Reasoning
### Trade-offs
### Consequences
### Alternatives Rejected
```

---

## DEC-001: Use file-based Markdown memory in `.agent/`, loaded via the root `CLAUDE.md`
Date: 2026-11-02
Status: Accepted

### Context / Problem
The user requires that project context, decisions, and progress persist across Claude Code sessions, compactions, and agent switches without the user repeating themselves.

### Options Considered
1. Markdown files in `.agent/`, with key files imported through `@` in the root `CLAUDE.md`
2. Claude Code's per-user auto-memory (`~/.claude/projects/.../memory/`) only
3. Everything in one large `CLAUDE.md`

### Decision
Option 1. The root `CLAUDE.md` stays short and imports `.agent/AGENTS.md`, `.agent/SESSION_START.md`, `.agent/CONSTRAINTS.md`, and `.agent/MEMORY.md`. The other files are read on demand by following the `SESSION_START.md` checklist.

### Reasoning
- Claude Code loads the root `CLAUDE.md` automatically at session start and expands `@path` imports, so the core rules are always in context.
- The files sit in the repository, so they are versioned and shared with any agent or tool, unlike per-user auto-memory.
- Keeping detailed files outside the auto-loaded set keeps the context small.

### Trade-offs
- Writing to the files depends on the agent following the protocol. Nothing forces it to.
- The files that aren't imported are read only if the agent completes the checklist.

### Consequences
- Every session pays the context cost of the four imported files, so they must stay concise.
- Other agents (non-Claude tools) should be pointed at `.agent/AGENTS.md`.

### Alternatives Rejected
- Option 2: per-user, invisible to other agents, and not versioned.
- Option 3: grows without bound and mixes concerns.

---

## DEC-002: Adopt ReproProof PRD Architecture, SQLite State Store, and Strict State Machine
Date: 2026-11-02
Status: Accepted

### Context / Problem
The project objective is set by `PRD.md` for the Meta Global AI Developer Hackathon. We need a reliable architecture that enforces strict state transitions, human approval before patching, test freezing with SHA-256, source-only patch validation, and isolated fresh-copy verification.

### Options Considered
1. Adhere strictly to the PRD layout with SQLite run database, Pydantic schemas, modular core package (`controller`, `planner`, `compiler`, `patcher`, `verifier`, `evidence`, `limits`, `model_adapter`), CLI runner, and Streamlit UI.
2. Build an ad-hoc monolithic single-file script.

### Decision
Option 1. Implement the modular `reproproof` structure according to the PRD contract. Use SQLite for persistent run records so background worker processes and Streamlit can query state asynchronously.

### Reasoning
- Matches all PRD requirements (R1–R12) cleanly.
- Decouples UI from runner/worker.
- Strict state machine enforces constraints H-5 through H-10 in code.

### Trade-offs
- Requires boilerplate for schemas and state machine, but prevents state corruption and ensures reproducible evaluation.

### Consequences
- All run states and artifacts are tracked in SQLite and file-based bundles.
- Model adapters will support both live Meta API (`https://api.meta.ai/v1`) and mock mode for testing without secrets.

---

## DEC-003: Remediate Review Findings with Secure Structured Test Driver, Git Apply, and Evidence-Gated State Machine
Date: 2026-11-03
Status: Accepted

### Context / Problem
An independent review marked ReproProof NOT PRODUCTION READY due to:
1. Prompt-injection-to-RCE vulnerability in test compiler string interpolation.
2. Unsafe custom patch heuristics with blind line-deletion fallback.
3. Controller permitting unverified state transitions.
4. Fabricated benchmark evaluation results.
5. Fragile hardcoded ports and environment leakage in runner/verifier.

### Options Considered
1. Patch ad-hoc string regexes and heuristics.
2. Re-architect compiler to use a fixed, static Playwright driver that loads a validated JSON action plan (eliminating string-to-code execution entirely); use `git apply` with strict boundary checks; require verified cryptographic/execution evidence in the controller before `passes_frozen_test`; use ephemeral ports and sanitize process environments; execute real tests in evals and remove all fabricated metrics.

### Decision
Option 2. Implement robust architectural defenses:
- Safe structured serialization: The Playwright test script will consist of a fixed, static driver template that receives a validated JSON payload. No model-generated strings are ever interpolated into JS code or comments.
- Secure patch application: Use `git apply --check` and `git apply` on the temporary clone, with pre-validation rejecting directory traversal, symlinks, absolute paths, and protected files.
- Controller evidence gate: `PASSES_FROZEN_TEST` can only be transitioned by submitting a signed/validated `VerificationResult` verifying byte-identical SHA-256 and zero exit codes.
- Real execution: Remove all manufactured numbers. Run genuine Playwright tests against `inventory-demo` on ephemeral ports.

### Consequences
- Eliminates the RCE attack surface.
- Ensures patch integrity.
- Restores complete honesty and credibility to the project.


---

## DEC-004: Final Remediation — Non-Fabricated Evidence, Explicit Regression Semantics, Controller Integrity, and Execution Disclosure
Date: 2026-11-03
Status: Superseded by DEC-005

### Context / Problem
A secondary independent audit identified remaining blockers before hackathon demo:
1. `app.py` exported hardcoded evidence bundle fields (patch diff, expected behavior, PASSED check results).
2. The UI silently ran mock mode without clear user notification or audit trails.
3. Verifier initialized `regression_passed = True`, misrepresenting skipped or failed suites.
4. Public caller could pass `_internal_evidence_verified=True` to bypass controller evidence verification.
5. Path validation in `patcher.py` was vulnerable to allowed-path prefix bypass (e.g. `srcX/evil.js` matching `src`).
6. Protocol-relative navigation (`//evil.com`, `/\evil.com`) was not rejected.
7. Verification test runs overwrote reproduction screenshots.
8. Execution environment was not clearly documented as a temporary directory rather than an OS sandbox.

### Decisions
1. **Dynamic Evidence Export:** `EvidenceExporter.create_bundle_from_run` pulls all evidence directly from controller run records and verified disk artifacts. Verifies SHA-256 and records explicit integrity checks (`VALID`, `FAILED`, `MISSING`).
2. **Explicit Model-Mode Tracking:** `ModelMode` (`LIVE_MODEL` vs `MOCK_MODEL`) is tracked in schema, DB, UI badges/warning banners, evidence bundles, and evaluation reports. Disclose that DEV-01 in mock mode uses a deterministic template.
3. **Explicit Regression Semantics:** Replaced boolean with `RegressionStatus` enum (`PASSED`, `FAILED`, `NOT_RUN`, `ERROR`). Skipped suites are `NOT_RUN`. Controller only grants `PASSES_FROZEN_TEST` when regression is `PASSED`.
4. **Authoritative Controller Enforcement:** Deleted `_internal_evidence_verified` bypass parameter. Calling `transition(..., PASSES_FROZEN_TEST)` is unconditionally prohibited. Only internal verification result recording with matching hashes can grant the state.
5. **Path & URL Hardening:** Canonical path validation with explicit directory boundary checks (`clean_path == allowed or clean_path.startswith(allowed + "/")`), rejecting prefix bypasses. Schema rejects all protocol-relative and backslash URLs.
6. **Screenshot Preservation:** Reproduction screenshots are backed up before verification and restored, with verification screenshots preserved separately with genuine timestamps.
7. **Execution Boundary Disclosure:** Documented clearly that temporary directories provide replay isolation, not OS sandboxing. Processes run on trusted allowlisted demo apps.

### Consequences
- Eliminates fabricated evidence and bypass vectors.
- 41/41 unit, integration, and security tests pass.
- Demo is credible, safe, and transparent for hackathon presentation.

---

## DEC-005: Controller-executed verification, approval bound to stored test, no host execution of live-model patches
Date: 2026-11-03 · Status: Accepted · Supersedes: DEC-004

### Context
Session 5 checked DEC-004's implementation against the code and found it incomplete:
- `record_verification_result(passed_frozen_test=True, passed_regression=True, ...)` was public, so any caller could still reach `passes_frozen_test` with no execution (the bypass had been renamed, not removed).
- Approval accepted any non-"placeholder" string when no reproduced test was stored (e.g. `"abc123sha"`).
- Screenshot backup/restore never ran: its regex never matched the compiled test (ERR-001).
- Mock mode still produced a plausible plan for any report.
- `EvidenceExporter.create_bundle` (caller-supplied values) still existed.
- `/<TAB>/evil.example` passed path validation (URL parsers strip tabs, which leaves `//evil.example`).

### Decision
1. `RunController.run_verification(run_id)` is the only path to `passes_frozen_test`. It reads the frozen test and patch from SQLite, loads the allowlisted manifest itself, runs `FreshCopyVerifier`, and checks the result's run id, test hash, patch hash and source-tree hash (`tree_sha256`, recorded at reproduction). `record_verification_result` was deleted.
2. Approval requires the reproduced test stored in `REPRODUCING`, a 64-hex hash equal to its hash, matching code if supplied, and a non-empty approver. `record_plan`/`record_reproduction`/`record_patch` are rejected outside RECEIVED/REPRODUCING/PATCHING.
3. Execution boundary: with no sandbox available (no Docker on host), `LIVE_MODEL` patches are not executed unless `REPROPROOF_ALLOW_UNSANDBOXED_HOST_EXECUTION=1`. The run ends `unresolved` with the patch recorded.
4. `MOCK_MODEL` accepts only `MOCK_SCRIPTED_REPORT` (DEV-01) and refuses other reports with `clarification_required`. Model ids are `mock:hand-written-plan` / `mock:hand-written-patch`, with 0 tokens.
5. Evidence: only `create_bundle_from_run`. Every artifact (including screenshots, hashed at capture) is re-hashed; any FAILED/CORRUPTED, or anything not VALID on a success claim, gives `evidence_valid=false` and `INVALID_EVIDENCE` check results.
6. Screenshots: the reproduction capture is copied to the immutable `runs/repro_<run_id>.png`; verification moves its capture to `runs/verify_<run_id>_<patch12>.png`.
7. Evals report reproduction/repair rate as `NOT_MEASURED` in mock mode, and the false-success rate as `NOT_MEASURED` (hidden checks are never executed).

### Consequences
- A public caller cannot manufacture success short of monkeypatching or writing to SQLite directly. Both are outside the API; direct DB edits are caught by the exporter's integrity checks.
- Live-model repair is not demonstrable on this host without the explicit opt-in.
- Old DB rows with NULL `model_mode` can't be loaded by `get_run` (RunRecord requires a mode). They are listed only via `list_runs`.
