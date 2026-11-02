"""Pydantic schemas for ReproProof contracts, state machine, and action plans."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


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


class ActionStep(BaseModel):
    """Single step proposed by the model."""
    model_config = ConfigDict(extra="forbid")

    action: AllowedActionType
    path: Optional[str] = Field(default=None, max_length=256)
    selector: Optional[str] = Field(default=None, max_length=256)
    role: Optional[str] = Field(default=None, max_length=64)
    name: Optional[str] = Field(default=None, max_length=128)
    value: Optional[str] = Field(default=None, max_length=512)
    text: Optional[str] = Field(default=None, max_length=512)


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
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    model_ids: List[str] = Field(default_factory=list)
    patch_attempts: int = 0
    usage: UsageRecord = Field(default_factory=UsageRecord)
    artifact_ids: List[str] = Field(default_factory=list)
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
    """R9 evidence bundle contract."""
    bundle_id: str
    run_id: str
    app_id: str
    report_text: str
    screenshot_filename: Optional[str] = None
    expected_behavior: str
    model_ids: List[str]
    source_revision: Optional[str] = None
    patched_revision: Optional[str] = None
    test_sha256: str
    frozen_test_code: str
    intended_assertion: str
    before_screenshot_b64: Optional[str] = None
    after_screenshot_b64: Optional[str] = None
    patch_diff: Optional[str] = None
    check_results: Dict[str, Any] = Field(default_factory=dict)
    rejected_attempts: List[Dict[str, Any]] = Field(default_factory=list)
    usage: UsageRecord
    final_status: RunStatus
    created_at: str
