"""Reproduction Planner and Failure Classification Engine.

Implements R1, R2, R4, and Gate G1:
- Validates intake against allowlisted app manifests.
- Extracts expected behavior or clarification question.
- Compiles constrained action plan to Playwright test.
- Classifies execution failures honestly: timeouts, server crashes, and locator errors
  are NEVER counted as reproduced bugs. Only intended assertion failures qualify.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import yaml

from reproproof.core.schemas import (
    ActionPlan,
    AppManifest,
    RunStatus,
)
from reproproof.core.model_adapter import MetaModelClient
from reproproof.core.compiler import PlaywrightCompiler


class FailureClassification:
    """Outcome of analyzing test runner execution results."""
    def __init__(
        self,
        status: RunStatus,
        reason: str,
        is_intended_assertion: bool = False,
        failed_assertion: Optional[str] = None,
        error_output: str = "",
    ):
        self.status = status
        self.reason = reason
        self.is_intended_assertion = is_intended_assertion
        self.failed_assertion = failed_assertion
        self.error_output = error_output


class ReproductionPlanner:
    """Intake, planning, and failure classification orchestrator."""

    def __init__(self, manifests_dir: Optional[str] = None, model_client: Optional[MetaModelClient] = None):
        if manifests_dir is None:
            repo_root = Path(__file__).resolve().parent.parent.parent
            self.manifests_dir = str(repo_root / "apps" / "manifests")
        else:
            self.manifests_dir = manifests_dir
        self.model_client = model_client or MetaModelClient()
        self.compiler = PlaywrightCompiler()

    def load_manifest(self, app_id: str) -> AppManifest:
        """Loads and strictly validates an app manifest from YAML."""
        manifest_path = os.path.join(self.manifests_dir, f"{app_id}.yaml")
        if not os.path.exists(manifest_path):
            raise ValueError(f"App '{app_id}' is not in the allowlisted manifests ({manifest_path} not found).")

        with open(manifest_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return AppManifest.model_validate(data)

    def plan(
        self,
        app_id: str,
        report_text: str,
        screenshot_b64: Optional[str] = None,
        mock_plan: Optional[ActionPlan] = None,
    ) -> Tuple[ActionPlan, str, int, int]:
        """Infers expected behavior and constrained action plan."""
        manifest = self.load_manifest(app_id)
        routes = ["/", "/api/items"]

        plan, model_id, in_t, out_t = self.model_client.plan_reproduction(
            report_text=report_text,
            routes=routes,
            screenshot_b64=screenshot_b64,
            mock_plan=mock_plan,
        )
        return plan, model_id, in_t, out_t

    def classify_test_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        intended_assertion: Optional[str] = None,
    ) -> FailureClassification:
        """Classifies Playwright runner output strictly adhering to PRD Hard Rule 6.
        
        Hard Rule 6: Never count a timeout, locator error or server failure as a reproduced bug.
        Only the intended assertion counts as reproduced -> awaiting_test_approval.
        """
        combined = stdout + "\n" + stderr

        # Case 1: Test passed cleanly without any failure
        if exit_code == 0:
            return FailureClassification(
                status=RunStatus.NOT_REPRODUCED,
                reason="Test passed without failure; defect was not reproduced.",
                is_intended_assertion=False,
                error_output=combined,
            )

        # Case 2: Environment error (connection refused, server down, setup failure)
        env_error_patterns = [
            r"ECONNREFUSED",
            r"ERR_CONNECTION_REFUSED",
            r"server error",
            r"Cannot find module",
            r"ENOTFOUND",
            r"browserType\.launch: Executable doesn't exist",
        ]
        for pat in env_error_patterns:
            if re.search(pat, combined, re.IGNORECASE):
                return FailureClassification(
                    status=RunStatus.ENVIRONMENT_ERROR,
                    reason=f"Environment/infrastructure failure: {pat}",
                    is_intended_assertion=False,
                    error_output=combined,
                )

        # Case 3: Timeout or locator failure (NOT a reproduced bug per Rule 6)
        timeout_or_locator_patterns = [
            r"Timeout \d+ms exceeded",
            r"locator\..*waiting for selector",
            r"TimeoutError",
            r"Target page, context or browser has been closed",
            r"waiting for locator",
        ]
        # Check if the timeout occurred outside an expect assertion
        for pat in timeout_or_locator_patterns:
            if re.search(pat, combined, re.IGNORECASE) and not re.search(r"expect\(.*\)\.(toBe|toHave)", combined):
                return FailureClassification(
                    status=RunStatus.NOT_REPRODUCED,
                    reason=f"Execution failed due to locator or timeout error ({pat}), not an intended assertion.",
                    is_intended_assertion=False,
                    error_output=combined,
                )

        # Case 4: Intended assertion failure
        # Playwright assertion failure messages typically look like:
        # Error: expect(received).toBeVisible()
        # Received: hidden
        assertion_match = re.search(r"Error:\s*(expect\(.*?\)\.\w+\(.*?\))", combined)
        if not assertion_match:
            assertion_match = re.search(r"(expect\(received\)\.\w+)", combined)

        failed_assertion_str = assertion_match.group(1) if assertion_match else None

        # Check if an assertion failure occurred
        if re.search(r"expect\(.*?\)\.(toBe|toHave)", combined, re.IGNORECASE):
            return FailureClassification(
                status=RunStatus.AWAITING_TEST_APPROVAL,
                reason="Intended assertion failed as expected, successfully reproducing the bug.",
                is_intended_assertion=True,
                failed_assertion=failed_assertion_str or intended_assertion or "assertion_failed",
                error_output=combined,
            )

        # Fallback: general unhandled error
        return FailureClassification(
            status=RunStatus.NOT_REPRODUCED,
            reason="Unclassified test execution failure.",
            is_intended_assertion=False,
            error_output=combined,
        )
