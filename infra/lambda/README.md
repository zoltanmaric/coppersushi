# Deploy Copper Sushi to AWS

This directory manages the Lambda deployment and CloudFront hostname at
[coppersushi.121gigawatts.org](https://coppersushi.121gigawatts.org).

## Deploy an update

Run commands from the repository root. Tracked `infra/lambda/` holds the Terraform
source; the existing production working directory is ignored
`.secrets/aws-production/`. Its `terraform.tfstate` is authoritative and
`terraform.tfvars.json` holds the deployment inputs. Read its `README.local.txt`
before use. Keep the previous `image_uri` digest for rollback.

Ignored deployment files do not follow Git worktrees. If this directory is absent,
locate the primary checkout with `git worktree list` and check there before asking
for configuration. Do not initialize replacement state for an existing deployment.
Refresh the working directory's `main.tf`, `hostname.tf` and `.terraform.lock.hcl`
from the merged `infra/lambda/` sources before planning; preserve its state and inputs.

1. Run `pixi run --locked setup-app` in this checkout to prepare the validated
   endpoint seed, locator, element catalog and country outlines. This is the same
   setup used for local development and needs no data from another worktree.
   Downloads remain outside Docker; the image build validates its bundled inputs
   and precomputes hourly OPF maps. See the [catalog workflow](../../config/element-catalog/README.md).
2. Build the Lambda target with a new image tag:
   `docker build --platform linux/amd64 --provenance=false --target lambda -t <image> .`
   For a GHCR token error, see [GHCR authentication](#ghcr-authentication).
3. Authenticate Docker to ECR using the configured AWS profile. Tag and push the
   image to the `repository_url` Terraform output. ECR tags are immutable: use a
   fresh tag for each build.
4. Set `image_uri` in the ignored variables file to the pushed image's **digest
   URI**, then review and apply a saved plan:

   ```sh
   terraform -chdir=.secrets/aws-production init
   terraform -chdir=.secrets/aws-production plan -out=deploy.tfplan
   terraform -chdir=.secrets/aws-production apply deploy.tfplan
   ```

5. If static assets or Dash dependencies changed, invalidate `/assets/*` and
   `/_dash-component-suites/*` on the CloudFront distribution. Quote both paths
   when passing them to the AWS CLI. Wait for invalidation to complete before
   reloading the site for verification; old component assets can break the new UI.
6. Confirm Lambda reports a successful update and its resolved image digest matches
   the pushed digest. Verify `/opf-2024`, `/embed/opf-2024` and a dated `/cnec/<day>`
   page through the public hostname. Exercise the hourly controls and constraint selection; a
   successful HTML response alone does not verify Dash callbacks.

To roll back, restore the previous image digest, review and apply another plan,
and invalidate the static paths again.

## GHCR authentication

A saved GHCR credential rejected with HTTP 403 can block pulling the public Pixi
image even when anonymous access and CI work. On macOS, an empty `DOCKER_CONFIG`
directory is not an anonymous test: Docker can still discover the native keychain
([Docker credential-store behavior](https://docs.docker.com/reference/cli/docker/login/#default-behavior)).

For a local Docker Desktop build without changing saved logins, explicitly supply
an empty GHCR auth entry and retain the current daemon endpoint:

```sh
(
  set -e
  registry_config=$(mktemp -d)
  trap 'rm -rf "$registry_config"' EXIT
  printf '%s\n' '{"auths":{"ghcr.io":{}}}' > "$registry_config/config.json"
  docker_endpoint=$(docker context inspect --format '{{.Endpoints.docker.Host}}')
  DOCKER_CONFIG="$registry_config" DOCKER_HOST="$docker_endpoint" \
    docker build --platform linux/amd64 --provenance=false --target lambda -t <image> .
)
```

Use the normal Docker configuration for the ECR login and push. To repair the
normal GHCR login instead, refresh its credentials, or run `docker logout ghcr.io`
if authenticated GHCR access is no longer needed. A successful anonymous build
identifies the saved-credential problem; it does not establish why that credential
was rejected.

## Initial setup

Configure `profile` and `region` in the ignored variables file. Leave `image_uri`
and `custom_domain` unset for the first apply; this creates the repository, private
cache bucket, secret metadata, IAM role and logs. Set the API keys below, then
deploy an image using the steps above before adding the hostname.

Set API keys separately:

```sh
python infra/lambda/configure-keys.py --profile <profile>
```

This needs Python with `boto3` and the Terraform CLI. Values come from
`MAPBOX_TOKEN` and `ELECTRICITY_MAPS_API_KEY`, or their files in `.secrets/`.
They do not enter command arguments, the image or Terraform state. Pass `--region`
if using a region other than eu-west-1.

For the hostname, set `custom_domain`, plan/apply only `aws_acm_certificate.app`,
and publish the `certificate_dns` CNAME at the DNS provider. Then review and apply
an untargeted plan. Point the hostname's DNS-only CNAME at `hostname_target`.
The certificate is created in us-east-1 for CloudFront.

## State

Keep state, plans, variables and credentials out of Git. Preserve the existing
resource names and cache bucket; changing an identifier can replace a resource.
The Terraform output `trial_url` names the direct Function URL; use `custom_url`
for the public site.

## Runtime

Lambda runs in eu-west-1 with 2 GB memory, 1 GB of disposable `/tmp` space, a
120-second timeout, concurrency capped at 10, and seven-day logs. The image is
read-only. Complete validated cache bundles persist in private S3; related
tables publish together and endpoint discoveries merge without lost concurrent
writes. Failed fetches remain retryable.

The `bundle-builder` stage uses the `build` environment to precompute zone outlines
and 24 hourly OPF figures without credentials. The final image uses `runtime`,
which omits PyPSA and its solver dependencies.
Runtime reads the selected hour and adds the Mapbox token. Local OPF views without
bundles render on demand; country outlines require `pixi run --locked build-zone-shapes`.
Lambda initialization and first-use data loading are separate costs. Buffered synchronous responses must fit Lambda's 6 MB limit.
Scale-to-zero avoids idle compute charges; storage, logs and requests still cost.

## Tracing

Active X-Ray service tracing samples Lambda requests and separates AWS environment
preparation from function execution. The execution role permits trace ingestion;
no application SDK is installed. Inspect traces in eu-west-1 alongside the matching
CloudWatch request IDs. See [AWS's trace structure](https://docs.aws.amazon.com/lambda/latest/dg/services-xray.html).

`AWS_LWA_ASYNC_INIT=true` lets application startup continue into the first invocation
after the adapter's roughly 9.8-second initialization limit. Lambda's `Init Duration`
therefore need not cover all application startup. Service traces do not profile
individual Python imports.

Lambda Insights is not installed: its agent officially supports Amazon Linux 2/2023,
whereas this image uses Ubuntu. See [container support](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Lambda-Insights-Getting-Started-docker.html).

## Delivery

CloudFront forwards cookies, query strings and headers except Host, which names
the Lambda origin. Only `/assets/*` and `/_dash-component-suites/*` are cached,
with query strings in cache keys. Fingerprinted bundles retain Dash's cache
lifetime; other static files have a five-minute minimum edge lifetime. Browser
headers are unchanged. Page layouts and callback POSTs remain uncached.

HTTPS is enforced for viewers and origin connections. CloudFront's 60-second
origin read timeout can end a slow callback before Lambda's 120-second timeout.
The direct Function URL remains accessible.

## Prepared CNEC data

The scheduled producer uses the same image in a separate Lambda without a Function
URL. It refreshes the current and next market day hourly, serially. The hourly schedule exceeds the 15-minute runtime limit, and
automatic invocation retries are disabled. Failed source loads leave the last published generation intact.

Complete day bundles and their initial-interval slices live under `data/cnec/v1/`
in the private cache bucket. CloudFront can read only that published prefix; raw
source cache objects remain private. The producer uploads immutable generation
objects before replacing a manifest cached for 60 seconds. A browser loads the
requested interval first, then shares one background request for the whole day.
Dates without prepared artifacts fall back to the data API.

To publish a historical day, run `python -m coppersushi.data_sources.cnec_bundles
YYYY-MM-DD --bucket <cache_bucket>` in the configured runtime environment. Add
`--refresh` to refetch published inputs. Never upload the raw source-cache prefix
as browser data.

## Handler separation

CloudFront serves `/cnec*` and `/assets/*` from the published private S3 UI
prefix. `/api/cnec/*` goes to the lightweight `cnec_server:server` fallback handler. OPF and Dash component routes stay on `app:server`.
The CNEC shell imports neither Dash nor pandas. Preparation dependencies load only
for dates missing from prepared data. The frontend uses the official React Plotly
component and a pinned Mapbox-only Plotly bundle.

Publish the built shell and public assets with
`python -m coppersushi.data_sources.cnec_static --bucket <cache_bucket>` before
applying the static-route change. Invalidate `/cnec*`, `/assets/*` and
`/data/cnec/v1/ui/*` after publishing changes. The browser computes the default
market date locally; a cached shell cannot freeze it on its publication date.
