# Static application hosting and publication

CloudFront serves app shells, shared assets and prepared CNEC/OPF files from
the private S3 bucket at [coppersushi.121gigawatts.org](https://coppersushi.121gigawatts.org).
The native CNEC publisher Lambda and its Step Functions schedule prepare market data.
Python prepares sanctioned OPF hours offline; no public app server is required.

## Deployment state

Tracked `coppersushi/infra/lambda/` owns Terraform source. Ignored `.secrets/aws-production/`
holds the authoritative `terraform.tfstate` and `terraform.tfvars.json`; read its
`README.local.txt` first. If missing, locate the primary checkout with
`git worktree list`. Never initialize replacement state. Refresh all tracked `*.tf`
and `.terraform.lock.hcl` in that directory; delete obsolete mirrored Terraform source
files while preserving state, inputs and rollback notes.

## Frontend and OPF publication

Use one merged checkout for preparation, publication and rollback notes:

1. Run `pixi run --locked setup-app`, `pixi run --locked frontend-test` and routing tests.
2. Generate token-free OPF files with
   `pixi run --locked -e build python -m coppersushi.pipelines.powerflow.data_sources.dataset coppersushi/networks/opf-2024-08-29.nc coppersushi/data/browser/data/opf/v2/opf-2024`.
3. Before overwriting UI or the OPF manifest, archive `data/cnec/v1/ui/` and
   `data/opf/v2/opf-2024/manifest.json` when present under a unique `ui-rollback/<release>/`
   prefix. If the active frontend still uses v1, archive its v1 manifest as well.
   Preserve the manifest matching the frontend release being saved.
   Use `aws s3 cp --copy-props default` to preserve encoding, MIME types
   and cache headers. Record the release revision and previous publisher digest
   in ignored deployment notes. Keep private rollback prefixes out of origin policy.
4. Publish immutable hours first:
   `pixi run --locked -e build python -m coppersushi.pipelines.powerflow.data_sources.dataset coppersushi/networks/opf-2024-08-29.nc coppersushi/data/browser/data/opf/v2/opf-2024 --bucket <bucket>`.
   This uploads all content-versioned hours before the timestamp manifest.
5. Publish view shells and shared assets:
   `pixi run --locked python -m coppersushi.frontend.packaging.publish --bucket <bucket>`.
6. Invalidate `/`, `/cnec*`, `/embed/cnec*`, `/opf-2024*`, `/embed/opf-2024*`,
   `/assets/*`, `/data/cnec/v1/ui/*` and `/data/opf/v2/opf-2024/manifest.json`.
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
`docker build -f coppersushi/infra/lambda/Dockerfile --platform linux/amd64 --provenance=false --target publisher -t <image> .`,
authenticate Docker to ECR with the configured AWS profile, and push a fresh immutable
tag to the `repository_url` output. Set `producer_image_uri` to its digest URI,
review a full saved Terraform plan, and apply it. Verify the publisher update,
workflow target and enabled daily schedule. Preserve its previous digest for rollback.

Set API key values separately with `python coppersushi/infra/lambda/configure-keys.py --profile <profile>`.
Keys come from the environment or ignored files; never put values in Terraform inputs,
command arguments or Git. The native publisher runs on `awslambdaric` and needs no Flask,
Dash or Web Adapter. For local map inspection, follow [Preview a candidate network](../../pipelines/powerflow/README.md#preview-a-candidate-network).

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
    docker build -f coppersushi/infra/lambda/Dockerfile --platform linux/amd64 --provenance=false --target publisher -t <image> .
)
```

Use the normal Docker configuration for the ECR login and push. To repair the
normal GHCR login instead, refresh its credentials, or run `docker logout ghcr.io`
if authenticated GHCR access is no longer needed. A successful anonymous build
identifies the saved-credential problem; it does not establish why that credential
was rejected.

## Prepared CNEC data

Shared metadata and uniform interval objects live under `data/cnec/v3/` in the private cache bucket. The publisher writes immutable objects before replacing a manifest cached for 60 seconds. The browser loads the selected interval first and prefetches the rest in parallel through shared query keys. Dates without a prepared publication show an availability message.

Publish a day with `python -m coppersushi.pipelines.cnec.data_sources.bundles YYYY-MM-DD --bucket <cache_bucket>`. Use `--refresh` for a correction, or `--directory coppersushi/data/browser` for local static files. Frontend publication and rollback follow [Frontend and OPF publication](#frontend-and-opf-publication).

### Rebuilding prepared data after a contract change

The scheduler skips any day whose manifest already exists. Deploying a publisher
image does not rebuild those days. For a data-contract change:

1. Save each existing supported day's manifest with the image/UI rollback notes.
   For the v2 → v3 migration, list `data/cnec/v2/` in the private bucket and select the dated manifests in the
   supported window (starting 5 November 2025). Preserve those v2 objects; publish
   and verify corresponding v3 manifests before frontend rollout. Use a fresh backfill
   report for the migration; resumed reports also recheck destination manifests.
2. From the new checkout, run the publication CLI above for **every listed day**.
   Do not use the scheduled handler: its manifest-existence check skips the work.
   The CLI prepares and publishes unconditionally; `--refresh` is only needed to
   refresh upstream observations. For historical days with accepted Polish
   attribution gaps, add `--allow-partial-attribution`; alpha and receipt checks
   still apply. Confirm every physical row has its required EIC.
3. Each rebuild writes a new immutable content-hash generation, then replaces the
   day manifest. Invalidate `/data/cnec/v3/*/manifest.json` on CloudFront and wait
   for completion before publishing the new frontend. Keep the previous generations.
4. Deploy the matching publisher and frontend following the deployment steps above.
   Existing open tabs may fail validation during this silent-release cutover; reload
   them after the new frontend is published. No cross-version compatibility is promised.

Rollback restores the saved manifests **as well as** the previous image and UI,
then invalidates manifests and frontend assets. Old generations alone are insufficient:
the restored manifest must point to the generation matching that reader's contract.

### Daily publication

EventBridge Scheduler starts a Step Functions Standard execution at 15:50 Europe/Brussels. The scheduled instant pins tomorrow’s delivery date, including across DST. A dedicated publisher first requires JAO monitoring to mark Active FB Constraints, Allocation Constraints, Alpha factor from MCP and Net Position as Received for that delivery day. Only then are sparse active rows meaningful: a received empty set is valid; an absent or pending publication is retried. Interval attribution and prices must also be complete before fetching geometry. If only the Polish alternative-price feed is empty, the publisher serves available data with an interval warning wherever the cap contribution is unknown. The manifest’s S3 metadata records partial attribution. The same workflow checks every six hours for a complete replacement, up to the Standard workflow’s one-year limit. Complete days are skipped. Missing publications and transient upstream failures wait two minutes before another attempt; initial publication stops after five hours. Unexpected failures get three short retries, then fail visibly in the execution history. Lambda only runs during an attempt. Every deferred attempt logs its delivery date, exception type and reason to the publisher’s CloudWatch log. Unpublished days in the browser recheck the manifest every minute while visible and on return to the page; polling stops after publication.

JAO’s [Core handbook](https://publicationtool.jao.eu/PublicationHandbook/Core_PublicationTool_Handbook_v2.2.pdf) lists active constraints at 13:30 D−1 and alpha/net positions at 15:50 D−1. All required feeds must be complete before the manifest is exposed.

The reserve-enriched Critical Elements publication uses `data/cnec/v3`.
Populate required historical days through the existing publisher/backfill path before
switching the frontend to v3. Preserve v2 objects for older clients. Refresh a v3 day
explicitly to retry missing PSE evidence; completed publications are otherwise skipped.

## Fixed export-cap study

The third page and two embeds use the existing static origin. Prepare the complete
fixed-window artifact from the investigated CSV and prepared November extension:

```sh
pixi run --locked python -m scripts.polish_cap_page build --baseline <baseline.csv> --extension <prepared-extension-directory> --directory coppersushi/data/browser
pixi run --locked python -m scripts.polish_cap_page publish --directory coppersushi/data/browser --bucket <bucket>
```

The build reconciles all binding rows against immutable CNEC generations, verifies
the overlap and complete population, and writes under
`data/cnec/studies/polish-export-caps/`. The local preview serves this study from disk.
Publication validates the content hash and checks that pinned map metadata exists
in S3 before uploading the study, then its manifest. Preserve all pinned generations.
Raw research files remain local; review redistribution rights before publication.

Archive the study manifest alongside the UI before replacing either. Publish the
study before the frontend shells. The initial route addition needs a reviewed full
Terraform plan from the existing state; later content updates do not. Invalidate
`/polish-export-caps*`, `/embed/polish-export-caps/*`, the study manifest and the
frontend paths listed above. Wait for completion, then verify all three public
routes, the fixed counts, filters, independent row scrolling, cross-day selection
and camera reload. Rollback restores the archived study manifest and UI together.

## Market archive collection

Build and push the Lambda Dockerfile’s `market-collector` target. Set `market_collector_image_uri`
to the immutable digest and configure the Electricity Maps and ENTSO-E credentials
with `configure-keys.py --profile "$AWS_PROFILE" --market-archive`. The four independent Scheduler targets collect today's
delivery day at fifteen-minute intervals from 09:00 to 10:45 Berlin and tomorrow's
at half-hour intervals from 13:00 to 18:30. Each target polls one publisher and
uses the scheduled date even when dispatch is delayed.

Set `market_collector_alert_topic_arn` to the monitoring stack’s `topic_arn` (or a same-region standard SNS topic with a confirmed operator subscription). An asynchronous invocation that exhausts Lambda’s retries sends its failure record to this topic. Each retry polls again with new attempt IDs. A publisher cooldown logs `poll_deferred` with the earlier attempt ID and retry time. A deferral confirms the pause only.

Use the notification’s function ARN and request ID to find the invocation in CloudWatch Logs. Trace `poll_started`, `raw_saved`, and the failed operation by attempt ID. A raw receipt alone means “response received; processing outcome unknown.” An `edition_published` event with zero rows identifies a validated empty response. Before rollout, inject an edition write failure in an isolated trial and confirm a subscriber can trace the terminal notification to the retained raw response.

To witness a completed delivery day on demand, invoke each publisher's Lambda:
`aws lambda invoke --function-name coppersushi-trial-market-entsoe --cli-binary-format raw-in-base64-out --payload '{"publisher":"entsoe","delivery_day":"2026-11-20"}' /tmp/market-poll-result.json`.
Repeat with `electricity_maps`, `smard`, or `jao` in both the function name and payload.
Inspect FunctionError and the returned attempt IDs. Inspect private archive objects
for diagnostics; an empty feed and an HTTP failure have distinct outcomes.

Collect the required delivery days before cutting consumers over. An on-demand
historical poll establishes usability from its actual collection and validation onward.
For a pre-archive decision deadline use the registered historical replay contract.
Keep `market-data/` private; only the product's existing public CNEC output is served.
