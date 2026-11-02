# CONSTRAINTS.md — Hard Rules & Preferences

**Hard constraints** are never violated without explicit user authorization, recorded as a DEC entry.
**Preferences** are defaults that can be departed from with a stated reason.

## Hard constraints
- H-1: Never store secrets, credentials, API keys, or sensitive personal data in the repository, logs, screenshots, or runner environment (especially `MODEL_API_KEY`).
- H-2: Get user approval before destructive, irreversible, externally visible, or security-sensitive actions (`AGENTS.md` §7).
- H-3: Never rewrite accepted decisions in place. Supersede them (`DECISIONS.md`).
- H-4: Never claim a task is complete without validation, or without an explicit statement that it could not be validated.
- H-5: **Models only propose**: Only the controller changes run state or claims a result.
- H-6: **Human-in-the-loop freeze**: Never call the patch model before a human approves the reproduction test. Once approved, the test is frozen (hashed with SHA-256) and cannot be modified.
- H-7: **Source-only patching**: Never let a patch change tests, test config, assertion helpers, package scripts, or dependency manifests. Patches outside allowed source paths or over size limits (>200 lines, >5 files) are rejected.
- H-8: **Clean verification**: Never set `passes_frozen_test` unless the same test hash and all regression checks pass on a fresh app copy.
- H-9: **Honest statuses**: Never use the word "verified" as a status. Use `passes_frozen_test`.
- H-10: **Accurate reproduction**: Never count a timeout, locator error, or server failure as a reproduced bug. Only the intended assertion failure counts.
- H-11: **Honest metrics**: Never invent metrics, users, interviews, or time savings. Report measured results with denominators, including failures.
- H-12: **Allowlist isolation**: Run only allowlisted apps defined in manifests. Do not accept arbitrary repositories or URLs, or auto-merge or deploy patches.

## Preferences
- P-1: Prefer minimal changes, the standard library, and existing dependencies over new code or packages.
- P-2: Keep memory files concise. Link to details instead of duplicating them.
- P-3: Platform is Windows. Scripts should work in PowerShell 5.1 or Git Bash.
- P-4: Provide offline/deterministic mock fallback mode when `MODEL_API_KEY` is not present, ensuring local tests and evals can run reliably.
