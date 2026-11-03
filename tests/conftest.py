"""Shared fixtures: drive runs through the genuine controller API (no DB writes, no bypasses)."""

import pytest

from reproproof.core import controller as controller_mod
from reproproof.core.controller import RunController
from reproproof.core.schemas import ActionPlan, ModelMode, PatchProposal, RegressionStatus, RunStatus
from reproproof.core.verifier import VerificationResult, resolve_app_dir, sha256_text, tree_sha256

TEST_CODE = "test('genuine repro', async () => {});"
PATCH = "--- a/src/inventory.js\n+++ b/src/inventory.js\n@@ -1,1 +1,1 @@\n-old\n+new\n"


@pytest.fixture
def ctrl(tmp_path):
    return RunController(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def make_run(ctrl):
    """Creates a run and advances it to `stage` (received|awaiting|approved|verifying) legitimately."""
    def _make(stage="verifying", mode=ModelMode.MOCK_MODEL, code=TEST_CODE, patch=PATCH, screenshot=None):
        run = ctrl.create_run("inventory-demo", model_mode=mode, report_text="Actual user defect report")
        if stage == "received":
            return run
        ctrl.record_plan(run.run_id, ActionPlan(expected_behavior="Widget B is deleted, Widget A remains.",
                                                steps=[{"action": "goto", "path": "/"}],
                                                assertions=[{"action": "assert_text_visible", "text": "Widget A"}]))
        ctrl.transition(run.run_id, RunStatus.REPRODUCING)
        ctrl.record_reproduction(run.run_id, test_code=code, screenshot_path=screenshot,
                                 screenshot_timestamp="2026-11-03T00:00:00+00:00", logs="repro log")
        ctrl.transition(run.run_id, RunStatus.AWAITING_TEST_APPROVAL)
        if stage == "awaiting":
            return run
        ctrl.record_human_approval(run.run_id, test_sha256=sha256_text(code), approved_by="auditor")
        if stage == "approved":
            return run
        ctrl.record_patch_attempt(run.run_id)
        ctrl.record_patch(run.run_id, PatchProposal(explanation="x", unified_diff=patch))
        ctrl.transition(run.run_id, RunStatus.VERIFYING)
        return run
    return _make


@pytest.fixture
def fake_verifier(monkeypatch):
    """Replaces browser execution with a scripted outcome that has honest provenance.

    Set state["frozen"] / state["reg"] for the outcome, state["override"] to forge fields.
    Used only for controller-logic tests; real execution is covered in test_e2e_workflow.py.
    """
    state = {"frozen": RegressionStatus.PASSED, "reg": RegressionStatus.PASSED, "override": {}, "calls": []}

    def verify_patch(self, app_source_dir, patch_proposal, frozen_test_code, expected_test_sha256, run_id, port=None):
        state["calls"].append(run_id)
        kw = dict(
            run_id=run_id,
            test_sha256=sha256_text(frozen_test_code),
            patch_diff_sha256=sha256_text(patch_proposal.unified_diff),
            frozen_test_status=state["frozen"],
            regression_status=state["reg"],
            details="scripted outcome",
            source_revision=tree_sha256(resolve_app_dir(app_source_dir)),
            patched_revision="tree-sha256:patched",
            patch_output="Patch applied cleanly via git apply.",
        )
        kw.update(state["override"])
        return VerificationResult(**kw)

    monkeypatch.setattr(controller_mod.FreshCopyVerifier, "verify_patch", verify_patch)
    return state
