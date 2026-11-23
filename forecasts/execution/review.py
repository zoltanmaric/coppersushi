"""Publish one conclusion artifact and derive its visible MLflow notes."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, NotRequired, TypedDict
from urllib.parse import quote

from mlflow.entities import RunTag

from forecasts.execution.tracking import tracking_client
from forecasts.inputs.input_types import Report

EvidenceStatus = Literal['accepted_baseline', 'invalid', 'superseded']
EVIDENCE_LABELS: dict[EvidenceStatus, str] = {
    'accepted_baseline': 'Accepted baseline',
    'invalid': 'Invalid experiment',
    'superseded': 'Superseded experiment',
}


class Conclusion(TypedDict):
    """Reviewed findings and the execution’s evidence status."""

    result: str
    limitations: str
    decision: str
    evidence_artifacts: NotRequired[list[str]]
    evidence_status: NotRequired[EvidenceStatus]


def publish(run_id: str, conclusion: Conclusion, artifact_path: str) -> None:
    """Save a conclusion and update the same run’s visible notes."""
    client = tracking_client()
    run = client.get_run(run_id)
    # Validate the synopsis before publishing either representation.
    sections = [f"**Result:** {conclusion['result']}",
                f"**Limitation:** {conclusion['limitations']}",
                f"**Decision:** {conclusion['decision']}"]
    status = conclusion.get('evidence_status')
    if status is not None:
        if status not in EVIDENCE_LABELS:
            raise ValueError('Unknown forecast evidence status')
        sections.insert(0, f'**Evidence status:** {EVIDENCE_LABELS[status]}')
    base = f"/get-artifact?run_id={run_id}&path="
    sections.append(f"[Full conclusion]({base}{quote(artifact_path, safe='')})")
    for evidence in conclusion.get('evidence_artifacts', []):
        prefix = f'runs:/{run_id}/'
        target = f"{base}{quote(evidence[len(prefix):], safe='')}" if evidence.startswith(prefix) else evidence
        sections.append(f"[Evidence: {evidence}]({target})")
    if run.data.tags.get('timing_semantics') == 'logging_only':
        sections.append('Duration measures result logging, not model training.')
    client.log_dict(run_id, dict(conclusion), artifact_path)
    tags = [RunTag('mlflow.note.content', '\n\n'.join(sections)), RunTag('forecast.conclusion_path', artifact_path)]
    if status is not None:
        tags.append(RunTag('evidence_status', status))
    client.log_batch(run_id, tags=tags)


def read_review(mlflow_run_id: str, forecast_run_id: str) -> Report:
    """Freeze the current review for this exact forecast execution in an offline export."""
    client = tracking_client()
    run = client.get_run(mlflow_run_id)
    tags = run.data.tags
    if tags.get('forecast_run') != forecast_run_id:
        raise ValueError('MLflow execution differs from the saved forecast run')
    status = tags.get('evidence_status')
    if status is not None and status not in EVIDENCE_LABELS:
        raise ValueError(f'Unknown tracked evidence status: {status}')
    path = tags.get('forecast.conclusion_path')
    if path is None:
        # Runs reviewed before the path tag used the standard conclusion artifact.
        standard = 'research/conclusion.json'
        if any(item.path == standard for item in client.list_artifacts(mlflow_run_id, 'research')):
            path = standard
    review: Report = {'mlflow_run_id': mlflow_run_id, 'evidence_status': status}
    if path is not None:
        with TemporaryDirectory() as tmp:
            artifact = Path(client.download_artifacts(mlflow_run_id, path, tmp))
            conclusion = json.loads(artifact.read_text())
        if conclusion.get('evidence_status', status) != status:
            raise ValueError('Tracked evidence status differs from the conclusion artifact')
        review.update(artifact_path=path, result=conclusion['result'],
                      limitations=conclusion['limitations'], decision=conclusion['decision'])
    return review


def main() -> None:
    """Publish a conclusion and its notes from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--conclusion', type=Path, required=True)
    parser.add_argument('--artifact-path', default='research/conclusion.json')
    args = parser.parse_args()
    publish(args.run, json.loads(args.conclusion.read_text()), args.artifact_path)


if __name__ == '__main__':
    main()
