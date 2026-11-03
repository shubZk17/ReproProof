"""Adversarial tests: callers must not be able to manufacture approval or verification."""

import json

import pytest

from conftest import PATCH, TEST_CODE
from reproproof.core import controller as controller_mod
from reproproof.core.controller import HOST_EXECUTION_FLAG, RunController, StateTransitionError
from reproproof.core.model_adapter import MetaModelClient
from reproproof.core.schemas import ModelMode, PatchProposal, RegressionStatus, RunStatus
from reproproof.core.verifier import sha256_text
from reproproof.worker.runner import JobRunner

GOOD_SHA = sha256_text(TEST_CODE)


# --- no public success API -----------------------------------------------------------------

def test_no_caller_supplied_success_api():
    assert not hasattr(RunController, "record_verification_result")


def test_direct_transition_to_passes_frozen_test_rejected(ctrl, make_run):
    run = make_run("verifying")
    with pytest.raises(StateTransitionError, match="prohibited"):
        ctrl.transition(run.run_id, RunStatus.PASSES_FROZEN_TEST)
    with pytest.raises(TypeError):
        ctrl.transition(run.run_id, RunStatus.PASSES_FROZEN_TEST, _internal_evidence_verified=True)
    assert ctrl.get_run(run.run_id).status == RunStatus.VERIFYING


def test_create_run_requires_mode_and_report(ctrl):
    with pytest.raises(TypeError):
        ctrl.create_run("inventory-demo", report_text="x")
    with pytest.raises(ValueError):
        ctrl.create_run("inventory-demo", model_mode=ModelMode.MOCK_MODEL, report_text="  ")
    with pytest.raises(ValueError):
        ctrl.create_run("inventory-demo", model_mode="LIVE_MODEL", report_text="x")


# --- approval binding ----------------------------------------------------------------------

def test_approval_rejected_without_reproduced_test(ctrl):
    run = ctrl.create_run("inventory-demo", model_mode=ModelMode.MOCK_MODEL, report_text="r")
    ctrl.transition(run.run_id, RunStatus.REPRODUCING)
    ctrl.transition(run.run_id, RunStatus.AWAITING_TEST_APPROVAL)
    with pytest.raises(StateTransitionError, match="no reproduced test"):
        ctrl.record_human_approval(run.run_id, test_sha256=GOOD_SHA, frozen_test_code=TEST_CODE)


@pytest.mark.parametrize("bad", ["", "sha256_placeholder", "abc123sha", "0" * 63, GOOD_SHA.upper()])
def test_approval_rejects_placeholder_or_malformed_hash(ctrl, make_run, bad):
    run = make_run("awaiting")
    with pytest.raises(StateTransitionError, match="placeholder or malformed"):
        ctrl.record_human_approval(run.run_id, test_sha256=bad)


def test_approval_rejects_mutated_test(ctrl, make_run):
    run = make_run("awaiting")
    mutated = "test('mutated', () => {});"
    with pytest.raises(StateTransitionError, match="differs from the reproduced test"):
        ctrl.record_human_approval(run.run_id, test_sha256=sha256_text(mutated), frozen_test_code=mutated)
    # correct hash but different code
    with pytest.raises(StateTransitionError, match="differs from the reproduced test"):
        ctrl.record_human_approval(run.run_id, test_sha256=GOOD_SHA, frozen_test_code=mutated)
    assert ctrl.get_run(run.run_id).status == RunStatus.AWAITING_TEST_APPROVAL


def test_approval_rejects_tampered_stored_test(ctrl, make_run):
    run = make_run("awaiting")
    with ctrl._get_connection() as conn:
        conn.execute("UPDATE runs SET reproduced_test_code = 'evil' WHERE run_id = ?", (run.run_id,))
    with pytest.raises(StateTransitionError, match="does not match its stored hash"):
        ctrl.record_human_approval(run.run_id, test_sha256=GOOD_SHA)


def test_approval_requires_approver_and_is_single_use(ctrl, make_run):
    run = make_run("awaiting")
    with pytest.raises(StateTransitionError, match="approver"):
        ctrl.record_human_approval(run.run_id, test_sha256=GOOD_SHA, approved_by=" ")
    approved = ctrl.record_human_approval(run.run_id, test_sha256=GOOD_SHA, approved_by="alice")
    assert approved.status == RunStatus.PATCHING
    assert approved.frozen_test_code == TEST_CODE and approved.test_sha256 == GOOD_SHA
    with pytest.raises(StateTransitionError, match="Cannot approve"):
        ctrl.record_human_approval(run.run_id, test_sha256=GOOD_SHA)


def test_reproduction_and_patch_cannot_be_swapped_later(ctrl, make_run):
    run = make_run("awaiting")
    with pytest.raises(StateTransitionError):
        ctrl.record_reproduction(run.run_id, test_code="test('swap', () => {});")
    with pytest.raises(StateTransitionError):
        ctrl.record_patch(run.run_id, PatchProposal(explanation="x", unified_diff=PATCH))
    run2 = make_run("verifying")
    with pytest.raises(StateTransitionError):
        ctrl.record_patch(run2.run_id, PatchProposal(explanation="x", unified_diff=PATCH + " "))


# --- verification provenance ---------------------------------------------------------------

def test_run_verification_only_in_verifying(ctrl, make_run, fake_verifier):
    run = make_run("approved")
    with pytest.raises(StateTransitionError):
        ctrl.run_verification(run.run_id)
    assert fake_verifier["calls"] == []


def test_run_verification_rejects_tampered_frozen_test(ctrl, make_run, fake_verifier):
    run = make_run("verifying")
    with ctrl._get_connection() as conn:
        conn.execute("UPDATE runs SET frozen_test_code = 'test(\"x\", () => {});' WHERE run_id = ?", (run.run_id,))
    with pytest.raises(StateTransitionError, match="does not match its approved hash"):
        ctrl.run_verification(run.run_id)
    assert fake_verifier["calls"] == []


def test_genuine_result_reaches_passes_frozen_test(ctrl, make_run, fake_verifier):
    run = make_run("verifying")
    final = ctrl.run_verification(run.run_id)
    assert final.status == RunStatus.PASSES_FROZEN_TEST
    ev = json.loads(final.verification_evidence)
    assert ev["run_id"] == run.run_id and ev["patch_diff_sha256"] == sha256_text(PATCH)
    assert ev["source_revision"] == final.source_revision


@pytest.mark.parametrize("forged", [
    {"run_id": "some-other-run"},
    {"test_sha256": "f" * 64},
    {"patch_diff_sha256": "e" * 64},
    {"source_revision": "tree-sha256:different-app"},
    {"source_revision": None},
])
def test_forged_or_foreign_evidence_rejected(ctrl, make_run, fake_verifier, forged):
    run = make_run("verifying")
    fake_verifier["override"] = forged
    final = ctrl.run_verification(run.run_id)
    assert final.status != RunStatus.PASSES_FROZEN_TEST


def test_verifier_crash_is_error_not_success(ctrl, make_run, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("chromium exploded")
    monkeypatch.setattr(controller_mod.FreshCopyVerifier, "verify_patch", boom)
    run = make_run("verifying")
    final = ctrl.run_verification(run.run_id)
    assert final.status == RunStatus.PATCHING  # attempt 1 of 2
    ev = json.loads(final.verification_evidence)
    assert ev["frozen_test_status"] == "ERROR" and ev["regression_status"] == "NOT_RUN"


# --- execution boundary --------------------------------------------------------------------

def test_live_model_patch_not_executed_on_host_by_default(ctrl, make_run, fake_verifier, monkeypatch):
    monkeypatch.delenv(HOST_EXECUTION_FLAG, raising=False)
    run = make_run("verifying", mode=ModelMode.LIVE_MODEL)
    final = ctrl.run_verification(run.run_id)
    assert fake_verifier["calls"] == []
    assert final.status == RunStatus.UNRESOLVED
    assert final.regression_status == RegressionStatus.NOT_RUN
    assert "NOT executed" in final.status_reason


def test_live_model_patch_executes_only_with_explicit_opt_in(ctrl, make_run, fake_verifier, monkeypatch):
    monkeypatch.setenv(HOST_EXECUTION_FLAG, "1")
    run = make_run("verifying", mode=ModelMode.LIVE_MODEL)
    assert ctrl.run_verification(run.run_id).status == RunStatus.PASSES_FROZEN_TEST
    assert fake_verifier["calls"] == [run.run_id]


def test_runner_refuses_mode_mismatch(ctrl, make_run):
    run = make_run("received", mode=ModelMode.LIVE_MODEL)
    runner = JobRunner(controller=ctrl, model_client=MetaModelClient(mock_mode=True))
    with pytest.raises(RuntimeError, match="refusing"):
        runner.run_reproduction_job(run.run_id)
