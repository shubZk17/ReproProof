"""Worker Execution Pipeline for ReproProof.

Runs reproduction and repair jobs in separate processes, persisting state in SQLite.
Enforces that no patch is ever attempted before human test approval.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Dict, Optional, Tuple

from reproproof.core.controller import RunController
from reproproof.core.limits import DEFAULT_LIMITS, RunLimits
from reproproof.core.model_adapter import MetaModelClient
from reproproof.core.patcher import PatchValidator
from reproproof.core.planner import ReproductionPlanner
from reproproof.core.schemas import ActionPlan, PatchProposal, RunStatus
from reproproof.core.verifier import FreshCopyVerifier
from reproproof.core.evidence import EvidenceExporter


class JobRunner:
    """Manages the lifecycle of reproduction and repair execution jobs."""

    def __init__(
        self,
        controller: Optional[RunController] = None,
        model_client: Optional[MetaModelClient] = None,
        manifests_dir: Optional[str] = None,
        limits: RunLimits = DEFAULT_LIMITS,
    ):
        self.limits = limits
        self.controller = controller or RunController(limits=limits)
        self.model_client = model_client or MetaModelClient()
        self.planner = ReproductionPlanner(manifests_dir=manifests_dir, model_client=self.model_client)
        self.evidence_exporter = EvidenceExporter()

    def run_reproduction_job(
        self,
        run_id: str,
        report_text: str,
        screenshot_path: Optional[str] = None,
        mock_plan: Optional[ActionPlan] = None,
        port: int = 3000,
    ) -> Tuple[RunStatus, str, str, str]:
        """Executes reproduction stage.
        
        Transitions: received -> reproducing -> awaiting_test_approval | not_reproduced | environment_error.
        Returns: (status, test_code, test_sha256, details)
        """
        run = self.controller.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")

        # 1. Plan reproduction while in RECEIVED state
        manifest = self.planner.load_manifest(run.app_id)
        plan, model_id, in_tokens, out_tokens = self.planner.plan(
            app_id=run.app_id,
            report_text=report_text,
            mock_plan=mock_plan,
        )
        self.controller.record_usage(
            run_id=run_id,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            cost_usd=(in_tokens * 0.0000015 + out_tokens * 0.000002),
            model_id=model_id,
        )

        # Ambiguous check: If model returned a clarification question, handle state per PRD (received -> clarification_required)
        if plan.clarification_question:
            self.controller.transition(
                run_id=run_id,
                to_status=RunStatus.CLARIFICATION_REQUIRED,
                reason=plan.clarification_question,
                actor="model",
            )
            return RunStatus.CLARIFICATION_REQUIRED, "", "", plan.clarification_question

        # 2. Transition to reproducing (received -> reproducing)
        self.controller.transition(
            run_id=run_id,
            to_status=RunStatus.REPRODUCING,
            reason="Starting model reproduction planning and execution",
            actor="worker",
        )

        # 3. Compile test
        test_code, test_sha256 = self.planner.compiler.compile(
            plan=plan,
            test_name=f"repro-{run_id[:8]}",
            screenshot_path=os.path.join("runs", f"ss_before_{run_id}.png"),
        )

        # Write test to temp file
        os.makedirs("runs", exist_ok=True)
        test_file_path = os.path.join("runs", f"test_{run_id}.spec.js")
        with open(test_file_path, "w", encoding="utf-8") as f:
            f.write(test_code)

        # 4. Start app process if needed
        app_full_dir = os.path.abspath(manifest.app_dir)
        env = os.environ.copy()
        env["PORT"] = str(port)
        env["BASE_URL"] = f"http://localhost:{port}"

        server_proc = subprocess.Popen(
            manifest.start_command.split(),
            cwd=app_full_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Wait for server ready
            verifier = FreshCopyVerifier(manifest, self.limits)
            if not verifier._wait_for_server(port, timeout_seconds=manifest.startup_timeout_seconds):
                self.controller.transition(
                    run_id=run_id,
                    to_status=RunStatus.ENVIRONMENT_ERROR,
                    reason="Target app server failed to become ready.",
                    actor="runner",
                )
                return RunStatus.ENVIRONMENT_ERROR, test_code, test_sha256, "Server failed to start."

            # 5. Run Playwright test
            run_cmd = f"npx.cmd playwright test {test_file_path}"
            test_proc = subprocess.run(
                run_cmd,
                shell=True,
                cwd=os.getcwd(),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.limits.browser_test_timeout_seconds,
            )

            # 6. Classify result
            classification = self.planner.classify_test_result(
                exit_code=test_proc.returncode,
                stdout=test_proc.stdout,
                stderr=test_proc.stderr,
                intended_assertion=plan.assertions[0].action if plan.assertions else None,
            )

            # 7. Transition controller state
            self.controller.transition(
                run_id=run_id,
                to_status=classification.status,
                reason=classification.reason,
                actor="runner",
            )

            return classification.status, test_code, test_sha256, classification.reason

        finally:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server_proc.kill()

    def run_repair_and_verify_job(
        self,
        run_id: str,
        report_text: str,
        frozen_test_code: str,
        frozen_test_sha256: str,
        failing_assertion: str,
        mock_patch: Optional[PatchProposal] = None,
        port: int = 3002,
    ) -> Tuple[RunStatus, str]:
        """Executes patch generation and clean verification.
        
        Hard Rule 2: Never called before human approval.
        Only allowed when run is in PATCHING state.
        """
        run = self.controller.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")

        if run.status != RunStatus.PATCHING:
            raise RuntimeError(
                f"Cannot execute repair: run is in state {run.status.value}. Must be in 'patching' state."
            )

        manifest = self.planner.load_manifest(run.app_id)
        verifier = FreshCopyVerifier(manifest, self.limits)

        # Read allowed source files for model context
        source_files: Dict[str, str] = {}
        app_dir = manifest.app_dir
        for allowed in manifest.allowed_source_paths:
            full_path = os.path.join(app_dir, allowed)
            if os.path.isdir(full_path):
                for root, _, files in os.walk(full_path):
                    for f in files:
                        rel = os.path.relpath(os.path.join(root, f), app_dir).replace("\\", "/")
                        with open(os.path.join(root, f), "r", encoding="utf-8") as sfile:
                            source_files[rel] = sfile.read()
            elif os.path.isfile(full_path):
                rel = os.path.relpath(full_path, app_dir).replace("\\", "/")
                with open(full_path, "r", encoding="utf-8") as sfile:
                    source_files[rel] = sfile.read()

        # Up to 2 attempts per PRD
        max_attempts = self.limits.max_patch_attempts

        for attempt in range(1, max_attempts + 1):
            self.controller.record_patch_attempt(run_id)

            # Propose patch
            patch, model_id, in_t, out_t = self.model_client.propose_patch(
                attempt=attempt,
                report_text=report_text,
                failing_test_code=frozen_test_code,
                failing_assertion=failing_assertion,
                source_files=source_files,
                mock_patch=mock_patch,
            )
            self.controller.record_usage(
                run_id=run_id,
                input_tokens=in_t,
                output_tokens=out_t,
                cost_usd=(in_t * 0.0000015 + out_t * 0.000002),
                model_id=model_id,
            )

            # Transition to verifying
            self.controller.transition(
                run_id=run_id,
                to_status=RunStatus.VERIFYING,
                reason=f"Attempt {attempt}: verifying proposed patch on clean app copy",
                actor="worker",
            )

            # Clean verification on fresh copy
            v_res = verifier.verify_patch(
                app_source_dir=manifest.app_dir,
                patch_proposal=patch,
                frozen_test_code=frozen_test_code,
                expected_test_sha256=frozen_test_sha256,
                port=port,
            )

            if v_res.status == RunStatus.PASSES_FROZEN_TEST:
                self.controller.transition(
                    run_id=run_id,
                    to_status=RunStatus.PASSES_FROZEN_TEST,
                    reason="Fresh copy verification succeeded for both frozen test and regression checks.",
                    actor="verifier",
                )
                return RunStatus.PASSES_FROZEN_TEST, "Verification passed successfully."

            # If attempt 1 failed, loop allows second attempt with model escalation
            if attempt < max_attempts:
                self.controller.transition(
                    run_id=run_id,
                    to_status=RunStatus.PATCHING,
                    reason=f"Attempt {attempt} verification failed. Retrying with escalation model.",
                    actor="verifier",
                )

        # Both attempts failed
        self.controller.transition(
            run_id=run_id,
            to_status=RunStatus.UNRESOLVED,
            reason=f"All {max_attempts} patch attempts failed fresh verification.",
            actor="verifier",
        )
        return RunStatus.UNRESOLVED, "All patch attempts failed."
