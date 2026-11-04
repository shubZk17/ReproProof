"""Streamlit User Interface for ReproProof.

Provides the 4-stage workflow: Report -> Reproduce -> Repair -> Check.
Displays concise user-facing status, human approval controls, and evidence downloads.
Strictly derived from actual controller-owned run records without hard-coding.
"""

from __future__ import annotations

import glob
import json
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # entry point only: picks up MODEL_API_KEY from a local, gitignored .env
import yaml

from reproproof.core.controller import RunController
from reproproof.core.limits import DEFAULT_LIMITS
from reproproof.core.model_adapter import MOCK_SCRIPTED_REPORT, MetaModelClient
from reproproof.core.schemas import ActionPlan, ModelMode, PatchProposal, RunStatus
from reproproof.worker.runner import JobRunner
from reproproof.core.evidence import EvidenceExporter


st.set_page_config(
    page_title="ReproProof — Bug Reproduction & Fresh-Copy Checking",
    page_icon="🛡️",
    layout="wide",
)

# Custom header styling
st.markdown("""
<style>
    .main-title { font-size: 2.2rem; font-weight: 700; color: #1e293b; margin-bottom: 0.2rem; }
    .subtitle { color: #64748b; font-size: 1.05rem; margin-bottom: 1.5rem; }
    .stage-card { padding: 1.2rem; border-radius: 8px; background: #f8fafc; border: 1px solid #e2e8f0; margin-bottom: 1rem; }
    .badge-status { padding: 0.3rem 0.6rem; border-radius: 4px; font-weight: 600; font-size: 0.85rem; }
    .badge-success { background: #dcfce7; color: #166534; }
    .badge-warn { background: #fef9c3; color: #854d0e; }
    .badge-fail { background: #fee2e2; color: #991b1b; }
    .badge-mock { background: #ffedd5; color: #9a3412; font-weight: bold; }
    .badge-live { background: #e0e7ff; color: #3730a3; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🛡️ ReproProof</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Browser test reproduction · Human test freeze · Source-only repair · Fresh-copy verification</div>', unsafe_allow_html=True)

# Initialize controller and runner in session state
if "controller" not in st.session_state:
    st.session_state.controller = RunController()
if "runner" not in st.session_state:
    st.session_state.runner = JobRunner(controller=st.session_state.controller)
if "current_run_id" not in st.session_state:
    st.session_state.current_run_id = None
if "evidence_zip" not in st.session_state:
    st.session_state.evidence_zip = None

controller: RunController = st.session_state.controller
runner: JobRunner = st.session_state.runner

# Sidebar: Manifests and Environment
st.sidebar.title("Configuration")
manifest_files = glob.glob("apps/manifests/*.yaml")
manifests = {}
for mf in manifest_files:
    with open(mf, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        manifests[data["app_id"]] = data

selected_app_id = st.sidebar.selectbox(
    "Allowlisted Application",
    options=list(manifests.keys()),
    format_func=lambda x: f"{manifests[x].get('name', x)} ({x})"
)

app_info = manifests[selected_app_id]
st.sidebar.info(f"**Base URL:** {app_info.get('base_url')}\n\n**Allowed Paths:** {', '.join(app_info.get('allowed_source_paths', []))}")

# Mode info (taken from the runner's actual client, not guessed from the environment)
is_mock = runner.model_client.is_mock
if not is_mock:
    st.sidebar.success("🟢 **LIVE MODEL** (`muse-spark-1.3`)")
    st.sidebar.caption("Model-generated patches are NOT executed on this host unless "
                       "REPROPROOF_ALLOW_UNSANDBOXED_HOST_EXECUTION=1 is set. There is no sandbox.")
else:
    st.sidebar.error("⚠️ **MOCK MODEL — NO AI**")
    st.sidebar.caption("MODEL_API_KEY is not set. No AI model is called. Plan and patch are hand-written templates.")

st.sidebar.markdown("---")
st.sidebar.markdown("### Hard Rules Active")
st.sidebar.caption("✓ Models only propose — controller owns run state\n\n✓ Human approval required before patching\n\n✓ Tests frozen with SHA-256\n\n✓ Source-only patches (no tests/configs)\n\n✓ Success only via `passes_frozen_test` on clean copy\n\n⚠ Not a sandbox: trusted demo apps only")


# --- Main 4-Stage Flow: Report -> Reproduce -> Repair -> Check ---

tab_pipeline, tab_evals, tab_audit = st.tabs(["⚡ Execution Pipeline", "📊 Benchmark Evals", "📜 Audit & Runs"])

with tab_pipeline:
    if is_mock:
        st.error("🟧 **MOCK MODEL — DEMO MODE, NO AI MODEL IS CALLED.** The reproduction plan and the patch "
                 "are hand-written templates for one scripted inventory-demo bug. The browser run, `git apply`, "
                 "fresh-copy check and regression suite are real. This is **not** an AI repair result.")

    stage_col1, stage_col2, stage_col3, stage_col4 = st.columns(4)

    run_record = controller.get_run(st.session_state.current_run_id) if st.session_state.current_run_id else None
    current_status = run_record.status.value if run_record else "No active run"

    with stage_col1:
        st.markdown("**1. Report**")
        st.caption("Intake & expected behavior")
    with stage_col2:
        st.markdown("**2. Reproduce**")
        st.caption("Constrained test synthesis")
    with stage_col3:
        st.markdown("**3. Repair**")
        st.caption("Human approval & patch")
    with stage_col4:
        st.markdown("**4. Check**")
        st.caption("Clean fresh-copy verification")

    st.markdown("---")

    # Current Status Banner
    if run_record:
        status_color = "badge-success" if run_record.status == RunStatus.PASSES_FROZEN_TEST else (
            "badge-warn" if "awaiting" in run_record.status.value or "patching" in run_record.status.value else "badge-fail"
        )
        mode_badge = "badge-mock" if run_record.model_mode == ModelMode.MOCK_MODEL else "badge-live"
        st.markdown(
            f'**Run ID:** `{run_record.run_id}` | '
            f'**Mode:** <span class="badge-status {mode_badge}">{run_record.model_mode.value}</span> | '
            f'**Status:** <span class="badge-status {status_color}">{run_record.status.value.upper()}</span> | '
            f'**Regression:** `{run_record.regression_status.value}` | '
            f'**Cost:** `${run_record.usage.cost_usd:.4f}` | **Attempts:** `{run_record.patch_attempts}/2`',
            unsafe_allow_html=True,
        )
        if run_record.status_reason:
            st.info(f"**Latest Event:** {run_record.status_reason}")

    # Stage 1: Report Intake
    with st.expander("Stage 1: Bug Report Intake", expanded=(run_record is None or run_record.status == RunStatus.RECEIVED)):
        report_text = st.text_area(
            "Bug Report Description", value=MOCK_SCRIPTED_REPORT, height=90, disabled=is_mock,
            help="Mock mode only supports this scripted report." if is_mock else None,
        )

        if st.button("Start Reproduction", type="primary"):
            new_run = controller.create_run(app_id=selected_app_id, model_mode=runner.model_mode,
                                            report_text=report_text)
            st.session_state.current_run_id = new_run.run_id
            with st.spinner("Planning and running the reproduction test in Chromium..."):
                runner.run_reproduction_job(run_id=new_run.run_id)
            st.rerun()

    # Stage 2: Reproduction Results & Human Approval Gate
    if run_record and run_record.status in [
        RunStatus.AWAITING_TEST_APPROVAL,
        RunStatus.NOT_REPRODUCED,
        RunStatus.ENVIRONMENT_ERROR,
        RunStatus.TEST_REJECTED,
        RunStatus.PATCHING,
        RunStatus.VERIFYING,
        RunStatus.PASSES_FROZEN_TEST,
        RunStatus.UNRESOLVED,
    ]:
        with st.expander("Stage 2: Reproduction & Test Approval", expanded=(run_record.status == RunStatus.AWAITING_TEST_APPROVAL)):
            st.markdown("### Synthesized Playwright Test")
            st.code(run_record.reproduced_test_code or "// No reproduction test was executed", language="javascript")

            if run_record.test_sha256:
                st.success(f"🔒 **Frozen Test SHA-256:** `{run_record.test_sha256}`")

            # Human Approval Gate (PRD R5)
            if run_record.status == RunStatus.AWAITING_TEST_APPROVAL:
                st.warning("⚠️ **Human-in-the-Loop Approval Required:** Verify that the test above accurately describes the reported defect. No patch model can be called before your approval.")

                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button("✅ Approve Test (Freeze Test & Proceed to Repair)", type="primary"):
                        # Binds approval to the exact test shown above (controller re-checks the hash).
                        controller.record_human_approval(
                            run_id=run_record.run_id,
                            test_sha256=run_record.reproduced_test_sha256 or "",
                            frozen_test_code=run_record.reproduced_test_code,
                            approved_by="human_operator",
                        )
                        st.rerun()
                with c2:
                    if st.button("❌ Reject Test (Halt Run)"):
                        controller.record_human_rejection(
                            run_id=run_record.run_id,
                            reason="Human operator rejected test as inaccurate.",
                        )
                        st.rerun()

    # Stage 3 & 4: Repair & Clean Verification
    if run_record and run_record.status in [
        RunStatus.PATCHING,
        RunStatus.VERIFYING,
        RunStatus.PASSES_FROZEN_TEST,
        RunStatus.UNRESOLVED,
    ]:
        with st.expander("Stage 3 & 4: Source-Only Repair & Clean Verification", expanded=True):
            if run_record.status == RunStatus.PATCHING:
                st.info("Test is frozen. Ready to generate source-only patch and verify on fresh app copy.")
                if st.button("Generate Patch & Verify on Clean Copy", type="primary"):
                    with st.spinner("Generating source patch and verifying on fresh temp copy..."):
                        runner.run_repair_and_verify_job(run_id=run_record.run_id)
                    st.rerun()

            if run_record.patch_diff:
                kind = ("hand-written mock template" if run_record.model_mode == ModelMode.MOCK_MODEL
                        else "model-proposed")
                st.markdown(f"### Patch ({kind})")
                st.code(run_record.patch_diff, language="diff")

            if run_record.status == RunStatus.PASSES_FROZEN_TEST:
                msg = ("**PASSES_FROZEN_TEST:** the byte-identical frozen test and the protected regression "
                       "suite both passed on a fresh patched copy.")
                if run_record.model_mode == ModelMode.MOCK_MODEL:
                    msg += " The patch was a **hand-written mock template**, not AI-generated."
                st.success(msg)
            elif run_record.status == RunStatus.UNRESOLVED:
                st.error(f"**UNRESOLVED:** {run_record.status_reason or ''}")

    # Evidence bundle for any run that reached a terminal state
    if run_record and run_record.status in [
        RunStatus.PASSES_FROZEN_TEST, RunStatus.UNRESOLVED, RunStatus.NOT_REPRODUCED,
        RunStatus.ENVIRONMENT_ERROR, RunStatus.TEST_REJECTED, RunStatus.CLARIFICATION_REQUIRED,
    ]:
        bundle = runner.evidence_exporter.create_bundle_from_run(run_id=run_record.run_id)
        if bundle.evidence_valid:
            st.caption("Evidence integrity checks: all stored artifacts match their recorded hashes.")
        else:
            st.error("Evidence integrity FAILED: " + "; ".join(bundle.integrity_failures))
        st.json(bundle.check_results)
        zip_path = runner.evidence_exporter.export_zip(bundle)
        with open(zip_path, "rb") as zf:
            st.download_button(
                label=f"📦 Download Evidence Bundle (ZIP, {run_record.model_mode.value})",
                data=zf.read(),
                file_name=f"reproproof_bundle_{run_record.run_id[:8]}_{run_record.model_mode.value}.zip",
                mime="application/zip",
            )

# Tab 2: Benchmark Evaluation View (R14)
with tab_evals:
    st.markdown("### 📊 Measured Benchmark Evaluation")
    st.caption("Rule 7: Never invent metrics. Report measured results with denominators, including failures.")

    eval_results_file = "evals/results/latest_run.json"
    if os.path.exists(eval_results_file):
        with open(eval_results_file, "r", encoding="utf-8") as ef:
            eval_data = json.load(ef)

        metrics = eval_data.get("metrics", {})
        if eval_data.get("model_mode") == "MOCK_MODEL":
            st.error("These results were produced in MOCK_MODEL mode with hand-written plans and patches. "
                     "They measure the pipeline's controls, not AI repair ability.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Reproduction Rate", metrics.get("reproduction_rate", "N/A"))
        c2.metric("Repair Rate (passes_frozen_test)", metrics.get("repair_rate", "N/A"))
        c3.metric("Control Handling", metrics.get("control_handling", "N/A"))
        c4.metric("False Success Rate", metrics.get("false_success_rate", "N/A"))
        st.caption(f"Model mode: **{eval_data.get('model_mode', 'UNKNOWN')}**")

        st.json(eval_data)
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Reproduction Rate", "NOT RUN")
        c2.metric("Repair Rate", "NOT RUN")
        c3.metric("Control Handling", "NOT RUN")
        c4.metric("False Success Rate", "NOT RUN")
        st.info("Run `python evals/run_eval.py` to execute the complete evaluation suite against hidden checks.")

# Tab 3: Audit & Run History
with tab_audit:
    st.markdown("### 📜 Run History & State Transitions")
    runs_rows = controller.list_runs()
    if runs_rows:
        st.table(runs_rows)
    else:
        st.caption("No runs recorded yet.")
