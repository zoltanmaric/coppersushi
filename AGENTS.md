# Agent Guidelines

1. **Support Codex and Claude Code (at minimum).** Agent instruction files must always be created in pairs: an `AGENTS.md` holding the actual content, and a `CLAUDE.md` next to it containing only an import of it (`@AGENTS.md`). Apply the same rule to any subdirectory that gets its own agent instructions (e.g. `v2/`). The same principle applies to skills: skills live in `.agents/skills/` (the cross-agent location), and `.claude/skills` is a symlink to that folder so Claude Code sees the identical skill set.

2. **Never push without asking.** Always ask the user before pushing to any remote.

3. **Commit deliberately, not per turn.** Don't commit after every instruction — the user often adjusts what they just asked for, and those adjustments belong in the same commit as the original change, not in a follow-up. Let work accumulate across a few turns, then group it into atomic, cohesive commits when a piece of work has settled.

4. **The user dictates via voice mode.** Messages are often transcribed speech and may contain garbled words, homophones, or mis-transcriptions (e.g. a wrong-but-similar-sounding word). Read for intent rather than literally; when a word seems out of place, infer the likely intended word from context, and ask only if the meaning is genuinely ambiguous.

5. **Conciseness is of utmost importance.** The bottleneck of agent-driven development is the human's comprehension and attention. Say only what needs to be said — so the human has the will to read it, can read it fast, and can therefore move fast. This applies to chat replies, documents, and wiki pages alike.

6. **Rely heavily on git — delete code with a heavy hand.** Git history is the archive. Never keep commented-out code, unused functions, "just in case" branches, or half-finished experiments in the tree; delete them and recover from history if ever needed. Prefer discarding stale uncommitted work over carrying it along.
