resource "aws_cloudwatch_log_group" "producer" {
  name              = "/aws/lambda/coppersushi-trial-producer"
  retention_in_days = 7
}
resource "aws_lambda_function" "producer" {
  count                          = var.image_uri == null ? 0 : 1
  function_name                  = "coppersushi-trial-producer"
  role                           = aws_iam_role.app.arn
  package_type                   = "Image"
  image_uri                      = var.image_uri
  architectures                  = ["x86_64"]
  memory_size                    = 2048
  timeout                        = 900
  reserved_concurrent_executions = 1
  ephemeral_storage { size = 1024 }
  environment {
    variables = {
      ROOT_VIEW                   = "full"
      XDG_CACHE_HOME              = "/tmp/cache"
      HOME                        = "/tmp"
      COPPERSUSHI_CACHE_BUCKET    = aws_s3_bucket.cache.id
      COPPERSUSHI_SECRET_ID       = aws_secretsmanager_secret.api.arn
      COPPERSUSHI_BUNDLE_PRODUCER = "true"
      AWS_LWA_PASS_THROUGH_PATH   = "/events"
      AWS_LWA_ERROR_STATUS_CODES  = "500,503"
      GUNICORN_TIMEOUT            = "900"
    }
  }
  depends_on = [aws_iam_role_policy.app]
}
resource "aws_cloudwatch_event_rule" "prepare" {
  name                = "coppersushi-prepare-day-data"
  schedule_expression = "rate(1 hour)"
}
resource "aws_cloudwatch_event_target" "prepare" {
  count = var.image_uri == null ? 0 : 1
  rule  = aws_cloudwatch_event_rule.prepare.name
  arn   = aws_lambda_function.producer[0].arn
  input = "{}"
}
resource "aws_lambda_permission" "prepare" {
  count         = var.image_uri == null ? 0 : 1
  function_name = aws_lambda_function.producer[0].function_name
  statement_id  = "ScheduledPreparation"
  action        = "lambda:InvokeFunction"
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.prepare.arn
}
