# Publication waits belong to Step Functions, never to a sleeping Lambda.
resource "aws_cloudwatch_log_group" "producer" {
  name              = "/aws/lambda/coppersushi-trial-producer"
  retention_in_days = 7
}
resource "aws_iam_role" "producer" {
  name_prefix = "coppersushi-publisher-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
}
resource "aws_iam_role_policy" "producer" {
  role = aws_iam_role.producer.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.cache.arn },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = ["${aws_s3_bucket.cache.arn}/cache/v1/*", "${aws_s3_bucket.cache.arn}/data/cnec/*"] },
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.api.arn },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.producer.arn}:*" }
  ] })
}
resource "aws_lambda_function" "producer" {
  count         = var.image_uri == null ? 0 : 1
  function_name = "coppersushi-trial-producer"
  role          = aws_iam_role.producer.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  image_config { command = ["bash", "infra/lambda/producer-start.sh"] }
  architectures = ["x86_64"]
  memory_size   = 2048
  timeout       = 900
  ephemeral_storage { size = 1024 }
  environment {
    variables = {
      XDG_CACHE_HOME             = "/tmp/cache"
      HOME                       = "/tmp"
      COPPERSUSHI_CACHE_BUCKET   = aws_s3_bucket.cache.id
      COPPERSUSHI_SECRET_ID      = aws_secretsmanager_secret.api.arn
      AWS_LWA_PASS_THROUGH_PATH  = "/events"
      AWS_LWA_ERROR_STATUS_CODES = "500-599"
      AWS_LWA_ENABLE_COMPRESSION = "false"
    }
  }
  depends_on = [aws_iam_role_policy.producer]
}
resource "aws_iam_role" "publication_workflow" {
  name_prefix = "coppersushi-publication-workflow-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "states.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
}
resource "aws_iam_role_policy" "publication_workflow" {
  count = var.image_uri == null ? 0 : 1
  role  = aws_iam_role.publication_workflow.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "lambda:InvokeFunction", Resource = aws_lambda_function.producer[0].arn
  }] })
}
resource "aws_sfn_state_machine" "publication" {
  count    = var.image_uri == null ? 0 : 1
  name     = "coppersushi-publish-day"
  role_arn = aws_iam_role.publication_workflow.arn
  type     = "STANDARD"
  definition = jsonencode({
    StartAt = "Prepare", TimeoutSeconds = 18000,
    States = {
      Prepare = {
        Type       = "Task", Resource = "arn:aws:states:::lambda:invoke",
        Parameters = { FunctionName = aws_lambda_function.producer[0].arn, Payload = { "started_at.$" = "$.started_at" } },
        ResultPath = "$.result", Next = "Published",
        Retry      = [{ ErrorEquals = ["States.TaskFailed"], IntervalSeconds = 10, BackoffRate = 2, MaxAttempts = 3 }]
      },
      Published          = { Type = "Choice", Choices = [{ Variable = "$.result.Payload.ready", BooleanEquals = true, Next = "Done" }], Default = "WaitForPublication" },
      WaitForPublication = { Type = "Wait", Seconds = 120, Next = "Prepare" },
      Done               = { Type = "Succeed" }
    }
  })
  depends_on = [aws_iam_role_policy.publication_workflow]
}
resource "aws_iam_role" "publication_schedule" {
  name_prefix = "coppersushi-publication-schedule-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
}
resource "aws_iam_role_policy" "publication_schedule" {
  count = var.image_uri == null ? 0 : 1
  role  = aws_iam_role.publication_schedule.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "states:StartExecution", Resource = aws_sfn_state_machine.publication[0].arn
  }] })
}
resource "aws_scheduler_schedule" "publication" {
  count                        = var.image_uri == null ? 0 : 1
  name                         = "coppersushi-publish-day"
  schedule_expression          = "cron(50 15 * * ? *)"
  schedule_expression_timezone = "Europe/Brussels"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_sfn_state_machine.publication[0].arn
    role_arn = aws_iam_role.publication_schedule.arn
    input    = jsonencode({ started_at = "<aws.scheduler.scheduled-time>" })
    retry_policy {
      maximum_event_age_in_seconds = 300
      maximum_retry_attempts       = 2
    }
  }
  depends_on = [aws_iam_role_policy.publication_schedule]
}
