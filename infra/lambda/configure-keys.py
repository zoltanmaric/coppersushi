"""Set the trial's private API keys without passing values through argv or Terraform."""
import argparse
import os
from pathlib import Path
import subprocess
import json

import boto3

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--profile", required=True)
parser.add_argument("--region", default="eu-west-1")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
secret = subprocess.check_output(["terraform", f"-chdir={root / 'infra/lambda'}", "output", "-raw", "secret_arn"], text=True).strip()
values = {}
for name, filename in [("MAPBOX_TOKEN", ".mapbox_token"), ("ELECTRICITY_MAPS_API_KEY", ".electricity_maps_api_key")]:
    values[name] = os.environ.get(name) or (root / ".secrets" / filename).read_text().strip()
    if not values[name]:
        raise ValueError(f"Missing {name}")
boto3.Session(profile_name=args.profile, region_name=args.region).client("secretsmanager").put_secret_value(
    SecretId=secret, SecretString=json.dumps(values))
print("Trial API keys configured; no values printed or written to Terraform state.")
