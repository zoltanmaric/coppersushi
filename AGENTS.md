# Agent Guidelines

- **cross-agent** — Support Codex and Claude Code (at minimum). Agent instruction files must always be created in pairs: an `AGENTS.md` holding the actual content, and a `CLAUDE.md` next to it containing only an import of it (`@AGENTS.md`). Apply the same rule to any subdirectory that gets its own agent instructions (e.g. `wiki/`). The same principle applies to skills: skills live in `.agents/skills/` (the cross-agent location), and `.claude/skills` is a symlink to that folder so Claude Code sees the identical skill set.

- **no-push** — Never push without asking. Always ask the user before pushing to any remote.

- **commit-cadence** — Commit deliberately, not per turn. Don't commit after every instruction — the user often adjusts what they just asked for, and those adjustments belong in the same commit as the original change, not in a follow-up. Let work accumulate across a few turns, then group it into atomic, cohesive commits when a piece of work has settled.

- **voice-mode** — The user dictates via voice mode. Messages are often transcribed speech and may contain garbled words, homophones, or mis-transcriptions (e.g. a wrong-but-similar-sounding word). Read for intent rather than literally; when a word seems out of place, infer the likely intended word from context, and ask only if the meaning is genuinely ambiguous.

- **conciseness** — Conciseness is of utmost importance. The bottleneck of agent-driven development is the human's comprehension and attention. Say only what needs to be said — so the human has the will to read it, can read it fast, and can therefore move fast. This applies to chat replies, documents, and wiki pages alike.

- **delete-heavily** — Rely heavily on git — delete code with a heavy hand. Git history is the archive. Never keep commented-out code, unused functions, "just in case" branches, or half-finished experiments in the tree; delete them and recover from history if ever needed. Prefer discarding stale uncommitted work over carrying it along.

- **design-first** — Design-first for non-trivial work.
  - When an ask is ambiguous, interrogate before implementing (`grill` skill), scaling depth to the ambiguity.
  - Before non-trivial work, ask whether this is the right question at all.
  - For large or multi-session tasks, use a spec (`spec` skill) — create one when obviously needed, suggest it in the gray zone.
  - When a spec or design has grown load-bearing, suggest a goldfish review (`goldfish` skill); the user pulls the trigger.

- **ablation** — Keep agent rules and skills minimal — ablate, don't accumulate. Every line here and in `.agents/skills/` is read on every run and must earn its place through an observed, repeated stumble — never a predicted one. As models improve, old corrective lines go stale: re-ablate occasionally by deleting lines and seeing what actually breaks. If nothing ever needs adding back, the deleting wasn't aggressive enough.

- **fix-the-generator** — Fix the generator, not the instance. Before patching a flagged problem, ask what produced it; prefer the fix that ends the class — restructure the code, restate the rule's principle — over the one that closes the single case. A second occurrence of anything is conclusive: the local level was the wrong level.

- **worktrees** — Isolate conflicting concurrent work. Multiple agents commonly work in this repository at once. Create worktrees under the gitignored `worktrees/` directory. If another agent's changes conflict with yours, offer to move your work to a worktree rather than overwrite or discard either set of changes.

- **architecture-delta** — Declare the architecture delta in every PR. Every PR body carries an "Architecture delta" section: "None", or one line per change to the dataflow graph in `wiki/sushi-2.md`, updated in the same PR. The graph holds implemented parts (solid) and planned parts (dashed, class `planned`): a plan PR adds or removes dashed parts, a feature PR turns them solid — reviewers see what was fleshed out.
