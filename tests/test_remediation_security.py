"""Path boundary and navigation validation (adversarial)."""

import os

import pytest

from reproproof.core.compiler import PlaywrightCompiler
from reproproof.core.patcher import PatchValidationError, PatchValidator
from reproproof.core.schemas import ActionPlan, ActionStep, AppManifest, PatchProposal


@pytest.fixture
def validator():
    return PatchValidator(AppManifest(
        app_id="test-app", base_url="http://localhost:3000", start_command="node server.js",
        app_dir="apps/test-app", allowed_source_paths=["src/"], protected_paths=["src/protected.js"],
    ))


def _diff(path):
    return PatchProposal(explanation="t", unified_diff=f"--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,1 @@\n-a\n+b\n")


def test_allowed_source_file_accepted(validator):
    assert validator.validate_patch(_diff("src/file.js")) == ["src/file.js"]


@pytest.mark.parametrize("path", [
    "srcX/evil.js", "src_evil/file.js", "src", "/etc/passwd", "C:/Windows/evil.js", "\\\\host\\share\\x.js",
    "src/../package.json", "../outside.js", "src/../../x.js", "src/protected.js", "package.json",
    ".git/config", "protected-tests/regression.spec.js",
])
def test_unsafe_paths_rejected(validator, path):
    with pytest.raises(PatchValidationError):
        validator.validate_patch(_diff(path))


def test_symlink_escape_rejected(validator, tmp_path):
    (tmp_path / "src").mkdir()
    outside = tmp_path.parent / "outside_target"
    outside.mkdir(exist_ok=True)
    try:
        os.symlink(outside, tmp_path / "src" / "link", target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted on this host")
    with pytest.raises(PatchValidationError):
        validator.validate_patch(_diff("src/link/evil.js"), base_dir=str(tmp_path))


@pytest.mark.parametrize("path", [
    "//evil.example/x", "/\\evil.example/x", "\\evil.example\\x", "/\t/evil.example/x", "/\n/evil.example",
    "http://evil.example", "javascript:alert(1)", "evil.example", "/ x", "",
])
def test_external_or_protocol_relative_navigation_rejected(path):
    with pytest.raises(ValueError, match="relative URL"):
        ActionStep(action="goto", path=path)


@pytest.mark.parametrize("path", ["/", "/items", "/a/b?c=1#d", "/%2Fx"])
def test_same_origin_navigation_accepted(path):
    assert ActionStep(action="goto", path=path).path == path


def test_driver_enforces_same_origin_at_runtime():
    code, _ = PlaywrightCompiler().compile(ActionPlan(expected_behavior="xxxxx", steps=[{"action": "goto", "path": "/"}]))
    assert "targetUrl.origin !== new URL(baseURL).origin" in code
