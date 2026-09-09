# Agent Guidelines

- **cross-agent** — Support Codex and Claude Code (at minimum). Agent instruction files must always be created in pairs: an `AGENTS.md` holding the actual content, and a `CLAUDE.md` next to it containing only an import of it (`@AGENTS.md`). Apply the same rule to any subdirectory that gets its own agent instructions (e.g. `wiki/`). The same principle applies to skills: skills live in `.agents/skills/` (the cross-agent location), and `.claude/skills` is a symlink to that folder so Claude Code sees the identical skill set.

- **public-repo** — Everything here is public: code, wiki, commit messages, PR bodies, review comments. Nothing enters that isn't already public — no secrets, no private repositories or their paths, no employer or client material, no personal information. When knowledge came from a private source, carry the idea, never the pointer. Secrets live in the gitignored `.secrets/`.

- **main-push** — Ask before pushing directly to `main`. Push topic branches and create or update their pull requests without separate confirmation.

- **commit-cadence** — Commit deliberately, not per turn. Don't commit after every instruction — the user often adjusts what they just asked for, and those adjustments belong in the same commit as the original change, not in a follow-up. Let work accumulate across a few turns, then group it into atomic, cohesive commits when a piece of work has settled.

- **voice-mode** — The user dictates via voice mode. Messages are often transcribed speech and may contain garbled words, homophones, or mis-transcriptions (e.g. a wrong-but-similar-sounding word). Read for intent rather than literally; when a word seems out of place, infer the likely intended word from context, and ask only if the meaning is genuinely ambiguous.

- **conciseness** — Conciseness is of utmost importance. The bottleneck of agent-driven development is the human's comprehension and attention. Say only what needs to be said — so the human has the will to read it, can read it fast, and can therefore move fast. This applies to chat replies, documents, and wiki pages alike.

- **delete-heavily** — Rely heavily on git — delete code with a heavy hand. Git history is the archive. Never keep commented-out code, unused functions, "just in case" branches, or half-finished experiments in the tree; delete them and recover from history if ever needed. Prefer discarding stale uncommitted work over carrying it along.

- **design-first** — Design-first for non-trivial work.
  - Interrogate before implementing (`grill` skill) on every non-trivial ask, clear or not: first whether it is the right question at all, then what exactly is asked; depth scales with ambiguity.
  - For large or multi-session tasks, use a spec (`spec` skill) — create one when obviously needed, suggest it in the gray zone.
  - When a spec or design has grown load-bearing, suggest a goldfish review (`goldfish` skill); the user pulls the trigger.

- **ablation** — Keep agent rules and skills minimal — ablate, don't accumulate. Every line here and in `.agents/skills/` is read on every run and must earn its place through an observed, repeated stumble — never a predicted one — recorded in `wiki/rule-provenance.md`. The user may override the repetition bar after the agent names the missing evidence and gets the user's explicit confirmation. As models improve, old corrective lines go stale: re-ablate occasionally by deleting lines and seeing what actually breaks. If nothing ever needs adding back, the deleting wasn't aggressive enough.

- **fix-the-generator** — Fix the generator, not the instance. Before patching a flagged problem, ask what produced it; prefer the fix that ends the class — restructure the code, restate the rule's principle — over the one that closes the single case. A second occurrence of anything is conclusive: the local level was the wrong level.

- **absolute-paths** — Never `cd` inside a command chain: the working directory persists across `&&` and `;`, so every later step silently runs elsewhere. Use absolute paths, `git -C`, and put any `cd` inside the subshell that needs it.

- **file-urls** — Refer to files in chat by their full `file:///` URL, never by a bare or relative path.

- **named-adds** — Stage named paths, never `git add -A` or `git add .`: untracked files you didn't mean to commit ride along silently.

- **watch-long-runs** — Watch long runs from the first second. Anything that may run beyond a minute goes through the `job-supervision` skill before launch.

- **worktrees** — Isolate conflicting concurrent work. Multiple agents commonly work in this repository at once. Create worktrees under the gitignored `worktrees/` directory. If another agent's changes conflict with yours, offer to move your work to a worktree rather than overwrite or discard either set of changes.

- **architecture-delta** — Declare the architecture delta in every PR. Every PR body carries an "Architecture delta" section: "None", or one line per change to the dataflow graph in `wiki/sushi-2.md`, updated in the same PR. The graph holds implemented parts (solid) and planned parts (dashed, class `planned`): a plan PR adds or removes dashed parts, a feature PR turns them solid — reviewers see what was fleshed out.
