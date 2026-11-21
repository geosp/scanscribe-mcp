# Decision log

Decisions about constraints, interfaces, tooling and process that are not recorded in an ADR. Newest first. Plans keep their own decision logs; add a line here only when a decision applies to the project as a whole.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-21 | Reviews follow the `small` profile in `docs/reviews/README.md` | Sized to the project; change it here and in that file if the project grows |
| 2026-11-21 | No license is declared yet | Owner's choice at setup. Revisit before inviting contributions or publishing a package. |
| 2026-11-21 | Commits use the owner's chosen address (a GitHub noreply address by default), set in the repository's local Git config | Keeps a personal address out of the history of a repository that may become public |
| 2026-11-21 | Agent harnesses: Claude Code (`ENABLED_HARNESSES` in `.agents/sync_agents.py`) | Owner's choice. Adding a harness is a one-line change plus the tooling table in `AGENTS.md`. |
| 2026-11-21 | The Claude Code deny list (`.claude/settings.json`) is in the first commit, before any other agent tooling | Guardrails exist before any agent works in the repository |
