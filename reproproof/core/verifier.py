"""Fresh-Copy Isolated Verification Engine.

Enforces:
- R8: Clean verification on temporary fresh copy of app.
- Ephemeral Ports: Dynamically allocated port avoids port collisions.
- Sanitized Environment: Strips MODEL_API_KEY and credentials from runner environment.
- Process Tree Cleanup: Reliable process tree termination on Windows.
- Hard Rule 4: Never set passes_frozen_test unless same test hash and regression checks pass.
- Hard Rule 5: Never use 'verified' as a status. Use 'passes_frozen_test'.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request
from typing import Dict, Optional

from reproproof.core.schemas import AppManifest, PatchProposal, RunStatus
from reproproof.core.patcher import PatchValidator
from reproproof.core.limits import DEFAULT_LIMITS, RunLimits
from reproproof.core.proc_utils import find_free_port, get_sanitized_runner_env, kill_process_tree


class VerificationResult:
    def __init__(
        self,
        passed_frozen_test: bool,
        passed_regression: bool,
        status: RunStatus,
        details: str,
        test_sha256: str,
        stdout: str = "",
        stderr: str = "",
    ):
        self.passed_frozen_test = passed_frozen_test
        self.passed_regression = passed_regression
        self.status = status
        self.details = details
        self.test_sha256 = test_sha256
        self.stdout = stdout
        self.stderr = stderr


class FreshCopyVerifier:
    """Runs clean verification on fresh copy of application."""

    def __init__(self, manifest: AppManifest, limits: RunLimits = DEFAULT_LIMITS):
        self.manifest = manifest
        self.limits = limits
        self.validator = PatchValidator(manifest, limits)

    def _wait_for_server(self, port: int, timeout_seconds: int = 15) -> bool:
        """Polls server until it responds with 200 OK or timeout occurs."""
        start_time = time.time()
        url = f"http://127.0.0.1:{port}/health"
        while time.time() - start_time < timeout_seconds:
            try:
                with urllib.request.urlopen(url, timeout=1.0) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                time.sleep(0.25)
        return False

    def verify_patch(
        self,
        app_source_dir: str,
        patch_proposal: PatchProposal,
        frozen_test_code: str,
        expected_test_sha256: str,
        port: Optional[int] = None,
    ) -> VerificationResult:
        """Executes full clean verification on a temporary directory copy."""
        # 1. Byte-identical test hash verification (Rule 4)
        actual_test_sha = hashlib.sha256(frozen_test_code.encode("utf-8")).hexdigest()
        if actual_test_sha != expected_test_sha256:
            return VerificationResult(
                passed_frozen_test=False,
                passed_regression=False,
                status=RunStatus.UNRESOLVED,
                details=f"Test hash mismatch: expected {expected_test_sha256}, got {actual_test_sha}",
                test_sha256=actual_test_sha,
            )

        # 2. Validate patch syntax and boundaries
        self.validator.validate_patch(patch_proposal)

        # 3. Create fresh temporary copy
        repo_root = Path(__file__).resolve().parent.parent.parent
        real_source_dir = str(repo_root / app_source_dir) if not os.path.isabs(app_source_dir) else app_source_dir

        temp_dir = tempfile.mkdtemp(prefix="reproproof_verify_")
        app_copy_dir = os.path.join(temp_dir, "app")
        shutil.copytree(real_source_dir, app_copy_dir)

        # 4. Apply patch to fresh copy using git apply
        self.validator.apply_diff_to_directory(app_copy_dir, patch_proposal.unified_diff)

        # 5. Write frozen test into runs directory in repo_root
        runs_dir = repo_root / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        test_file = str(runs_dir / f"verify_{os.path.basename(temp_dir)}.spec.js")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(frozen_test_code)

        server_proc = None
        allocated_port = port or find_free_port()
        try:
            # 6. Start patched server in temp copy with sanitized environment
            safe_env = get_sanitized_runner_env(allocated_port)

            start_parts = self.manifest.start_command.split()
            server_proc = subprocess.Popen(
                start_parts,
                cwd=app_copy_dir,
                env=safe_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Wait for server ready
            if not self._wait_for_server(allocated_port, timeout_seconds=self.manifest.startup_timeout_seconds):
                return VerificationResult(
                    passed_frozen_test=False,
                    passed_regression=False,
                    status=RunStatus.ENVIRONMENT_ERROR,
                    details="Patched server failed to become ready within startup timeout.",
                    test_sha256=expected_test_sha256,
                )

            # 7. Run the frozen Playwright test against patched app from repo_root
            rel_test = os.path.relpath(test_file, str(repo_root)).replace("\\", "/")
            run_cmd = f'npx.cmd playwright test "{rel_test}"'
            test_proc = subprocess.run(
                run_cmd,
                shell=True,
                cwd=str(repo_root),
                env=safe_env,
                capture_output=True,
                text=True,
                timeout=self.limits.browser_test_timeout_seconds,
            )

            frozen_test_passed = (test_proc.returncode == 0)

            # 8. Run regression suite if regression command is provided
            regression_passed = True
            reg_stdout, reg_stderr = "", ""
            if self.manifest.regression_command and frozen_test_passed:
                reg_cmd = self.manifest.regression_command.replace("npx playwright", "npx.cmd playwright")
                reg_proc = subprocess.run(
                    reg_cmd,
                    shell=True,
                    cwd=str(repo_root),
                    env=safe_env,
                    capture_output=True,
                    text=True,
                    timeout=self.limits.browser_test_timeout_seconds,
                )
                regression_passed = (reg_proc.returncode == 0)
                reg_stdout = reg_proc.stdout
                reg_stderr = reg_proc.stderr

            if frozen_test_passed and regression_passed:
                # PRD Hard Rule 5: Never use 'verified' as a status. Use 'passes_frozen_test'.
                status = RunStatus.PASSES_FROZEN_TEST
                details = "Both byte-identical frozen test and regression suite passed on fresh app copy."
            else:
                status = RunStatus.UNRESOLVED
                details = f"Verification failed: frozen_test_passed={frozen_test_passed}, regression_passed={regression_passed}"

            return VerificationResult(
                passed_frozen_test=frozen_test_passed,
                passed_regression=regression_passed,
                status=status,
                details=details,
                test_sha256=expected_test_sha256,
                stdout=test_proc.stdout + "\n" + reg_stdout,
                stderr=test_proc.stderr + "\n" + reg_stderr,
            )

        finally:
            if server_proc:
                kill_process_tree(server_proc)
            shutil.rmtree(temp_dir, ignore_errors=True)
