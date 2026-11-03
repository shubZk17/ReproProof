"""Worker Execution Pipeline for ReproProof.

Runs reproduction and repair jobs on ephemeral ports with a scrubbed environment and
process-tree cleanup. All state changes go through the controller; verification is
executed by `RunController.run_verification`, never asserted by this module.

NOT A SANDBOX: the app and tests run as the current OS user (see README "Execution boundary").
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
from typing import Dict, Optional, Tuple

from reproproof.core.controller import RunController
from reproproof.core.evidence import EvidenceExporter
from reproproof.core.limits import DEFAULT_LIMITS, RunLimits
from reproproof.core.model_adapter import MetaModelClient
from reproproof.core.planner import ReproductionPlanner
from reproproof.core.proc_utils import find_free_port, get_sanitized_runner_env, kill_process_tree
from reproproof.core.schemas import ActionPlan, ModelMode, PatchProposal, RunStatus
from reproproof.core.verifier import REPO_ROOT, RUNS_DIR, FreshCopyVerifier, resolve_app_dir


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
        self.evidence_exporter = EvidenceExporter(controller=self.controller)

    @property
    def model_mode(self) -> ModelMode:
        return ModelMode.MOCK_MODEL if self.model_client.is_mock else ModelMode.LIVE_MODEL

    def _check_mode(self, run) -> None:
        if run.model_mode != self.model_mode:
            raise RuntimeError(
                f"Run was created as {run.model_mode.value} but this runner is {self.model_mode.value}; refusing."
            )

    def run_reproduction_job(
        self,
        run_id: str,
        mock_plan: Optional[ActionPlan] = None,
        port: Optional[int] = None,
    ) -> Tuple[RunStatus, str, str, str]:
        """received -> reproducing -> awaiting_test_approval | not_reproduced | environment_error."""
        run = self.controller.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")
        self._check_mode(run)

        server_proc = None
        test_file_path = RUNS_DIR / f"test_{run_id}.spec.js"
        capture_path = str(RUNS_DIR / f"capture_{run_id}.png")
        allocated_port = port or find_free_port()

        try:
            manifest = self.planner.load_manifest(run.app_id)
            plan, model_id, in_tokens, out_tokens = self.planner.plan(
                app_id=run.app_id, report_text=run.report_text, mock_plan=mock_plan,
            )
            self.controller.record_usage(run_id, in_tokens, out_tokens,
                                         cost_usd=(in_tokens * 0.0000015 + out_tokens * 0.000002), model_id=model_id)
            self.controller.record_plan(run_id, plan)

            if plan.clarification_question:
                self.controller.transition(run_id, RunStatus.CLARIFICATION_REQUIRED,
                                           reason=plan.clarification_question, actor="model")
                return RunStatus.CLARIFICATION_REQUIRED, "", "", plan.clarification_question

            self.controller.transition(run_id, RunStatus.REPRODUCING,
                                       reason="Executing reproduction test", actor="worker")

            RUNS_DIR.mkdir(parents=True, exist_ok=True)
            test_code, test_sha256 = self.planner.compiler.compile(
                plan=plan, test_name=f"repro-{run_id[:8]}", screenshot_path=capture_path,
            )
            test_file_path.write_text(test_code, encoding="utf-8")

            safe_env = get_sanitized_runner_env(allocated_port)
            server_proc = subprocess.Popen(
                manifest.start_command.split(),
                cwd=resolve_app_dir(manifest.app_dir),
                env=safe_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if not FreshCopyVerifier(manifest, self.limits)._wait_for_server(
                allocated_port, timeout_seconds=manifest.startup_timeout_seconds
            ):
                self.controller.transition(run_id, RunStatus.ENVIRONMENT_ERROR,
                                           reason="Target app server failed to become ready on ephemeral port.",
                                           actor="runner")
                return RunStatus.ENVIRONMENT_ERROR, test_code, test_sha256, "Server failed to start."

            # Forward slashes: Playwright treats backslashes in the filter as regex escapes.
            rel_test_path = os.path.relpath(test_file_path, REPO_ROOT).replace("\\", "/")
            test_proc = subprocess.run(
                f'npx.cmd playwright test "{rel_test_path}"', shell=True, cwd=str(REPO_ROOT), env=safe_env,
                capture_output=True, text=True, timeout=self.limits.browser_test_timeout_seconds,
            )

            # Copy the capture to an immutable reproduction path; later runs of the frozen test
            # (verification) write to capture_path and must never touch this file.
            repro_ss_path = None
            if os.path.exists(capture_path):
                repro_ss_path = str(RUNS_DIR / f"repro_{run_id}.png")
                shutil.copy2(capture_path, repro_ss_path)
                os.remove(capture_path)

            self.controller.record_reproduction(
                run_id,
                test_code=test_code,
                screenshot_path=repro_ss_path,
                screenshot_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                logs=test_proc.stdout + "\n" + test_proc.stderr,
            )

            classification = self.planner.classify_test_result(
                exit_code=test_proc.returncode, stdout=test_proc.stdout, stderr=test_proc.stderr,
                intended_assertion=plan.assertions[0].action if plan.assertions else None,
            )
            self.controller.transition(run_id, classification.status, reason=classification.reason, actor="runner")
            return classification.status, test_code, test_sha256, classification.reason

        except Exception as e:
            current = self.controller.get_run(run_id)
            if current and current.status == RunStatus.REPRODUCING:
                self.controller.transition(run_id, RunStatus.ENVIRONMENT_ERROR,
                                           reason=f"Reproduction job crashed: {e}", actor="runner")
            raise

        finally:
            if server_proc:
                kill_process_tree(server_proc)
            test_file_path.unlink(missing_ok=True)

    def run_repair_and_verify_job(
        self,
        run_id: str,
        mock_patch: Optional[PatchProposal] = None,
    ) -> Tuple[RunStatus, str]:
        """patching -> verifying -> passes_frozen_test | patching (retry) | unresolved.

        Only runs after human approval (state PATCHING). The frozen test, report and
        failing assertion are read from the controller record, not from the caller.
        """
        run = self.controller.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found.")
        if run.status != RunStatus.PATCHING:
            raise RuntimeError(f"Cannot execute repair: run is in state {run.status.value}. Must be 'patching'.")
        self._check_mode(run)

        manifest = self.planner.load_manifest(run.app_id)
        plan = json.loads(run.plan_json) if run.plan_json else {}
        failing_assertion = json.dumps(plan.get("assertions", []))

        app_dir = resolve_app_dir(manifest.app_dir)
        source_files: Dict[str, str] = {}
        for allowed in manifest.allowed_source_paths:
            full_path = os.path.join(app_dir, allowed)
            paths = [os.path.join(r, f) for r, _, fs in os.walk(full_path) for f in fs] if os.path.isdir(full_path) \
                else ([full_path] if os.path.isfile(full_path) else [])
            for p in paths:
                with open(p, "r", encoding="utf-8") as sfile:
                    source_files[os.path.relpath(p, app_dir).replace("\\", "/")] = sfile.read()

        try:
            for attempt in range(1, self.limits.max_patch_attempts + 1):
                self.controller.record_patch_attempt(run_id)
                patch, model_id, in_t, out_t = self.model_client.propose_patch(
                    attempt=attempt, report_text=run.report_text, failing_test_code=run.frozen_test_code,
                    failing_assertion=failing_assertion, source_files=source_files, mock_patch=mock_patch,
                )
                self.controller.record_usage(run_id, in_t, out_t,
                                             cost_usd=(in_t * 0.0000015 + out_t * 0.000002), model_id=model_id)
                self.controller.record_patch(run_id, patch)
                self.controller.transition(run_id, RunStatus.VERIFYING,
                                           reason=f"Attempt {attempt}: verifying patch on clean app copy",
                                           actor="worker")
                updated = self.controller.run_verification(run_id)
                if updated.status != RunStatus.PATCHING:
                    return updated.status, updated.status_reason or ""
        except Exception as e:
            current = self.controller.get_run(run_id)
            if current and current.status in (RunStatus.PATCHING, RunStatus.VERIFYING):
                self.controller.transition(run_id, RunStatus.UNRESOLVED,
                                           reason=f"Repair job crashed: {type(e).__name__}: {e}", actor="worker")
                return RunStatus.UNRESOLVED, f"Repair job crashed: {e}"
            raise

        current = self.controller.get_run(run_id)
        if current.status == RunStatus.PATCHING:
            self.controller.transition(run_id, RunStatus.UNRESOLVED,
                                       reason="Patch attempt budget exhausted.", actor="worker")
        return RunStatus.UNRESOLVED, "All patch attempts failed."
