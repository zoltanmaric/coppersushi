variable "market_collector_image_uri" {
  description = "Digest URI of the market-collector image. Set separately from the CNEC consumer."
  type        = string
  default     = null
}

variable "market_collector_alert_topic_arn" {
  description = "Same-region SNS topic with a confirmed operator subscription for exhausted collector invocations."
  type        = string
  default     = null
}

locals {
  market_publishers = var.market_collector_image_uri == null ? toset([]) : toset(["entsoe", "electricity_maps", "smard", "jao"])
  market_windows = {
    morning   = { cron = "cron(0,15,30,45 9-10 * * ? *)", offset = 0 }
    afternoon = { cron = "cron(0,30 13-18 * * ? *)", offset = 1 }
  }
  market_schedules = { for pair in setproduct(local.market_publishers, keys(local.market_windows)) :
    "${pair[0]}-${pair[1]}" => { publisher = pair[0], window = local.market_windows[pair[1]] }
  }
}

resource "aws_cloudwatch_log_group" "market_archive" {
  for_each          = local.market_publishers
  name              = "/aws/lambda/coppersushi-trial-market-${each.key}"
  retention_in_days = 7
}

resource "aws_iam_role" "market_archive" {
  count       = var.market_collector_image_uri == null ? 0 : 1
  name_prefix = "coppersushi-market-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
}

resource "aws_iam_role_policy" "market_archive" {
  count = var.market_collector_image_uri == null ? 0 : 1
  role  = aws_iam_role.market_archive[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["sns:Publish"], Resource = var.market_collector_alert_topic_arn },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${aws_s3_bucket.cache.arn}/market-data/*" },
    { Effect = "Allow", Action = "s3:ListBucket", Resource = aws_s3_bucket.cache.arn, Condition = { StringLike = { "s3:prefix" = "market-data/*" } } },
    { Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = aws_secretsmanager_secret.api.arn },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = [for group in aws_cloudwatch_log_group.market_archive : "${group.arn}:*"] }
  ] })
  lifecycle {
    precondition {
      condition     = var.market_collector_alert_topic_arn != null
      error_message = "Set market_collector_alert_topic_arn when enabling market collection."
    }
  }
}

resource "aws_lambda_function" "market_archive" {
  for_each      = local.market_publishers
  function_name = "coppersushi-trial-market-${each.key}"
  role          = aws_iam_role.market_archive[0].arn
  package_type  = "Image"
  image_uri     = var.market_collector_image_uri
  architectures = ["x86_64"]
  memory_size   = 2048
  timeout       = 900
  image_config { command = ["coppersushi.pipelines.market_data.data_sources.market_collection_handler.handler"] }
  environment {
    variables = {
      COPPERSUSHI_CACHE_BUCKET = aws_s3_bucket.cache.id
      COPPERSUSHI_SECRET_ID    = aws_secretsmanager_secret.api.arn
      XDG_CACHE_HOME           = "/tmp/cache"
      HOME                     = "/tmp"
    }
  }
  depends_on = [aws_iam_role_policy.market_archive]
}

resource "aws_lambda_function_event_invoke_config" "market_archive" {
  for_each               = aws_lambda_function.market_archive
  function_name          = each.value.function_name
  maximum_retry_attempts = 2
  destination_config {
    on_failure {
      destination = var.market_collector_alert_topic_arn
    }
  }
}

resource "aws_iam_role_policy" "market_schedule" {
  count = var.market_collector_image_uri == null ? 0 : 1
  role  = aws_iam_role.publication_schedule.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "lambda:InvokeFunction", Resource = [for fn in aws_lambda_function.market_archive : fn.arn]
  }] })
}

resource "aws_scheduler_schedule" "market_archive" {
  for_each                     = local.market_schedules
  name                         = "coppersushi-market-${each.key}"
  schedule_expression          = each.value.window.cron
  schedule_expression_timezone = "Europe/Berlin"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_lambda_function.market_archive[each.value.publisher].arn
    role_arn = aws_iam_role.publication_schedule.arn
    input    = "{\"publisher\":\"${each.value.publisher}\",\"scheduled_at\":\"<aws.scheduler.scheduled-time>\",\"day_offset\":${each.value.window.offset}}"
    retry_policy {
      maximum_event_age_in_seconds = 300
      maximum_retry_attempts       = 2
    }
  }
  depends_on = [aws_iam_role_policy.market_schedule, aws_lambda_function_event_invoke_config.market_archive]
}
