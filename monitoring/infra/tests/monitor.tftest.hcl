mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_resource "aws_ecr_repository" {
    defaults = { repository_url = "123456789012.dkr.ecr.eu-central-1.amazonaws.com/website-monitor", arn = "arn:aws:ecr:eu-central-1:123456789012:repository/website-monitor" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/website-monitor" }
  }
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:eu-central-1:123456789012:website-monitor-alerts" }
  }
  mock_resource "aws_lambda_function" {
    defaults = { arn = "arn:aws:lambda:eu-central-1:123456789012:function:website-monitor" }
  }
}
run "bootstrap_is_inert" {
  command = apply
  assert {
    condition     = length(aws_lambda_function.monitor) == 0 && length(aws_scheduler_schedule.monitor) == 0 && !aws_cloudwatch_metric_alarm.heartbeat.actions_enabled
    error_message = "Bootstrap must not invoke checks or send alarm transitions."
  }
}
run "hourly_alarm_contract" {
  command = apply
  variables {
    image_uri        = "123456789012.dkr.ecr.eu-central-1.amazonaws.com/website-monitor@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    recipient_email  = "monitor@example.com"
    enabled          = true
    interval_minutes = 60
  }
  assert {
    condition = alltrue([for alarm in aws_cloudwatch_metric_alarm.check :
      alarm.period == 3600 && alarm.evaluation_periods == 2 && alarm.datapoints_to_alarm == 2 &&
      alarm.statistic == "Maximum" && alarm.treat_missing_data == "ignore" &&
      length(alarm.alarm_actions) == 1 && length(alarm.ok_actions) == 1
    ]) && aws_cloudwatch_metric_alarm.heartbeat.period == 3600 && aws_cloudwatch_metric_alarm.heartbeat.treat_missing_data == "breaching"
    error_message = "Cadence must propagate to result and missing-checker alarms."
  }
  assert {
    condition     = strcontains(aws_scheduler_schedule.monitor[0].target[0].input, "<aws.scheduler.scheduled-time>")
    error_message = "Scheduler needs literal angle brackets to substitute its context timestamp."
  }
  assert {
    condition     = aws_lambda_function.monitor[0].memory_size == 2048 && aws_lambda_function_event_invoke_config.monitor[0].maximum_retry_attempts == 0 && aws_scheduler_schedule.monitor[0].schedule_expression == "rate(60 minutes)"
    error_message = "Runner must remain bounded and avoid ordinary scheduled overlap."
  }
}
run "reject_invalid_cadence" {
  command = plan
  variables { interval_minutes = 1 }
  expect_failures = [var.interval_minutes]
}
run "reject_activation_without_image" {
  command = plan
  variables { enabled = true }
  expect_failures = [terraform_data.activation]
}
