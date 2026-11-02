# IMPLEMENTATION_PLAN.md — Hackathon-Ready Hardening Plan

**Objective:** Transform ReproProof from a preliminary prototype into a safe, credible, verifiable hackathon MVP for the Meta Developer Hackathon / Indie Hackathon.

## Phase Overview & Priority Sequencing

### Phase 1: Baseline & Defect Inventory
- [x] Inspect existing working tree and test baseline.
- [x] Catalog review findings into explicit remediation tracks.
- [x] Establish implementation plan and verification log.

### Phase 2: Critical Security Fixes
- [ ] **Track A: Prevent Generated-Test Code Injection (RCE defense)**
  - Re-architect test compiler from string interpolation/comments to safe structured JSON plan embedding.
  - Implement strict schema validator for actions (`goto`, `click`, `fill`, `select`, `assert_*`).
  - Add adversarial tests with newlines, script tags, Unicode separators, quotes, and malicious JavaScript.
- [ ] **Track B: Fix Patch Application (Safe, Git-backed patching)**
  - Replace heuristic substring/line-deletion patcher with robust `git apply` / validation engine.
  - Validate patch file paths: reject traversal (`..`), symlinks, absolute paths, and protected paths (`package.json`, tests, configs).
  - Add test suite covering pure additions, mismatched context, CRLF files, traversal attempts, and protected files.

### Phase 3: Controller State-Transition Invariants & Persistence
- [ ] **Track C: Controller State Enforcement**
  - Store frozen test, SHA-256 hash, execution logs, plan, and patch persistently in SQLite.
  - Disallow direct transitions to `PASSES_FROZEN_TEST`. Require verified `VerificationResult` evidence.
  - Make human approval atomic and immutable. Once approved, reject test mutations.
  - Prevent duplicate approvals and concurrent state corruption.

### Phase 4: Reliable Playwright Infrastructure & Process Isolation
- [ ] **Track D: Real Execution Environment & Process Management**
  - Ephemeral free port allocation for test instances to prevent port conflicts.
  - Process tree tracking and reliable termination on Windows (`taskkill /F /T /PID`).
  - Environment sanitization: scrub `MODEL_API_KEY` and credentials from test and server environments.
  - Quoted paths and robust Playwright configuration for Windows paths.

### Phase 5: Honest Evaluation & Clean Verification
- [ ] **Track E: Remove Fabricated Results & Real E2E Verification**
  - Rewrite `evals/run_eval.py` to execute real test runs; mark unsupported or skipped cases as `NOT RUN`.
  - Clean up README, UI, and documentation to remove unverified numbers.
  - Run real end-to-end bug reproduction -> human approval -> patch application -> fresh-copy verification on `inventory-demo`.
  - Generate genuine evidence bundle with real execution artifacts.
