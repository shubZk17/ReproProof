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
