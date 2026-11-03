"""Controller and State Machine Engine for ReproProof runs.

Enforces in code:
- H-5 Models only propose. Only the controller changes run state.
- H-6 No patch before human approval; approval binds to the exact controller-stored
  reproduced test and its SHA-256. Once approved the test is frozen.
- H-8 `passes_frozen_test` is reachable ONLY through `run_verification()`, which itself runs
  the fresh-copy verifier on the controller-stored test and patch, then checks the
  result's provenance (run id, test hash, patch hash, source revision). There is no public
  method that accepts a caller-supplied success flag.
- H-9 The word "verified" is never a status.
- Execution boundary: LIVE_MODEL patches are not executed on the host unless the operator
  explicitly opts in with HOST_EXECUTION_FLAG=1 (there is no sandbox).
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import re
import sqlite3
import uuid
from typing import Iterator, List, Optional

from reproproof.core.limits import DEFAULT_LIMITS, BudgetExceededError, RunLimits
from reproproof.core.planner import load_manifest
from reproproof.core.schemas import (
    VALID_TRANSITIONS,
    ActionPlan,
    ModelMode,
    PatchProposal,
    RegressionStatus,
    RunRecord,
    RunStatus,
    UsageRecord,
)
from reproproof.core.verifier import (
    FreshCopyVerifier,
    VerificationResult,
    resolve_app_dir,
    sha256_file,
    sha256_text,
    tree_sha256,
)

HOST_EXECUTION_FLAG = "REPROPROOF_ALLOW_UNSANDBOXED_HOST_EXECUTION"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")

# Columns added after the first schema version (migrated in place on existing DBs).
_EXTRA_COLUMNS = [
    ("model_mode", "TEXT"),
    ("regression_status", "TEXT NOT NULL DEFAULT 'NOT_RUN'"),
    ("report_text", "TEXT"),
    ("reproduced_test_code", "TEXT"),
    ("reproduced_test_sha256", "TEXT"),
    ("patch_application_output", "TEXT"),
    ("reproduction_logs", "TEXT"),
    ("reproduction_screenshot_path", "TEXT"),
    ("reproduction_screenshot_timestamp", "TEXT"),
    ("reproduction_screenshot_sha256", "TEXT"),
    ("verification_screenshot_path", "TEXT"),
    ("verification_screenshot_timestamp", "TEXT"),
    ("verification_screenshot_sha256", "TEXT"),
]


class StateTransitionError(Exception):
    """Raised when an illegal or unverified state transition is attempted."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class RunController:
    """Orchestrates run lifecycle and enforces hard rules in code."""

    def __init__(self, db_path: str = "reproproof.db", limits: RunLimits = DEFAULT_LIMITS,
                 manifests_dir: Optional[str] = None):
        self.db_path = db_path
        self.limits = limits
        self.manifests_dir = manifests_dir
        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """Yields a connection inside a transaction (commit/rollback) and always closes it."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    app_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_revision TEXT,
                    patched_revision TEXT,
                    test_sha256 TEXT,
                    frozen_test_code TEXT,
                    approved_at TEXT,
                    approved_by TEXT,
                    model_ids TEXT NOT NULL,
                    patch_attempts INTEGER DEFAULT 0,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0.0,
                    artifact_ids TEXT NOT NULL,
                    status_reason TEXT,
                    plan_json TEXT,
                    patch_diff TEXT,
                    verification_evidence TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    from_status TEXT NOT NULL,
                    to_status TEXT NOT NULL,
                    reason TEXT,
                    actor TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs (run_id)
                )
            """)
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
            for name, ddl in _EXTRA_COLUMNS:
                if name not in existing:
                    conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {ddl}")

    # ---------------------------------------------------------------- reads

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        return RunRecord(
            **{k: data[k] for k in RunRecord.model_fields if k in data and k not in ("usage", "model_ids", "artifact_ids")},
            model_ids=json.loads(data["model_ids"]),
            artifact_ids=json.loads(data["artifact_ids"]),
            usage=UsageRecord(input_tokens=data["input_tokens"], output_tokens=data["output_tokens"],
                              cost_usd=data["cost_usd"]),
        )

    def list_runs(self) -> List[dict]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT run_id, app_id, status, model_mode, regression_status, patch_attempts, cost_usd, created_at "
                "FROM runs ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def _require(self, run_id: str, status: Optional[RunStatus] = None) -> RunRecord:
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")
        if status is not None and run.status != status:
            raise StateTransitionError(f"Run is in state '{run.status.value}', expected '{status.value}'.")
        return run

    def _update(self, run_id: str, **fields) -> None:
        fields["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._get_connection() as conn:
            conn.execute(f"UPDATE runs SET {cols} WHERE run_id = ?", (*fields.values(), run_id))

    # ---------------------------------------------------------------- writes

    def create_run(self, app_id: str, *, model_mode: ModelMode, report_text: str,
                   source_revision: Optional[str] = None) -> RunRecord:
        """Creates a run in RECEIVED. Model mode and report are mandatory and immutable."""
        if not isinstance(model_mode, ModelMode):
            raise ValueError("model_mode must be ModelMode.LIVE_MODEL or ModelMode.MOCK_MODEL.")
        if not report_text or not report_text.strip():
            raise ValueError("report_text is required.")
        now = _now()
        record = RunRecord(run_id=str(uuid.uuid4()), app_id=app_id, status=RunStatus.RECEIVED,
                           source_revision=source_revision, model_mode=model_mode, report_text=report_text,
                           created_at=now, updated_at=now)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO runs (run_id, app_id, status, source_revision, model_ids, artifact_ids,
                                  model_mode, report_text, regression_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, '[]', '[]', ?, ?, ?, ?, ?)
            """, (record.run_id, app_id, RunStatus.RECEIVED.value, source_revision, model_mode.value,
                  report_text, RegressionStatus.NOT_RUN.value, now, now))
            conn.execute(
                "INSERT INTO transitions (run_id, from_status, to_status, reason, actor, timestamp) "
                "VALUES (?, 'NONE', ?, 'Run created', 'controller', ?)",
                (record.run_id, RunStatus.RECEIVED.value, now),
            )
        return record

    def record_plan(self, run_id: str, plan: ActionPlan) -> None:
        self._require(run_id, RunStatus.RECEIVED)
        self._update(run_id, plan_json=json.dumps(plan.model_dump(), ensure_ascii=False))

    def record_reproduction(self, run_id: str, test_code: str, screenshot_path: Optional[str] = None,
                            screenshot_timestamp: Optional[str] = None, logs: Optional[str] = None) -> None:
        """Stores the executed reproduction test. Only while REPRODUCING, so it cannot be swapped later.

        The controller computes the test hash and the app source revision itself.
        """
        run = self._require(run_id, RunStatus.REPRODUCING)
        if not test_code or not test_code.strip():
            raise StateTransitionError("Reproduction test code is empty.")
        manifest = load_manifest(run.app_id, self.manifests_dir)
        self._update(
            run_id,
            reproduced_test_code=test_code,
            reproduced_test_sha256=sha256_text(test_code),
            source_revision=tree_sha256(resolve_app_dir(manifest.app_dir)),
            reproduction_screenshot_path=screenshot_path,
            reproduction_screenshot_sha256=sha256_file(screenshot_path),
            reproduction_screenshot_timestamp=screenshot_timestamp if screenshot_path else None,
            reproduction_logs=logs,
        )

    def record_patch(self, run_id: str, patch: PatchProposal) -> None:
        self._require(run_id, RunStatus.PATCHING)
        self._update(run_id, patch_diff=patch.unified_diff)

    def transition(self, run_id: str, to_status: RunStatus, reason: Optional[str] = None,
                   actor: str = "controller") -> RunRecord:
        """Legal state transitions only. PASSES_FROZEN_TEST is never reachable from here."""
        if to_status == RunStatus.PASSES_FROZEN_TEST:
            raise StateTransitionError(
                "Direct transition to passes_frozen_test is prohibited. Use run_verification()."
            )
        run = self._require(run_id)
        allowed = VALID_TRANSITIONS.get(run.status, [])
        if to_status not in allowed:
            raise StateTransitionError(
                f"Illegal state transition from {run.status.value} to {to_status.value}. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )
        self._write_transition(run_id, run.status, to_status, reason, actor)
        return self.get_run(run_id)

    def _write_transition(self, run_id: str, from_status: RunStatus, to_status: RunStatus,
                          reason: Optional[str], actor: str, **fields) -> None:
        now = _now()
        fields.update(status=to_status.value, status_reason=reason, updated_at=now)
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._get_connection() as conn:
            cur = conn.execute(f"UPDATE runs SET {cols} WHERE run_id = ? AND status = ?",
                               (*fields.values(), run_id, from_status.value))
            if cur.rowcount != 1:
                raise StateTransitionError("Concurrent update or state mismatch; transition aborted.")
            conn.execute(
                "INSERT INTO transitions (run_id, from_status, to_status, reason, actor, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, from_status.value, to_status.value, reason or "", actor, now),
            )

    def record_human_approval(self, run_id: str, test_sha256: str, frozen_test_code: Optional[str] = None,
                              approved_by: str = "human_operator") -> RunRecord:
        """Freezes the reproduced test. Approval binds to the controller-stored test and its hash.

        Rejects: wrong state, duplicate approval, missing reproduced test, malformed/placeholder hash,
        a hash or code that differs from the reproduced test, and an empty approver.
        """
        run = self._require(run_id)
        if run.status != RunStatus.AWAITING_TEST_APPROVAL:
            raise StateTransitionError(
                f"Cannot approve test in state '{run.status.value}'. Must be in 'awaiting_test_approval'."
            )
        if run.approved_at is not None:
            raise StateTransitionError("Duplicate approval rejected: test is already approved and frozen.")
        if not approved_by or not approved_by.strip():
            raise StateTransitionError("Approval rejected: approver identity is required.")
        if not test_sha256 or not _SHA256_RE.fullmatch(test_sha256):
            raise StateTransitionError(
                f"Approval rejected: test SHA-256 hash is empty, placeholder or malformed: '{test_sha256}'."
            )
        if not run.reproduced_test_code or not run.reproduced_test_sha256:
            raise StateTransitionError("Approval rejected: no reproduced test code is stored for this run.")
        if sha256_text(run.reproduced_test_code) != run.reproduced_test_sha256:
            raise StateTransitionError("Approval rejected: stored reproduced test does not match its stored hash.")
        if test_sha256 != run.reproduced_test_sha256:
            raise StateTransitionError(
                f"Test code differs from the reproduced test: reproduced hash is "
                f"{run.reproduced_test_sha256}, approved hash is {test_sha256}."
            )
        if frozen_test_code is not None and frozen_test_code != run.reproduced_test_code:
            raise StateTransitionError("Test code differs from the reproduced test.")

        now = _now()
        self._write_transition(
            run_id, RunStatus.AWAITING_TEST_APPROVAL, RunStatus.PATCHING,
            f"Approved by {approved_by} with frozen test SHA-256: {test_sha256[:12]}...", approved_by,
            test_sha256=test_sha256, frozen_test_code=run.reproduced_test_code,
            approved_at=now, approved_by=approved_by,
        )
        return self.get_run(run_id)

    def record_human_rejection(self, run_id: str,
                               reason: str = "Test does not accurately capture the reported defect",
                               rejected_by: str = "human_operator") -> RunRecord:
        return self.transition(run_id, RunStatus.TEST_REJECTED, reason=reason, actor=rejected_by)

    # ---------------------------------------------------------------- verification

    def run_verification(self, run_id: str) -> RunRecord:
        """Executes fresh-copy verification of the stored patch against the stored frozen test.

        This is the only path to PASSES_FROZEN_TEST. Inputs come from the run record and the
        allowlisted manifest, never from the caller.
        """
        run = self._require(run_id, RunStatus.VERIFYING)
        if not run.approved_at or not run.approved_by:
            raise StateTransitionError("Cannot verify: no human approval recorded.")
        if not run.frozen_test_code or not run.test_sha256:
            raise StateTransitionError("Cannot verify: no frozen test stored.")
        if sha256_text(run.frozen_test_code) != run.test_sha256 or run.test_sha256 != run.reproduced_test_sha256:
            raise StateTransitionError("Cannot verify: frozen test does not match its approved hash.")
        if not run.patch_diff:
            raise StateTransitionError("Cannot verify: no patch stored.")

        if run.model_mode == ModelMode.LIVE_MODEL and os.environ.get(HOST_EXECUTION_FLAG) != "1":
            result = VerificationResult(
                run_id=run.run_id, test_sha256=run.test_sha256, patch_diff_sha256=sha256_text(run.patch_diff),
                frozen_test_status=RegressionStatus.NOT_RUN, regression_status=RegressionStatus.NOT_RUN,
                details=(f"Model-generated patch NOT executed: no sandbox is available and {HOST_EXECUTION_FLAG}"
                         " is not set. Patch is recorded for human review only."),
            )
            return self._record_verification(run, result, terminal=True)

        manifest = load_manifest(run.app_id, self.manifests_dir)
        try:
            result = FreshCopyVerifier(manifest, self.limits).verify_patch(
                app_source_dir=manifest.app_dir,
                patch_proposal=PatchProposal(explanation="controller-stored patch", unified_diff=run.patch_diff),
                frozen_test_code=run.frozen_test_code,
                expected_test_sha256=run.test_sha256,
                run_id=run.run_id,
            )
        except Exception as e:  # infrastructure crash: record as ERROR, never as success
            result = VerificationResult(
                run_id=run.run_id, test_sha256=run.test_sha256, patch_diff_sha256=sha256_text(run.patch_diff),
                frozen_test_status=RegressionStatus.ERROR, regression_status=RegressionStatus.NOT_RUN,
                details=f"Verifier crashed: {type(e).__name__}: {e}",
            )
        return self._record_verification(run, result)

    def _record_verification(self, run: RunRecord, result: VerificationResult, terminal: bool = False) -> RunRecord:
        """Validates verifier provenance against the run record, persists evidence, transitions."""
        problems = []
        if result.run_id != run.run_id:
            problems.append(f"evidence run_id {result.run_id} != {run.run_id}")
        if result.test_sha256 != run.test_sha256:
            problems.append("evidence test hash does not match the frozen test hash")
        if result.patch_diff_sha256 != sha256_text(run.patch_diff or ""):
            problems.append("evidence patch hash does not match the stored patch")
        if run.source_revision and result.source_revision and result.source_revision != run.source_revision:
            problems.append("app source changed between reproduction and verification")

        success = (not problems and not terminal
                   and result.frozen_test_status == RegressionStatus.PASSED
                   and result.regression_status == RegressionStatus.PASSED
                   and result.source_revision is not None)

        evidence = {
            "run_id": result.run_id,
            "test_sha256": result.test_sha256,
            "patch_diff_sha256": result.patch_diff_sha256,
            "source_revision": result.source_revision,
            "patched_revision": result.patched_revision,
            "frozen_test_status": result.frozen_test_status.value,
            "regression_status": result.regression_status.value,
            "details": result.details,
            "provenance_problems": problems,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "patch_application_output": result.patch_output,
            "verification_screenshot_path": result.verification_screenshot_path,
            "verification_screenshot_sha256": result.verification_screenshot_sha256,
            "verified_at": result.timestamp,
            "recorded_by": "controller.run_verification",
        }
        fields = dict(
            verification_evidence=json.dumps(evidence),
            regression_status=result.regression_status.value,
            patch_application_output=result.patch_output or None,
            patched_revision=result.patched_revision,
            verification_screenshot_path=result.verification_screenshot_path,
            verification_screenshot_sha256=result.verification_screenshot_sha256,
            verification_screenshot_timestamp=result.verification_screenshot_timestamp,
        )

        if success:
            self._write_transition(run.run_id, RunStatus.VERIFYING, RunStatus.PASSES_FROZEN_TEST,
                                   result.details, "controller", **fields)
            return self.get_run(run.run_id)

        reason = result.details + (f" Provenance rejected: {'; '.join(problems)}." if problems else "")
        if not terminal and not problems and run.patch_attempts < self.limits.max_patch_attempts:
            to_status, reason = RunStatus.PATCHING, f"Attempt {run.patch_attempts} failed: {reason} Retrying."
        else:
            to_status = RunStatus.UNRESOLVED
        self._write_transition(run.run_id, RunStatus.VERIFYING, to_status, reason, "controller", **fields)
        return self.get_run(run.run_id)

    # ---------------------------------------------------------------- budget

    def record_usage(self, run_id: str, input_tokens: int, output_tokens: int, cost_usd: float,
                     model_id: Optional[str] = None) -> RunRecord:
        """Tracks token and monetary usage against the spend limit."""
        run = self._require(run_id)
        models = list(run.model_ids)
        if model_id and model_id not in models:
            models.append(model_id)
        new_cost = run.usage.cost_usd + cost_usd
        self._update(run_id, input_tokens=run.usage.input_tokens + input_tokens,
                     output_tokens=run.usage.output_tokens + output_tokens,
                     cost_usd=new_cost, model_ids=json.dumps(models))
        if new_cost > self.limits.spend_limit_usd:
            self.transition(run_id, RunStatus.BUDGET_EXCEEDED,
                            reason=f"Spend ${new_cost:.2f} exceeded limit ${self.limits.spend_limit_usd:.2f}")
            raise BudgetExceededError(f"Spend limit of ${self.limits.spend_limit_usd:.2f} exceeded.")
        return self.get_run(run_id)

    def record_patch_attempt(self, run_id: str) -> int:
        run = self._require(run_id, RunStatus.PATCHING)
        self._update(run_id, patch_attempts=run.patch_attempts + 1)
        return run.patch_attempts + 1
