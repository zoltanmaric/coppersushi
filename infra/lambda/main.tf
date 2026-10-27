terraform {
  required_version = ">= 1.5.0, < 2.0.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "6.70.0" }
  }
}
variable "profile" { type = string }
variable "region" {
  type    = string
  default = "eu-west-1"
}
variable "image_uri" {
  type    = string
  default = null
}
provider "aws" {
  profile = var.profile
  region  = var.region
  default_tags { tags = { Project = "coppersushi-lambda-trial" } }
}
data "aws_caller_identity" "current" {}

resource "aws_ecr_repository" "app" {
  name                 = "coppersushi-lambda-trial"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_ecr_repository_policy" "lambda" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Principal = { Service = "lambda.amazonaws.com" },
    Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
    Condition = { StringLike = { "aws:sourceArn" = "arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:coppersushi-trial" } }
  }] })
}
resource "aws_s3_bucket" "cache" { bucket_prefix = "coppersushi-lambda-cache-" }
resource "aws_s3_bucket_public_access_block" "cache" {
  bucket                  = aws_s3_bucket.cache.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "cache" {
  bucket = aws_s3_bucket.cache.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_policy" "cache" {
  bucket = aws_s3_bucket.cache.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Deny", Principal = "*", Action = "s3:*",
    Resource  = [aws_s3_bucket.cache.arn, "${aws_s3_bucket.cache.arn}/*"],
    Condition = { Bool = { "aws:SecureTransport" = "false" } }
  }] })
}
# Only metadata is managed here. Secret values are set separately, never in state.
resource "aws_secretsmanager_secret" "api" { name_prefix = "coppersushi-lambda-trial-" }
resource "aws_cloudwatch_log_group" "app" {
  name              = "/aws/lambda/coppersushi-trial"
  retention_in_days = 7
}
resource "aws_iam_role" "app" {
  name_prefix = "coppersushi-lambda-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
}
resource "aws_iam_role_policy" "app" {
  role = aws_iam_role.app.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.cache.arn },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${aws_s3_bucket.cache.arn}/cache/v1/*" },
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.api.arn },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.app.arn}:*" }
  ] })
}
resource "aws_lambda_function" "app" {
  count         = var.image_uri == null ? 0 : 1
  function_name = "coppersushi-trial"
  role          = aws_iam_role.app.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = ["x86_64"]
  memory_size   = 2048
  timeout       = 120
  ephemeral_storage { size = 1024 }
  environment {
    variables = {
      ROOT_VIEW                = "embed"
      XDG_CACHE_HOME           = "/tmp/cache"
      HOME                     = "/tmp"
      COPPERSUSHI_CACHE_BUCKET = aws_s3_bucket.cache.id
      COPPERSUSHI_SECRET_ID    = aws_secretsmanager_secret.api.arn
    }
  }
  depends_on = [aws_iam_role_policy.app]
}
resource "aws_lambda_function_url" "app" {
  count              = var.image_uri == null ? 0 : 1
  function_name      = aws_lambda_function.app[0].function_name
  authorization_type = "NONE"
}
resource "aws_lambda_permission" "url" {
  count                  = var.image_uri == null ? 0 : 1
  function_name          = aws_lambda_function.app[0].function_name
  statement_id           = "PublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  principal              = "*"
  function_url_auth_type = "NONE"
}
resource "aws_lambda_permission" "invoke" {
  count                    = var.image_uri == null ? 0 : 1
  function_name            = aws_lambda_function.app[0].function_name
  statement_id             = "OnlyThroughFunctionUrl"
  action                   = "lambda:InvokeFunction"
  principal                = "*"
  invoked_via_function_url = true
}
output "repository_url" { value = aws_ecr_repository.app.repository_url }
output "cache_bucket" { value = aws_s3_bucket.cache.id }
output "secret_arn" { value = aws_secretsmanager_secret.api.arn }
output "trial_url" { value = try(aws_lambda_function_url.app[0].function_url, null) }
