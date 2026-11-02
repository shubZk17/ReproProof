# 🛡️ ReproProof

> **Autonomous bug reproduction, frozen browser tests, source-only repair, and fresh-copy verification.**  
> Built for the **Meta Global AI Developer Hackathon (Indie Developer Track)**.

---

## 💡 The Core Idea

When a software bug is reported, AI code models typically jump straight to modifying code without proving the bug exists or proving the fix works.

**ReproProof introduces an audit-grade contract:**
1. **Constrained Reproduction:** The model turns a user report and screenshot into an executable browser test (using Playwright).
2. **Human-in-the-Loop Freeze:** A human inspects the failing assertion and screenshot. If approved, the test is **frozen** (cryptographically hashed with SHA-256) and stored outside the model's writable tree. **No patch model may be invoked before human approval.**
3. **Source-Only Repair:** The model proposes a minimal source patch. The controller strictly rejects any changes to tests, runner configs, or dependency manifests.
4. **Clean Verification (`passes_frozen_test`):** The patch is applied to a **fresh temporary copy** of the application. The system executes the byte-identical frozen test (verifying the SHA-256 hash matches) and runs protected regression suites.
5. **Honest Statuses:** The word *"verified"* is never used as a status. Only when both the frozen test and regression suite pass on a clean copy is `passes_frozen_test` granted.

---

## 🏗️ Architecture & 4-Stage Workflow

```
[ 1. Report ] ──► [ 2. Reproduce ] ──► [ Human Approval Gate ] ──► [ 3. Repair ] ──► [ 4. Check ]
 User report &     Playwright test       Approves & freezes test     Source patch      Clean copy runs
 screenshot        synthesized           with SHA-256 hash           proposed          frozen test & regression
```

For the complete state machine and transition rules, see [docs/architecture.md](docs/architecture.md).

---

## 🔒 Security, Isolation, & Model Policy

- **Isolation Boundary Notice:** ReproProof creates temporary directory copies of allowlisted applications to test patches. **This temporary-copy approach is designed for filesystem isolation and replay reproducibility, not as an OS-level security sandbox.**
- **Secret Hygiene:** `MODEL_API_KEY` is loaded from the environment and is never written to repositories, databases, logs, screenshots, or runner processes.
- **Model Escalation:**
  - **Attempt 1:** Default model `muse-spark-1.3` on Meta AI endpoint (`https://api.meta.ai/v1`).
  - **Attempt 2:** Escalates to `muse-wonder-1.0` if attempt 1 fails fresh verification.
- **Offline / Deterministic Mode:** If `MODEL_API_KEY` is not provided, ReproProof runs seamlessly in offline mock mode for deterministic development and automated testing.

---

## 🚀 Quick Start

### 1. Requirements
- Python ≥ 3.11
- Node.js ≥ 18 & npm

### 2. Setup
```bash
# Clone the repository
git clone https://github.com/your-username/reproproof.git
cd reproproof

# Install Python dependencies
pip install -r requirements.txt

# (Optional) Install Playwright browser
npx playwright install chromium
```

### 3. Environment Configuration
```bash
cp .env.example .env
# Edit .env and enter your Meta AI API key:
# MODEL_API_KEY=your_key_here
```

### 4. Launch the Interactive Dashboard
```bash
streamlit run reproproof/ui/app.py
```
Open your browser to `http://localhost:8501`.

---

## 📊 Benchmark Evaluation Results

Run the full 8-case benchmark against hidden ground-truth assertions:
```bash
python evals/run_eval.py
```

### Measured Performance (8 Cases)
| Metric | Target | Measured Result |
|---|---|---|
| **False Success Rate** | 0.0% | **0 / 4 (0.0%)** |
| **Control Handling** | 100% | **2 / 2 (100.0%)** |
| **Reproduction Rate** | ≥ 4 / 6 | **6 / 6 (100.0%)** |
| **Repair Rate** | ≥ 3 / 6 | **4 / 6 (66.7%)** |
| **Median Duration** | Report | **0.04s** (mock) / **~18s** (live) |

Full methodology and failure analyses are documented in [docs/evaluation.md](docs/evaluation.md).

---

## 📦 Allowlisted Applications

1. **Warehouse Inventory Demo (`inventory-demo`)**:
   - Seeded web app with wrong-row deletion bug (`deleteItem` removes index 0 instead of matching ID).
   - Manifest: `apps/manifests/inventory-demo.yaml`.
2. **Pinned TodoMVC (`todo-app`)**:
   - Pinned micro-task application testing filter interaction defects.
   - Manifest: `apps/manifests/todo-app.yaml`.
   - Licensed under the MIT License (see `THIRD_PARTY_NOTICES.md`).

---

## 🧪 Running Tests

```bash
# Run core test suite
python -m pytest tests/ -v
```

---

## 📜 Attribution & Third-Party Notices

All core algorithms, state controllers, Playwright compilers, and evaluators were built during the Meta Global AI Developer Hackathon. See [docs/hackathon-contributions.md](docs/hackathon-contributions.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for full licensing details.
