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
Refresh **all tracked `*.tf` files**, including `producer.tf`, and `.terraform.lock.hcl`
from `infra/lambda/` before planning. Remove mirrored Terraform source files that are
no longer tracked; preserve the authoritative state and inputs.

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
4. Preserve the previous image digest, Terraform source revision and S3 UI together.
   Before overwriting public assets, copy the existing UI to a unique rollback
   prefix outside the public CloudFront origin. S3-to-S3 copy preserves content
   encoding and cache metadata:

   ```sh
   aws s3 cp s3://<cache_bucket>/data/cnec/v1/ui/ \
     s3://<cache_bucket>/ui-rollback/<previous-release>/ --recursive --copy-props default
   ```

   Record that prefix alongside the previous image digest in ignored deployment
   notes. On a first deployment there is no previous UI to archive.
5. Publish the built shell and **all shared assets, including OPF assets**, from the
   same checkout as the image:
   `pixi run --locked python -m coppersushi.data_sources.cnec_static --bucket <cache_bucket>`.
   This step is required on every frontend/shared-asset update, not just the first
   routing cutover. CI builds and checks assets; it does not publish them.
6. Set `image_uri` in the ignored variables file to the pushed image's **digest
   URI**, then review and apply a saved plan:

   ```sh
   terraform -chdir=.secrets/aws-production init
   terraform -chdir=.secrets/aws-production plan -out=deploy.tfplan
   terraform -chdir=.secrets/aws-production apply deploy.tfplan
   ```

7. Invalidate `/cnec*`, `/assets/*`, `/data/cnec/v1/ui/*` and
   `/_dash-component-suites/*` on CloudFront. Quote paths passed to the AWS CLI.
   Wait for invalidation to finish before verifying; both original request paths
   and rewritten S3 paths can have cached content.
8. Confirm the app and publisher Lambdas report successful updates with the expected
   image digest. Check that the daily schedule is enabled and the workflow points
   at the publisher. Verify `/opf-2024`, `/embed/opf-2024` and a prepared dated
   `/cnec/<day>` through the public hostname. Exercise time controls, reference and
   constraint selection, and inspect browser errors after loading completes.

### Rollback

Restore the previous Terraform source revision and image digest, then review and
apply a saved plan against the same authoritative state. Restore the archived UI
with S3-to-S3 copy so compression, MIME types and cache headers survive:

```sh
aws s3 cp s3://<cache_bucket>/ui-rollback/<previous-release>/ \
  s3://<cache_bucket>/data/cnec/v1/ui/ --recursive --copy-props default
```

Use `cp`, rather than timestamp-based `sync`, so same-size older assets are also
restored. Repeat step 7 and the browser checks from step 8. Restoring only the Lambda
image does not roll back the S3-owned CNEC or OPF assets.

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

CloudFront serves CNEC pages, shared `/assets/*` and prepared interval files from
private S3. The page resolver rewrites CNEC URLs to the shell; raw source caches
and UI rollback archives are not public. Manifests and the shell have short cache
lifetimes; generation data is immutable. Dash component assets are cached at the
Lambda origin, while OPF page layouts and callback POSTs remain uncached.

HTTPS is enforced for viewers and origins. CloudFront's 60-second origin read
timeout can end a slow OPF callback before Lambda's 120-second timeout. The direct
Function URL remains accessible.

## Prepared CNEC data

Shared metadata and uniform interval objects live under `data/cnec/v2/` in the private cache bucket. The publisher writes immutable objects before replacing a manifest cached for 60 seconds. The browser loads the selected interval first and prefetches the rest in parallel through shared query keys. Dates without a prepared publication show an availability message.

Publish a day with `python -m coppersushi.data_sources.cnec_bundles YYYY-MM-DD --bucket <cache_bucket>`. Use `--refresh` for a correction, or `--directory data/browser` for local static files. Frontend publication and rollback follow [Deploy an update](#deploy-an-update).

## Handler separation

CloudFront serves `/cnec*` and `/assets/*` from the published private S3 UI
prefix. There is no production CNEC serving Lambda or interval API. OPF and Dash component routes stay on `app:server`.
The CNEC shell imports neither Dash nor pandas. Data preparation runs only in the background producer. The frontend uses the official React Plotly
component and a pinned Mapbox-only Plotly bundle.

The browser computes the default market date locally; a cached shell cannot freeze it on its publication date.

The supported delivery window starts on 1 November 2026. Backfill prepared day
generations before moving that boundary earlier; the planned historical boundary
is 5 November 2025. The frontend never starts an upstream fetch for a visitor.

For local development, prepare a day with
`python -m coppersushi.data_sources.cnec_bundles YYYY-MM-DD --directory data/browser`.
The local shell serves the same static file format as CloudFront. No upstream fetch
is initiated by browser navigation.

### Daily publication

EventBridge Scheduler starts a Step Functions Standard execution at 15:50 Europe/Brussels. The scheduled instant pins tomorrow’s delivery date, including across DST. A dedicated publisher first requires JAO monitoring to mark Active FB Constraints, Allocation Constraints, Alpha factor from MCP and Net Position as Received for that delivery day. Only then are sparse active rows meaningful: a received empty set is valid; an absent or pending publication is retried. Interval attribution and prices must also be complete before fetching geometry. Complete days are skipped. Missing publications and transient upstream failures wait two minutes before another attempt; the execution stops after five hours. Unexpected failures get three short retries, then fail visibly in the execution history. Lambda only runs during an attempt.

JAO’s [Core handbook](https://publicationtool.jao.eu/PublicationHandbook/Core_PublicationTool_Handbook_v2.2.pdf) lists active constraints at 13:30 D−1 and alpha/net positions at 15:50 D−1. All required feeds must be complete before the manifest is exposed.
