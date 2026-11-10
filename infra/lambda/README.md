# Static application hosting and publication

CloudFront serves both app shells, shared assets and prepared CNEC/OPF files from
the private S3 bucket at [coppersushi.121gigawatts.org](https://coppersushi.121gigawatts.org).
The native CNEC publisher Lambda and its Step Functions schedule prepare market data.
Python prepares sanctioned OPF hours offline; no public app server is required.

## Deployment state

Tracked `infra/lambda/` owns Terraform source. Ignored `.secrets/aws-production/`
holds the authoritative `terraform.tfstate` and `terraform.tfvars.json`; read its
`README.local.txt` first. If missing, locate the primary checkout with
`git worktree list`. Never initialize replacement state. Refresh all tracked `*.tf`
and `.terraform.lock.hcl` in that directory; delete obsolete mirrored Terraform source
files while preserving state, inputs and rollback notes.

## Frontend and OPF publication

Use one merged checkout for preparation, publication and rollback notes:

1. Run `pixi run --locked setup-app`, `pixi run --locked frontend-test` and routing tests.
2. Generate token-free OPF files with
   `pixi run --locked -e build python -m coppersushi.opf.data_sources.opf_bundle`.
3. Before overwriting UI or the OPF manifest, archive `data/cnec/v1/ui/` and
   `data/opf/v1/opf-2024/manifest.json` under a unique `ui-rollback/<release>/`
   prefix. Use `aws s3 cp --copy-props default` to preserve encoding, MIME types
   and cache headers. Record the release revision and previous publisher digest
   in ignored deployment notes. Keep private rollback prefixes out of origin policy.
4. Publish immutable hours first:
   `pixi run --locked python -m frontend.opf_data --directory data/opf-2024 --bucket <bucket>`.
   This uploads all content-versioned hours before the timestamp manifest.
5. Publish both view shells and shared assets:
   `pixi run --locked python -m frontend.publish --bucket <bucket>`.
6. Invalidate `/`, `/cnec*`, `/embed/cnec*`, `/opf-2024*`, `/embed/opf-2024*`,
   `/assets/*`, `/data/cnec/v1/ui/*` and `/data/opf/v1/opf-2024/manifest.json`.
   Quote paths. Wait for invalidation completion before verifying.
7. Through the public hostname, verify CNEC day/interval/reference/selection and
   Power Flow hours, hover content, direction markers, camera persistence, rapid
   scrubbing, embed sizing and loading/errors. Inspect console and failed requests.

Ordinary frontend updates require no image build or Terraform apply. Preserve immutable
OPF generations so cached manifests and rollback shells continue to resolve.

## Cut over from the serving Lambda

Do not retire the server before static data and shells are published.

1. Back up state, variables and old Terraform source revision. Record the serving
   image digest and Function URL for rollback. Remove `image_uri` from the new
   inputs; preserve `producer_image_uri`, bucket, repository and secret resources.
2. Publish and verify the frontend and OPF data as above in local standalone preview.
3. Refresh tracked Terraform source and initialize the existing working directory.
   Save a **routing-only** plan:

   ```sh
   terraform -chdir=.secrets/aws-production plan -target=aws_cloudfront_distribution.app -target=aws_s3_bucket_policy.cache -out=static-routing.tfplan
   terraform -chdir=.secrets/aws-production show static-routing.tfplan
   terraform -chdir=.secrets/aws-production apply static-routing.tfplan
   ```

   Review the plan: it changes CloudFront routing and origin permissions, with the
   serving Lambda still present in state. The default origin is S3; unrecognized
   app paths return 404 at the edge. Direct data behaviors expose only intended
   `data/cnec/*` and `data/opf/*` prefixes.
4. Wait for CloudFront deployment, invalidate the paths above, and complete public
   browser verification. Confirm there are no Dash callback/component requests.
   Confirm the publisher Lambda, workflow and daily schedule remain unchanged.
5. Only after that verification, review a full saved plan and apply it to remove
   the retired serving Lambda, public Function URL, permissions, role and log group.
   No publisher, storage, secret, repository or schedule resources should be destroyed.

Targeted apply is a one-time migration step. All subsequent infrastructure updates
use full saved plans.

## Rollback

Before retirement, restore the previous Terraform source and variables and review
and apply a full plan to return CloudFront to the existing Lambda. After retirement,
the same rollback recreates the server from its preserved image digest. Preserve
that digest in ECR until the release is accepted.

Restore archived UI and OPF manifest with S3-to-S3 `cp --copy-props default`, then
invalidate and verify again. Do not use timestamp-based `sync`: same-size older
assets must also be restored. Immutable hours do not need overwriting.

## Publisher deployment

For changes to market preparation, run `pixi run --locked setup-app`, build
`docker build --platform linux/amd64 --provenance=false --target publisher -t <image> .`,
authenticate Docker to ECR with the configured AWS profile, and push a fresh immutable
tag to the `repository_url` output. Set `producer_image_uri` to its digest URI,
review a full saved Terraform plan, and apply it. Verify the publisher update,
workflow target and enabled daily schedule. Preserve its previous digest for rollback.

Set API key values separately with `python infra/lambda/configure-keys.py --profile <profile>`.
Keys come from the environment or ignored files; never put values in Terraform inputs,
command arguments or Git. The native publisher runs on `awslambdaric` and needs no Flask,
Dash or Web Adapter. Candidate solves remain local tooling through `app.py`.

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

