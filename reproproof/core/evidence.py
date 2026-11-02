"""Evidence Bundle Exporter (R9 & R15).

Packages run reports, frozen tests, SHA-256 hashes, diffs, screenshots,
and check results into downloadable ZIP and JSON bundles.
"""

from __future__ import annotations

import base64
import json
import os
import zipfile
from typing import Any, Dict, List, Optional

from reproproof.core.schemas import EvidenceBundle, RunRecord, RunStatus, UsageRecord


class EvidenceExporter:
    """Exports and packages audit-grade evidence bundles."""

    def __init__(self, export_dir: str = "runs"):
        self.export_dir = export_dir
        os.makedirs(export_dir, exist_ok=True)

    def create_bundle(
        self,
        run_record: RunRecord,
        report_text: str,
        expected_behavior: str,
        intended_assertion: str,
        frozen_test_code: str,
        test_sha256: str,
        patch_diff: Optional[str] = None,
        before_screenshot_bytes: Optional[bytes] = None,
        after_screenshot_bytes: Optional[bytes] = None,
        check_results: Optional[Dict[str, Any]] = None,
        rejected_attempts: Optional[List[Dict[str, Any]]] = None,
    ) -> EvidenceBundle:
        """Constructs an in-memory EvidenceBundle object."""
        bundle_id = f"bundle-{run_record.run_id[:8]}"
        before_b64 = base64.b64encode(before_screenshot_bytes).decode("ascii") if before_screenshot_bytes else None
        after_b64 = base64.b64encode(after_screenshot_bytes).decode("ascii") if after_screenshot_bytes else None

        bundle = EvidenceBundle(
            bundle_id=bundle_id,
            run_id=run_record.run_id,
            app_id=run_record.app_id,
            report_text=report_text,
            expected_behavior=expected_behavior,
            model_ids=run_record.model_ids,
            source_revision=run_record.source_revision,
            patched_revision=run_record.patched_revision,
            test_sha256=test_sha256,
            frozen_test_code=frozen_test_code,
            intended_assertion=intended_assertion,
            before_screenshot_b64=before_b64,
            after_screenshot_b64=after_b64,
            patch_diff=patch_diff,
            check_results=check_results or {},
            rejected_attempts=rejected_attempts or [],
            usage=run_record.usage,
            final_status=run_record.status,
            created_at=run_record.updated_at,
        )
        return bundle

    def export_zip(self, bundle: EvidenceBundle) -> str:
        """Exports the EvidenceBundle as a ZIP file on disk. Returns zip file path."""
        run_folder = os.path.join(self.export_dir, bundle.run_id)
        os.makedirs(run_folder, exist_ok=True)

        zip_path = os.path.join(run_folder, f"evidence_bundle_{bundle.run_id}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Metadata JSON
            bundle_dict = bundle.model_dump(exclude={"before_screenshot_b64", "after_screenshot_b64"})
            zf.writestr("manifest.json", json.dumps(bundle_dict, indent=2))

            # Frozen test
            zf.writestr("frozen_test.spec.js", bundle.frozen_test_code)

            # Patch diff if available
            if bundle.patch_diff:
                zf.writestr("patch.diff", bundle.patch_diff)

            # Screenshots
            if bundle.before_screenshot_b64:
                zf.writestr("screenshot_before.png", base64.b64decode(bundle.before_screenshot_b64))
            if bundle.after_screenshot_b64:
                zf.writestr("screenshot_after.png", base64.b64decode(bundle.after_screenshot_b64))

            # Verification and check results
            zf.writestr("check_results.json", json.dumps(bundle.check_results, indent=2))

        return zip_path
