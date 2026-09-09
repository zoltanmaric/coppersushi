# Rule provenance

The stumble behind each line in `AGENTS.md` and `.agents/skills/`. Rules and skills stay imperative; this table is where the `ablation` rule looks before deleting a line, and where a new line records the occurrence that earned it.

Rules older than this page carry no row and are the first ablation candidates.

| Line | Stumble |
|---|---|
| `information-home` | Config comments carried backtest narrative and a spec step number, a PR description recounted the agent's own corrected drafts, and a test helper's docstring explained its caller and the bug's history — three corrections in one session, each information that belonged in the wiki, the PR body, or nowhere |
| `design-first`, `ablation`, `grill`/`spec`/`goldfish` skills | Design conversation, see [agent-workflow-design](agent-workflow-design.md) |
| `watch-long-runs`, `job-supervision`: detach from the tool's timeout | The first PyPSA-Eur run was a background tool call capped at 10 min; stopped and relaunched |
| `job-supervision`: own process group, confirm the PGID | A `nohup … &` from the tool shell inherits the shell's group; `kill -- -<pid>` failed with "no such process" and `pgrep -g` reported the job gone while it ran |
| `job-supervision`: gate, preflight, stuck vs. slow | Adopted with the skill; no local occurrence recorded yet |
| `job-supervision`: keep the exit status | A relaunch died on an import error with no exit line; the watcher saw silence until the user asked |
| `job-supervision`: verify downloads by size | 788 MB of a 6.6 GB cutout accepted with HTTP 200; failure surfaced two rules later as an unreadable NetCDF |
| `job-supervision`: watcher covers terminal states | The truncated download was caught only because the filter included `Traceback` |
| `job-supervision`: kill the process group | `pkill -f` missed a download script's subshell; a second `curl` wrote the same file beside the new one |
| `absolute-paths` | Twice, a `cd` at the start of a command chain sent a pin edit and a launch into the sibling repo |
| `named-adds` | `git add -A` during a merge swept two tokens from an unignored `.secrets/` into a local commit; GitHub push protection caught it. Again on a rules-only branch: a 31 MB candidate network rode along and had to be amended out |
| `sanction-by-hand` (`networks/AGENTS.md`) | A 31 MB solve was about to be committed as the day's network by an agent, with no human having looked at it |
| `public-repo` | A private repository path was cited as a source in a skill and a PR body |
| `main-push`; PR creation and updates need no confirmation | Opening PR #49 was blocked after the user had requested it because `no-push` demanded a redundant second confirmation; the user narrowed the gate to direct pushes to `main` |
| `vendor-guidelines` (`.agents/skills/AGENTS.md`) | A skill's first draft carried an incident log and a source citation; the vendor pages forbid both |
| `pull-request` ledger verdicts | A separable layer was listed as a piggyback without a chop offer; a goldfish critic flagged it |
| `pull-request` new layer via `gh stack add` | Two layers were opened with `gh pr create` and rebased by hand; GitHub showed a two-PR stack with the new PRs outside it until `gh stack link` repaired it |
| `mermaid` theme unset; fill paired with colour | Two spec diagrams with light fills and no text colour rendered grey-on-white in GitHub's dark theme; the user had hit the same on another project. Aligned with Princeton University Library's accessible-Mermaid guide and GitHub community discussion 35733 |
| `mermaid` placeholders as `‹x›` | `&lt;day&gt;` in two spec diagrams rendered as nothing: "networks/opf-.nc" |
| `pull-request` insert or reorder layers via `unstack`, `init`, `submit` | A middle layer was inserted under an open stacked PR; `submit` and `link` both failed with "PullRequest.base is invalid" and the PR was declared un-retargetable until the user pushed back and the tool's troubleshooting notes were read. Second time, following that recipe: bare `unstack` refused because the stale stack held a merged layer, `init` refused on the stacked branch, and `submit` started a new stack without the middle branch; `unstack <number>`, `pr edit --base`, `link`, `init` did it |
| `pull-request` critic reads the vendor guidelines | A skill draft with an incident log and a source citation passed two automated reviews; the user caught it |
| `pull-request` opt-in inline review threads and attribution | A goldfish review was about to be posted as consolidated PR comments; the first corrective rule then made posting automatic. The user clarified that findings stay in chat unless requested, exact comments and anchors need approval, and every posted finding gets its own inline thread even when only an approximate line exists |
| `ablation` user override | The repeated-stumble bar blocked that first-occurrence review rule; after the missing repetition was named, the user explicitly overrode the bar and asked that future overrides require confirmation |
| `design-first`: question zero on clear asks too | Twice in one session a clear ask was executed as stated and the user had to prompt the pushback: three documents were digested where one answered the question, and a diagram rule went in without its no-process caveat |
| `one-to-one`, `link-only`, `sparingly` (`wiki/literature/AGENTS.md`) | Decided in the grill that created the folder (log, 2026-09-08 ingest): three documents were about to be digested with raw text copies committed, one of which forbids reproduction |
| `project-lens` (`wiki/literature/AGENTS.md`) | Added with the folder: the user asked that digests keep the repository's angle rather than summarise the document in general |
| `diagram` (`wiki/literature/AGENTS.md`) | The first methodology digest narrated the note's eleven-step process table in prose; the user asked for the diagram |
| `relative-time` (wiki) | "Today it points at the fork's `coppersushi` branch" written into pypsa-eur-sibling on 2026-09-08; eight older "today"s found on the same sweep |
| `file-urls` | Files named by bare or relative paths in chat, many times; on 2026-09-09 the user could not find a scratchpad CSV named that way and overrode the repetition bar |
| `page-names` (wiki) | Two pages named from generic words on 2026-09-09: `core-capacity-calculation`, which the user could not place from its name, and a proposed `core-domain-inputs` that described a whole process |
| `term-anchors` (wiki) | Terms defined in a bullet list on one page and met cold on another: on 2026-09-09 the user could not place D2CF in the forecast spec after the concept page had defined it, hours after that page itself had to be rewritten because its terms had no definitions a reader could reach; the first link form, GitHub's slug of a two-word heading, then failed to resolve in Obsidian the same day |
