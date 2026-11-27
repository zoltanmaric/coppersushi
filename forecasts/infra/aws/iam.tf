locals {
  ecs_trust = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account }
        ArnLike      = { "aws:SourceArn" = "arn:${local.partition}:ecs:${local.service_arn}:*" }
      }
    }]
  })
  task_read = [
    {
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:GetObjectVersion"]
      Resource = "${aws_s3_bucket.operations.arn}/*"
    },
    {
      # S3 returns 403 for absent keys without bucket listing permission.
      Effect   = "Allow"
      Action   = "s3:ListBucket"
      Resource = aws_s3_bucket.operations.arn
    }
  ]
  task_write_prefixes = {
    worker  = ["metaflow", "fits", "issues", "bundles", "attempts", "replays/*/fits", "replays/*/issues", "replays/*/bundles", "replays/*/attempts"]
    witness = ["metaflow", "receipts", "attempts", "replays/*/receipts", "replays/*/attempts"]
  }
}

resource "aws_iam_role" "worker" {
  name               = "${local.name}-worker"
  assume_role_policy = local.ecs_trust
}

resource "aws_iam_role" "witness" {
  name               = "${local.name}-witness"
  assume_role_policy = local.ecs_trust
}

resource "aws_iam_role_policy" "task" {
  for_each = {
    worker  = aws_iam_role.worker.name
    witness = aws_iam_role.witness.name
  }

  role = each.value
  name = "operations-store"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(local.task_read, [
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:AbortMultipartUpload"]
        Resource = [for prefix in local.task_write_prefixes[each.key] : "${aws_s3_bucket.operations.arn}/${prefix}/*"]
      },
      {
        # An IAM wildcard can span slash-separated path components.
        Effect = "Deny"
        Action = "s3:PutObject"
        Resource = [
          for prefix in(each.key == "worker" ? ["receipts"] : ["fits", "issues", "bundles"]) :
          "${aws_s3_bucket.operations.arn}/replays/*/${prefix}/*"
        ]
      }
    ])
  })
}

resource "aws_iam_role_policy" "archive" {
  role = aws_iam_role.worker.name
  name = "market-archive-read"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectVersion"]
        Resource = "${local.market_arn}/market-data/*"
      },
      {
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = local.market_arn
        Condition = { StringLike = { "s3:prefix" = "market-data/*" } }
      }
    ]
  })
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = local.ecs_trust
}

resource "aws_iam_role_policy" "execution" {
  role = aws_iam_role.execution.name
  name = "image-and-logs"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
        Resource = aws_ecr_repository.forecast.arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["${aws_cloudwatch_log_group.batch.arn}:log-stream:*", "${local.default_logs}:log-stream:*"]
      }
    ]
  })
}

resource "aws_iam_role" "workflows" {
  name = "${local.name}-workflows"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account }
        ArnEquals    = { "aws:SourceArn" = [local.monthly_arn, local.daily_arn] }
      }
    }]
  })
}

resource "aws_iam_role_policy" "workflows" {
  role = aws_iam_role.workflows.name
  name = "batch-workflows"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "batch:SubmitJob"
        Resource = [
          aws_batch_job_queue.forecast.arn,
          "arn:${local.partition}:batch:${local.service_arn}:job-definition/metaflow_*",
          "arn:${local.partition}:batch:${local.service_arn}:job/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = "batch:DescribeJobs"
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "batch:TerminateJob"
        Resource = "arn:${local.partition}:batch:${local.service_arn}:job/*"
      },
      {
        Effect   = "Allow"
        Action   = ["events:PutTargets", "events:PutRule", "events:DescribeRule"]
        Resource = "arn:${local.partition}:events:${local.service_arn}:rule/StepFunctionsGetEventsForBatchJobsRule"
      }
    ]
  })
}
