"""Compare the baseline and candidate on the same historical checkout."""

import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORKFLOW = ROOT / ".agents/skills/pull-request/scripts/review.py"
CASES = json.loads((HERE / "cases.json").read_text())


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def routing_passes(expectation, runs):
    specialists = [item for item in runs if item["id"].startswith("specialist-")]
    if expectation == "solo":
        return not specialists
    if expectation == "some":
        return any(item["status"] == "completed" for item in specialists)
    if expectation == "two":
        return len({item["assignment"] for item in specialists
                    if item["status"] == "completed"}) >= 2
    return True


def replay(case, output, trials, runner, model):
    output.mkdir(parents=True, exist_ok=False)
    with TemporaryDirectory(prefix="pr-review-") as temp:
        checkout = Path(temp) / "source"
        # A disposable clone keeps local edits and the grader outside the case.
        run("git", "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(checkout))
        run("git", "-C", str(checkout), "checkout", "--quiet", "--detach", case["head"],
            env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})
        run("git", "-C", str(checkout), "cat-file", "-e", case["base"] + "^{commit}")
        for index in range(1, trials + 1):
            trial = output / str(index)
            trial.mkdir()
            modes = ["baseline", "candidate"]
            random.SystemRandom().shuffle(modes)
            key = {}
            for label, mode in zip("AB", modes):
                artifacts = trial / "artifacts" / mode
                artifacts.parent.mkdir(exist_ok=True)
                args = [sys.executable, str(WORKFLOW), "--repo", str(checkout),
                        "--base", case["base"], "--question", case["question"],
                        "--output", str(artifacts), "--lead", runner,
                        "--specialist-runner", runner]
                if model:
                    args.extend(["--lead-model", model, "--specialist-model", model])
                if mode == "baseline":
                    args.append("--baseline")
                started = monotonic()
                run(*args)
                if mode == "baseline":
                    answer = (artifacts / "baseline.md").read_text()
                else:
                    final = json.loads((artifacts / "final.json").read_text())
                    answer = final["verdict"] + "\n\n" + "\n".join(
                        f"{item['path']}:{item['line']} — {item['observation']}"
                        for item in final["evidence"])
                    answer += "\n" + "\n".join(final["limitations"])
                key[label] = {"mode": mode, "seconds": round(monotonic() - started),
                              "words": len(answer.split())}
                if mode == "candidate":
                    runs = json.loads((artifacts / "run.json").read_text())["runs"]
                    key[label]["routing_pass"] = routing_passes(case["routing"], runs)
                (trial / f"{label}.md").write_text(answer.strip() + "\n")
            (trial / "key.json").write_text(json.dumps(key, indent=2) + "\n")
            print(f"Grade {trial}/A.md and B.md before opening key.json", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path, help="New directory outside the repository")
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--runner", choices=["codex", "claude"], default="codex")
    parser.add_argument("--model")
    args = parser.parse_args()
    if args.trials < 1 or args.output.resolve().is_relative_to(ROOT):
        parser.error("Use a positive trial count and a new output directory outside the checkout")
    replay(CASES[args.case], args.output.resolve(), args.trials, args.runner, args.model)
