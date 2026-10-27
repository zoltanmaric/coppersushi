# Lambda trial

Terraform owns the isolated trial's AWS resources. The `lambda` Docker target adds AWS Web
Adapter; the default Docker target retains Heroku behavior. Architecture and acceptance:
[Lambda hosting](../../wiki/aws-lambda-hosting.md).

Put the selected AWS profile and region in ignored `terraform.tfvars.json`.
Run `terraform init`, `terraform plan`, and review the plan before `terraform apply` here.
With `image_uri` omitted, the first apply creates the private repository, cache, secret
metadata, role and logs. Set keys using `python infra/lambda/configure-keys.py --profile <profile>`
from the repo root. Values come from the environment or ignored `.secrets/`, never argv or state.

Build from the repo root with `docker build --platform linux/amd64 --target lambda -t <image> .`.
The [Heroku build inputs](../../README.md#installation-on-heroku) also supply the network,
endpoint seed and locator. Authenticate to private ECR, tag and push the image to the
`repository_url` output. Add its digest URI as `image_uri` in the ignored variables file;
review and apply a new plan. `trial_url` is the separate public endpoint.

The bootstrap copies the read-only seed to writable /tmp. Optional `COPPERSUSHI_CACHE_BUCKET`
enables S3 cache bundles; local use without it retains disk-only behavior. Lambda uses
`COPPERSUSHI_SECRET_ID` to read its own keys at runtime. The trial inherits the account's
existing concurrency limit of ten; it does not request a quota increase.

State, plans, account identifiers and credentials remain ignored. Do not destroy the cache
bucket until its retained data is deliberately no longer needed. Production cutover and
blog edits require a separate user decision.
