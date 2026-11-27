# Forecast operations on AWS

[Forecasts](../../README.md) · [Forecast input storage](../README.md)

Terraform owns the operations bucket, image repository, Batch queue, job roles and Berlin schedules. The separately deployed Metaflow workflows submit Linux x86-64 Fargate jobs. Public subnets route outbound HTTPS, with public IPs assigned to the jobs and no inbound security group rules. Batch scales to zero.

The operations bucket stores versioned workflow artifacts, pinned inputs, fit bundles, issues, first-read receipts and diagnostics. Its policy preserves live and replay fit pointers, issues, receipts, bundles and attempts through conditional creation and delete protection. The worker role can read the `market-data/` prefix of the existing archive. The witness role reads the operations bucket and can publish first-read receipts.

## Deploy for replay

If the market archive bucket is unknown, use the [market archive runbook](../../../coppersushi/infra/lambda/README.md#market-archive-collection) to locate the deployed app state. Supply the current cache bucket as `market_archive_bucket`.

Save forecast operations state, input variables and plans in a dedicated ignored directory. Keep the same state for subsequent changes. Terraform writes account resource identifiers to state and outputs.

```sh
export AWS_PROFILE=YOUR_LOCAL_PROFILE
forecast_state="$PWD/.secrets/forecast-operations"
mkdir -p "$forecast_state"
terraform -chdir=forecasts/infra/aws init
terraform -chdir=forecasts/infra/aws plan \
  -state="$forecast_state/terraform.tfstate" \
  -var="market_archive_bucket=$COPPERSUSHI_CACHE_BUCKET" \
  -out="$forecast_state/replay.tfplan"
terraform -chdir=forecasts/infra/aws show "$forecast_state/replay.tfplan"
terraform -chdir=forecasts/infra/aws apply \
  -state="$forecast_state/terraform.tfstate" "$forecast_state/replay.tfplan"
terraform -chdir=forecasts/infra/aws output -state="$forecast_state/terraform.tfstate" -json
```

Use the outputs for the Metaflow deployment. Provide an immutable image digest from `repository_url`, the `metaflow_environment` variables, the witness role, and the Batch log group. The state machine names are `DeLuMonthlyFit` and `DeLuDailyIssue`. Keep the workflows' own schedule decorators off. Job definitions use `awslogs` with `awslogs-group` set to the `log_group` output and `awslogs-stream-prefix` set to `forecast`.

## Schedule and diagnose

Set `publication_deadline_berlin` to the agreed Berlin wall time before staging all three disabled schedules. The monthly schedule runs on the last calendar day at 11:00, and the daily issue schedule runs at 11:00. Each workflow receives the planned start time. The overdue check starts a separate daily execution in check-only mode at the deadline. That execution checks the expected dated issue even if the daily issue trigger failed. Enable all three with `schedules_enabled=true` after historical verification and agreement on the deadline. Observe an actual scheduled issue and the first delivery of the new month to verify them.

Look up errors by scheduled time in the schedule group's dead-letter queue using `scheduler_dead_letter_queue_url`. For started workflows, open the Step Functions execution history and follow its AWS Batch job IDs to the job status and CloudWatch log stream. The dated `attempts/` records link scientific failures to their inputs and affected quarters. Use a new workflow execution with the original scheduled date and pins for recovery, using a replay prefix for late work.
