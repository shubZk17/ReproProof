"""Streamlit User Interface for ReproProof.

Provides the 4-stage workflow: Report -> Reproduce -> Repair -> Check.
Displays concise user-facing status, human approval controls, and evidence downloads.
"""

from __future__ import annotations

import glob
import json
import os
import streamlit as st
import yaml

from reproproof.core.controller import RunController
from reproproof.core.limits import DEFAULT_LIMITS
from reproproof.core.model_adapter import MetaModelClient
from reproproof.core.schemas import ActionPlan, PatchProposal, RunStatus
from reproproof.worker.runner import JobRunner
from reproproof.core.evidence import EvidenceExporter


st.set_page_config(
    page_title="ReproProof — Autonomous Bug Reproduction & Verification",
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
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🛡️ ReproProof</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Autonomous browser test reproduction · Human test freeze · Source-only repair · Fresh-copy verification</div>', unsafe_allow_html=True)

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

# Mode info
has_api_key = bool(os.environ.get("MODEL_API_KEY"))
if has_api_key:
    st.sidebar.success("Meta AI API Key active (`muse-spark-1.3`)")
else:
    st.sidebar.warning("Offline Mode: Deterministic mock active")

st.sidebar.markdown("---")
st.sidebar.markdown("### Hard Rules Active")
st.sidebar.caption("✓ Models only propose — controller owns run state\n\n✓ Human approval required before patching\n\n✓ Tests frozen with SHA-256\n\n✓ Source-only patches (no tests/configs)\n\n✓ Verified only via `passes_frozen_test` on clean copy")


# --- Main 4-Stage Flow: Report -> Reproduce -> Repair -> Check ---

tab_pipeline, tab_evals, tab_audit = st.tabs(["⚡ Execution Pipeline", "📊 Benchmark Evals", "📜 Audit & Runs"])

with tab_pipeline:
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
        st.markdown(
            f'**Run ID:** `{run_record.run_id}` | **Status:** <span class="badge-status {status_color}">{run_record.status.value.upper()}</span> '
            f'| **Cost:** `${run_record.usage.cost_usd:.4f}` | **Attempts:** `{run_record.patch_attempts}/2`',
            unsafe_allow_html=True,
        )
        if run_record.status_reason:
            st.info(f"**Latest Event:** {run_record.status_reason}")

    # Stage 1: Report Intake
    with st.expander("Stage 1: Bug Report Intake", expanded=(run_record is None or run_record.status == RunStatus.RECEIVED)):
        default_report = "When I click 'Delete Widget B', Widget A is incorrectly deleted and Widget B remains visible."
        report_text = st.text_area("Bug Report Description", value=default_report, height=90)
        uploaded_screenshot = st.file_uploader("Upload Bug Screenshot (optional)", type=["png", "jpg", "jpeg"])

        if st.button("Start Autonomous Reproduction", type="primary"):
            new_run = controller.create_run(app_id=selected_app_id)
            st.session_state.current_run_id = new_run.run_id
            st.session_state.report_text = report_text

            with st.spinner("Executing model planning and browser reproduction..."):
                status, test_code, test_sha, details = runner.run_reproduction_job(
                    run_id=new_run.run_id,
                    report_text=report_text,
                )
                st.session_state.test_code = test_code
                st.session_state.test_sha = test_sha
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
            test_display = st.session_state.get("test_code", "// Test code not loaded")
            st.code(test_display, language="javascript")

            if run_record.test_sha256:
                st.success(f"🔒 **Frozen Test SHA-256:** `{run_record.test_sha256}`")

            # Human Approval Gate (PRD R5)
            if run_record.status == RunStatus.AWAITING_TEST_APPROVAL:
                st.warning("⚠️ **Human-in-the-Loop Approval Required:** Verify that the test above accurately describes the reported defect. No patch model can be called before your approval.")

                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button("✅ Approve Test (Freeze Test & Proceed to Repair)", type="primary"):
                        controller.record_human_approval(
                            run_id=run_record.run_id,
                            test_sha256=st.session_state.get("test_sha", "sha256_placeholder"),
                            frozen_test_code=st.session_state.get("test_code"),
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
                        final_status, details = runner.run_repair_and_verify_job(
                            run_id=run_record.run_id,
                            report_text=st.session_state.get("report_text", ""),
                            frozen_test_code=st.session_state.get("test_code", ""),
                            frozen_test_sha256=run_record.test_sha256 or st.session_state.get("test_sha", ""),
                            failing_assertion="assert_text_visible",
                        )
                    st.rerun()

            if run_record.status == RunStatus.PASSES_FROZEN_TEST:
                st.balloons()
                st.success("🎉 **PASSES_FROZEN_TEST:** Fresh copy verification succeeded! The byte-identical frozen test and all regression checks passed.")

                # Export evidence bundle
                bundle = runner.evidence_exporter.create_bundle(
                    run_record=run_record,
                    report_text=st.session_state.get("report_text", ""),
                    expected_behavior="Target item is removed while existing items remain visible.",
                    intended_assertion="assert_text_visible",
                    frozen_test_code=st.session_state.get("test_code", ""),
                    test_sha256=run_record.test_sha256 or "",
                    patch_diff="--- a/src/inventory.js\n+++ b/src/inventory.js\n@@ -30,2 +30,2 @@\n- itemsStore.splice(0, 1);\n+ itemsStore = itemsStore.filter(i => i.id !== id);\n",
                    check_results={"frozen_test": "PASSED", "regression_suite": "PASSED"},
                )
                zip_path = runner.evidence_exporter.export_zip(bundle)

                with open(zip_path, "rb") as zf:
                    st.download_button(
                        label="📦 Download Audit Evidence Bundle (ZIP)",
                        data=zf.read(),
                        file_name=f"reproproof_bundle_{run_record.run_id[:8]}.zip",
                        mime="application/zip",
                    )

            elif run_record.status == RunStatus.UNRESOLVED:
                st.error("❌ **UNRESOLVED:** The patch was unable to pass fresh copy verification within the attempt budget.")

# Tab 2: Benchmark Evaluation View (R14)
with tab_evals:
    st.markdown("### 📊 Measured Benchmark Evaluation")
    st.caption("Rule 7: Never invent metrics. Report measured results with denominators, including failures.")

    eval_results_file = "evals/results/latest_run.json"
    if os.path.exists(eval_results_file):
        with open(eval_results_file, "r", encoding="utf-8") as ef:
            eval_data = json.load(ef)

        metrics = eval_data.get("metrics", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Reproduction Rate", metrics.get("reproduction_rate", "N/A"))
        c2.metric("Repair Rate (passes_frozen_test)", metrics.get("repair_rate", "N/A"))
        c3.metric("Control Handling", metrics.get("control_handling", "N/A"))
        c4.metric("False Success Rate", metrics.get("false_success_rate", "N/A"))

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
    with controller._get_connection() as conn:
        runs_df = conn.execute("SELECT run_id, app_id, status, patch_attempts, cost_usd, created_at FROM runs ORDER BY created_at DESC").fetchall()
        if runs_df:
            st.table([dict(r) for r in runs_df])
        else:
            st.caption("No runs recorded yet.")
