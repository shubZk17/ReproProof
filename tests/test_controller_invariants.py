"""Unit tests verifying Controller-Owned State Invariants and Evidence Gates."""

import hashlib
import pytest
from reproproof.core.controller import RunController, StateTransitionError
from reproproof.core.schemas import ActionPlan, PatchProposal, RunStatus


@pytest.fixture
def temp_ctrl(tmp_path):
    db_file = tmp_path / "test_ctrl.db"
    return RunController(db_path=str(db_file))


def test_direct_transition_to_passes_frozen_test_rejected(temp_ctrl):
    run = temp_ctrl.create_run(app_id="inventory-demo")
    temp_ctrl.transition(run.run_id, RunStatus.REPRODUCING)
    temp_ctrl.transition(run.run_id, RunStatus.AWAITING_TEST_APPROVAL)
    temp_ctrl.record_human_approval(run.run_id, test_sha256="abc123sha")
    temp_ctrl.transition(run.run_id, RunStatus.VERIFYING)

    # Calling transition to PASSES_FROZEN_TEST directly must be REJECTED
    with pytest.raises(StateTransitionError, match="Direct transition to passes_frozen_test is prohibited"):
        temp_ctrl.transition(run.run_id, RunStatus.PASSES_FROZEN_TEST)


def test_approval_hash_integrity(temp_ctrl):
    run = temp_ctrl.create_run(app_id="inventory-demo")
    temp_ctrl.transition(run.run_id, RunStatus.REPRODUCING)
    temp_ctrl.transition(run.run_id, RunStatus.AWAITING_TEST_APPROVAL)

    code = "test('hello', () => {});"
    actual_sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
    fake_sha = "0000000000000000000000000000000000000000000000000000000000000000"

    # Mismatched hash rejected
    with pytest.raises(StateTransitionError, match="Test hash mismatch on approval"):
        temp_ctrl.record_human_approval(run.run_id, test_sha256=fake_sha, frozen_test_code=code)

    # Correct hash accepted
    temp_ctrl.record_human_approval(run.run_id, test_sha256=actual_sha, frozen_test_code=code)
    run_after = temp_ctrl.get_run(run.run_id)
    assert run_after.status == RunStatus.PATCHING
    assert run_after.test_sha256 == actual_sha
    assert run_after.frozen_test_code == code


def test_duplicate_approval_rejected(temp_ctrl):
    run = temp_ctrl.create_run(app_id="inventory-demo")
    temp_ctrl.transition(run.run_id, RunStatus.REPRODUCING)
    temp_ctrl.transition(run.run_id, RunStatus.AWAITING_TEST_APPROVAL)
    temp_ctrl.record_human_approval(run.run_id, test_sha256="abc123sha")

    # Duplicate approval call must raise error
    with pytest.raises(StateTransitionError, match="Cannot approve test in state 'patching'"):
        temp_ctrl.record_human_approval(run.run_id, test_sha256="abc123sha")


def test_verification_result_enforcement(temp_ctrl):
    run = temp_ctrl.create_run(app_id="inventory-demo")
    temp_ctrl.transition(run.run_id, RunStatus.REPRODUCING)
    temp_ctrl.transition(run.run_id, RunStatus.AWAITING_TEST_APPROVAL)
    temp_ctrl.record_human_approval(run.run_id, test_sha256="expected_sha_123")
    temp_ctrl.transition(run.run_id, RunStatus.VERIFYING)

    # Hash mismatch during verification must be rejected
    with pytest.raises(StateTransitionError, match="Verification test hash .* does not match frozen test hash"):
        temp_ctrl.record_verification_result(
            run_id=run.run_id,
            passed_frozen_test=True,
            passed_regression=True,
            actual_test_sha256="different_sha",
            details="Mismatch",
        )

    # Valid evidence transitions to PASSES_FROZEN_TEST
    updated = temp_ctrl.record_verification_result(
        run_id=run.run_id,
        passed_frozen_test=True,
        passed_regression=True,
        actual_test_sha256="expected_sha_123",
        details="Clean run passed",
    )
    assert updated.status == RunStatus.PASSES_FROZEN_TEST
    assert "Clean run passed" in updated.verification_evidence
