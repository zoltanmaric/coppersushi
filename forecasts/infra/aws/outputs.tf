output "operations_bucket" {
  value = aws_s3_bucket.operations.id
}

output "repository_url" {
  value = aws_ecr_repository.forecast.repository_url
}

output "batch_job_queue_arn" {
  value = aws_batch_job_queue.forecast.arn
}

output "batch_task_role_arn" {
  value = aws_iam_role.worker.arn
}

output "batch_execution_role_arn" {
  value = aws_iam_role.execution.arn
}

output "witness_task_role_arn" {
  value = aws_iam_role.witness.arn
}

output "step_functions_role_arn" {
  value = aws_iam_role.workflows.arn
}

output "log_group" {
  value = aws_cloudwatch_log_group.batch.name
}

output "scheduler_dead_letter_queue_url" {
  value = aws_sqs_queue.scheduler.url
}

output "metaflow_environment" {
  value = {
    METAFLOW_DEFAULT_DATASTORE          = "s3"
    METAFLOW_DEFAULT_METADATA           = "local"
    METAFLOW_DATASTORE_SYSROOT_S3       = "s3://${aws_s3_bucket.operations.id}/metaflow"
    METAFLOW_BATCH_JOB_QUEUE            = aws_batch_job_queue.forecast.name
    METAFLOW_ECS_S3_ACCESS_IAM_ROLE     = aws_iam_role.worker.arn
    METAFLOW_ECS_FARGATE_EXECUTION_ROLE = aws_iam_role.execution.arn
    # The Metaflow deployer checks this even when disabling its unused Events rule.
    METAFLOW_EVENTS_SFN_ACCESS_IAM_ROLE = aws_iam_role.scheduler.arn
    METAFLOW_SFN_IAM_ROLE               = aws_iam_role.workflows.arn
  }
}
