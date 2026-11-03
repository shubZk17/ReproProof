# LEARNINGS.md — Reusable Knowledge

Record only actionable, project-specific insights that would be costly to rediscover. Format: `L-NNN (date): insight. Why it matters / how to apply.`

- **L-001 (2026-11-02):** The repository is inside a OneDrive-synced folder. Sync can lock files briefly or create `-<PCNAME>` conflict copies, and it handles large `node_modules`/`.venv` trees badly. If writes fail intermittently, suspect OneDrive first. Consider excluding build and dependency directories from sync.
- **L-002 (2026-11-02):** Claude Code auto-loads the root `CLAUDE.md` and expands `@relative/path` imports inside it. Other Markdown files are **not** loaded just because they exist; they must be imported or explicitly read.
- **L-003 (2026-11-02):** In this environment, one Bash call containing many quoted heredocs failed with `unexpected EOF while looking for matching '`. Write files with the Write tool or one heredoc per call.
- **L-004 (2026-11-03):** On Windows, git object files are read-only, so `shutil.rmtree(..., ignore_errors=True)` silently leaves them. Use `proc_utils.force_rmtree`.
- **L-005 (2026-11-03):** WHATWG URL parsing strips tab/CR/LF, so `/\t/evil.example` becomes the protocol-relative `//evil.example`. Validate paths with an allowlist regex (`schemas._SAFE_PATH_RE`), not a blocklist.
- **L-006 (2026-11-03):** Prior "N/N tests passing" claims here encoded the bypasses as expected behaviour. Re-read what the tests assert before trusting a count.
- **L-007 (2026-11-03):** The Streamlit UI can be driven headlessly with `streamlit.testing.v1.AppTest` (click buttons by label). Set `PYTHONIOENCODING=utf-8` to print emoji labels on the cp1252 console.
