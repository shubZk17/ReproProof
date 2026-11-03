"""Evidence Bundle Exporter (R9 & R15).

Builds bundles ONLY from the controller-owned run record and on-disk artifacts referenced by
it. Every artifact is re-hashed and cross-checked; anything missing, corrupt or inconsistent
is reported as MISSING / CORRUPTED / FAILED and makes the bundle `evidence_valid = False`.
There is deliberately no API that accepts caller-supplied results.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from reproproof.core.schemas import EvidenceBundle, ModelMode, RunStatus

_POST_APPROVAL = {RunStatus.PATCHING, RunStatus.VERIFYING, RunStatus.PASSES_FROZEN_TEST, RunStatus.UNRESOLVED}

MODE_DISCLOSURE = {
    ModelMode.MOCK_MODEL: ("MOCK_MODEL: no AI model was called. The reproduction plan and patch are "
                           "hand-written templates (reproproof/core/model_adapter.py) or were supplied by the "
                           "caller. Browser execution, git apply and verification were real."),
    ModelMode.LIVE_MODEL: "LIVE_MODEL: plan and patch were proposed by the configured remote model.",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class EvidenceExporter:
    """Exports evidence bundles derived from controller run records."""

    def __init__(self, export_dir: str = "runs", controller: Optional[Any] = None):
        self.export_dir = export_dir
        self.controller = controller
        os.makedirs(export_dir, exist_ok=True)

    @staticmethod
    def _load_screenshot(path: Optional[str], stored_sha: Optional[str]) -> Tuple[str, Optional[str]]:
        if not path:
            return "NOT_RUN", None
        if not os.path.isfile(path):
            return "MISSING: file not found", None
        with open(path, "rb") as f:
            data = f.read()
        if not stored_sha:
            return "FAILED: no stored hash to check against", None
        if _sha(data) != stored_sha:
            return f"FAILED: SHA-256 mismatch (stored={stored_sha}, actual={_sha(data)})", None
        return "VALID", base64.b64encode(data).decode("ascii")

    def create_bundle_from_run(self, run_id: str, controller: Optional[Any] = None) -> EvidenceBundle:
        ctrl = controller or self.controller
        if not ctrl:
            raise ValueError("RunController instance required to build evidence bundle from run.")
        run = ctrl.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found in controller store.")

        integ: Dict[str, str] = {}
        claims_success = run.status == RunStatus.PASSES_FROZEN_TEST
        approved = run.approved_at is not None

        # Plan
        expected_behavior = intended_assertion = "MISSING"
        if run.plan_json:
            try:
                plan = json.loads(run.plan_json)
                expected_behavior = plan.get("expected_behavior") or "MISSING"
                assertions = plan.get("assertions") or []
                intended_assertion = assertions[0].get("action", "MISSING") if assertions else "NONE"
                integ["plan"] = "VALID"
            except (ValueError, AttributeError, TypeError):
                expected_behavior = intended_assertion = "CORRUPTED"
                integ["plan"] = "CORRUPTED"
        else:
            integ["plan"] = "MISSING"

        # Reproduced test (what actually ran during reproduction)
        if run.reproduced_test_code and run.reproduced_test_sha256:
            ok = _sha(run.reproduced_test_code.encode("utf-8")) == run.reproduced_test_sha256
            integ["reproduced_test"] = "VALID" if ok else "FAILED: SHA-256 mismatch"
        else:
            integ["reproduced_test"] = "MISSING" if run.status not in (RunStatus.RECEIVED, RunStatus.CLARIFICATION_REQUIRED) else "NOT_RUN"

        # Frozen test + approval
        frozen_code, test_sha = run.frozen_test_code or "", run.test_sha256 or ""
        if frozen_code and test_sha:
            actual = _sha(frozen_code.encode("utf-8"))
            if actual != test_sha:
                integ["frozen_test"] = f"FAILED: SHA-256 mismatch (stored={test_sha}, actual={actual})"
            elif test_sha != run.reproduced_test_sha256:
                integ["frozen_test"] = "FAILED: frozen test is not the reproduced test"
            else:
                integ["frozen_test"] = "VALID"
        elif approved or run.status in _POST_APPROVAL:
            integ["frozen_test"] = "MISSING: test code absent" if not frozen_code else "MISSING: test hash absent"
        else:
            integ["frozen_test"] = "NOT_RUN"

        human_approval = None
        if approved:
            human_approval = {"approved_by": run.approved_by, "approved_at": run.approved_at,
                              "approved_test_sha256": run.test_sha256}
            integ["approval"] = "VALID" if run.approved_by and test_sha else "FAILED: incomplete approval record"
        else:
            integ["approval"] = "MISSING" if run.status in _POST_APPROVAL else "NOT_RUN"

        # Verification evidence (written only by controller.run_verification)
        evidence: Optional[Dict[str, Any]] = None
        if run.verification_evidence:
            try:
                evidence = json.loads(run.verification_evidence)
                if not isinstance(evidence, dict):
                    raise ValueError
            except ValueError:
                evidence = None
                integ["verification_evidence"] = "CORRUPTED"
            else:
                bad = []
                if evidence.get("run_id") != run.run_id:
                    bad.append("run_id does not match this run")
                if evidence.get("test_sha256") != test_sha:
                    bad.append("test hash does not match the frozen test")
                if evidence.get("regression_status") != run.regression_status.value:
                    bad.append("regression status disagrees with run record")
                if evidence.get("recorded_by") != "controller.run_verification":
                    bad.append("not written by controller.run_verification")
                integ["verification_evidence"] = ("FAILED: " + "; ".join(bad)) if bad else "VALID"
        else:
            integ["verification_evidence"] = "MISSING" if claims_success else "NOT_RUN"

        # Patch: must be the exact patch the verifier applied
        if run.patch_diff:
            patch_sha = _sha(run.patch_diff.encode("utf-8"))
            if evidence is None:
                integ["patch"] = "VALID (not verified)"
            elif evidence.get("patch_diff_sha256") != patch_sha:
                integ["patch"] = (f"FAILED: patch mismatch with verification evidence "
                                  f"({patch_sha} != {evidence.get('patch_diff_sha256')})")
            else:
                integ["patch"] = "VALID"
        else:
            integ["patch"] = "MISSING" if run.status in (RunStatus.VERIFYING, RunStatus.PASSES_FROZEN_TEST) else "NOT_RUN"

        # Screenshots (re-hashed against hashes recorded at capture time)
        integ["reproduction_screenshot"], before_b64 = self._load_screenshot(
            run.reproduction_screenshot_path, run.reproduction_screenshot_sha256)
        integ["verification_screenshot"], after_b64 = self._load_screenshot(
            run.verification_screenshot_path, run.verification_screenshot_sha256)

        failures: List[str] = [f"{k}: {v}" for k, v in integ.items() if v.startswith(("FAILED", "CORRUPTED"))]
        if claims_success:
            failures += [f"{k}: {v}" for k, v in integ.items()
                         if k not in ("reproduction_screenshot", "verification_screenshot")
                         and not v.startswith("VALID")]
            if evidence and not (evidence.get("frozen_test_status") == "PASSED"
                                 and evidence.get("regression_status") == "PASSED"):
                failures.append("final status passes_frozen_test is not backed by PASSED evidence")
        failures = sorted(set(failures))
        valid = not failures

        if evidence is None:
            frozen_result = "INVALID_EVIDENCE" if integ["verification_evidence"] == "CORRUPTED" else "NOT_RUN"
            regression_result = frozen_result
        elif not valid:
            frozen_result = regression_result = "INVALID_EVIDENCE"
        else:
            frozen_result = evidence.get("frozen_test_status", "MISSING")
            regression_result = evidence.get("regression_status", "MISSING")

        check_results = {
            "frozen_test": frozen_result,
            "regression_suite": regression_result,
            "details": evidence.get("details", "") if evidence else "",
            "final_status": run.status.value,
            "evidence_valid": valid,
        }

        return EvidenceBundle(
            bundle_id=f"bundle-{run.run_id[:8]}",
            run_id=run.run_id,
            app_id=run.app_id,
            report_text=run.report_text or "MISSING",
            expected_behavior=expected_behavior,
            plan_json=run.plan_json,
            model_ids=run.model_ids,
            model_mode=run.model_mode,
            model_mode_disclosure=MODE_DISCLOSURE[run.model_mode],
            source_revision=run.source_revision,
            patched_revision=run.patched_revision,
            test_sha256=test_sha,
            frozen_test_code=frozen_code,
            intended_assertion=intended_assertion,
            before_screenshot_b64=before_b64,
            after_screenshot_b64=after_b64,
            reproduction_screenshot_sha256=run.reproduction_screenshot_sha256,
            verification_screenshot_sha256=run.verification_screenshot_sha256,
            reproduction_screenshot_timestamp=run.reproduction_screenshot_timestamp,
            verification_screenshot_timestamp=run.verification_screenshot_timestamp,
            patch_diff=run.patch_diff,
            patch_application_output=run.patch_application_output,
            reproduction_logs=run.reproduction_logs,
            verification_evidence=evidence,
            check_results=check_results,
            usage=run.usage,
            final_status=run.status,
            regression_status=run.regression_status,
            human_approval=human_approval,
            artifacts_integrity=integ,
            evidence_valid=valid,
            integrity_failures=failures,
            run_created_at=run.created_at,
            run_updated_at=run.updated_at,
        )

    def export_zip(self, bundle: EvidenceBundle) -> str:
        """Writes the bundle as a ZIP under export_dir/<run_id>/ and returns its path."""
        run_folder = os.path.join(self.export_dir, bundle.run_id)
        os.makedirs(run_folder, exist_ok=True)
        files: Dict[str, bytes] = {"frozen_test.spec.js": bundle.frozen_test_code.encode("utf-8"),
                                   "check_results.json": json.dumps(bundle.check_results, indent=2).encode("utf-8")}
        if bundle.patch_diff:
            files["patch.diff"] = bundle.patch_diff.encode("utf-8")
        if bundle.patch_application_output:
            files["patch_application_output.txt"] = bundle.patch_application_output.encode("utf-8")
        if bundle.reproduction_logs:
            files["reproduction_logs.txt"] = bundle.reproduction_logs.encode("utf-8")
        if bundle.before_screenshot_b64:
            files["screenshot_reproduction.png"] = base64.b64decode(bundle.before_screenshot_b64)
        if bundle.after_screenshot_b64:
            files["screenshot_verification.png"] = base64.b64decode(bundle.after_screenshot_b64)

        manifest = bundle.model_dump(mode="json", exclude={"before_screenshot_b64", "after_screenshot_b64"})
        manifest["file_sha256"] = {name: _sha(data) for name, data in files.items()}

        zip_path = os.path.join(run_folder, f"evidence_bundle_{bundle.run_id}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            for name, data in files.items():
                zf.writestr(name, data)
        return zip_path
