"""Pydantic schemas for ReproProof contracts, state machine, and action plans."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RunStatus(str, Enum):
    """Honest run statuses defined by PRD §State machine.
    
    HARD RULE: Never use the word 'verified' as a status. Use 'passes_frozen_test'.
    """
    RECEIVED = "received"
    CLARIFICATION_REQUIRED = "clarification_required"
    REPRODUCING = "reproducing"
    AWAITING_TEST_APPROVAL = "awaiting_test_approval"
    NOT_REPRODUCED = "not_reproduced"
    ENVIRONMENT_ERROR = "environment_error"
    TEST_REJECTED = "test_rejected"
    PATCHING = "patching"
    VERIFYING = "verifying"
    PASSES_FROZEN_TEST = "passes_frozen_test"
    UNRESOLVED = "unresolved"
    BUDGET_EXCEEDED = "budget_exceeded"


class ModelMode(str, Enum):
    """Explicit model execution mode tracking."""
    LIVE_MODEL = "LIVE_MODEL"
    MOCK_MODEL = "MOCK_MODEL"


class RegressionStatus(str, Enum):
    """Explicit regression execution outcome semantics."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_RUN = "NOT_RUN"
    ERROR = "ERROR"


# Valid state machine transitions per PRD §State machine
VALID_TRANSITIONS: Dict[RunStatus, List[RunStatus]] = {
    RunStatus.RECEIVED: [
        RunStatus.CLARIFICATION_REQUIRED,
        RunStatus.REPRODUCING,
        RunStatus.BUDGET_EXCEEDED,
    ],
    RunStatus.CLARIFICATION_REQUIRED: [
        RunStatus.RECEIVED,
        RunStatus.BUDGET_EXCEEDED,
    ],
    RunStatus.REPRODUCING: [
        RunStatus.AWAITING_TEST_APPROVAL,
        RunStatus.NOT_REPRODUCED,
        RunStatus.ENVIRONMENT_ERROR,
        RunStatus.BUDGET_EXCEEDED,
    ],
    RunStatus.AWAITING_TEST_APPROVAL: [
        RunStatus.TEST_REJECTED,
        RunStatus.PATCHING,
        RunStatus.BUDGET_EXCEEDED,
    ],
    RunStatus.TEST_REJECTED: [],  # terminal
    RunStatus.NOT_REPRODUCED: [],  # terminal
    RunStatus.ENVIRONMENT_ERROR: [],  # terminal
    RunStatus.PATCHING: [
        RunStatus.VERIFYING,
        RunStatus.UNRESOLVED,
        RunStatus.BUDGET_EXCEEDED,
    ],
    RunStatus.VERIFYING: [
        RunStatus.PASSES_FROZEN_TEST,
        RunStatus.PATCHING,  # attempt 2 only
        RunStatus.UNRESOLVED,
        RunStatus.BUDGET_EXCEEDED,
    ],
    RunStatus.PASSES_FROZEN_TEST: [],  # terminal success
    RunStatus.UNRESOLVED: [],  # terminal failure
    RunStatus.BUDGET_EXCEEDED: [],  # terminal limit hit
}


# --- Model-Proposed Action Plan Contract ---

AllowedActionType = Literal[
    "goto",
    "click",
    "fill",
    "select",
    "assert_text_visible",
    "assert_text_hidden",
    "assert_element_visible",
    "assert_value_equals",
    "assert_url_contains",
]

ALLOWED_ROLES = {
    "button", "link", "textbox", "checkbox", "radio", "combobox",
    "heading", "row", "cell", "tab", "menuitem", "dialog", "alert", "status",
}


_SAFE_PATH_RE = re.compile(r"/(?![/\\])[A-Za-z0-9\-._~!$&'()*+,;=@%/?#]*")


class ActionStep(BaseModel):
    """Single step proposed by the model with strict security validation."""
    model_config = ConfigDict(extra="forbid")

    action: AllowedActionType
    path: Optional[str] = Field(default=None, max_length=256)
    selector: Optional[str] = Field(default=None, max_length=256)
    role: Optional[str] = Field(default=None, max_length=64)
    name: Optional[str] = Field(default=None, max_length=128)
    value: Optional[str] = Field(default=None, max_length=512)
    text: Optional[str] = Field(default=None, max_length=512)
    exact: Optional[bool] = Field(default=None)

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: Optional[str]) -> Optional[str]:
        # Single leading '/', then only printable URL characters. Rejects '//', '/\', schemes (':'),
        # backslashes, whitespace and control chars (the URL parser strips tab/newline, so
        # '/<TAB>/evil.example' would otherwise become protocol-relative '//evil.example').
        if v is not None:
            if not _SAFE_PATH_RE.fullmatch(v):
                raise ValueError(
                    "Path must be a relative URL starting with a single '/' and cannot contain ':', '\\\\', or protocol-relative schemes."
                )
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.lower() not in ALLOWED_ROLES:
            raise ValueError(f"Role '{v}' is not an allowlisted ARIA role. Allowed: {sorted(list(ALLOWED_ROLES))}")
        return v.lower() if v else None

    @model_validator(mode="after")
    def validate_step_action_requirements(self) -> ActionStep:
        if self.action == "goto" and not self.path:
            raise ValueError("Action 'goto' requires 'path'.")
        if self.action == "click" and not (self.role or self.name or self.selector):
            raise ValueError("Action 'click' requires at least one of 'role', 'name', or 'selector'.")
        if self.action in ("fill", "select") and not (self.selector and self.value is not None):
            raise ValueError(f"Action '{self.action}' requires both 'selector' and 'value'.")
        if self.action in ("assert_text_visible", "assert_text_hidden") and not self.text:
            raise ValueError(f"Action '{self.action}' requires 'text'.")
        if self.action in ("assert_element_visible", "assert_value_equals") and not self.selector:
            raise ValueError(f"Action '{self.action}' requires 'selector'.")
        if self.action == "assert_url_contains" and not self.value:
            raise ValueError("Action 'assert_url_contains' requires 'value'.")
        return self


class ActionPlan(BaseModel):
    """Model-proposed action plan. Strict schema rejecting unknown fields."""
    model_config = ConfigDict(extra="forbid")

    expected_behavior: str = Field(..., min_length=5, max_length=500)
    clarification_question: Optional[str] = Field(default=None, max_length=500)
    steps: List[ActionStep] = Field(default_factory=list, max_length=30)
    assertions: List[ActionStep] = Field(default_factory=list, min_length=0, max_length=10)


# --- App Manifest Contract ---

class AppManifest(BaseModel):
    """Contract for supported apps allowlisted by manifests."""
    model_config = ConfigDict(extra="forbid")

    app_id: str = Field(..., max_length=64)
    name: str = Field(default="", max_length=128)
    description: str = Field(default="", max_length=500)
    base_url: str = Field(..., max_length=256)
    start_command: str = Field(..., max_length=256)
    app_dir: str = Field(default=".", max_length=256)
    allowed_source_paths: List[str] = Field(..., min_length=1)
    protected_paths: List[str] = Field(default_factory=list)
    regression_command: Optional[str] = Field(default=None, max_length=256)
    startup_timeout_seconds: int = Field(default=60, ge=5, le=300)


# --- Controller-Owned Run Record ---

class UsageRecord(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class RunRecord(BaseModel):
    """Controller-owned run record. Models must NEVER supply these fields."""
    run_id: str
    app_id: str
    status: RunStatus = RunStatus.RECEIVED
    source_revision: Optional[str] = None
    patched_revision: Optional[str] = None
    test_sha256: Optional[str] = None
    frozen_test_code: Optional[str] = None
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    model_ids: List[str] = Field(default_factory=list)
    patch_attempts: int = 0
    usage: UsageRecord = Field(default_factory=UsageRecord)
    artifact_ids: List[str] = Field(default_factory=list)
    plan_json: Optional[str] = None
    patch_diff: Optional[str] = None
    verification_evidence: Optional[str] = None
    model_mode: ModelMode
    regression_status: RegressionStatus = RegressionStatus.NOT_RUN
    report_text: Optional[str] = None
    reproduced_test_code: Optional[str] = None
    reproduced_test_sha256: Optional[str] = None
    patch_application_output: Optional[str] = None
    reproduction_logs: Optional[str] = None
    reproduction_screenshot_path: Optional[str] = None
    reproduction_screenshot_timestamp: Optional[str] = None
    reproduction_screenshot_sha256: Optional[str] = None
    verification_screenshot_path: Optional[str] = None
    verification_screenshot_timestamp: Optional[str] = None
    verification_screenshot_sha256: Optional[str] = None
    created_at: str
    updated_at: str
    status_reason: Optional[str] = None


# --- Patch Proposal ---

class PatchProposal(BaseModel):
    """Model proposed source code patch."""
    model_config = ConfigDict(extra="forbid")

    explanation: str = Field(..., max_length=1000)
    unified_diff: str = Field(..., min_length=1)
    target_files: List[str] = Field(default_factory=list, max_length=5)


# --- Evidence Bundle ---

class EvidenceBundle(BaseModel):
    """R9 evidence bundle. Built only by EvidenceExporter.create_bundle_from_run from the run record."""
    bundle_id: str
    run_id: str
    app_id: str
    report_text: str
    expected_behavior: str
    plan_json: Optional[str] = None
    model_ids: List[str]
    model_mode: ModelMode
    model_mode_disclosure: str
    source_revision: Optional[str] = None
    patched_revision: Optional[str] = None
    test_sha256: str
    frozen_test_code: str
    intended_assertion: str
    before_screenshot_b64: Optional[str] = None
    after_screenshot_b64: Optional[str] = None
    reproduction_screenshot_sha256: Optional[str] = None
    verification_screenshot_sha256: Optional[str] = None
    reproduction_screenshot_timestamp: Optional[str] = None
    verification_screenshot_timestamp: Optional[str] = None
    patch_diff: Optional[str] = None
    patch_application_output: Optional[str] = None
    reproduction_logs: Optional[str] = None
    verification_evidence: Optional[Dict[str, Any]] = None
    check_results: Dict[str, Any] = Field(default_factory=dict)
    usage: UsageRecord
    final_status: RunStatus
    regression_status: RegressionStatus
    human_approval: Optional[Dict[str, Any]] = None
    artifacts_integrity: Dict[str, str] = Field(default_factory=dict)
    evidence_valid: bool
    integrity_failures: List[str] = Field(default_factory=list)
    run_created_at: str
    run_updated_at: str
