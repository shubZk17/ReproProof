# AGENTS.md — Agent Governance (authoritative)

Entry point for every agent working in this repository. **The repository is the source of truth for project memory.** Chat history is not.

## 1. Operating principles
- Read before acting. Complete `SESSION_START.md` before any code change.
- Verify the codebase before trusting notes. Memory can be stale; when they disagree, the code wins and the note gets fixed.
- Do the smallest change that meets the requirement. Stay consistent with the existing architecture.
- Mark anything unverified as `UNKNOWN`, `TODO`, or `ASSUMPTION`. Never invent project facts.

## 2. Instruction precedence (highest first)
1. The user's explicit instructions in the current session
2. `CONSTRAINTS.md` hard constraints (a user can lift one only explicitly, and the change gets recorded)
3. This file
4. Accepted entries in `DECISIONS.md`
5. `CONSTRAINTS.md` preferences, `LEARNINGS.md`, and other memory files
6. General defaults

If a conflict remains, stop and ask. Record how it was resolved in `DECISIONS.md`.

## 3. Memory: where things go

| Event | File | When |
|---|---|---|
| Meaningful technical/architectural decision | `DECISIONS.md` (new DEC entry) | Immediately |
| Task started / finished / blocked / scope changed | `TASKS.md` | Immediately |
| Milestone reached, validation run | `PROGRESS.md` | Immediately |
| Reusable technical insight, failed approach | `LEARNINGS.md` | Immediately |
| Significant or recurring error | `ERRORS.md` | When it is resolved or abandoned |
| Fact every session must know | `MEMORY.md` (short, link out) | When discovered |
| Project scope, stack, or structure changed | `PROJECT_CONTEXT.md` | When it changes |
| Verified component, data flow, or API change | `ARCHITECTURE.md` | When it changes |
| New hard rule or preference from the user | `CONSTRAINTS.md` | Immediately |
| Session summary | `sessions/YYYY-MM-DD_session-N.md` | Before the session ends |

Write as you go. Don't wait until the end of the session, because context can be compacted or cut off at any time.

## 4. Before ending a session (mandatory)
1. Update `PROGRESS.md`, `TASKS.md`, and `MEMORY.md`, plus `DECISIONS.md`, `LEARNINGS.md`, and `ERRORS.md` if anything happened that belongs there.
2. Write the session log (format: `sessions/README.md`), including the **exact continuation point** and **next action**.
3. Check: could a new agent resume using only these files? If not, fix the files.

## 5. Decisions
- Record every decision that a future agent might otherwise reverse or rethink.
- `DECISIONS.md` is append-only. To change a decision: mark the old one `Superseded by DEC-NNN`, add the new one with its reasoning, then update the affected docs and code.
- Don't reopen accepted decisions unless there is new evidence. If there is, record the conflict first.

## 6. Code quality and validation
- Match the existing style, naming, and patterns.
- Prefer the standard library and existing dependencies. A new dependency needs a justification, recorded as a DEC entry.
- Non-trivial logic should come with at least one runnable check.
- A task is **done** only when it has been validated (tests, a build, or a demonstrated run). Record what was run in `PROGRESS.md`. If validation was not possible, say so explicitly.

## 7. Prohibited without explicit user approval
- Destructive or irreversible actions: deleting files or branches, force-pushes, history rewrites, dropping data.
- Externally visible actions: pushing, publishing, deploying, sending messages, calling paid APIs.
- Security-sensitive changes: auth, secrets, or permissions.
- Changing a hard constraint, or reversing an accepted decision.
- Storing secrets, credentials, API keys, or sensitive personal data in any file, including these memory files.

## 8. Stop and ask the user when
- Requirements are ambiguous and the choice is hard to undo.
- The work would violate a hard constraint or an accepted decision.
- Memory and code contradict each other and the code doesn't settle which is right.
- The same approach has failed twice (check `ERRORS.md` first).
- Any action from §7 is needed.

## 9. Memory hygiene
- Keep `MEMORY.md` under about 60 lines. Move detail into the specialized files and link to it.
- Each fact lives in one file; other files link to it instead of copying it.
- Mark outdated content `~~struck~~ (outdated YYYY-MM-DD: reason)`. Delete it only after verifying it no longer matters.
- Use absolute dates (YYYY-MM-DD).
