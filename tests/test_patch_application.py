"""Unit tests verifying patch validation and git-backed application."""

import os
import shutil
import tempfile
import pytest

from reproproof.core.schemas import AppManifest, PatchProposal
from reproproof.core.patcher import PatchValidator, PatchValidationError


@pytest.fixture
def test_manifest():
    return AppManifest(
        app_id="test-app",
        base_url="http://localhost:3000",
        start_command="node server.js",
        app_dir="apps/test-app",
        allowed_source_paths=["src/"],
        protected_paths=["package.json", "tests/", "playwright.config.ts"],
    )


@pytest.fixture
def temp_workspace(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    sample_file = src_dir / "app.js"
    sample_file.write_text(
        "function deleteItem(id) {\n"
        "  // Buggy deletion\n"
        "  items.splice(0, 1);\n"
        "  return items;\n"
        "}\n",
        encoding="utf-8",
    )
    return str(tmp_path)


def test_patch_path_traversal_rejected(test_manifest, temp_workspace):
    validator = PatchValidator(test_manifest)
    diff = (
        "--- a/src/../package.json\n"
        "+++ b/src/../package.json\n"
        "@@ -1,2 +1,2 @@\n"
        "-bad\n"
        "+good\n"
    )
    with pytest.raises(PatchValidationError, match="Path traversal detected"):
        validator.apply_diff_to_directory(temp_workspace, diff)


def test_patch_absolute_path_rejected(test_manifest, temp_workspace):
    validator = PatchValidator(test_manifest)
    diff = (
        "--- /etc/passwd\n"
        "+++ /etc/passwd\n"
        "@@ -1,1 +1,1 @@\n"
        "-root\n"
        "+hacked\n"
    )
    with pytest.raises(PatchValidationError, match="Absolute path detected"):
        validator.apply_diff_to_directory(temp_workspace, diff)


def test_patch_protected_file_rejected(test_manifest, temp_workspace):
    validator = PatchValidator(test_manifest)
    diff = (
        "--- a/package.json\n"
        "+++ b/package.json\n"
        "@@ -1,1 +1,1 @@\n"
        "-a\n"
        "+b\n"
    )
    with pytest.raises(PatchValidationError, match="forbidden protected path"):
        validator.validate_patch(PatchProposal(explanation="Edit pkg", unified_diff=diff))


def test_patch_outside_allowed_paths_rejected(test_manifest, temp_workspace):
    validator = PatchValidator(test_manifest)
    diff = (
        "--- a/config/db.js\n"
        "+++ b/config/db.js\n"
        "@@ -1,1 +1,1 @@\n"
        "-a\n"
        "+b\n"
    )
    with pytest.raises(PatchValidationError, match="outside allowed source paths"):
        validator.validate_patch(PatchProposal(explanation="Edit config", unified_diff=diff))


def test_patch_mismatched_context_rejected(test_manifest, temp_workspace):
    validator = PatchValidator(test_manifest)
    # Target line does not exist in src/app.js
    diff = (
        "--- a/src/app.js\n"
        "+++ b/src/app.js\n"
        "@@ -1,3 +1,3 @@\n"
        " function completelyDifferent() {\n"
        "-  oldCode();\n"
        "+  newCode();\n"
        " }\n"
    )
    with pytest.raises(PatchValidationError, match="Git apply pre-check failed"):
        validator.apply_diff_to_directory(temp_workspace, diff)


def test_patch_pure_addition_hunk(test_manifest, temp_workspace):
    validator = PatchValidator(test_manifest)
    diff = (
        "--- a/src/app.js\n"
        "+++ b/src/app.js\n"
        "@@ -5,0 +5,3 @@\n"
        "+function helper() {\n"
        "+  return true;\n"
        "+}\n"
    )
    validator.apply_diff_to_directory(temp_workspace, diff)

    content = open(os.path.join(temp_workspace, "src", "app.js")).read()
    assert "function helper()" in content


def test_patch_crlf_handling(test_manifest, temp_workspace):
    # Write CRLF file
    file_path = os.path.join(temp_workspace, "src", "app.js")
    with open(file_path, "wb") as f:
        f.write(b"function test() {\r\n  return 1;\r\n}\r\n")

    validator = PatchValidator(test_manifest)
    diff = (
        "--- a/src/app.js\n"
        "+++ b/src/app.js\n"
        "@@ -1,3 +1,3 @@\n"
        " function test() {\n"
        "-  return 1;\n"
        "+  return 2;\n"
        " }\n"
    )
    validator.apply_diff_to_directory(temp_workspace, diff)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "return 2;" in content


def test_patch_successful_application(test_manifest, temp_workspace):
    validator = PatchValidator(test_manifest)
    diff = (
        "--- a/src/app.js\n"
        "+++ b/src/app.js\n"
        "@@ -1,5 +1,5 @@\n"
        " function deleteItem(id) {\n"
        "   // Buggy deletion\n"
        "-  items.splice(0, 1);\n"
        "+  items = items.filter(item => item.id !== id);\n"
        "   return items;\n"
        " }\n"
    )
    validator.apply_diff_to_directory(temp_workspace, diff)

    content = open(os.path.join(temp_workspace, "src", "app.js")).read()
    assert "items.filter(item => item.id !== id)" in content
    assert "items.splice(0, 1)" not in content
