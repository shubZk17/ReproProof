"""Default limits and budget enforcement for ReproProof runs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RunLimits:
    max_patch_attempts: int = 2
    max_tool_steps: int = 20
    browser_test_timeout_seconds: int = 60
    run_timeout_seconds: int = 600  # 10 minutes
    spend_limit_usd: float = 1.00
    max_patch_changed_lines: int = 200
    max_patch_changed_files: int = 5
    max_active_runs: int = 1


DEFAULT_LIMITS = RunLimits()


class BudgetExceededError(Exception):
    """Raised when any run budget or safety limit is breached."""
    pass
