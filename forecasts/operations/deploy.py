"""Deploy both Metaflow state machines from committed code and pinned inputs."""
import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

import boto3

from forecasts.operations.artifacts import ObjectPin
from forecasts.operations.flow_inputs import settings_from_pin
from forecasts.provenance import ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--config-pin", type=Path, required=True)
    args = parser.parse_args()
    pin = ObjectPin.model_validate_json(args.config_pin.read_bytes())
    settings = settings_from_pin(pin.model_dump_json())
    outputs = json.loads(subprocess.check_output(
        ["terraform", f"-chdir={ROOT}/forecasts/infra/aws", "output", "-json", f"-state={args.state.resolve()}"]
    ))
    if settings.bucket != outputs["operations_bucket"]["value"]:
        raise ValueError("Pinned settings point outside the Terraform operations bucket")
    repository = outputs["repository_url"]["value"].split("/", 1)[1]
    details = boto3.client("ecr").describe_images(repositoryName=repository, imageIds=[{"imageDigest": settings.image_digest}])
    revisions = [tag for tag in details["imageDetails"][0]["imageTags"] if re.fullmatch("[a-f0-9]{40}", tag)]
    if len(revisions) != 1:
        raise ValueError("The image must identify one exact Git revision")
    image = f"{outputs['repository_url']['value']}@{settings.image_digest}"
    env = {**os.environ, **outputs["metaflow_environment"]["value"], "METAFLOW_BATCH_CONTAINER_IMAGE": image,
           "FORECAST_CONFIG_PIN": pin.model_dump_json(),
           "FORECAST_READER_ROLE": outputs["witness_task_role_arn"]["value"],
           }
    with TemporaryDirectory() as directory:
        release = Path(directory)
        with subprocess.Popen(["git", "archive", revisions[0], "forecasts", "coppersushi/__init__.py",
                               "coppersushi/pipelines", "pyproject.toml", "pixi.lock"], cwd=ROOT,
                              stdout=subprocess.PIPE) as archive:
            assert archive.stdout is not None
            with tarfile.open(fileobj=archive.stdout, mode="r|") as contents:
                contents.extractall(release, filter="data")
            if archive.wait():
                raise ValueError("Unable to load the image revision from Git")
        env["PYTHONPATH"] = str(release)
        for flow in ("monthly_flow.py", "daily_flow.py"):
            subprocess.run([sys.executable, str(release / "forecasts/operations" / flow), "step-functions", "create"],
                           env=env, cwd=release, check=True)


if __name__ == "__main__":
    main()
