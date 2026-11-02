"""Controller and State Machine Engine for ReproProof runs.

Maintains strict state transitions, human approval gate, test freeze (SHA-256),
and persistent SQLite run storage.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from reproproof.core.schemas import (
    RunRecord,
    RunStatus,
    UsageRecord,
    VALID_TRANSITIONS,
)
from reproproof.core.limits import DEFAULT_LIMITS, RunLimits, BudgetExceededError


class StateTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""
    pass


class RunController:
    """Orchestrates run lifecycle and enforces hard rules in code."""

    def __init__(self, db_path: str = "reproproof.db", limits: RunLimits = DEFAULT_LIMITS):
        self.db_path = db_path
        self.limits = limits
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initializes the SQLite schema for run records and audit events."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    app_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_revision TEXT,
                    patched_revision TEXT,
                    test_sha256 TEXT,
                    approved_at TEXT,
                    approved_by TEXT,
                    model_ids TEXT NOT NULL,
                    patch_attempts INTEGER DEFAULT 0,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0.0,
                    artifact_ids TEXT NOT NULL,
                    status_reason TEXT,
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
                    test_sha256, approved_at, approved_by, model_ids, patch_attempts,
                    input_tokens, output_tokens, cost_usd, artifact_ids,
                    status_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.run_id,
                record.app_id,
                record.status.value,
                record.source_revision,
                record.patched_revision,
                record.test_sha256,
                record.approved_at,
                record.approved_by,
                json.dumps(record.model_ids),
                record.patch_attempts,
                record.usage.input_tokens,
                record.usage.output_tokens,
                record.usage.cost_usd,
                json.dumps(record.artifact_ids),
                record.status_reason,
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
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def transition(
        self,
        run_id: str,
        to_status: RunStatus,
        reason: Optional[str] = None,
        actor: str = "controller",
    ) -> RunRecord:
        """Enforces legal state transitions per PRD §State machine.
        
        Hard Rule: Reject any other transition in code.
        """
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")

        from_status = run.status

        # Check validity
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
        approved_by: str = "human_operator",
    ) -> RunRecord:
        """Records human test approval and transitions to PATCHING.
        
        Hard rule: Never call the patch model before a human approves the reproduction test.
        Freezes the test SHA-256.
        """
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")

        if run.status != RunStatus.AWAITING_TEST_APPROVAL:
            raise StateTransitionError(
                f"Cannot approve test in state {run.status.value}. Must be awaiting_test_approval."
            )

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE runs
                SET test_sha256 = ?, approved_at = ?, approved_by = ?, updated_at = ?
                WHERE run_id = ?
            """, (test_sha256, now, approved_by, now, run_id))
            conn.commit()

        return self.transition(
            run_id=run_id,
            to_status=RunStatus.PATCHING,
            reason=f"Approved by {approved_by} with frozen test SHA256: {test_sha256[:12]}...",
            actor=approved_by,
        )

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
