# Hackathon Contributions & Attribution Record

**Event:** Meta Global AI Developer Hackathon  
**Track:** Indie Developer Track  
**Submission Cutoff:** Nov 4, 2026, 6:00 PM IST  

---

## 1. Original Work Built During Event
The entirety of the ReproProof core architecture, controller state machine, model adapter, Playwright compiler, patch validator, fresh-copy verifier, Streamlit user interface, and evaluation benchmark harness were conceived and implemented during the hackathon period:

- **Core Engine:**
  - `reproproof/core/controller.py`: Strict finite state machine enforcing human test approval before patching, SHA-256 test freezing, and SQLite run storage.
  - `reproproof/core/model_adapter.py`: Meta AI API adapter using the OpenAI SDK with `muse-spark-1.3` and escalation to `muse-wonder-1.0`.
  - `reproproof/core/compiler.py`: Safe compilation of constrained action schemas to executable Playwright JavaScript tests with intended assertion markers.
  - `reproproof/core/patcher.py`: Source-only patch validator enforcing manifest path bounds and rejecting modifications to tests, package files, or configs.
  - `reproproof/core/verifier.py`: Isolated fresh-copy verification checking byte-identical test hashes and running protected regression suites.
  - `reproproof/core/evidence.py`: Exporter generating tamper-evident ZIP evidence bundles with SHA-256 signatures, screenshots, and logs.
- **Seeded Demo Application:**
  - `apps/demo-app/`: Warehouse Inventory application with a seeded wrong-row deletion bug (`deleteItem` splicing index 0).
- **Harness & UI:**
  - `reproproof/ui/app.py`: Streamlit dashboard implementing the 4-stage pipeline (Report -> Reproduce -> Repair -> Check).
  - `evals/run_eval.py`: 8-case benchmark harness evaluating against hidden assertions.

---

## 2. Pinned Third-Party Software Used
- **TodoMVC Reference Implementation (`apps/third-party/todo-app`)**:
  - Pinned micro-task application used to fulfill requirement **R12**.
  - Licensed under the **MIT License**.
  - Full license terms and copyright notices recorded in `THIRD_PARTY_NOTICES.md`.
