"""Source-Only Patch Proposal, Boundary Validation, and Safe Application Engine.

Enforces:
- R7: Source-only patching (no tests, no package.json, no configs).
- Strict path boundaries: Rejects traversal (..), symlinks, and absolute paths.
- Reliable patch application: Uses `git apply --check` and `git apply`.
- Hard Rule: Never falls back to blind line-number deletion or insertion.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional, Set

from reproproof.core.schemas import AppManifest, PatchProposal
from reproproof.core.limits import DEFAULT_LIMITS, RunLimits


class PatchValidationError(Exception):
    """Raised when a proposed patch violates safety, path, boundary, or context rules."""
    pass


class PatchValidator:
    """Validates unified diffs against safety constraints and manifest path boundaries."""

    def __init__(self, manifest: AppManifest, limits: RunLimits = DEFAULT_LIMITS):
        self.manifest = manifest
        self.limits = limits

    def extract_touched_files(self, unified_diff: str) -> List[str]:
        """Extracts modified target file paths from unified diff headers."""
        touched: Set[str] = set()
        for line in unified_diff.splitlines():
            # Check both --- and +++ lines
            if line.startswith("+++ ") or line.startswith("--- "):
                target = line[4:].strip()
                if target.startswith("a/") or target.startswith("b/"):
                    target = target[2:]
                target = target.split("\t")[0].strip()
                if target and target != "/dev/null":
                    touched.add(target.replace("\\", "/"))
        return sorted(list(touched))

    def count_changed_lines(self, unified_diff: str) -> int:
        """Counts added and removed lines in unified diff, excluding headers."""
        count = 0
        for line in unified_diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                count += 1
            elif line.startswith("-") and not line.startswith("---"):
                count += 1
        return count

    def check_path_safety(self, base_dir: Optional[str], rel_path: str) -> str:
        """Checks for path traversal, absolute paths, and symlink escapes."""
        # 1. Absolute path check
        if os.path.isabs(rel_path) or (len(rel_path) > 1 and rel_path[1] == ":") or rel_path.startswith("/") or rel_path.startswith("\\"):
            raise PatchValidationError(f"Absolute path detected in patch: '{rel_path}'")

        # 2. Path traversal check (check both raw components and normalized)
        parts = rel_path.replace("\\", "/").split("/")
        if ".." in parts:
            raise PatchValidationError(f"Path traversal detected in patch: '{rel_path}'")

        norm = os.path.normpath(rel_path).replace("\\", "/")
        if norm.startswith("../") or norm == ".." or "/../" in norm:
            raise PatchValidationError(f"Path traversal detected in patch: '{rel_path}'")

        if base_dir and os.path.exists(base_dir):
            real_base = os.path.realpath(os.path.abspath(base_dir))
            full_path = os.path.realpath(os.path.abspath(os.path.join(base_dir, norm)))
            if not (full_path == real_base or full_path.startswith(real_base + os.sep)):
                raise PatchValidationError(f"Path escapes base directory: '{rel_path}'")

            # Check for symlinks in path components
            cur = base_dir
            for part in norm.split("/"):
                cur = os.path.join(cur, part)
                if os.path.islink(cur):
                    raise PatchValidationError(f"Symlink escape detected in path: '{cur}'")

        return norm

    def validate_patch(self, proposal: PatchProposal, base_dir: Optional[str] = None) -> List[str]:
        """Validates patch proposal strictly according to PRD R7 and Hard Rule 3.

        Raises PatchValidationError if any rule is broken.
        Returns the list of validated touched file paths.
        """
        diff = proposal.unified_diff
        touched = self.extract_touched_files(diff)

        if not touched:
            raise PatchValidationError("Patch does not modify any files.")

        # Check file count limit
        if len(touched) > self.limits.max_patch_changed_files:
            raise PatchValidationError(
                f"Patch modifies {len(touched)} files, exceeding limit of {self.limits.max_patch_changed_files}."
            )

        # Check line count limit
        changed_lines = self.count_changed_lines(diff)
        if changed_lines > self.limits.max_patch_changed_lines:
            raise PatchValidationError(
                f"Patch modifies {changed_lines} lines, exceeding limit of {self.limits.max_patch_changed_lines}."
            )

        # Universal protected filenames across all apps
        universal_protected = [
            "package.json",
            "package-lock.json",
            "playwright.config.ts",
            "playwright.config.js",
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "protected-tests",
            "evals",
            ".env",
            ".git",
        ]

        all_protected = set(self.manifest.protected_paths + universal_protected)

        for file_path in touched:
            # 1. Path safety checks (no traversal, no symlink escape, no absolute paths)
            norm_path = self.check_path_safety(base_dir, file_path)

            # 2. Must NOT touch any protected path
            for prot in all_protected:
                norm_prot = os.path.normpath(prot).replace("\\", "/")
                if norm_path == norm_prot or norm_path.startswith(norm_prot + "/"):
                    raise PatchValidationError(
                        f"Patch touches forbidden protected path: '{file_path}' (rule H-7: source-only patching)."
                    )

            # 3. Must be within allowed_source_paths
            is_allowed = False
            for allowed in self.manifest.allowed_source_paths:
                norm_allowed = os.path.normpath(allowed).replace("\\", "/")
                if norm_path.startswith(norm_allowed):
                    is_allowed = True
                    break

            if not is_allowed:
                raise PatchValidationError(
                    f"File '{file_path}' is outside allowed source paths: {self.manifest.allowed_source_paths}."
                )

        return touched

    def apply_diff_to_directory(self, target_dir: str, unified_diff: str) -> None:
        """Applies a validated unified diff to target_dir using git apply.

        Hard Rule: Never falls back to blind line-number deletion or insertion.
        If git apply fails due to context mismatch or corrupt patch, raises PatchValidationError.
        """
        # First validate paths against target_dir
        proposal = PatchProposal(explanation="Validation check", unified_diff=unified_diff)
        self.validate_patch(proposal, base_dir=target_dir)

        # Normalize line endings in diff (CRLF vs LF)
        normalized_diff = unified_diff.replace("\r\n", "\n")
        if not normalized_diff.endswith("\n"):
            normalized_diff += "\n"

        # Ensure target_dir has a temporary git index to allow git apply
        git_dir = os.path.join(target_dir, ".git")
        had_git = os.path.exists(git_dir)
        if not had_git:
            subprocess.run(["git", "init", "-q"], cwd=target_dir, check=True)
            subprocess.run(["git", "config", "user.name", "ReproProof"], cwd=target_dir, check=True)
            subprocess.run(["git", "config", "user.email", "reproproof@example.local"], cwd=target_dir, check=True)
            subprocess.run(["git", "add", "."], cwd=target_dir, check=True)
            subprocess.run(["git", "commit", "-qm", "temp-baseline"], cwd=target_dir, check=True)

        with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False, encoding="utf-8") as f:
            f.write(normalized_diff)
            diff_file_path = f.name

        try:
            # 1. First dry-run: git apply --check
            check_proc = subprocess.run(
                ["git", "apply", "--check", "--whitespace=nowarn", diff_file_path],
                cwd=target_dir,
                capture_output=True,
                text=True,
            )

            if check_proc.returncode != 0:
                err_msg = check_proc.stderr.strip() or check_proc.stdout.strip()
                raise PatchValidationError(
                    f"Git apply pre-check failed (mismatched context, corrupt patch, or invalid targets): {err_msg}"
                )

            # 2. Apply: git apply
            apply_proc = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", diff_file_path],
                cwd=target_dir,
                capture_output=True,
                text=True,
            )

            if apply_proc.returncode != 0:
                err_msg = apply_proc.stderr.strip() or apply_proc.stdout.strip()
                raise PatchValidationError(f"Git apply execution failed: {err_msg}")

        finally:
            if os.path.exists(diff_file_path):
                os.remove(diff_file_path)
            # Remove transient .git folder if we initialized it
            if not had_git and os.path.exists(git_dir):
                shutil.rmtree(git_dir, ignore_errors=True)
