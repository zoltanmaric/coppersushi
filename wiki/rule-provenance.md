# Rule provenance

The stumble behind each line in `AGENTS.md` and `.agents/skills/`. Rules and skills stay imperative; this table is where the `ablation` rule looks before deleting a line, and where a new line records the occurrence that earned it.

Rules older than this page carry no row and are the first ablation candidates.

| Line | Stumble |
|---|---|
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
| `vendor-guidelines` (`.agents/skills/AGENTS.md`) | A skill's first draft carried an incident log and a source citation; the vendor pages forbid both |
| `pull-request` ledger verdicts | A separable layer was listed as a piggyback without a chop offer; a goldfish critic flagged it |
| `pull-request` new layer via `gh stack add` | Two layers were opened with `gh pr create` and rebased by hand; GitHub showed a two-PR stack with the new PRs outside it until `gh stack link` repaired it |
| `mermaid` theme unset; fill paired with colour | Two spec diagrams with light fills and no text colour rendered grey-on-white in GitHub's dark theme; the user had hit the same on another project. Aligned with Princeton University Library's accessible-Mermaid guide and GitHub community discussion 35733 |
| `mermaid` placeholders as `‹x›` | `&lt;day&gt;` in two spec diagrams rendered as nothing: "networks/opf-.nc" |
| `pull-request` critic reads the vendor guidelines | A skill draft with an incident log and a source citation passed two automated reviews; the user caught it |
| `design-first`: question zero on clear asks too | Twice in one session a clear ask was executed as stated and the user had to prompt the pushback: three documents were digested where one answered the question, and a diagram rule went in without its no-process caveat |
| `project-lens` (`wiki/literature/AGENTS.md`) | Added with the folder: the user asked that digests keep the repository's angle rather than summarise the document in general |
| `diagram` (`wiki/literature/AGENTS.md`) | The first methodology digest narrated the note's eleven-step process table in prose; the user asked for the diagram |
