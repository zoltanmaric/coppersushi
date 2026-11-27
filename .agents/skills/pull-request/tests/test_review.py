"""Exercise routing and handoff through the CLI with local runner stubs."""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


REVIEW = Path(__file__).resolve().parents[1] / "scripts" / "review.py"
QUESTION = "Does this change put transport failures at the right boundary?"
STUB = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
import time

args = sys.argv[1:]
prompt = sys.stdin.read()
is_codex = '--output-last-message' in args
if is_codex:
    assert args[args.index('--sandbox') + 1] == 'read-only'
    assert args[args.index('--ask-for-approval') + 1] == 'never'
    path = Path(args[args.index('--output-last-message') + 1])
    name = path.stem
else:
    assert args[args.index('--tools') + 1] == 'Read,Glob,Grep'
    assert '--restricted' in args
    name = 'specialist-1'
assert json.dumps(os.environ['REVIEW_TEST_QUESTION']) in prompt
fixtures = json.loads(Path(os.environ['REVIEW_TEST_FIXTURES']).read_text())
response = fixtures[name]
if response is None:
    print('runner refused the request', file=sys.stderr)
    sys.exit(3)
if name.startswith('specialist-'):
    assert 'Reviewer answers:' not in prompt
    assert 'Independently investigate this assignment:' in prompt
    if 'specialist-2' in fixtures:
        directory = Path(os.environ['REVIEW_TEST_FIXTURES']).parent
        (directory / f'{name}.started').touch()
        stop = time.monotonic() + 3
        while len(list(directory.glob('specialist-*.started'))) < 2:
            assert time.monotonic() < stop, 'The specialists did not start together.'
            time.sleep(0.01)
if name == 'final':
    assert 'This reviewer subprocess must not launch additional agents.' in prompt
    assert 'Keep routing and execution commentary out of the verdict.' in prompt
    record = json.loads((path.parent / 'run.json').read_text())
    completed = [item['id'] for item in record['runs'] if item['status'] == 'completed']
    assert completed[0] == 'lead' and 'specialist-1' in completed
    assert f'verified completed reviewer IDs: {json.dumps(completed)}.' in prompt
    assert 'Reviewer answers:' in prompt
    assert fixtures['lead']['evidence'][0]['observation'] in prompt
    assert 'specialist-1' in prompt
if is_codex:
    path.write_text(response if name == 'baseline' else json.dumps(response))
else:
    print(json.dumps({'structured_output': response, 'is_error': False}))
"""


def evidence(observation, line=1):
    return {"path": "component.py", "line": line, "observation": observation}


def answer(observation="The transport adapter classifies the error.", **updates):
    return {"question": QUESTION, "status": "assessed", "verdict": "Yes.",
            "evidence": [evidence(observation)], "limitations": []} | updates


def lead(*assignments):
    return answer(delegation={"reason": "Inspect the ownership boundary.", "assignments": assignments})


def resolution(source, index=1, disposition="retained"):
    return {"source": source, "verdict_resolution": "Used to confirm the boundary.",
            "evidence": [{"index": index, "disposition": disposition, "explanation": "Checked in the tree."}]}


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.repo = self.directory / "repo"
        self.repo.mkdir()
        self.git("init", "--quiet")
        (self.repo / "component.py").write_text("# old module\n", encoding="utf-8")
        self.git("add", "component.py")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").strip()
        (self.repo / "component.py").write_text("# adapter\n# caller\n", encoding="utf-8")
        self.git("add", "component.py")
        self.git("commit", "-qm", "head")
        self.output = self.directory / "results"
        for runner in ("codex", "claude"):
            stub = self.directory / runner
            stub.write_text(STUB, encoding="utf-8")
            stub.chmod(0o755)

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-c", "user.name=Review Test", "-c", "user.email=review@example.invalid",
             "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
            cwd=self.repo, text=True,
        )

    def run_cli(self, fixtures, *flags):
        fixture_path = self.directory / "fixtures.json"
        fixture_path.write_text(json.dumps(fixtures), encoding="utf-8")
        env = os.environ | {"PATH": f"{self.directory}:{os.environ['PATH']}",
                            "REVIEW_TEST_QUESTION": QUESTION,
                            "REVIEW_TEST_FIXTURES": str(fixture_path)}
        return subprocess.run(
            [sys.executable, str(REVIEW), "--repo", str(self.repo), "--base", self.base,
             "--question", QUESTION, "--output", str(self.output), *flags],
            env=env, capture_output=True, text=True, timeout=15,
        )

    def read(self, name):
        return json.loads((self.output / f"{name}.json").read_text(encoding="utf-8"))

    def test_one_coherent_path_needs_only_the_lead(self):
        completed = self.run_cli({"lead": lead()})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.read("final"), answer())
        self.assertEqual(self.read("run")["routing"]["assignments"], [])
        self.assertEqual([run["id"] for run in self.read("run")["runs"]], ["lead"])

    def test_routes_independent_assignments_and_preserves_provenance_in_synthesis(self):
        assignments = ["Trace the transport failure path.", "Trace the public caller."]
        completed = self.run_cli({
            "lead": lead(*assignments),
            "specialist-1": answer("The transport failure stops at the adapter."),
            "specialist-2": answer(evidence=[evidence("The caller reads the typed failure.", 2)]),
            "final": answer(evidence=[evidence("The adapter stops the failure."),
                                      evidence("The caller reads the typed failure.", 2)],
                            handoff=[resolution(name) for name in ("lead", "specialist-1", "specialist-2")]),
        })
        self.assertEqual(completed.returncode, 0, completed.stderr)
        record = self.read("run")
        self.assertEqual(record["routing"]["assignments"], assignments)
        self.assertEqual([run["status"] for run in record["runs"]], ["completed"] * 4)
        self.assertEqual(self.read("specialist-2")["question"], QUESTION)
        final = self.read("final")
        self.assertEqual(final["verdict"], "Yes.")
        self.assertEqual(len(final["handoff"]), 3)

    def test_explicit_independence_dispatches_even_if_lead_does_not_route(self):
        completed = self.run_cli({"lead": lead(), "specialist-1": answer(),
                                  "final": answer(handoff=[resolution("lead"), resolution("specialist-1")])},
                                 "--independent", "--specialist-runner", "claude", "--specialist-model", "test")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        _, specialist, _ = self.read("run")["runs"]
        self.assertEqual((specialist["runner"], specialist["model"], specialist["status"]),
                         ("claude", "test", "completed"))

    def test_specialist_failure_is_visible_and_prevents_verified_final(self):
        completed = self.run_cli({"lead": lead("Check the caller."), "specialist-1": None})
        self.assertEqual(completed.returncode, 1)
        self.assertIn("specialist-1: codex exited 3", completed.stderr)
        self.assertEqual(self.read("run")["runs"][-1]["status"], "failed")
        self.assertFalse((self.output / "final.json").exists())
        self.assertEqual(self.read("lead")["question"], QUESTION)

    def test_synthesis_cannot_silently_drop_a_specialist_anchor(self):
        completed = self.run_cli({"lead": lead("Check the caller."),
                                  "specialist-1": answer(evidence=[evidence("Caller checks it.", 2)]),
                                  "final": answer(handoff=[resolution("lead"), resolution("specialist-1")])})
        self.assertEqual(completed.returncode, 1)
        self.assertIn("Retained evidence from specialist-1 is absent", completed.stderr)
        self.assertFalse((self.output / "final.json").exists())

    def test_changed_question_is_rejected(self):
        completed = self.run_cli({"lead": lead() | {"question": "Will this compile?"}})
        self.assertEqual(completed.returncode, 1)
        self.assertIn("lead changed the review question", completed.stderr)

    def test_baseline_keeps_prose_and_uses_the_same_snapshot(self):
        completed = self.run_cli({"baseline": "The adapter reports transport failures."}, "--baseline")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.read("run")["base"], self.base)
        self.assertEqual(self.read("run")["head"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual((self.output / "baseline.md").read_text(encoding="utf-8"),
                         "The adapter reports transport failures.")


if __name__ == "__main__":
    unittest.main()
