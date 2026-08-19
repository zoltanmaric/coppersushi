# Agent Guidelines

1. **Support Codex and Claude Code (at minimum).** Agent instruction files must always be created in pairs: an `AGENTS.md` holding the actual content, and a `CLAUDE.md` next to it containing only an import of it (`@AGENTS.md`). Apply the same rule to any subdirectory that gets its own agent instructions (e.g. `v2/`). The same principle applies to skills: skills live in `.agents/skills/` (the cross-agent location), and `.claude/skills` is a symlink to that folder so Claude Code sees the identical skill set.

2. **Rely heavily on git — delete code with a heavy hand.** Git history is the archive. Never keep commented-out code, unused functions, "just in case" branches, or half-finished experiments in the tree; delete them and recover from history if ever needed. Prefer discarding stale uncommitted work over carrying it along.
