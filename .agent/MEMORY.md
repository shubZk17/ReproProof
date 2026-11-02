# MEMORY.md — Persistent Working Memory

High-signal facts only. Details live in the linked files. Last reviewed: 2026-11-02.

## Current state
- Project: **ReproProof** (Meta Global AI Developer Hackathon, Indie Dev track).
- Status: Fully built and verified. All 8 core unit tests passing, 8 evaluation cases measured.
- Git repository initialized with clean history at commit `7076d5b`.
- Architecture: Streamlit UI (`reproproof/ui/app.py`), SQLite run state store, Playwright test compiler, fresh-copy verifier (`passes_frozen_test`), Meta AI model adapter (`muse-spark-1.3`, `muse-wonder-1.0`).
- Seeded apps: `apps/demo-app` (Inventory demo), `apps/third-party/todo-app` (TodoMVC MIT).

## Environment
- Windows 11, under `C:\Users\BIT\OneDrive\Desktop\Meta`.
- Python 3.12.1, Node.js v22.14.0, npm.cmd 10.9.2, Playwright.

## Links
Rules: `AGENTS.md` · Startup: `SESSION_START.md` · Hard limits: `CONSTRAINTS.md` · Status: `PROGRESS.md` · Work: `TASKS.md` · Decisions: `DECISIONS.md`
