# Deploy Copper Sushi to AWS

This directory manages the Lambda deployment and CloudFront hostname at
[coppersushi.121gigawatts.org](https://coppersushi.121gigawatts.org).

## Deploy an update

Run commands from the repository root. Use the existing ignored
`infra/lambda/terraform.tfvars.json` and Terraform state for this deployment.
Keep the previous `image_uri` digest for rollback.

1. Run `git lfs pull` and prepare the JAO endpoint seed and OSM locator using the
   [market-data commands](../../README.md#market-data). The Docker build validates
   these inputs and precomputes the hourly OPF maps.
2. Build the Lambda target with a new image tag:
   `docker build --platform linux/amd64 --provenance=false --target lambda -t <image> .`
3. Authenticate Docker to ECR using the configured AWS profile. Tag and push the
   image to the `repository_url` Terraform output. ECR tags are immutable: use a
   fresh tag for each build.
4. Publish static files from that same image before changing the Lambda image.
   Create an empty `/tmp/coppersushi-static` directory, then export:

   ```sh
   docker run --rm --platform linux/amd64 --entrypoint micromamba \
     --mount type=bind,src=/tmp/coppersushi-static,dst=/export \
     <image> run -n base python infra/lambda/static_assets.py --output /export
   aws --profile <profile> s3 cp /tmp/coppersushi-static/ s3://<static_bucket>/ \
     --recursive --cache-control 'public,max-age=300'
   aws --profile <profile> s3 cp /tmp/coppersushi-static/ s3://<static_bucket>/ \
     --recursive --exclude '*' --include '*.v*m*.*' \
     --cache-control 'public,max-age=31536000,immutable'
   ```

   Use the `static_bucket` Terraform output. Retain older objects for pages still
   using earlier fingerprinted URLs. After changing assets or dependencies,
   invalidate `/assets/*` and `/_dash-component-suites/*` on CloudFront; quote
   both paths in the CLI. The image digest and exported files must match.
5. Set `image_uri` in the ignored variables file to the pushed image's **digest
   URI**, then review and apply a saved plan:

   ```sh
   terraform -chdir=infra/lambda init
   terraform -chdir=infra/lambda plan -out=deploy.tfplan
   terraform -chdir=infra/lambda apply deploy.tfplan
   ```

6. Verify `/opf-2024`, `/embed/opf-2024` and a dated `/cnec/<day>` page through the
   public hostname. Exercise the hourly controls and constraint selection; a
   successful HTML response alone does not verify Dash callbacks.

To roll back, restore the previous image digest, review and apply another plan,
and invalidate the static paths again.

## Initial setup

Configure `profile` and `region` in the ignored variables file. Leave `image_uri`
and `custom_domain` unset for the first apply; this creates the repository, private
cache bucket, secret metadata, IAM role and logs. Set the API keys below, then
build and push an image, set `image_uri`, and apply a plan. Add the hostname
after the function exists; publish static files once its asset bucket exists.

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
On the first deployment, leave `static_assets_enabled=false` until the bucket
and access policy exist and all image assets are uploaded. Then set it to `true`
and apply another plan to switch the two static paths to S3. Keep it enabled for
subsequent deployments. Setting it to `false` restores Lambda asset delivery.


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

The image precomputes zone outlines and 24 hourly OPF figures without credentials.
Runtime reads the selected hour and adds the Mapbox token. Local checkouts without
bundles render on demand. Lambda initialization and first-use data loading are
separate costs. Buffered synchronous responses must fit Lambda's 6 MB limit.
Scale-to-zero avoids idle compute charges; storage, logs and requests still cost.

## Delivery

CloudFront forwards cookies, query strings and headers except Host, which names
the Lambda origin for dynamic requests. `/assets/*` and
`/_dash-component-suites/*` use a separate private S3 origin and are cached,
with query strings in cache keys. Fingerprinted bundles retain Dash's cache
lifetime; other static files have a five-minute minimum edge lifetime. Browser
headers retain the published cache lifetimes. CloudFront alone can read the
asset bucket through signed origin requests. Page layouts and callback POSTs
remain uncached on Lambda.

HTTPS is enforced for viewers and origin connections. CloudFront's 60-second
origin read timeout can end a slow callback before Lambda's 120-second timeout.
The direct Function URL remains accessible.
