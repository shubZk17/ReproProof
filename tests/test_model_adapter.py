"""Unit tests for MetaModelClient and schemas."""

import pytest
from reproproof.core.schemas import ActionPlan, PatchProposal, RunStatus, VALID_TRANSITIONS
from reproproof.core.model_adapter import MOCK_PLAN_ID, MOCK_SCRIPTED_REPORT, MetaModelClient


def test_schemas_strictness():
    # Valid plan
    plan = ActionPlan(
        expected_behavior="Item A remains visible after deletion of Item B.",
        steps=[{"action": "goto", "path": "/"}],
        assertions=[{"action": "assert_text_visible", "text": "Item A"}],
    )
    assert plan.expected_behavior.startswith("Item A")

    # Extra fields must be forbidden
    with pytest.raises(Exception):
        ActionPlan(
            expected_behavior="Item A remains visible",
            steps=[],
            assertions=[],
            unexpected_field="hack",
        )


def test_valid_transitions_rule():
    # Never use 'verified' as a status
    assert "verified" not in [s.value for s in RunStatus]
    assert RunStatus.PASSES_FROZEN_TEST.value == "passes_frozen_test"

    # From Awaiting approval can only go to test_rejected, patching, budget_exceeded
    allowed = VALID_TRANSITIONS[RunStatus.AWAITING_TEST_APPROVAL]
    assert set(allowed) == {
        RunStatus.TEST_REJECTED,
        RunStatus.PATCHING,
        RunStatus.BUDGET_EXCEEDED,
    }


def test_meta_model_client_mock():
    client = MetaModelClient(mock_mode=True)
    assert client.is_mock is True

    # Escalation check
    assert client.get_model_for_attempt(1) == "muse-spark-1.3"
    assert client.get_model_for_attempt(2) == "muse-wonder-1.0"

    # Mock is not an AI model: an unscripted report is refused, not "analysed"
    plan, model_id, in_t, out_t = client.plan_reproduction("Delete button deletes wrong item", routes=["/"])
    assert plan.clarification_question and "not analysed" in plan.clarification_question
    assert not plan.steps and model_id == MOCK_PLAN_ID and in_t == out_t == 0

    plan, model_id, _, _ = client.plan_reproduction(MOCK_SCRIPTED_REPORT, routes=["/"])
    assert isinstance(plan, ActionPlan) and plan.steps and plan.clarification_question is None
    assert model_id == MOCK_PLAN_ID

    patch, model_id_p, in_tp, out_tp = client.propose_patch(
        attempt=1,
        report_text="Bug report",
        failing_test_code="test()",
        failing_assertion="assert_text_hidden",
        source_files={"src/app.js": "function() {}"},
    )
    assert isinstance(patch, PatchProposal)
    assert len(patch.target_files) == 1
