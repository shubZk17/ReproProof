# PROJECT_CONTEXT.md — Project Overview

Last verified: 2026-11-02. Update this file whenever the fundamentals change.

| Item | Value |
|---|---|
| Objective | Build ReproProof: a tool turning a bug report and screenshot into a failing browser test frozen upon human approval, a source-only patch, and an evidence bundle verifying `passes_frozen_test` on a fresh app copy. |
| Core functionality | Report intake, expected-behavior inference, constrained Playwright reproduction, failure classification, human test approval & test freeze, source-only patching, fresh-copy verification, evidence bundle export, budget & safety limits. |
| Technology stack | Python 3.12 (controller, CLI, Streamlit UI, schemas), Playwright (Chromium JS/TS browser runner), SQLite (run state storage), Pydantic v2 (validation & schemas), OpenAI SDK (Meta AI endpoint client). |
| Important dependencies | `streamlit`, `pydantic`, `openai`, `playwright`, `pytest`, `pytest-asyncio`, `pyyaml` |
| External integrations | Meta AI API (`https://api.meta.ai/v1`, models `muse-spark-1.3`, `muse-wonder-1.0`) |
| Maturity | In active development (Stage 1: Core foundation & demo app) |
| Version control | Git (to be initialized / managed) |
| Dev environment | Windows 11, PowerShell 5.1 / Git Bash, OneDrive-synced folder `C:\Users\BIT\OneDrive\Desktop\Meta` |

## Repository structure (planned & verified)
```
Meta/
├── CLAUDE.md
├── PRD.md
├── .agent/                  # Memory & governance system
├── reproproof/
│   ├── __init__.py
│   ├── ui/                  # Streamlit application
│   │   ├── __init__.py
│   │   └── app.py
│   ├── core/                # State machine & orchestration
│   │   ├── __init__.py
│   │   ├── controller.py    # State transitions & run lifecycle
│   │   ├── model_adapter.py # Model client (Meta API / mock fallback)
│   │   ├── schemas.py       # Pydantic models for runs, actions, patches
│   │   ├── planner.py       # Action planning from bug report & screenshot
│   │   ├── compiler.py      # Plan -> Playwright test compiler
│   │   ├── patcher.py       # Source-only patch request & validation
│   │   ├── verifier.py      # Clean temp-copy verification
│   │   ├── evidence.py      # SHA-256 hashes & evidence bundle export
│   │   └── limits.py        # Run budget, time & step limits
│   └── worker/              # Process execution & runner
│       ├── __init__.py
│       └── runner.py
├── apps/
│   ├── manifests/           # YAML app manifests
│   │   └── inventory-demo.yaml
│   ├── demo-app/            # Seeded demo web app with known defect
│   └── third-party/         # Pinned permissively licensed app
├── protected-tests/         # Regression tests never exposed to patcher
├── evals/                   # Evaluation cases and harness
│   ├── cases.jsonl
│   ├── run_eval.py
│   ├── hidden/              # Trusted assertions
│   └── results/
├── docs/
│   ├── architecture.md
│   ├── evaluation.md
│   └── hackathon-contributions.md
├── README.md
├── THIRD_PARTY_NOTICES.md
├── .env.example
└── .gitignore
```
