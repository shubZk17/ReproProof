"""Comprehensive unit and integration test suite for ReproProof core."""

import hashlib
import os
import pytest
from pathlib import Path

from reproproof.core.schemas import (
    ActionPlan,
    AppManifest,
    ModelMode,
    PatchProposal,
    RunStatus,
    VALID_TRANSITIONS,
)
from reproproof.core.controller import RunController, StateTransitionError
from reproproof.core.compiler import PlaywrightCompiler
from reproproof.core.patcher import PatchValidator, PatchValidationError
from reproproof.core.planner import ReproductionPlanner
from reproproof.core.limits import DEFAULT_LIMITS


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test.db"
    return str(db_file)


@pytest.fixture
def manifest():
    return AppManifest(
        app_id="inventory-demo",
        name="Inventory Demo",
        base_url="http://localhost:3000",
        start_command="node src/server.js",
        app_dir="apps/demo-app",
        allowed_source_paths=["src/"],
        protected_paths=["tests/", "package.json", "playwright.config.ts"],
    )


def test_state_machine_strict_transitions(temp_db):
    ctrl = RunController(db_path=temp_db)
    run = ctrl.create_run("inventory-demo", model_mode=ModelMode.MOCK_MODEL, report_text="r")
    assert run.status == RunStatus.RECEIVED

    # Legal: received -> reproducing
    ctrl.transition(run.run_id, RunStatus.REPRODUCING)
    assert ctrl.get_run(run.run_id).status == RunStatus.REPRODUCING

    # Illegal: reproducing -> passes_frozen_test (must go through awaiting approval & patching & verifying)
    with pytest.raises(StateTransitionError):
        ctrl.transition(run.run_id, RunStatus.PASSES_FROZEN_TEST)

    # Legal: reproducing -> awaiting_test_approval (after the reproduced test is stored)
    code = "test('repro', () => {});"
    ctrl.record_reproduction(run.run_id, test_code=code)
    ctrl.transition(run.run_id, RunStatus.AWAITING_TEST_APPROVAL)

    # Illegal: awaiting_test_approval -> verifying (must be approved and patched first)
    with pytest.raises(StateTransitionError):
        ctrl.transition(run.run_id, RunStatus.VERIFYING)

    # Legal: Human approval freezes test and moves to PATCHING
    sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
    ctrl.record_human_approval(run.run_id, test_sha256=sha, approved_by="alice")
    updated = ctrl.get_run(run.run_id)
    assert updated.status == RunStatus.PATCHING
    assert updated.test_sha256 == sha
    assert updated.approved_by == "alice"


def test_patch_validation_protected_files(manifest):
    validator = PatchValidator(manifest)

    # 1. Patch touching package.json must be REJECTED (Rule H-7)
    bad_diff_pkg = (
        "--- a/package.json\n"
        "+++ b/package.json\n"
        "@@ -1,3 +1,3 @@\n"
        "-  \"version\": \"1.0.0\"\n"
        "+  \"version\": \"1.0.1\"\n"
    )
    with pytest.raises(PatchValidationError, match="forbidden protected path"):
        validator.validate_patch(
            PatchProposal(explanation="Bump version", unified_diff=bad_diff_pkg)
        )

    # 2. Patch outside allowed_source_paths must be REJECTED
    bad_diff_outside = (
        "--- a/scripts/deploy.sh\n"
        "+++ b/scripts/deploy.sh\n"
        "@@ -1,2 +1,2 @@\n"
        "-echo hi\n"
        "+echo bye\n"
    )
    with pytest.raises(PatchValidationError, match="outside allowed source paths"):
        validator.validate_patch(
            PatchProposal(explanation="Edit script", unified_diff=bad_diff_outside)
        )

    # 3. Patch within src/ must be ACCEPTED
    good_diff = (
        "--- a/src/inventory.js\n"
        "+++ b/src/inventory.js\n"
        "@@ -1,2 +1,2 @@\n"
        "-items.splice(0, 1);\n"
        "+items = items.filter(i => i.id !== id);\n"
    )
    touched = validator.validate_patch(
        PatchProposal(explanation="Fix row deletion", unified_diff=good_diff)
    )
    assert "src/inventory.js" in touched


def test_compiler_code_generation():
    compiler = PlaywrightCompiler()
    plan = ActionPlan(
        expected_behavior="Widget B is deleted while Widget A remains visible.",
        steps=[
            {"action": "goto", "path": "/"},
            {"action": "click", "role": "button", "name": "Delete Widget B"},
        ],
        assertions=[
            {"action": "assert_text_visible", "text": "Widget A"},
            {"action": "assert_text_hidden", "text": "Widget B"},
        ],
    )

    code, sha256 = compiler.compile(plan, test_name="test-widget-deletion")
    assert "const PLAN = JSON.parse(" in code
    assert "test('test-widget-deletion'" in code
    assert "Widget B" in code
    assert "Widget A" in code
    assert len(sha256) == 64  # SHA-256 length


def test_failure_classification_honest_statuses():
    planner = ReproductionPlanner()

    # Intended assertion failure -> AWAITING_TEST_APPROVAL
    stdout_assertion = "Error: expect(received).toBeVisible()\nReceived: hidden"
    c_assert = planner.classify_test_result(1, stdout_assertion, "")
    assert c_assert.status == RunStatus.AWAITING_TEST_APPROVAL
    assert c_assert.is_intended_assertion is True

    # Server connection refused -> ENVIRONMENT_ERROR
    stdout_conn = "page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3000"
    c_env = planner.classify_test_result(1, stdout_conn, "")
    assert c_env.status == RunStatus.ENVIRONMENT_ERROR

    # Timeout / locator error -> NOT_REPRODUCED (Rule 6: Never count timeout as reproduced bug)
    stdout_timeout = "Timeout 30000ms exceeded while waiting for locator('button#missing')"
    c_timeout = planner.classify_test_result(1, stdout_timeout, "")
    assert c_timeout.status == RunStatus.NOT_REPRODUCED

    # Clean pass -> NOT_REPRODUCED
    c_pass = planner.classify_test_result(0, "1 passed (1.2s)", "")
    assert c_pass.status == RunStatus.NOT_REPRODUCED
