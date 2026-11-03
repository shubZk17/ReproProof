"""Regression result semantics: only an executed, successful suite is PASSED, and only
frozen PASSED + regression PASSED reaches passes_frozen_test. Real-browser variants of
these cases live in test_e2e_workflow.py."""

import json

import pytest

from reproproof.core.schemas import RegressionStatus as R
from reproproof.core.schemas import RunStatus


@pytest.mark.parametrize("frozen,reg,expected_status", [
    (R.PASSED, R.PASSED, RunStatus.PASSES_FROZEN_TEST),
    (R.PASSED, R.FAILED, RunStatus.PATCHING),
    (R.FAILED, R.NOT_RUN, RunStatus.PATCHING),     # frozen failed -> regression skipped
    (R.PASSED, R.ERROR, RunStatus.PATCHING),
    (R.PASSED, R.NOT_RUN, RunStatus.PATCHING),     # missing regression configuration
    (R.ERROR, R.NOT_RUN, RunStatus.PATCHING),
])
def test_regression_status_mapping(ctrl, make_run, fake_verifier, frozen, reg, expected_status):
    run = make_run("verifying")
    fake_verifier["frozen"], fake_verifier["reg"] = frozen, reg
    final = ctrl.run_verification(run.run_id)
    assert final.status == expected_status
    assert final.regression_status == reg
    ev = json.loads(final.verification_evidence)
    assert ev["regression_status"] == reg.value and ev["frozen_test_status"] == frozen.value


def test_second_failure_is_terminal_unresolved(ctrl, make_run, fake_verifier):
    from reproproof.core.schemas import PatchProposal
    from conftest import PATCH
    run = make_run("verifying")
    fake_verifier["reg"] = R.FAILED
    assert ctrl.run_verification(run.run_id).status == RunStatus.PATCHING
    ctrl.record_patch_attempt(run.run_id)
    ctrl.record_patch(run.run_id, PatchProposal(explanation="x", unified_diff=PATCH))
    ctrl.transition(run.run_id, RunStatus.VERIFYING)
    final = ctrl.run_verification(run.run_id)
    assert final.status == RunStatus.UNRESOLVED
    assert final.regression_status == R.FAILED
