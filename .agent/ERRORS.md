# ERRORS.md — Failure & Debugging Registry

Check this file before debugging anything that looks familiar. Don't retry an approach listed here as failed.

Template:
```markdown
## ERR-NNN: <short description>
Date: YYYY-MM-DD · Status: Resolved | Open | Workaround
- Symptom / message:
- Root cause:
- Resolution:
- Prevention:
- Failed approaches:
- Related: files, DEC-NNN, TASK-NNN
```

---
## ERR-001: Screenshot preservation silently never ran
Date: 2026-11-03 · Status: Resolved
- Symptom: the reproduction screenshot was overwritten by verification even though TASK-023 was marked done.
- Root cause: the verifier's regex `"screenshot_path":\s*"..."` never matches the double-JSON-encoded plan (`\"screenshot_path\": ...`) in compiled tests.
- Resolution: `PlaywrightCompiler.extract_plan()` decodes the plan; the runner copies the capture to the immutable `runs/repro_<id>.png`; covered by a real-browser e2e assertion.
- Prevention: assert behaviour in a real run, not with a simulated file-copy test.
- Related: DEC-005, TASK-025

## ERR-002: Verify temp dirs leaked on Windows
Date: 2026-11-03 · Status: Resolved
- Symptom: one `%TEMP%\reproproof_verify_*` dir left per verification.
- Root cause: git object files are read-only; `shutil.rmtree(ignore_errors=True)` silently skips them.
- Resolution: `proc_utils.force_rmtree` (chmod on error) in patcher and verifier.
- Related: L-004
