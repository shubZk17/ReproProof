"""Fresh-Copy Verification Engine.

Runs the frozen test, then the protected regression suite, against a patched temporary
copy of an allowlisted app on an ephemeral port with a scrubbed environment.

NOT A SANDBOX: the patched app and the tests run as the current OS user, with that user's
filesystem and network access. Only trusted, allowlisted demo apps and trusted patches may
be executed (see `controller.HOST_EXECUTION_FLAG` and README "Execution boundary").

The verifier only reports what actually happened, with provenance. The controller
validates that report and alone decides the run status (H-5).
"""

from __future__ import annotations

import datetime
import hashlib
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from reproproof.core.compiler import PlaywrightCompiler
from reproproof.core.limits import DEFAULT_LIMITS, RunLimits
from reproproof.core.patcher import PatchValidationError, PatchValidator
from reproproof.core.proc_utils import find_free_port, force_rmtree, get_sanitized_runner_env, kill_process_tree
from reproproof.core.schemas import AppManifest, PatchProposal, RegressionStatus

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUNS_DIR = REPO_ROOT / "runs"
MAX_LOG_CHARS = 20000
_TREE_SKIP = {".git", "node_modules"}

# Same PASSED / FAILED / NOT_RUN / ERROR semantics apply to the frozen test.
CheckStatus = RegressionStatus


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Optional[str]) -> Optional[str]:
    if not path or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def tree_sha256(root: str) -> str:
    """Content hash of a source tree (relative paths + bytes), used as the app revision."""
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _TREE_SKIP)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            h.update(os.path.relpath(full, root).replace("\\", "/").encode("utf-8") + b"\0")
            with open(full, "rb") as f:
                h.update(hashlib.sha256(f.read()).digest())
    return "tree-sha256:" + h.hexdigest()


def resolve_app_dir(app_dir: str) -> str:
    return app_dir if os.path.isabs(app_dir) else str(REPO_ROOT / app_dir)


def _tail(text: str) -> str:
    return text if len(text) <= MAX_LOG_CHARS else "...[truncated]...\n" + text[-MAX_LOG_CHARS:]


@dataclass
class VerificationResult:
    """What the verifier observed, with provenance. Carries no run status: the controller decides."""
    run_id: str
    test_sha256: str
    patch_diff_sha256: str
    frozen_test_status: RegressionStatus
    regression_status: RegressionStatus
    details: str
    source_revision: Optional[str] = None
    patched_revision: Optional[str] = None
    patch_output: str = ""
    verification_screenshot_path: Optional[str] = None
    verification_screenshot_sha256: Optional[str] = None
    verification_screenshot_timestamp: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    timestamp: str = field(default_factory=_now)


class FreshCopyVerifier:
    """Runs clean verification on a fresh copy of the application."""

    def __init__(self, manifest: AppManifest, limits: RunLimits = DEFAULT_LIMITS):
        self.manifest = manifest
        self.limits = limits
        self.validator = PatchValidator(manifest, limits)

    def _wait_for_server(self, port: int, timeout_seconds: int = 15) -> bool:
        """Polls /health until it returns 200 or the timeout elapses."""
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
        run_id: str,
        port: Optional[int] = None,
    ) -> VerificationResult:
        """Applies the patch to a fresh copy and runs frozen test + regression suite."""
        test_sha = sha256_text(frozen_test_code)
        patch_sha = sha256_text(patch_proposal.unified_diff)

        def result(frozen, reg, details, **kw) -> VerificationResult:
            return VerificationResult(run_id=run_id, test_sha256=test_sha, patch_diff_sha256=patch_sha,
                                      frozen_test_status=frozen, regression_status=reg, details=details, **kw)

        NOT_RUN = RegressionStatus.NOT_RUN
        if test_sha != expected_test_sha256:
            return result(NOT_RUN, NOT_RUN, f"Test hash mismatch: expected {expected_test_sha256}, got {test_sha}")

        try:
            self.validator.validate_patch(patch_proposal)
        except PatchValidationError as e:
            return result(NOT_RUN, NOT_RUN, f"Patch rejected before execution: {e}")

        temp_dir = tempfile.mkdtemp(prefix="reproproof_verify_")
        test_file = RUNS_DIR / f"verify_{os.path.basename(temp_dir)}.spec.js"
        server_proc: Optional[subprocess.Popen] = None
        try:
            app_copy_dir = os.path.join(temp_dir, "app")
            shutil.copytree(resolve_app_dir(app_source_dir), app_copy_dir)
            source_rev = tree_sha256(app_copy_dir)

            try:
                patch_output = self.validator.apply_diff_to_directory(app_copy_dir, patch_proposal.unified_diff)
            except PatchValidationError as e:
                return result(NOT_RUN, NOT_RUN, f"Patch rejected by git apply: {e}", source_revision=source_rev)
            patched_rev = tree_sha256(app_copy_dir)
            prov = dict(source_revision=source_rev, patched_revision=patched_rev, patch_output=patch_output)

            RUNS_DIR.mkdir(parents=True, exist_ok=True)
            test_file.write_text(frozen_test_code, encoding="utf-8")

            # The frozen test writes its screenshot to a fixed scratch path. The reproduction
            # screenshot was already copied elsewhere by the runner, so clear stale bytes here
            # and move the fresh capture to a verification-specific path afterwards.
            capture_path = PlaywrightCompiler.extract_plan(frozen_test_code).get("screenshot_path")
            if capture_path and os.path.exists(capture_path):
                os.remove(capture_path)

            allocated_port = port or find_free_port()
            safe_env = get_sanitized_runner_env(allocated_port)
            server_proc = subprocess.Popen(
                self.manifest.start_command.split(),
                cwd=app_copy_dir,
                env=safe_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if not self._wait_for_server(allocated_port, timeout_seconds=self.manifest.startup_timeout_seconds):
                return result(RegressionStatus.ERROR, NOT_RUN,
                              "Patched server failed to become ready within startup timeout.", **prov)

            rel_test = os.path.relpath(test_file, REPO_ROOT).replace("\\", "/")
            try:
                test_proc = subprocess.run(
                    f'npx.cmd playwright test "{rel_test}"', shell=True, cwd=str(REPO_ROOT), env=safe_env,
                    capture_output=True, text=True, timeout=self.limits.browser_test_timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                return result(RegressionStatus.ERROR, NOT_RUN, "Frozen test timed out.", **prov)
            frozen_status = RegressionStatus.PASSED if test_proc.returncode == 0 else RegressionStatus.FAILED

            shot = {}
            if capture_path and os.path.exists(capture_path):
                verify_path = str(RUNS_DIR / f"verify_{run_id}_{patch_sha[:12]}.png")
                os.replace(capture_path, verify_path)
                shot = dict(verification_screenshot_path=verify_path,
                            verification_screenshot_sha256=sha256_file(verify_path),
                            verification_screenshot_timestamp=_now())

            reg_status, reg_out, reg_err = NOT_RUN, "", ""
            if frozen_status != RegressionStatus.PASSED:
                reg_note = "skipped because the frozen test did not pass"
            elif not self.manifest.regression_command:
                reg_note = "not configured in the app manifest"
            else:
                reg_note = ""
                try:
                    reg_proc = subprocess.run(
                        self.manifest.regression_command.replace("npx playwright", "npx.cmd playwright"),
                        shell=True, cwd=str(REPO_ROOT), env=safe_env, capture_output=True, text=True,
                        timeout=self.limits.browser_test_timeout_seconds,
                    )
                    reg_out, reg_err = reg_proc.stdout, reg_proc.stderr
                    reg_status = RegressionStatus.PASSED if reg_proc.returncode == 0 else RegressionStatus.FAILED
                except Exception as ex:
                    reg_status, reg_err = RegressionStatus.ERROR, f"Regression suite execution error: {ex}"

            details = f"Frozen test {frozen_status.value}; regression suite {reg_status.value}"
            details += f" ({reg_note})." if reg_note else "."
            return result(frozen_status, reg_status, details, **prov, **shot,
                          stdout=_tail(test_proc.stdout + "\n" + reg_out),
                          stderr=_tail(test_proc.stderr + "\n" + reg_err))
        finally:
            if server_proc:
                kill_process_tree(server_proc)
            try:
                test_file.unlink(missing_ok=True)
            except OSError:
                pass
            force_rmtree(temp_dir)
