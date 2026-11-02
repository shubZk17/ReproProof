# LEARNINGS.md — Reusable Knowledge

Record only actionable, project-specific insights that would be costly to rediscover. Format: `L-NNN (date): insight. Why it matters / how to apply.`

- **L-001 (2026-11-02):** The repository is inside a OneDrive-synced folder. Sync can lock files briefly or create `-<PCNAME>` conflict copies, and it handles large `node_modules`/`.venv` trees badly. If writes fail intermittently, suspect OneDrive first. Consider excluding build and dependency directories from sync.
- **L-002 (2026-11-02):** Claude Code auto-loads the root `CLAUDE.md` and expands `@relative/path` imports inside it. Other Markdown files are **not** loaded just because they exist; they must be imported or explicitly read.
- **L-003 (2026-11-02):** In this environment, one Bash call containing many quoted heredocs failed with `unexpected EOF while looking for matching '`. Write files with the Write tool or one heredoc per call.
