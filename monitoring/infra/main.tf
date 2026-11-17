terraform {
  required_version = ">= 1.7.0, < 2.0.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "6.70.0" }
  }
}
provider "aws" {
  region = var.region
  default_tags { tags = { Project = "website-monitor" } }
}
variable "region" {
  type    = string
  default = "eu-central-1"
}
variable "image_uri" {
  description = "Immutable ECR digest. Null bootstraps the image repository and notification plumbing."
  type        = string
  default     = null
  validation {
    condition     = var.image_uri == null ? true : can(regex("@sha256:[a-f0-9]{64}$", var.image_uri))
    error_message = "Use an immutable image digest."
  }
}
variable "recipient_email" {
  type      = string
  sensitive = true
  default   = null
}
variable "enabled" {
  description = "Enable schedule and alarm actions only after readiness and SNS confirmation."
  type        = bool
  default     = false
}
variable "interval_minutes" {
  type    = number
  default = 30
  validation {
    condition     = var.interval_minutes >= 5 && var.interval_minutes <= 60 && floor(var.interval_minutes) == var.interval_minutes
    error_message = "Choose a whole number of minutes from 5 through 60."
  }
}
locals {
  name      = "website-monitor"
  namespace = "WebsiteMonitor"
  period    = var.interval_minutes * 60
  checks = {
    blog              = "https://121gigawatts.org/"
    critical-elements = "https://coppersushi.121gigawatts.org/cnec"
    power-flow        = "https://coppersushi.121gigawatts.org/opf-2024"
    ghost-origin      = "https://121gigawatts.org/?uptime=1"
  }
  logs_url = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#logsV2:log-groups/log-group/$252Faws$252Flambda$252F${local.name}"
}
data "aws_caller_identity" "current" {}
resource "aws_ecr_repository" "monitor" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_ecr_repository_policy" "lambda" {
  repository = aws_ecr_repository.monitor.name
  policy = jsonencode({
    Version = "2012-10-17", Statement = [{
      Effect    = "Allow", Principal = { Service = "lambda.amazonaws.com" },
      Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
      Condition = { ArnLike = { "aws:SourceArn" = "arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:${local.name}" } }
    }]
  })
}
resource "aws_ecr_lifecycle_policy" "untagged" {
  repository = aws_ecr_repository.monitor.name
  policy = jsonencode({ rules = [{
    rulePriority = 1, description = "Remove untagged build residue after seven days",
    selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 7 },
    action       = { type = "expire" }
  }] })
}
resource "aws_cloudwatch_log_group" "monitor" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}
resource "aws_iam_role" "monitor" {
  name = local.name
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
}
resource "aws_iam_role_policy" "monitor" {
  role = aws_iam_role.monitor.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.monitor.arn}:*" },
    { Effect = "Allow", Action = "cloudwatch:PutMetricData", Resource = "*", Condition = { StringEquals = { "cloudwatch:namespace" = local.namespace } } }
  ] })
}
resource "aws_lambda_function" "monitor" {
  count                          = var.image_uri == null ? 0 : 1
  function_name                  = local.name
  package_type                   = "Image"
  image_uri                      = var.image_uri
  architectures                  = ["x86_64"]
  role                           = aws_iam_role.monitor.arn
  memory_size                    = 2048
  timeout                        = 240
  reserved_concurrent_executions = 1
  ephemeral_storage { size = 1024 }
  environment { variables = { METRIC_NAMESPACE = local.namespace } }
  depends_on = [aws_iam_role_policy.monitor, aws_ecr_repository_policy.lambda]
  lifecycle {
    precondition {
      condition     = startswith(var.image_uri, "${aws_ecr_repository.monitor.repository_url}@sha256:")
      error_message = "The image must belong to this monitoring repository and region."
    }
  }
}
resource "aws_lambda_function_event_invoke_config" "monitor" {
  count                        = var.image_uri == null ? 0 : 1
  function_name                = aws_lambda_function.monitor[0].function_name
  maximum_event_age_in_seconds = 60
  maximum_retry_attempts       = 0
}
resource "aws_sns_topic" "alerts" { name = "${local.name}-alerts" }
resource "aws_sns_topic_policy" "alerts" {
  arn = aws_sns_topic.alerts.arn
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "cloudwatch.amazonaws.com" },
    Action = "SNS:Publish", Resource = aws_sns_topic.alerts.arn,
    Condition = {
      StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id },
      ArnLike      = { "aws:SourceArn" = "arn:aws:cloudwatch:${var.region}:${data.aws_caller_identity.current.account_id}:alarm:${local.name}-*" }
    }
  }] })
}
resource "aws_sns_topic_subscription" "email" {
  count     = nonsensitive(var.recipient_email == null ? 0 : 1)
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.recipient_email
}
resource "aws_cloudwatch_metric_alarm" "check" {
  for_each            = local.checks
  alarm_name          = "${local.name}-${each.key}"
  alarm_description   = "${each.key == "ghost-origin" ? "Ghost origin path unavailable; cached public pages may still work." : "Public page unavailable."} URL: ${each.value} Logs: ${local.logs_url}"
  namespace           = local.namespace
  metric_name         = "Failed"
  dimensions          = { Check = each.key }
  statistic           = "Maximum"
  period              = local.period
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "ignore"
  actions_enabled     = var.enabled
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}
resource "aws_cloudwatch_metric_alarm" "heartbeat" {
  alarm_name          = "${local.name}-checker"
  alarm_description   = "Checker stopped completing; page health is unknown. Logs: ${local.logs_url}"
  namespace           = local.namespace
  metric_name         = "Completed"
  statistic           = "Sum"
  period              = local.period
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  actions_enabled     = var.enabled
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}
resource "aws_scheduler_schedule_group" "monitor" { name = local.name }
resource "aws_iam_role" "scheduler" {
  name = "${local.name}-scheduler"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole",
    Condition = {
      StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id },
      ArnEquals    = { "aws:SourceArn" = aws_scheduler_schedule_group.monitor.arn }
    }
  }] })
}
resource "aws_iam_role_policy" "scheduler" {
  count = var.image_uri == null ? 0 : 1
  role  = aws_iam_role.scheduler.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "lambda:InvokeFunction", Resource = aws_lambda_function.monitor[0].arn
  }] })
}
resource "aws_scheduler_schedule" "monitor" {
  count               = var.image_uri == null ? 0 : 1
  name                = local.name
  group_name          = aws_scheduler_schedule_group.monitor.name
  schedule_expression = "rate(${var.interval_minutes} minutes)"
  state               = var.enabled ? "ENABLED" : "DISABLED"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_lambda_function.monitor[0].arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ scheduledTime = "<aws.scheduler.scheduled-time>" })
    retry_policy {
      maximum_event_age_in_seconds = 60
      maximum_retry_attempts       = 0
    }
  }
  depends_on = [aws_iam_role_policy.scheduler, aws_lambda_function_event_invoke_config.monitor]
}
resource "terraform_data" "activation" {
  lifecycle {
    precondition {
      condition     = !var.enabled || (var.image_uri != null && var.recipient_email != null)
      error_message = "Activation requires an image digest and a confirmed email recipient."
    }
  }
}
output "repository_url" { value = aws_ecr_repository.monitor.repository_url }
output "function_name" { value = var.image_uri == null ? null : aws_lambda_function.monitor[0].function_name }
output "topic_arn" { value = aws_sns_topic.alerts.arn }
output "logs_url" { value = local.logs_url }
