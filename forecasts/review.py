"""Publish one conclusion artifact and derive its visible MLflow notes."""
import argparse
import json
from pathlib import Path
from urllib.parse import quote

from forecasts.run import tracking_client


def publish(run_id, conclusion, artifact_path):
    client = tracking_client()
    run = client.get_run(run_id)
    # Validate the synopsis before publishing either representation.
    sections = [f"**{label}:** {conclusion[key]}" for label, key in
                [('Result', 'result'), ('Limitation', 'limitations'), ('Decision', 'decision')]]
    base = f"#/experiments/{run.info.experiment_id}/runs/{run_id}/artifacts"
    sections.append(f"[Full conclusion]({base}?path={quote(artifact_path, safe='')})")
    for evidence in conclusion.get('evidence_artifacts', []):
        prefix = f'runs:/{run_id}/'
        target = f"{base}?path={quote(evidence[len(prefix):], safe='')}" if evidence.startswith(prefix) else evidence
        sections.append(f"[Evidence: {evidence}]({target})")
    if run.data.tags.get('timing_semantics') == 'logging_only':
        sections.append('Historical duration is logging-only; compute time was not recorded.')
    client.log_dict(run_id, conclusion, artifact_path)
    client.set_tag(run_id, 'mlflow.note.content', '\n\n'.join(sections))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--conclusion', type=Path, required=True)
    parser.add_argument('--artifact-path', default='research/conclusion.json')
    args = parser.parse_args()
    publish(args.run, json.loads(args.conclusion.read_text()), args.artifact_path)
