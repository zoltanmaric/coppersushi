# Retrieve a DE–LU forecast

The reader needs AWS access to the private operations bucket and the release’s configuration pin. In the main checkout the ignored deployment directory is `.secrets/forecast-operations/`. A linked worktree shares that state. Use the release pin for the issue month. `replay-pin.json` selects the November parity namespace. The live release uses its own pin.

```sh
export AWS_PROFILE=YOUR_LOCAL_PROFILE AWS_DEFAULT_REGION=eu-west-1
forecast_state="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.secrets/forecast-operations"
pixi run --locked -e runtime python -m forecasts.operations.read \
  --config-pin "$forecast_state/replay-pin.json" --delivery-date 2026-11-24 > issue.json
jq '{delivery_date,mode,run_id,fit_receipt,availability,quarters:(.quarters|length)}' issue.json
```

The configuration pin is a JSON object with S3 bucket, key, version ID and SHA-256. It can be used from any authorized machine. An operator can recover the deployed default from the first state's `METAFLOW_DEFAULT_PARAMETERS` in the Step Functions definition. Keep prior release pins for old months. The reader checks the dated object against the committed month pointer and the training manifest. A live result also needs a matching on-time first-read receipt. Each UTC quarter has five CatBoost prices and five seasonal reference prices.

## Trace or retry

1. Follow `fit_receipt.fit` to the exact S3 version of `fits/YYYY-MM.json`. Its `files` map pins the model, seasonal reference, configuration and archive selection audit. The pointer records the training execution, code, image digest and input versions. The edition carries the daily lag evidence.
2. List `attempts/YYYY-MM-DD/` in the same bucket. Each attempt has a start record and a result with the stage, reason, input versions, and Batch job ID. Replays put these keys under `replays/NAME/`. An incomplete start record points to a stopped job. Inspect its Batch status, then its CloudWatch stream in `/coppersushi/forecast-operations/batch`.
3. If the attempt never started, inspect the corresponding `DeLuDailyIssue` or `DeLuMonthlyFit` execution history and the Scheduler group's dead-letter queue. The separate due-time check diagnoses a missing daily receipt by delivery day. A missing monthly pointer requires the correct monthly fit. A gap in prices requires inspecting the receipts or snapshot rows listed by the scientific command.
4. Retry with the original scheduled instant and configuration pin. The first complete month pointer and first issue win conditional writes. A late recovery uses a separate replay namespace. Preserve the failed attempt and the dated evidence.

To trigger the corresponding state machine, supply the planned instant on the day before delivery. The monthly workflow requires tomorrow to be the first of a month.

```sh
parameters=$(jq -nc --arg time "$SCHEDULED_AT" --arg pin "$(cat "$CONFIG_PIN")" '{scheduled_at:$time,config_pin:$pin}')
aws stepfunctions start-execution --state-machine-arn "$WORKFLOW_ARN" \
  --input "$(jq -nc --arg p "$parameters" '{Parameters:$p}')"
```

## Release

Provision [AWS resources](../infra/aws/README.md) with disabled schedules. Build from a committed revision and push the immutable tag to the Terraform ECR repository. Resolve the published digest with `aws ecr describe-images`. Use separate snapshot-only historical pins and archive-backed live pins.

```sh
forecasts/operations/build-image.sh "$REPOSITORY:$REVISION" "$REVISION"
docker push "$REPOSITORY:$REVISION"
pixi run --locked -e runtime python -m forecasts.operations.stage \
  --bucket "$OPERATIONS_BUCKET" --snapshot "$SNAPSHOT" --config "$CONFIG" \
  --image-digest "$DIGEST" --replay november-parity > "$CONFIG_PIN"
pixi run --locked -e runtime python -m forecasts.operations.deploy \
  --state "$forecast_state/terraform.tfstate" --config-pin "$CONFIG_PIN"
```

For a live release, pass `--archive-bucket` and `--publication-time HH:MM` to staging in place of `--replay`. Set the same Berlin time on the Terraform schedules. Bootstrap the active month with its approved training inputs and retain its pointer. Test the reader before enabling the live schedule. Each release needs a complete archive-first fit audit at the rollover cutoff.
