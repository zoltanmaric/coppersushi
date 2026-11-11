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
    Condition = { StringLike = { "aws:sourceArn" = "arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:coppersushi-trial*" } }
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
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([{
    Effect    = "Deny", Principal = "*", Action = "s3:*",
    Resource  = [aws_s3_bucket.cache.arn, "${aws_s3_bucket.cache.arn}/*"],
    Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }], var.custom_domain == null ? [] : [{
    Effect    = "Allow", Principal = { Service = "cloudfront.amazonaws.com" }, Action = "s3:GetObject",
    Resource  = ["${aws_s3_bucket.cache.arn}/data/cnec/*", "${aws_s3_bucket.cache.arn}/data/opf/*"],
    Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.app[0].arn } }
  }]) })
}
# Only metadata is managed here. Secret values are set separately, never in state.
resource "aws_secretsmanager_secret" "api" { name_prefix = "coppersushi-lambda-trial-" }
output "repository_url" { value = aws_ecr_repository.app.repository_url }
output "cache_bucket" { value = aws_s3_bucket.cache.id }
output "secret_arn" { value = aws_secretsmanager_secret.api.arn }
