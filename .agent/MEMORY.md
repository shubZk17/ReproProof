# MEMORY.md — Persistent Working Memory

High-signal facts only. Details live in the linked files. Last reviewed: 2026-11-02.

## Current state
- Project: **ReproProof** (Meta Global AI Developer Hackathon, Indie Dev track). PRD confirmed in `PRD.md`.
- Target: Autonomous reproduction, human test freeze, source-only repair, fresh-copy verification (`passes_frozen_test`), evidence bundle.
- Stack: Python 3.12, Streamlit, Playwright (Chromium), SQLite, Pydantic v2, OpenAI SDK (Meta AI endpoint `https://api.meta.ai/v1`, models `muse-spark-1.3`, `muse-wonder-1.0`).
- Hard constraints active: H-1 through H-12 (see `CONSTRAINTS.md`). No patch without human test approval; freeze test with SHA-256; fresh copy verification; never claim 'verified', use `passes_frozen_test`.

## Environment
- Windows 11, under `C:\Users\BIT\OneDrive\Desktop\Meta`.
- Shells: PowerShell 5.1 (primary) and Git Bash.
- Python 3.12.1 with pip, Node.js v22.14.0, npm.cmd 10.9.2, Playwright installed.

## Current priorities
1. Build model adapter and core foundation (TASK-003, TASK-005).
2. Create seeded demo app with reproducible defect (TASK-004).
3. Connect planner & compiler to achieve Gate G1 (TASK-006, TASK-007).

## Links
Rules: `AGENTS.md` · Startup: `SESSION_START.md` · Hard limits: `CONSTRAINTS.md` · Status: `PROGRESS.md` · Work: `TASKS.md` · Decisions: `DECISIONS.md`
