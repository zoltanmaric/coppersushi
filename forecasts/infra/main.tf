terraform {
  required_version = ">= 1.5.0, < 2.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "5.100.0"
    }
  }
}

variable "profile" {
  type        = string
  description = "Authenticated user-local AWS profile; never commit its configuration."
}

variable "region" {
  type    = string
  default = "eu-west-1"
}

variable "bucket_name" {
  type        = string
  default     = null
  description = "Optional existing bucket to import; account-specific values stay outside Git."
}

provider "aws" {
  profile = var.profile
  region  = var.region
}

resource "aws_s3_bucket" "forecast" {
  bucket        = var.bucket_name
  bucket_prefix = var.bucket_name == null ? "coppersushi-forecasts-" : null
  force_destroy = false
  tags          = { Project = "coppersushi-forecasts" }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "forecast" {
  bucket                  = aws_s3_bucket.forecast.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "forecast" {
  bucket = aws_s3_bucket.forecast.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "forecast" {
  bucket = aws_s3_bucket.forecast.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "forecast" {
  bucket = aws_s3_bucket.forecast.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "forecast" {
  bucket = aws_s3_bucket.forecast.id
  rule {
    id     = "AbortIncompleteUploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "require_tls" {
  statement {
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.forecast.arn, "${aws_s3_bucket.forecast.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "require_tls" {
  bucket = aws_s3_bucket.forecast.id
  policy = data.aws_iam_policy_document.require_tls.json
}

output "bucket_name" {
  value = aws_s3_bucket.forecast.id
}
