# Agent Guidelines

1. **Support Codex and Claude Code (at minimum).** Agent instruction files must always be created in pairs: an `AGENTS.md` holding the actual content, and a `CLAUDE.md` next to it containing only an import of it (`@AGENTS.md`). Apply the same rule to any subdirectory that gets its own agent instructions (e.g. `v2/`). The same principle applies to skills: skills live in `.agents/skills/` (the cross-agent location), and `.claude/skills` is a symlink to that folder so Claude Code sees the identical skill set.

2. **Never push without asking.** Always ask the user before pushing to any remote.

3. **Commit deliberately, not per turn.** Don't commit after every instruction — the user often adjusts what they just asked for, and those adjustments belong in the same commit as the original change, not in a follow-up. Let work accumulate across a few turns, then group it into atomic, cohesive commits when a piece of work has settled.

4. **The user dictates via voice mode.** Messages are often transcribed speech and may contain garbled words, homophones, or mis-transcriptions (e.g. a wrong-but-similar-sounding word). Read for intent rather than literally; when a word seems out of place, infer the likely intended word from context, and ask only if the meaning is genuinely ambiguous.

5. **Conciseness is of utmost importance.** The bottleneck of agent-driven development is the human's comprehension and attention. Say only what needs to be said — so the human has the will to read it, can read it fast, and can therefore move fast. This applies to chat replies, documents, and wiki pages alike.

6. **Rely heavily on git — delete code with a heavy hand.** Git history is the archive. Never keep commented-out code, unused functions, "just in case" branches, or half-finished experiments in the tree; delete them and recover from history if ever needed. Prefer discarding stale uncommitted work over carrying it along.

7. **Design-first for non-trivial work.**
   - When an ask is ambiguous, interrogate before implementing (`grill` skill), scaling depth to the ambiguity.
   - Before non-trivial work, ask whether this is the right question at all.
   - For large or multi-session tasks, use a spec (`spec` skill) — create one when obviously needed, suggest it in the gray zone.
   - When a spec or design has grown load-bearing, suggest a goldfish review (`goldfish` skill); the user pulls the trigger.

8. **Keep agent rules and skills minimal — ablate, don't accumulate.** Every line here and in `.agents/skills/` is read on every run and must earn its place through an observed, repeated stumble — never a predicted one. As models improve, old corrective lines go stale: re-ablate occasionally by deleting lines and seeing what actually breaks. If nothing ever needs adding back, the deleting wasn't aggressive enough.
