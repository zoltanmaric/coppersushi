variable "publication_deadline_berlin" {
  type        = string
  default     = null
  description = "Agreed daily publication deadline as HH:MM Berlin time. Creates the overdue check schedule."

  validation {
    condition     = var.publication_deadline_berlin == null || can(regex("^(1[1-9]|2[0-3]):[0-5][0-9]$", var.publication_deadline_berlin))
    error_message = "Use a Berlin time between 11:00 and 23:59."
  }
}

variable "schedules_enabled" {
  type        = bool
  default     = false
  description = "Enable all forecast schedules after the live rollout checks."
}

locals {
  scheduler_parameters = { scheduled_at = "SCHEDULER_SCHEDULED_TIME", scheduled_live = "yes" }
  deadline_hours       = var.publication_deadline_berlin == null ? null : tonumber(split(":", var.publication_deadline_berlin)[0])
  deadline_minutes     = var.publication_deadline_berlin == null ? null : tonumber(split(":", var.publication_deadline_berlin)[1])
  schedules = merge({
    monthly-fit = {
      expression = "cron(0 11 L * ? *)"
      workflow   = local.monthly_arn
      parameters = local.scheduler_parameters
    }
    daily-issue = {
      expression = "cron(0 11 * * ? *)"
      workflow   = local.daily_arn
      parameters = local.scheduler_parameters
    }
    }, var.publication_deadline_berlin == null ? {} : {
    overdue-check = {
      expression = "cron(${local.deadline_minutes} ${local.deadline_hours} * * ? *)"
      workflow   = local.daily_arn
      parameters = merge(local.scheduler_parameters, { check_only = "yes" })
    }
  })
}

resource "aws_scheduler_schedule_group" "forecast" {
  name = local.name
}

resource "aws_sqs_queue" "scheduler" {
  name                      = "${local.name}-schedule-failures"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_iam_role" "scheduler" {
  name = "${local.name}-scheduler"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account }
        ArnEquals    = { "aws:SourceArn" = aws_scheduler_schedule_group.forecast.arn }
      }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  role = aws_iam_role.scheduler.name
  name = "start-forecast-workflows"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "states:StartExecution"
        Resource = [local.monthly_arn, local.daily_arn]
      },
      {
        Effect   = "Allow"
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.scheduler.arn
      }
    ]
  })
}

resource "aws_scheduler_schedule" "forecast" {
  for_each = local.schedules

  name                         = each.key
  group_name                   = aws_scheduler_schedule_group.forecast.name
  schedule_expression          = each.value.expression
  schedule_expression_timezone = "Europe/Berlin"
  state                        = var.schedules_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = each.value.workflow
    role_arn = aws_iam_role.scheduler.arn
    # Insert the token after JSON encoding so Scheduler sees literal angle brackets.
    input = replace(
      jsonencode({ Parameters = jsonencode(each.value.parameters) }),
      "SCHEDULER_SCHEDULED_TIME",
      "<aws.scheduler.scheduled-time>",
    )

    dead_letter_config {
      arn = aws_sqs_queue.scheduler.arn
    }

    retry_policy {
      maximum_event_age_in_seconds = 900
      maximum_retry_attempts       = 3
    }
  }

  lifecycle {
    precondition {
      condition     = !var.schedules_enabled || var.publication_deadline_berlin != null
      error_message = "Set the agreed publication deadline before enabling the forecast schedules."
    }
  }

  depends_on = [aws_iam_role_policy.scheduler]
}
