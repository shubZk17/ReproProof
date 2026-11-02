# SESSION_START.md — Mandatory Initialization

Complete this checklist before making **any** code change. It also applies after a context compaction or when resuming an interrupted task.

`AGENTS.md`, `CONSTRAINTS.md`, and `MEMORY.md` are auto-loaded through the root `CLAUDE.md`. Read the rest yourself.

1. [ ] `AGENTS.md`: rules and precedence (auto-loaded)
2. [ ] `CONSTRAINTS.md`: hard limits (auto-loaded)
3. [ ] `PROJECT_CONTEXT.md`
4. [ ] `MEMORY.md` (auto-loaded)
5. [ ] `DECISIONS.md`: at minimum, every entry with status `Accepted` or `Proposed`
6. [ ] `TASKS.md`
7. [ ] `PROGRESS.md`
8. [ ] `LEARNINGS.md`
9. [ ] The latest one or two logs in `sessions/` (newest file name sorts last)
10. [ ] Repository state: `git status`, `git log --oneline -10`, and recently changed files.
    *If the directory is not a git repo, list it and compare against `PROJECT_CONTEXT.md` instead.*
11. [ ] Identify the current task: the user's request, otherwise the item marked In Progress in `TASKS.md`, otherwise the "Next action" in `PROGRESS.md`
12. [ ] Reconcile: does the actual repository match what memory says? Spot-check at least one claim marked completed.

## If something is missing or contradictory
- A memory file is missing: recreate it from the structure in `AGENTS.md` §3 and record it in `ERRORS.md`.
- Memory claims X but the code shows Y: trust the code, correct the memory file, and note the correction in the session log.
- The user's request conflicts with an accepted decision or a hard constraint: stop and ask (`AGENTS.md` §8).

## Then
- Start or continue the session log `sessions/YYYY-MM-DD_session-N.md`, where N is the next number for that date.
- Mark the current task In Progress in `TASKS.md`.
