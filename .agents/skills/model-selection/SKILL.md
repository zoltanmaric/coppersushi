---
name: model-selection
description: Selects models for authorized delegation and independent reviews using available models, task difficulty and recorded quota usage. Use before launching a sub-agent, selecting a reviewer or escalating a model.
---

# Model selection

Honor explicit model choices and the current harness's delegation permissions. This
skill chooses how to staff authorized work; it does not authorize extra agents or
change the current conversation's model.

Discover available models and usage tools before claiming either is unavailable.
For Codex, call `get_usage_limits`. After each successful check, pass the response's
JSON payload (not its tool envelope) on stdin to `python .agents/skills/model-selection/scripts/quota.py record`,
using the selected local Python environment. Transfer JSON as data, not interpolated
shell code. The recorder uses only the standard library on macOS/Linux.

The recorder stores account/bucket identifiers, observation times, usage percentages
and reset windows in `~/.local/state/agent-quota/usage.csv`, shared across repositories.
It omits other response fields and uses a file lock for concurrent writers. Never
commit live responses or the log. Use `--log` for isolated test data. If access is
denied, report the recording limit and use the live reading; do not relocate private
history into the repository or claim it was saved.

Choose the lightest suitable available model:

| Work | Preferred family, when available |
| --- | --- |
| Clear, bounded inspection or routine work | Terra |
| Ordinary implementation and investigation | Sol |
| Difficult reasoning or architecture that needs stronger reasoning | Astra |

Use equivalent models when the harness exposes different names. Prefer Astra for
a first full independent review when the scope warrants it and quota allows it.
When quota is tight, use a lighter model even for the first full review.
For follow-up reviews of specific fixes, default to the lightest suitable model.
Match reasoning effort to difficulty. Do not launch duplicate attempts by default.

Use all applicable quota windows: remaining capacity, time until reset and task scope.
Compare observed consumption rates with the recorder's sustainable rate (remaining
percentage points divided by hours until reset). Its early/late rates describe
observations, not a forecast or per-model cost. Sparse or brief coverage does not
establish a full-window trend. Do not infer spare capacity in one bucket from another.
Respect live availability flags and retry delays even if a percentage suggests room.

If quota data is unavailable, keep concurrency modest and use task difficulty to
choose. If recording fails, use live headroom without claiming a historical trend.
Recheck during long tasks and before expanding concurrency or escalating models;
do not poll just to fill the log. The recorder saves material changes and an hourly
observation when checked, while each summary includes the live reading.

## Apply the choice at launch

Before each launch, choose the effective model and concurrency from the task and the
latest quota evidence. When remaining capacity is tight and recent consumption is
materially above the sustainable rate, default to one delegated agent at a time.
Treat a brief spike as a reason for caution.

If continuing at the current pace is likely to exhaust quota before reset, tell
the user before launching. Give the remaining quota, reset time, the lighter
model you will use and any work it may leave unresolved. Proceed with that model
on work it can handle. Identify any work that still needs stronger reasoning.
Honor explicit user model choices and live availability limits.

Inherit the parent model only when it matches the chosen model. Otherwise pass the
chosen model explicitly in the spawn call. For example, when an audit calls for Sol
and the parent uses Astra, set `model: "gpt-6.2-sol"`. If an override requires a
fresh context, give the agent a self-contained brief. Keep a short record of the
task, effective model, concurrency and quota reason.

Before escalating, distinguish missing context or tool failure from a capability
gap. Give concrete feedback and escalate only when the remaining task needs it.
The lead integrates and verifies delegated results. Give independent reviewers a fresh context and a self-contained brief, even
when they inherit the parent model. In Codex, set `fork_turns: "none"` at launch.
