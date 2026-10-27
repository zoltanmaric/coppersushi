# AWS Lambda hosting

As of 2026-10-27, the isolated Lambda trial uses an S3-backed cache for
Copper Sushi. Heroku remains production.

## Trial

Keep the existing Dash app and route contract; wrap the web server with
[AWS Lambda Web Adapter](https://github.com/aws/aws-lambda-web-adapter). The trial
uses a separate public Function URL, a private ECR image repository and a private
S3 bucket in eu-west-1. No blog edit or production cutover is part of the trial.

Starting settings: 2 GB memory, 1 GB /tmp, 120-second timeout, concurrency capped at
the account’s existing limit of 10, seven-day logs. These are the deployed trial settings.
Keys are read from a trial-specific Secrets Manager secret at runtime. Terraform manages only its metadata; secret values stay outside the image and state. The image contains
the solved network, derived Core-zone outline bundle, locator CSVs and endpoint seed; dynamic caches use /tmp and S3.

## Cache

The [Lambda image filesystem is read-only](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html).
Only /tmp is writable and its contents are disposable. Complete validated cache entries
must survive instance replacement in private S3. Related tables publish together;
partial provider fetches must not become complete cache hits. Endpoint discoveries use
separate entries containing the complete validated result for a published hour, not
just that request's missing endpoints. Merge these with the seed; verify simultaneous
writes to the same hour and different hours without lost discoveries. Failed reads or fetches remain explicit and retryable.

## Verification

Measure cold/warm OPF and CNEC loads, memory and largest Dash responses; test a
cross-origin iframe and mobile controls. Verify that a fresh instance reuses S3 and
concurrent endpoint discoveries survive. The [Lambda limits](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)
include 10 GB container images and 6 MB buffered synchronous responses; the existing
2.2 GB image fits, while the largest measured OPF response is 3.24 MB uncompressed (589 KB gzip).
Live OPF, CNEC selection, private-cache reuse and cross-origin framing passed. The
first-image startup outlier still needs assessment before a production cutover.

The [hosting decision](copper-sushi-app.md#hosting) accepts occasional loads around
30 seconds. Moving production requires verified trial behavior and a separate decision
about the blog iframe's destination. Scale-to-zero avoids idle compute charges; storage,
logs and requests still incur usage charges.

## Startup

Lambda initialization and application-cache loading are separate costs. A warm execution
environment that previously served only assets may still need its first CNEC day. The
2026-10-27 trial recorded an 11.7-second invocation without Lambda initialization. Local
profiling of that interval spent 2.63 of 3.57 seconds reconstructing the solved network
just for country outlines. The image therefore builds a small zone-outline bundle; the
page shell also defers PyPSA imports until an OPF request. These changes preserve the
same polygons and dispatch. Live verification found two subsequent new execution environments at 5.34 and 5.56
seconds end to end, including 2.29 and 2.66 seconds of Lambda initialization. A warm
request took 0.95 seconds. The first request to the newly deployed image took 47 seconds;
that outlier remains unresolved. These are samples for a day already in S3, not a latency
guarantee or evidence about uncached provider requests.
