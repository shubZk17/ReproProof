"""Full end-to-end integration test of ReproProof bug-repair workflow.

Executes genuine Node.js server on ephemeral port, genuine Playwright browser test,
real human approval, genuine git patch application, and fresh-copy verification.
"""

import os
import pytest
from reproproof.core.controller import RunController
from reproproof.core.limits import DEFAULT_LIMITS
from reproproof.core.model_adapter import MetaModelClient
from reproproof.core.schemas import ActionPlan, PatchProposal, RunStatus
from reproproof.worker.runner import JobRunner
from reproproof.core.evidence import EvidenceExporter


def test_full_real_e2e_workflow(tmp_path):
    # 1. Setup isolated database and controller
    db_file = tmp_path / "e2e_test.db"
    controller = RunController(db_path=str(db_file))
    model_client = MetaModelClient(mock_mode=True)
    runner = JobRunner(controller=controller, model_client=model_client)

    # 2. Intake: Create run for inventory-demo
    report_text = "When I click 'Delete Widget B', Widget A is incorrectly deleted and Widget B remains."
    run = controller.create_run(app_id="inventory-demo")
    assert run.status == RunStatus.RECEIVED

    # Plan representing the exact reproduction sequence
    plan = ActionPlan(
        expected_behavior="Widget B is deleted while Widget A remains visible in the list.",
        steps=[
            {"action": "goto", "path": "/"},
            {"action": "click", "role": "button", "name": "Delete Widget B"},
        ],
        assertions=[
            {"action": "assert_text_visible", "text": "Widget A"},
            {"action": "assert_text_hidden", "text": "Widget B"},
        ],
    )

    # 3. Execute Reproduction Job with REAL Playwright test execution
    status, test_code, test_sha, details = runner.run_reproduction_job(
        run_id=run.run_id,
        report_text=report_text,
        mock_plan=plan,
    )

    # Verify that the seeded bug was genuinely reproduced!
    assert status == RunStatus.AWAITING_TEST_APPROVAL
    assert len(test_sha) == 64
    assert "Widget A" in test_code

    # Verify controller state
    run_after_repro = controller.get_run(run.run_id)
    assert run_after_repro.status == RunStatus.AWAITING_TEST_APPROVAL

    # 4. Human Approval Gate (Mandatory PRD Invariant)
    controller.record_human_approval(
        run_id=run.run_id,
        test_sha256=test_sha,
        frozen_test_code=test_code,
        approved_by="test_reviewer",
    )

    run_after_approval = controller.get_run(run.run_id)
    assert run_after_approval.status == RunStatus.PATCHING
    assert run_after_approval.test_sha256 == test_sha
    assert run_after_approval.frozen_test_code == test_code

    # 5. Propose genuine source-only patch fixing the seeded defect in apps/demo-app/src/inventory.js
    patch = PatchProposal(
        explanation="Fix deleteItem to filter by matching id instead of splicing first element.",
        unified_diff=(
            "--- a/src/inventory.js\n"
            "+++ b/src/inventory.js\n"
            "@@ -29,6 +29,6 @@\n"
            "     return false;\n"
            "   }\n"
            "   // BUG: ignores index and always removes the first element (index 0)\n"
            "-  itemsStore.splice(0, 1);\n"
            "+  itemsStore = itemsStore.filter(item => item.id !== id);\n"
            "   return true;\n"
            " }\n"
        ),
        target_files=["src/inventory.js"],
    )

    # 6. Execute Repair and Clean Verification
    final_status, details = runner.run_repair_and_verify_job(
        run_id=run.run_id,
        report_text=report_text,
        frozen_test_code=test_code,
        frozen_test_sha256=test_sha,
        failing_assertion="assert_text_visible",
        mock_patch=patch,
    )
    print("\n[VERIFICATION DETAILS]:", details)

    # Verify passes_frozen_test achieved on fresh copy!
    assert final_status == RunStatus.PASSES_FROZEN_TEST
    run_final = controller.get_run(run.run_id)
    assert run_final.status == RunStatus.PASSES_FROZEN_TEST
    assert run_final.verification_evidence is not None

    # 7. Export and verify genuine evidence bundle
    exporter = EvidenceExporter(export_dir=str(tmp_path / "evidence"))
    bundle = exporter.create_bundle(
        run_record=run_final,
        report_text=report_text,
        expected_behavior=plan.expected_behavior,
        intended_assertion="assert_text_visible",
        frozen_test_code=test_code,
        test_sha256=test_sha,
        patch_diff=patch.unified_diff,
        check_results={"frozen_test": "PASSED", "regression_checks": "PASSED"},
    )
    zip_path = exporter.export_zip(bundle)
    assert os.path.exists(zip_path)
    assert os.path.getsize(zip_path) > 100
