# AWS Lambda deployment

Production: [coppersushi.121gigawatts.org](https://coppersushi.121gigawatts.org).

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

The image includes derived zone outlines and all 24 hourly OPF figures. Each
compressed figure contains one hour without credentials; runtime reads the
selected hour and adds the Mapbox token. Neither page reconstructs the solved
network at runtime. Local checkouts without bundles render on demand.
Lambda initialization and first-use data loading are separate costs. Buffered
synchronous responses must fit Lambda's 6 MB limit. Scale-to-zero removes idle
compute charges; storage, logs and requests still incur charges.

Cached-day measurements on 2026-10-27 put new-environment OPF callbacks at
4.3–6.0 seconds and warm callbacks at 0.65–0.78 seconds. These samples are not
a latency guarantee and do not cover uncached provider requests.

## Hostname

For a custom hostname, set `custom_domain`. First plan/apply only
`aws_acm_certificate.app`, publish the `certificate_dns` CNAME in the existing DNS
provider, then plan/apply the full configuration. Point the hostname at
`hostname_target` with a DNS-only CNAME. ACM certificates for CloudFront use us-east-1.

CloudFront forwards cookies, query strings and request headers except Host, which
names the Lambda origin. Only `/assets/*` and `/_dash-component-suites/*` are cached, with query strings
in cache keys. Fingerprinted bundles retain Dash’s cache lifetime; other static
files have a five-minute minimum edge lifetime. Browser headers are unchanged.
Page layouts and callback POSTs remain uncached. HTTPS is enforced on both
connections. The 60-second origin read timeout can end a slow callback before
Lambda’s 120-second timeout. The direct Function URL remains accessible.

After asset or Dash dependency changes, invalidate `/assets/*` and
`/_dash-component-suites/*` on the distribution, quoting both paths.
