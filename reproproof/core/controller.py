"""Controller and State Machine Engine for ReproProof runs.

Enforces:
- Hard Rule 1: Models only propose. Only the controller changes run state.
- Hard Rule 2: Never call patch model before human approves reproduction test.
- Hard Rule 4: Never set passes_frozen_test unless same test hash and regression checks pass.
- Hard Rule 5: Never use 'verified' as a status. Use 'passes_frozen_test'.
- Invariant: Approval binds to exact test hash; duplicate or mutated approvals are rejected.
- Invariant: Direct caller transition to passes_frozen_test without evidence is rejected.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from reproproof.core.schemas import (
    ActionPlan,
    PatchProposal,
    RunRecord,
    RunStatus,
    UsageRecord,
    VALID_TRANSITIONS,
)
from reproproof.core.limits import DEFAULT_LIMITS, RunLimits, BudgetExceededError


class StateTransitionError(Exception):
    """Raised when an illegal or unverified state transition is attempted."""
    pass


class RunController:
    """Orchestrates run lifecycle and enforces hard rules in code."""

    def __init__(self, db_path: str = "reproproof.db", limits: RunLimits = DEFAULT_LIMITS):
        self.db_path = db_path
        self.limits = limits
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initializes the SQLite schema with complete persistence fields."""
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
            conn.commit()

    def create_run(self, app_id: str, source_revision: Optional[str] = None) -> RunRecord:
        """Initializes a new run in RECEIVED state."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        run_id = str(uuid.uuid4())
        record = RunRecord(
            run_id=run_id,
            app_id=app_id,
            status=RunStatus.RECEIVED,
            source_revision=source_revision,
            created_at=now,
            updated_at=now,
        )

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO runs (
                    run_id, app_id, status, source_revision, patched_revision,
                    test_sha256, frozen_test_code, approved_at, approved_by, model_ids, patch_attempts,
                    input_tokens, output_tokens, cost_usd, artifact_ids,
                    status_reason, plan_json, patch_diff, verification_evidence,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.run_id,
                record.app_id,
                record.status.value,
                record.source_revision,
                record.patched_revision,
                record.test_sha256,
                record.frozen_test_code,
                record.approved_at,
                record.approved_by,
                json.dumps(record.model_ids),
                record.patch_attempts,
                record.usage.input_tokens,
                record.usage.output_tokens,
                record.usage.cost_usd,
                json.dumps(record.artifact_ids),
                record.status_reason,
                record.plan_json,
                record.patch_diff,
                record.verification_evidence,
                record.created_at,
                record.updated_at,
            ))
            conn.execute("""
                INSERT INTO transitions (run_id, from_status, to_status, reason, actor, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (run_id, "NONE", RunStatus.RECEIVED.value, "Run created", "controller", now))
            conn.commit()

        return record

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        """Retrieves a run by run_id."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if not row:
                return None
            return RunRecord(
                run_id=row["run_id"],
                app_id=row["app_id"],
                status=RunStatus(row["status"]),
                source_revision=row["source_revision"],
                patched_revision=row["patched_revision"],
                test_sha256=row["test_sha256"],
                frozen_test_code=row["frozen_test_code"],
                approved_at=row["approved_at"],
                approved_by=row["approved_by"],
                model_ids=json.loads(row["model_ids"]),
                patch_attempts=row["patch_attempts"],
                usage=UsageRecord(
                    input_tokens=row["input_tokens"],
                    output_tokens=row["output_tokens"],
                    cost_usd=row["cost_usd"],
                ),
                artifact_ids=json.loads(row["artifact_ids"]),
                status_reason=row["status_reason"],
                plan_json=row["plan_json"],
                patch_diff=row["patch_diff"],
                verification_evidence=row["verification_evidence"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def record_plan(self, run_id: str, plan: ActionPlan) -> None:
        """Stores reproduction plan in run record."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        plan_str = json.dumps(plan.model_dump(), ensure_ascii=False)
        with self._get_connection() as conn:
            conn.execute("UPDATE runs SET plan_json = ?, updated_at = ? WHERE run_id = ?", (plan_str, now, run_id))
            conn.commit()

    def record_patch(self, run_id: str, patch: PatchProposal) -> None:
        """Stores patch proposal in run record."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("UPDATE runs SET patch_diff = ?, updated_at = ? WHERE run_id = ?", (patch.unified_diff, now, run_id))
            conn.commit()

    def transition(
        self,
        run_id: str,
        to_status: RunStatus,
        reason: Optional[str] = None,
        actor: str = "controller",
        _internal_evidence_verified: bool = False,
    ) -> RunRecord:
        """Enforces legal state transitions per PRD §State machine.

        Hard Rule: Reject any other transition in code.
        Hard Rule: Direct caller transition to PASSES_FROZEN_TEST without verified evidence is prohibited.
        """
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")

        from_status = run.status

        # Invariant: PASSES_FROZEN_TEST requires evidence
        if to_status == RunStatus.PASSES_FROZEN_TEST and not _internal_evidence_verified:
            raise StateTransitionError(
                "Direct transition to passes_frozen_test is prohibited. "
                "Must invoke record_verification_result with verified fresh-copy evidence."
            )

        # Check transition validity
        allowed = VALID_TRANSITIONS.get(from_status, [])
        if to_status not in allowed:
            raise StateTransitionError(
                f"Illegal state transition from {from_status.value} to {to_status.value}. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE runs
                SET status = ?, status_reason = ?, updated_at = ?
                WHERE run_id = ?
            """, (to_status.value, reason, now, run_id))

            conn.execute("""
                INSERT INTO transitions (run_id, from_status, to_status, reason, actor, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (run_id, from_status.value, to_status.value, reason or "", actor, now))
            conn.commit()

        run.status = to_status
        run.status_reason = reason
        run.updated_at = now
        return run

    def record_human_approval(
        self,
        run_id: str,
        test_sha256: str,
        frozen_test_code: Optional[str] = None,
        approved_by: str = "human_operator",
    ) -> RunRecord:
        """Records human test approval and freezes the reproduction test.

        Enforces:
        - Transition only from AWAITING_TEST_APPROVAL.
        - Hash verification: computed SHA-256 of code must match test_sha256.
        - Atomic transition preventing duplicate approval.
        - Test is immutable once approved.
        """
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")

        if run.status != RunStatus.AWAITING_TEST_APPROVAL:
            raise StateTransitionError(
                f"Cannot approve test in state '{run.status.value}'. Must be in 'awaiting_test_approval'."
            )

        if run.approved_at is not None:
            raise StateTransitionError("Duplicate approval rejected: test is already approved and frozen.")

        # If code is supplied, verify hash integrity
        if frozen_test_code:
            actual_sha = hashlib.sha256(frozen_test_code.encode("utf-8")).hexdigest()
            if actual_sha != test_sha256:
                raise StateTransitionError(
                    f"Test hash mismatch on approval: expected {test_sha256}, calculated {actual_sha}."
                )

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            # Atomic update checking status and approved_at
            cursor = conn.execute("""
                UPDATE runs
                SET test_sha256 = ?, frozen_test_code = COALESCE(?, frozen_test_code),
                    approved_at = ?, approved_by = ?, status = ?,
                    status_reason = ?, updated_at = ?
                WHERE run_id = ? AND status = ? AND approved_at IS NULL
            """, (
                test_sha256,
                frozen_test_code,
                now,
                approved_by,
                RunStatus.PATCHING.value,
                f"Approved by {approved_by} with frozen test SHA-256: {test_sha256[:12]}...",
                now,
                run_id,
                RunStatus.AWAITING_TEST_APPROVAL.value,
            ))
            if cursor.rowcount == 0:
                raise StateTransitionError("Approval failed: concurrent update or state mismatch.")

            conn.execute("""
                INSERT INTO transitions (run_id, from_status, to_status, reason, actor, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (run_id, RunStatus.AWAITING_TEST_APPROVAL.value, RunStatus.PATCHING.value, f"Approved by {approved_by}", approved_by, now))
            conn.commit()

        run.test_sha256 = test_sha256
        if frozen_test_code:
            run.frozen_test_code = frozen_test_code
        run.approved_at = now
        run.approved_by = approved_by
        run.status = RunStatus.PATCHING
        run.updated_at = now
        return run

    def record_human_rejection(
        self,
        run_id: str,
        reason: str = "Test does not accurately capture the reported defect",
        rejected_by: str = "human_operator",
    ) -> RunRecord:
        """Records human rejection of the reproduction test."""
        return self.transition(
            run_id=run_id,
            to_status=RunStatus.TEST_REJECTED,
            reason=reason,
            actor=rejected_by,
        )

    def record_verification_result(
        self,
        run_id: str,
        passed_frozen_test: bool,
        passed_regression: bool,
        actual_test_sha256: str,
        details: str,
        stdout: str = "",
        stderr: str = "",
    ) -> RunRecord:
        """Records clean verification evidence and transitions state accordingly.

        Hard Rule 4: Never set passes_frozen_test unless same test hash and regression checks pass.
        """
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")

        if run.status != RunStatus.VERIFYING:
            raise StateTransitionError(
                f"Cannot record verification result in state '{run.status.value}'. Must be in 'verifying'."
            )

        # Hash integrity check
        if run.test_sha256 and actual_test_sha256 != run.test_sha256:
            raise StateTransitionError(
                f"Verification test hash ({actual_test_sha256}) does not match frozen test hash ({run.test_sha256})."
            )

        evidence = {
            "passed_frozen_test": passed_frozen_test,
            "passed_regression": passed_regression,
            "actual_test_sha256": actual_test_sha256,
            "details": details,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        evidence_json = json.dumps(evidence)

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE runs
                SET verification_evidence = ?, updated_at = ?
                WHERE run_id = ?
            """, (evidence_json, now, run_id))
            conn.commit()

        if passed_frozen_test and passed_regression:
            return self.transition(
                run_id=run_id,
                to_status=RunStatus.PASSES_FROZEN_TEST,
                reason=details,
                actor="verifier",
                _internal_evidence_verified=True,
            )
        else:
            # Check attempts: if under limit, can retry (PATCHING); else UNRESOLVED
            if run.patch_attempts < self.limits.max_patch_attempts:
                return self.transition(
                    run_id=run_id,
                    to_status=RunStatus.PATCHING,
                    reason=f"Verification failed on attempt {run.patch_attempts}: {details}. Retrying.",
                    actor="verifier",
                )
            else:
                return self.transition(
                    run_id=run_id,
                    to_status=RunStatus.UNRESOLVED,
                    reason=f"Verification failed and all {self.limits.max_patch_attempts} attempts exhausted.",
                    actor="verifier",
                )

    def record_usage(
        self,
        run_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        model_id: Optional[str] = None,
    ) -> RunRecord:
        """Tracks token and monetary usage against PRD budget limits."""
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")

        new_in = run.usage.input_tokens + input_tokens
        new_out = run.usage.output_tokens + output_tokens
        new_cost = run.usage.cost_usd + cost_usd
        models = list(run.model_ids)
        if model_id and model_id not in models:
            models.append(model_id)

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE runs
                SET input_tokens = ?, output_tokens = ?, cost_usd = ?, model_ids = ?, updated_at = ?
                WHERE run_id = ?
            """, (new_in, new_out, new_cost, json.dumps(models), now, run_id))
            conn.commit()

        run.usage.input_tokens = new_in
        run.usage.output_tokens = new_out
        run.usage.cost_usd = new_cost
        run.model_ids = models

        # Check spend limit
        if new_cost > self.limits.spend_limit_usd:
            self.transition(
                run_id=run_id,
                to_status=RunStatus.BUDGET_EXCEEDED,
                reason=f"Spend ${new_cost:.2f} exceeded limit ${self.limits.spend_limit_usd:.2f}",
                actor="controller",
            )
            raise BudgetExceededError(f"Spend limit of ${self.limits.spend_limit_usd:.2f} exceeded.")

        return run

    def record_patch_attempt(self, run_id: str) -> int:
        """Increments patch attempt count."""
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")

        new_attempts = run.patch_attempts + 1
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE runs
                SET patch_attempts = ?, updated_at = ?
                WHERE run_id = ?
            """, (new_attempts, now, run_id))
            conn.commit()

        return new_attempts
