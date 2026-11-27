# PR review replays

Run a single reviewer using the pinned pre-change instructions and the candidate workflow against the same public revision,
question, runner and model. Each arm starts a fresh agent. The questions reproduce
the decision under review. The grader stays outside the historical checkout.

```sh
python3 evals/pr-review/replay.py folders /tmp/review-folders
```

Run `receipt`, `independent`, `parallel` and `clean` the same way with new output directories.
Use `--model` to pin an available model. Each trial uses the local authenticated
CLI and consumes its quota. Keep the same CLI configuration and reasoning budget
for both arms. The default runs two trials per case. The pinned Git objects must
be available locally. In a fresh clone, fetch any missing public commit by SHA.

For each trial, read the question and criteria in `cases.json`. Read A and B before
opening the key. Mark each criterion pass or fail and quote the deciding evidence.
Count unsupported findings and record which answer would let you decide without
asking again. Open the key to compare word count, elapsed time and routing. Answer
format can still hint at the arm. Use the individual and lead artifacts to locate
where evidence was lost. A failed process is a failed trial; retain its artifacts
and use a new output directory for a retry.

The explicit delegation case grades completed assignments from the runner. The two-part stack
review tests whether independent work is delegated without an explicit instruction. The
clean case catches unnecessary fan-out. The other cases permit either routing
decision. Qualitative grading can accept different architectural recommendations.
Try the winning version on an unseen PR before changing the default.

The single-reviewer control measures answer quality against a fixed starting point.
Routing scores apply to the candidate. They cannot estimate how often interactive
Codex or Claude sessions delegated before this workflow existed.

## Review one comparison

For a recorded review, run the following from the harness checkout. Supply a
clean checkout of the reviewed tip, its merge base with the target, and a new
output directory outside the checkout.

```sh
python3 .agents/skills/pull-request/scripts/review.py \
  --repo <reviewed-checkout> --base <merge-base> \
  --question '<review question>' --output <new-directory>
```

Read `final.json` for the verdict and `run.json` for observed calls and failures.
Use `--independent` to require a second assessment or repeat `--specialist` to
assign distinct questions. Use `--help` for runner and model selection.
