"""Evidence bundles come only from stored run artifacts; corrupt or missing artifacts
must never be presented as valid evidence."""

import json
import zipfile

import pytest

from conftest import PATCH, TEST_CODE
from reproproof.core.evidence import EvidenceExporter
from reproproof.core.schemas import ModelMode, RegressionStatus, RunStatus


@pytest.fixture
def exporter(ctrl, tmp_path):
    return EvidenceExporter(export_dir=str(tmp_path / "exports"), controller=ctrl)


@pytest.fixture
def passed_run(ctrl, make_run, fake_verifier, tmp_path):
    shot = tmp_path / "repro.png"
    shot.write_bytes(b"PNG-REPRODUCTION")
    run = make_run("verifying", screenshot=str(shot))
    assert ctrl.run_verification(run.run_id).status == RunStatus.PASSES_FROZEN_TEST
    return run, shot


def _sql(ctrl, sql, *args):
    with ctrl._get_connection() as conn:
        conn.execute(sql, args)


def test_bundle_is_built_from_run_record(ctrl, exporter, passed_run):
    run, _ = passed_run
    b = exporter.create_bundle_from_run(run.run_id)
    assert b.evidence_valid, b.integrity_failures
    assert b.report_text == "Actual user defect report"
    assert b.frozen_test_code == TEST_CODE and b.patch_diff == PATCH
    assert b.model_mode == ModelMode.MOCK_MODEL and "no AI model" in b.model_mode_disclosure
    assert b.check_results["frozen_test"] == "PASSED" and b.check_results["regression_suite"] == "PASSED"
    assert b.human_approval["approved_by"] == "auditor"
    assert b.patch_application_output == "Patch applied cleanly via git apply."
    assert b.reproduction_logs == "repro log"
    assert b.source_revision and b.source_revision == b.verification_evidence["source_revision"]
    assert b.artifacts_integrity["reproduction_screenshot"] == "VALID" and b.before_screenshot_b64

    with zipfile.ZipFile(exporter.export_zip(b)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert zf.read("patch.diff").decode() == PATCH
        assert zf.read("screenshot_reproduction.png") == b"PNG-REPRODUCTION"
        assert set(manifest["file_sha256"]) == set(zf.namelist()) - {"manifest.json"}
        assert manifest["evidence_valid"] is True


@pytest.mark.parametrize("sql,needle", [
    ("UPDATE runs SET frozen_test_code = 'tampered' WHERE run_id = ?", "frozen_test"),
    ("UPDATE runs SET patch_diff = '--- a/x\n+++ b/x\n' WHERE run_id = ?", "patch"),
    ("UPDATE runs SET verification_evidence = '{not json' WHERE run_id = ?", "verification_evidence"),
    ("UPDATE runs SET verification_evidence = NULL WHERE run_id = ?", "verification_evidence"),
    ("UPDATE runs SET verification_evidence = replace(verification_evidence, run_id, 'other-run') WHERE run_id = ?",
     "verification_evidence"),
    ("UPDATE runs SET regression_status = 'FAILED' WHERE run_id = ?", "verification_evidence"),
    ("UPDATE runs SET approved_by = NULL WHERE run_id = ?", "approval"),
])
def test_tampered_artifacts_invalidate_bundle(ctrl, exporter, passed_run, sql, needle):
    run, _ = passed_run
    _sql(ctrl, sql, run.run_id)
    b = exporter.create_bundle_from_run(run.run_id)
    assert not b.evidence_valid
    assert any(f.startswith(needle) for f in b.integrity_failures), b.integrity_failures
    assert b.check_results["frozen_test"] != "PASSED"


def test_success_status_without_passed_evidence_is_invalid(ctrl, exporter, make_run, fake_verifier):
    run = make_run("verifying")
    fake_verifier["reg"] = RegressionStatus.FAILED
    ctrl.run_verification(run.run_id)
    _sql(ctrl, "UPDATE runs SET status = 'passes_frozen_test' WHERE run_id = ?", run.run_id)  # forged
    b = exporter.create_bundle_from_run(run.run_id)
    assert not b.evidence_valid
    assert b.check_results["regression_suite"] == "INVALID_EVIDENCE"


def test_tampered_or_missing_screenshot_not_embedded(ctrl, exporter, passed_run):
    run, shot = passed_run
    shot.write_bytes(b"PNG-SWAPPED")
    b = exporter.create_bundle_from_run(run.run_id)
    assert b.artifacts_integrity["reproduction_screenshot"].startswith("FAILED")
    assert b.before_screenshot_b64 is None and not b.evidence_valid
    shot.unlink()
    b = exporter.create_bundle_from_run(run.run_id)
    assert b.artifacts_integrity["reproduction_screenshot"].startswith("MISSING")
    assert b.before_screenshot_b64 is None


def test_fresh_run_reports_not_run(exporter, make_run):
    run = make_run("received")
    b = exporter.create_bundle_from_run(run.run_id)
    assert b.expected_behavior == "MISSING"
    assert b.artifacts_integrity["plan"] == "MISSING"
    assert b.artifacts_integrity["patch"] == "NOT_RUN"
    assert b.check_results["frozen_test"] == "NOT_RUN"
    assert b.check_results["regression_suite"] == "NOT_RUN"
    assert b.final_status == RunStatus.RECEIVED


def test_no_caller_supplied_bundle_api():
    assert not hasattr(EvidenceExporter, "create_bundle")
