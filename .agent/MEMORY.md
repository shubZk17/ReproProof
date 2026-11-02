# MEMORY.md — Persistent Working Memory

High-signal facts only. Details live in the linked files. Last reviewed: 2026-11-03.

## Current State
- Project: **ReproProof** (Meta Global AI Developer Hackathon, Indie Dev track).
- Status: **Hackathon-Ready MVP with Verified Implementation**.
- Review Verdict: Refactored and fully hardened against production review findings.
- Test Suite: **25 / 25 unit, security, invariant, and real E2E tests passing**.
- Evaluation: Genuine execution harness with real Playwright browser verification on ephemeral ports; all fabricated numbers eliminated; honest metrics reported with explicit denominators in UI, README, and docs.
- Architecture:
  - Controller: SQLite-backed authoritative state machine with atomic transactions and hash binding.
  - Compiler: Safe structured JSON data driver (`STATIC_TEST_DRIVER`) eliminating prompt-injection-to-RCE.
  - Patcher: `git apply --check` and `git apply` with path traversal, symlink escape, and protected file defenses.
  - Verifier: Fresh-copy verifier executing frozen tests and regression suites on ephemeral ports with sanitized environments (`MODEL_API_KEY` scrubbed).
  - UI: Streamlit 4-stage pipeline with dynamic evaluation metrics reading directly from measured run artifacts.

## Environment
- Windows 11, workspace under `C:\Users\BIT\OneDrive\Desktop\Meta`.
- Python 3.12.1, Node.js v22.14.0, npm.cmd 10.9.2, Playwright with Chromium headless shell.

## Links
Rules: `AGENTS.md` · Tasks: `TASKS.md` · Decisions: `DECISIONS.md` · Plan: `IMPLEMENTATION_PLAN.md` · Verification: `VERIFICATION_LOG.md`
