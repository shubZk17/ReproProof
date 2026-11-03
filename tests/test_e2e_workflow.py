"""Real end-to-end tests: real Node server on an ephemeral port, real Chromium via Playwright,
real git apply on a fresh copy, real protected regression suite. MOCK_MODEL supplies the
hand-written plan/patch only; nothing about execution is mocked here."""

import json
import os
import zipfile

import pytest

from reproproof.core.compiler import PlaywrightCompiler
from reproproof.core.controller import RunController
from reproproof.core.evidence import EvidenceExporter
from reproproof.core.limits import RunLimits
from reproproof.core.model_adapter import MOCK_SCRIPTED_REPORT, MetaModelClient
from reproproof.core.planner import load_manifest
from reproproof.core.schemas import ModelMode, PatchProposal, RegressionStatus, RunStatus
from reproproof.core.verifier import FreshCopyVerifier, sha256_file, sha256_text
from reproproof.worker.runner import JobRunner

NON_FIXING_PATCH = (
    "--- a/src/inventory.js\n+++ b/src/inventory.js\n@@ -29,6 +29,6 @@\n"
    "     return false;\n   }\n"
    "-  // BUG: ignores index and always removes the first element (index 0)\n"
    "+  // comment changed, behaviour unchanged\n"
    "   itemsStore.splice(0, 1);\n   return true;\n }\n"
)
FIX_BUT_BREAK_ADD_PATCH = (
    "--- a/src/inventory.js\n+++ b/src/inventory.js\n@@ -18,7 +18,7 @@\n"
    "     name,\n     count: parseInt(count, 10) || 1,\n   };\n"
    "-  itemsStore.push(newItem);\n+  // regression: new items are never stored\n"
    "   return newItem;\n }\n \n"
    "@@ -29,6 +29,6 @@\n     return false;\n   }\n"
    "   // BUG: ignores index and always removes the first element (index 0)\n"
    "-  itemsStore.splice(0, 1);\n+  itemsStore = itemsStore.filter(item => item.id !== id);\n"
    "   return true;\n }\n"
)


def _runner(tmp_path, attempts=2):
    limits = RunLimits(max_patch_attempts=attempts)
    ctrl = RunController(db_path=str(tmp_path / "e2e.db"), limits=limits)
    return ctrl, JobRunner(controller=ctrl, model_client=MetaModelClient(mock_mode=True), limits=limits)


def _reproduce_and_approve(ctrl, runner):
    run = ctrl.create_run("inventory-demo", model_mode=ModelMode.MOCK_MODEL, report_text=MOCK_SCRIPTED_REPORT)
    status, test_code, test_sha, _ = runner.run_reproduction_job(run.run_id)
    assert status == RunStatus.AWAITING_TEST_APPROVAL
    ctrl.record_human_approval(run.run_id, test_sha256=test_sha, frozen_test_code=test_code, approved_by="reviewer")
    return run.run_id


def test_full_real_e2e_workflow(tmp_path):
    ctrl, runner = _runner(tmp_path)
    run_id = _reproduce_and_approve(ctrl, runner)

    repro = ctrl.get_run(run_id)
    assert repro.reproduction_screenshot_path and os.path.exists(repro.reproduction_screenshot_path)
    before_sha = sha256_file(repro.reproduction_screenshot_path)
    assert before_sha == repro.reproduction_screenshot_sha256
    assert repro.source_revision.startswith("tree-sha256:")

    final_status, _ = runner.run_repair_and_verify_job(run_id)  # hand-written mock patch
    assert final_status == RunStatus.PASSES_FROZEN_TEST
    final = ctrl.get_run(run_id)
    assert final.regression_status == RegressionStatus.PASSED
    assert final.patched_revision and final.patched_revision != final.source_revision

    # Screenshot preservation: reproduction capture untouched; verification capture is separate.
    assert sha256_file(final.reproduction_screenshot_path) == before_sha
    assert final.verification_screenshot_path != final.reproduction_screenshot_path
    assert sha256_file(final.verification_screenshot_path) == final.verification_screenshot_sha256
    assert final.verification_screenshot_timestamp > final.reproduction_screenshot_timestamp

    bundle = EvidenceExporter(export_dir=str(tmp_path / "ev"), controller=ctrl).create_bundle_from_run(run_id)
    assert bundle.evidence_valid, bundle.integrity_failures
    assert bundle.check_results["frozen_test"] == "PASSED" and bundle.check_results["regression_suite"] == "PASSED"
    assert bundle.verification_evidence["patch_diff_sha256"] == sha256_text(final.patch_diff)
    assert bundle.before_screenshot_b64 and bundle.after_screenshot_b64
    with zipfile.ZipFile(EvidenceExporter(export_dir=str(tmp_path / "ev")).export_zip(bundle)) as zf:
        assert zf.read("patch.diff").decode() == final.patch_diff
        assert json.loads(zf.read("manifest.json"))["model_mode"] == "MOCK_MODEL"


def test_failed_patch_cannot_succeed_and_regression_is_not_run(tmp_path):
    ctrl, runner = _runner(tmp_path, attempts=1)
    run_id = _reproduce_and_approve(ctrl, runner)
    status, _ = runner.run_repair_and_verify_job(
        run_id, mock_patch=PatchProposal(explanation="no-op", unified_diff=NON_FIXING_PATCH))
    final = ctrl.get_run(run_id)
    assert status == RunStatus.UNRESOLVED and final.status == RunStatus.UNRESOLVED
    assert final.regression_status == RegressionStatus.NOT_RUN
    ev = json.loads(final.verification_evidence)
    assert ev["frozen_test_status"] == "FAILED" and ev["regression_status"] == "NOT_RUN"
    bundle = EvidenceExporter(export_dir=str(tmp_path / "ev"), controller=ctrl).create_bundle_from_run(run_id)
    assert bundle.check_results["frozen_test"] == "FAILED"
    assert bundle.check_results["regression_suite"] == "NOT_RUN"


def test_regression_failure_blocks_success(tmp_path):
    ctrl, runner = _runner(tmp_path, attempts=1)
    run_id = _reproduce_and_approve(ctrl, runner)
    status, _ = runner.run_repair_and_verify_job(
        run_id, mock_patch=PatchProposal(explanation="fix+break", unified_diff=FIX_BUT_BREAK_ADD_PATCH))
    final = ctrl.get_run(run_id)
    assert status == RunStatus.UNRESOLVED
    ev = json.loads(final.verification_evidence)
    assert ev["frozen_test_status"] == "PASSED"
    assert final.regression_status == RegressionStatus.FAILED


def test_missing_regression_configuration_is_not_run(tmp_path):
    manifest = load_manifest("inventory-demo").model_copy(update={"regression_command": None})
    plan, *_ = MetaModelClient(mock_mode=True).plan_reproduction(MOCK_SCRIPTED_REPORT, routes=["/"])
    code, sha = PlaywrightCompiler().compile(plan, screenshot_path=str(tmp_path / "cap.png"))
    patch = MetaModelClient(mock_mode=True).propose_patch(1, "", "", "", {})[0]
    res = FreshCopyVerifier(manifest).verify_patch(manifest.app_dir, patch, code, sha, run_id="unit")
    assert res.frozen_test_status == RegressionStatus.PASSED
    assert res.regression_status == RegressionStatus.NOT_RUN
    assert "not configured" in res.details


def test_unsupported_report_in_mock_mode_is_refused(tmp_path):
    ctrl, runner = _runner(tmp_path)
    run = ctrl.create_run("inventory-demo", model_mode=ModelMode.MOCK_MODEL,
                          report_text="CSV export is missing the price column.")
    status, test_code, _, reason = runner.run_reproduction_job(run.run_id)
    assert status == RunStatus.CLARIFICATION_REQUIRED and test_code == ""
    assert "MOCK_MODEL" in reason and "not analysed" in reason
