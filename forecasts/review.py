"""Publish one conclusion artifact and derive its visible MLflow notes."""
import argparse
import json
from pathlib import Path
from urllib.parse import quote

from forecasts.run import tracking_client
from typing import NotRequired, TypedDict


class Conclusion(TypedDict):
    result: str
    limitations: str
    decision: str
    evidence_artifacts: NotRequired[list[str]]


def publish(run_id: str, conclusion: Conclusion, artifact_path: str) -> None:
    """Save a conclusion and update the same run’s visible notes."""
    client = tracking_client()
    run = client.get_run(run_id)
    # Validate the synopsis before publishing either representation.
    sections = [f"**Result:** {conclusion['result']}",
                f"**Limitation:** {conclusion['limitations']}",
                f"**Decision:** {conclusion['decision']}"]
    base = f"/get-artifact?run_id={run_id}&path="
    sections.append(f"[Full conclusion]({base}{quote(artifact_path, safe='')})")
    for evidence in conclusion.get('evidence_artifacts', []):
        prefix = f'runs:/{run_id}/'
        target = f"{base}{quote(evidence[len(prefix):], safe='')}" if evidence.startswith(prefix) else evidence
        sections.append(f"[Evidence: {evidence}]({target})")
    if run.data.tags.get('timing_semantics') == 'logging_only':
        sections.append('Duration measures result logging, not model training.')
    client.log_dict(run_id, dict(conclusion), artifact_path)
    client.set_tag(run_id, 'mlflow.note.content', '\n\n'.join(sections))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--conclusion', type=Path, required=True)
    parser.add_argument('--artifact-path', default='research/conclusion.json')
    args = parser.parse_args()
    publish(args.run, json.loads(args.conclusion.read_text()), args.artifact_path)
