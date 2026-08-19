# Agent workflow design (grill / spec / goldfish)

Design rationale for this repo's agent tooling: `AGENTS.md` rules 7–8 and the skills
`grill`, `spec`, `goldfish` (in `.agents/skills/`). Distilled 2026-08-19 from four
public sources and one design conversation.

## Sources

- **Dave Rensin, "Elephants, Goldfish and the New Golden Age of Software Engineering"**
  ([Medium](https://drensin.medium.com/elephants-goldfish-and-the-new-golden-age-of-software-engineering-c33641a48874)) —
  interrogate the human first; write a design doc; stress-test it with fresh memoryless
  readers (goldfish) before implementing.
- **Na'aman Hirschfeld, "Stop Writing Specs for Your Agents"**
  ([dev.to](https://dev.to/nhirschfeld/stop-writing-specs-for-your-agents-3fan)) — a
  monolithic spec conflates four artifacts with different lifetimes (requirements,
  architectural decisions, implementation plans, contracts); "the file decays at the
  speed of its fastest-rotting component." Layer by lifetime; never commit
  implementation plans; make contracts executable.
- **Boris Cherny, YC Startup School, Jul 2026**
  ([YouTube](https://www.youtube.com/watch?v=qyPCVqFUyDo)) — deleted 80% of Claude
  Code's system prompt for Opus 5. Method: delete, use, add a line back only on an
  *observed repeated* stumble. Overspecifying is the classic failure of experienced
  engineers; describe task + guardrails + exit criteria and let the model pick
  mechanics. Verification is the thing people most get wrong. (Grain of salt: launch
  event; hero anecdotes are survivorship showcases. But "rely on the model, not the
  harness" runs *against* a harness PM's product interest, which makes it more
  credible, and the core practices are self-verifiable by ablating one's own setup.)
- **Elon Musk's five-step algorithm**
  ([interview](https://www.startuparchive.org/p/elon-musk-explains-his-5-step-algorithm-for-running-companies-1eae)) —
  question requirements → delete → simplify → accelerate → automate, strictly in that
  order; "the most common error of a smart engineer is to optimize a thing that should
  not exist"; if you never add anything back, you didn't delete enough.

## Key decisions

- **Three independent skills, composed by offer, never auto-chained.** The parts have
  different frequencies and trigger owners; a pipeline protocol was the predecessor
  pattern's main flaw.
- **Interrogation trigger lives in `AGENTS.md` (rule 7), body in the `grill` skill.**
  Rules are always in context so the *default behavior* fires reliably; skills load on
  demand. Depth is left to agent discretion, scaled to ambiguity.
- **Question zero, three-verdict ladder** (in grill, reused by goldfish's deleter
  facet): wrong question → propose the right one; right problem, misaimed ask → adjust
  the requirement; right question → proceed silently. *Rejected:* requiring every
  challenge to come with a concrete alternative — it would incentivize confabulated
  alternatives and suppress honest "smells wrong because X" signal.
- **Spec = task-scoped burn-down file in gitignored `specs/`.** Resolves
  Rensin-vs-Hirschfeld: re-bootstrap and shared-intent benefits without committed-doc
  rot. Lifetime is the task, not a PR (repo is solo, main-push). Acceptance criteria
  are the load-bearing section; no file-by-file plan. Links to the wiki instead of
  restating it. *Rejected:* durable four-section design docs enumerating every file —
  the fastest-rotting layer, and unreadable.
- **Goldfish facets are a menu, not a mandate:** requirement deleter (whole before
  parts), comprehension, simplifier, critic, readiness — deleter runs first (Musk
  ordering). Comprehension tests *reachability from fresh context* (repo, wiki, links),
  not self-containment. *Rejected:* accelerate/automate facets (execution-phase, not
  review lenses) and the fixed 3-reviewers × 3-rounds procedure.
- **Ablation doctrine (rule 8, self-referential):** every rule/skill line earns its
  place by observed stumble; re-ablate as models improve; occasional add-backs are the
  proof of aggressive-enough deletion.
- **Wiki symbiosis:** spec = working memory (dies at task end), wiki = durable
  decision layer (this repo's `llm-wiki` skill owns the schema; its `log.md` serves as
  the append-only decision log — no separate ADR system). Spec completion ends with an
  *offer* to distill into the wiki, then deletion.
