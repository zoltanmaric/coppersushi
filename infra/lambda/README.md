# AWS Lambda deployment

Terraform owns the Lambda function, private image repository, private S3 cache,
secret metadata, runtime permissions and logs. The `lambda` Docker target serves
the Dash app through AWS Web Adapter; the default target supports Heroku.

Put the selected AWS profile and region in ignored `terraform.tfvars.json`.
Run `terraform init`, `terraform plan`, and review the plan before `terraform apply` here.
With `image_uri` omitted, the first apply creates the private repository, cache, secret
metadata, role and logs. Set keys using `python infra/lambda/configure-keys.py --profile <profile>`
from the repo root. Values come from the environment or ignored `.secrets/`, never argv or state.

Build from the repo root with `docker build --platform linux/amd64 --provenance=false --target lambda -t <image> .`.
The [Heroku build inputs](../../README.md#installation-on-heroku) also supply the network,
endpoint seed and locator. Authenticate to private ECR, tag and push the image to the
`repository_url` output. Add its digest URI as `image_uri` in the ignored variables file;
review and apply a new plan. `trial_url` is the separate public endpoint.

The bootstrap copies the read-only seed to writable /tmp. Optional `COPPERSUSHI_CACHE_BUCKET`
enables S3 cache bundles; local use without it retains disk-only behavior. Lambda uses
`COPPERSUSHI_SECRET_ID` to read its own keys at runtime. The function inherits the account's
existing concurrency limit of ten; it does not request a quota increase.

State, plans, account identifiers and credentials remain ignored. Do not destroy the cache
bucket until its retained data is deliberately no longer needed.

## Runtime

The function runs in eu-west-1 with 2 GB memory, 1 GB of `/tmp` space, a
120-second timeout and seven-day logs. The image filesystem is read-only;
`/tmp` is disposable. Complete validated cache bundles persist in private S3.
Related tables publish together, and per-hour endpoint discoveries merge with
the seed without losing concurrent discoveries. Failed fetches remain retryable.

The image includes solved network data and derived zone outlines. The page
shell uses the outline bundle and defers PyPSA imports until an OPF request.
Lambda initialization and first-use data loading are separate costs. Buffered
synchronous responses must fit Lambda's 6 MB limit. Scale-to-zero removes idle
compute charges; storage, logs and requests still incur charges.
