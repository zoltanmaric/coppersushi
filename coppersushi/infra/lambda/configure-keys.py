"""Set the app's private API keys without passing values through argv or Terraform."""
import argparse
import os
from pathlib import Path
import subprocess
import json

import boto3

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--profile", required=True)
parser.add_argument("--region", default="eu-west-1")
root = Path(__file__).resolve().parents[3]
parser.add_argument("--state-dir", type=Path, default=root / ".secrets/aws-production")
parser.add_argument("--key-dir", type=Path, default=root / ".secrets")
parser.add_argument("--market-archive", action="store_true", help="Also configure ENTSO-E for the market archive")
args = parser.parse_args()
secret = subprocess.check_output(["terraform", f"-chdir={args.state_dir}", "output", "-raw", "secret_arn"], text=True).strip()
client = boto3.Session(profile_name=args.profile, region_name=args.region).client("secretsmanager")
try:
    previous = client.get_secret_value(SecretId=secret)
except client.exceptions.ResourceNotFoundException:
    values = {}
else:
    values = json.loads(previous["SecretString"])
keys = [("MAPBOX_TOKEN", ".mapbox_token"), ("ELECTRICITY_MAPS_API_KEY", ".electricity_maps_api_key")]
if args.market_archive:
    keys.append(("ENTSOE_API_TOKEN", ".entsoe_api_token"))
for name, filename in keys:
    values[name] = os.environ.get(name) or (args.key_dir / filename).read_text().strip()
    if not values[name]:
        raise ValueError(f"Missing {name}")
client.put_secret_value(
    SecretId=secret, SecretString=json.dumps(values))
print("API keys configured; no values printed or written to Terraform state.")
