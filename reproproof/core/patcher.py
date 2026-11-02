"""Source-Only Patch Proposal and Validation Engine.

Enforces R7 and Hard Rule 3:
- Rejects edits to protected files, tests, manifests, and configs.
- Rejects edits outside allowlisted source paths.
- Rejects patches exceeding size limits (<= 200 lines, <= 5 files).
- Parses and applies unified diffs in memory / temp directory.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from reproproof.core.schemas import AppManifest, PatchProposal
from reproproof.core.limits import DEFAULT_LIMITS, RunLimits


class PatchValidationError(Exception):
    """Raised when a proposed patch violates safety, path, or size constraints."""
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
            # Standard unified diff header: +++ b/path/to/file or +++ path/to/file
            if line.startswith("+++ "):
                target = line[4:].strip()
                if target.startswith("b/"):
                    target = target[2:]
                target = target.split("\t")[0].strip()
                if target and target != "/dev/null":
                    touched.add(os.path.normpath(target).replace("\\", "/"))
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

    def validate_patch(self, proposal: PatchProposal) -> List[str]:
        """Validates patch proposal strictly according to PRD R7 and Hard Rule 3.
        
        Returns the list of validated touched file paths.
        Raises PatchValidationError if any rule is broken.
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

        # Forbidden protected filenames across all apps
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
        ]

        all_protected = set(self.manifest.protected_paths + universal_protected)

        for file_path in touched:
            # Normalize path
            norm_path = os.path.normpath(file_path).replace("\\", "/")

            # 1. Must NOT touch any protected path
            for prot in all_protected:
                norm_prot = os.path.normpath(prot).replace("\\", "/")
                if norm_path == norm_prot or norm_path.startswith(norm_prot + "/"):
                    raise PatchValidationError(
                        f"Patch touches forbidden protected path: '{file_path}' (rule H-7: source-only patching)."
                    )

            # 2. Must be within allowed_source_paths
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
        """Applies a validated unified diff to target_dir using patch logic."""
        # Simple unified diff applicator for pure source changes
        # Splits diff into per-file chunks
        file_chunks = re.split(r"(?=^--- )", unified_diff, flags=re.MULTILINE)
        for chunk in file_chunks:
            if not chunk.strip():
                continue

            lines = chunk.strip().splitlines()
            orig_header = None
            new_header = None
            for l in lines:
                if l.startswith("--- "):
                    orig_header = l[4:].strip()
                elif l.startswith("+++ "):
                    new_header = l[4:].strip()
                    break

            if not new_header:
                continue

            if new_header.startswith("b/"):
                new_header = new_header[2:]
            new_header = new_header.split("\t")[0].strip()

            target_file = os.path.join(target_dir, new_header)
            if not os.path.exists(target_file):
                raise PatchValidationError(f"Target file does not exist: {target_file}")

            with open(target_file, "r", encoding="utf-8") as f:
                original_content = f.read()

            patched_content = self._apply_hunks(original_content, lines)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(patched_content)

    def _apply_hunks(self, content: str, diff_lines: List[str]) -> str:
        """Applies diff hunks to string content."""
        file_lines = content.splitlines(keepends=True)
        hunk_header_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

        # Parse hunks
        hunks = []
        current_hunk = None

        for line in diff_lines:
            m = hunk_header_re.match(line)
            if m:
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = {"header": line, "lines": []}
            elif current_hunk:
                current_hunk["lines"].append(line)

        if current_hunk:
            hunks.append(current_hunk)

        if not hunks:
            return content

        # Apply hunks sequentially
        result_lines = list(file_lines)
        offset = 0

        for hunk in hunks:
            m = hunk_header_re.match(hunk["header"])
            orig_start = int(m.group(1)) - 1  # 0-indexed
            orig_count = int(m.group(2)) if m.group(2) else 1

            # Extract expected old lines and replacement lines from hunk
            expected_old = []
            replacement = []
            for hline in hunk["lines"]:
                if hline.startswith("-"):
                    expected_old.append(hline[1:])
                elif hline.startswith("+"):
                    replacement.append(hline[1:])
                elif hline.startswith(" "):
                    expected_old.append(hline[1:])
                    replacement.append(hline[1:])

            # Convert to lines with line endings
            expected_old_text = "\n".join(expected_old).strip()
            replacement_text = "\n".join(replacement).strip()

            # Join full content and replace
            full_text = "".join(result_lines)
            if expected_old_text in full_text:
                full_text = full_text.replace(expected_old_text, replacement_text, 1)
                result_lines = [l + "\n" for l in full_text.splitlines()]
            else:
                # If exact whitespace matching fails, try line replacement at orig_start
                pos = orig_start + offset
                del result_lines[pos : pos + orig_count]
                for r_line in reversed(replacement):
                    result_lines.insert(pos, r_line + ("\n" if not r_line.endswith("\n") else ""))
                offset += len(replacement) - orig_count

        return "".join(result_lines)
