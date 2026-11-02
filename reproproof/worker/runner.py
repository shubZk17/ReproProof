"""Worker Execution Pipeline for ReproProof.

Runs reproduction and repair jobs with:
- Ephemeral port allocation.
- Scrubbed environment (no MODEL_API_KEY leakage).
- Reliable process-tree termination.
- Strict controller evidence-backed state transitions.
- Robust exception handling ensuring runs never hang in active states.
"""

from __future__ import annotations

import os
from pathlib import Path
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
from reproproof.core.proc_utils import find_free_port, get_sanitized_runner_env, kill_process_tree


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
        port: Optional[int] = None,
    ) -> Tuple[RunStatus, str, str, str]:
        """Executes reproduction stage.

        Transitions: received -> reproducing -> awaiting_test_approval | not_reproduced | environment_error.
        Guarantees cleanup and terminal state on exceptions.
        """
        run = self.controller.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")

        server_proc = None
        allocated_port = port or find_free_port()

        try:
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
            self.controller.record_plan(run_id, plan)

            # Ambiguous check: If model returned a clarification question, handle state per PRD
            if plan.clarification_question:
                self.controller.transition(
                    run_id=run_id,
                    to_status=RunStatus.CLARIFICATION_REQUIRED,
                    reason=plan.clarification_question,
                    actor="model",
                )
                return RunStatus.CLARIFICATION_REQUIRED, "", "", plan.clarification_question

            # 2. Transition to reproducing
            self.controller.transition(
                run_id=run_id,
                to_status=RunStatus.REPRODUCING,
                reason="Starting model reproduction planning and execution",
                actor="worker",
            )

            # 3. Compile safe structured test
            repo_root = Path(__file__).resolve().parent.parent.parent
            runs_dir = repo_root / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)

            ss_out_path = str(runs_dir / f"ss_before_{run_id}.png")
            test_code, test_sha256 = self.planner.compiler.compile(
                plan=plan,
                test_name=f"repro-{run_id[:8]}",
                screenshot_path=ss_out_path,
            )

            test_file_path = str(runs_dir / f"test_{run_id}.spec.js")
            with open(test_file_path, "w", encoding="utf-8") as f:
                f.write(test_code)

            # 4. Start app process with sanitized environment and ephemeral port
            repo_root = Path(__file__).resolve().parent.parent.parent
            if not os.path.isabs(manifest.app_dir):
                app_full_dir = str(repo_root / manifest.app_dir)
            else:
                app_full_dir = manifest.app_dir
            safe_env = get_sanitized_runner_env(allocated_port)

            server_proc = subprocess.Popen(
                manifest.start_command.split(),
                cwd=app_full_dir,
                env=safe_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Wait for server ready
            verifier = FreshCopyVerifier(manifest, self.limits)
            if not verifier._wait_for_server(allocated_port, timeout_seconds=manifest.startup_timeout_seconds):
                self.controller.transition(
                    run_id=run_id,
                    to_status=RunStatus.ENVIRONMENT_ERROR,
                    reason="Target app server failed to become ready on ephemeral port.",
                    actor="runner",
                )
                return RunStatus.ENVIRONMENT_ERROR, test_code, test_sha256, "Server failed to start."

            # 5. Run Playwright test with forward-slashed relative path (Playwright treats backslashes as regex escapes)
            rel_test_path = os.path.relpath(test_file_path, str(repo_root)).replace("\\", "/")
            run_cmd = f'npx.cmd playwright test "{rel_test_path}"'
            test_proc = subprocess.run(
                run_cmd,
                shell=True,
                cwd=str(repo_root),
                env=safe_env,
                capture_output=True,
                text=True,
                timeout=self.limits.browser_test_timeout_seconds,
            )

            # 6. Classify test result
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

        except Exception as e:
            # Prevent runs from getting stuck in REPRODUCING
            current_run = self.controller.get_run(run_id)
            if current_run and current_run.status == RunStatus.REPRODUCING:
                self.controller.transition(
                    run_id=run_id,
                    to_status=RunStatus.ENVIRONMENT_ERROR,
                    reason=f"Reproduction job crashed: {str(e)}",
                    actor="runner",
                )
            raise

        finally:
            if server_proc:
                kill_process_tree(server_proc)

    def run_repair_and_verify_job(
        self,
        run_id: str,
        report_text: str,
        frozen_test_code: str,
        frozen_test_sha256: str,
        failing_assertion: str,
        mock_patch: Optional[PatchProposal] = None,
        port: Optional[int] = None,
    ) -> Tuple[RunStatus, str]:
        """Executes patch generation and clean verification.

        Hard Rule 2: Never called before human approval.
        Only allowed when run is in PATCHING state.
        Guarantees cleanup and terminal state on exceptions.
        """
        run = self.controller.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")

        if run.status != RunStatus.PATCHING:
            raise RuntimeError(
                f"Cannot execute repair: run is in state {run.status.value}. Must be in 'patching' state."
            )

        repo_root = Path(__file__).resolve().parent.parent.parent
        manifest = self.planner.load_manifest(run.app_id)
        verifier = FreshCopyVerifier(manifest, self.limits)

        # Read allowed source files for model context
        source_files: Dict[str, str] = {}
        if not os.path.isabs(manifest.app_dir):
            app_dir = str(repo_root / manifest.app_dir)
        else:
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
            self.controller.record_patch(run_id, patch)

            # Transition to verifying
            self.controller.transition(
                run_id=run_id,
                to_status=RunStatus.VERIFYING,
                reason=f"Attempt {attempt}: verifying proposed patch on clean app copy",
                actor="worker",
            )

            try:
                # Clean verification on fresh copy with ephemeral port
                v_res = verifier.verify_patch(
                    app_source_dir=manifest.app_dir,
                    patch_proposal=patch,
                    frozen_test_code=frozen_test_code,
                    expected_test_sha256=frozen_test_sha256,
                    port=port or find_free_port(),
                )
                print("\n[V_RES]:", v_res.status, v_res.details)
                print("[V_RES STDOUT]:\n", v_res.stdout)
                print("[V_RES STDERR]:\n", v_res.stderr)

                # Record verification evidence in controller
                updated_run = self.controller.record_verification_result(
                    run_id=run_id,
                    passed_frozen_test=v_res.passed_frozen_test,
                    passed_regression=v_res.passed_regression,
                    actual_test_sha256=v_res.test_sha256,
                    details=v_res.details,
                    stdout=v_res.stdout,
                    stderr=v_res.stderr,
                )

                if updated_run.status == RunStatus.PASSES_FROZEN_TEST:
                    return RunStatus.PASSES_FROZEN_TEST, "Verification passed successfully."

            except Exception as e:
                # If verifier raised an exception, record failure
                if attempt >= max_attempts:
                    self.controller.transition(
                        run_id=run_id,
                        to_status=RunStatus.UNRESOLVED,
                        reason=f"Verification crashed on final attempt: {str(e)}",
                        actor="worker",
                    )
                    return RunStatus.UNRESOLVED, f"Verification crashed: {str(e)}"
                else:
                    self.controller.transition(
                        run_id=run_id,
                        to_status=RunStatus.PATCHING,
                        reason=f"Verification attempt {attempt} failed: {str(e)}. Retrying.",
                        actor="worker",
                    )

        # Reached attempt limit without success
        current_run = self.controller.get_run(run_id)
        if current_run and current_run.status != RunStatus.UNRESOLVED:
            self.controller.transition(
                run_id=run_id,
                to_status=RunStatus.UNRESOLVED,
                reason=f"All {max_attempts} patch attempts failed fresh verification.",
                actor="verifier",
            )
        return RunStatus.UNRESOLVED, "All patch attempts failed."
