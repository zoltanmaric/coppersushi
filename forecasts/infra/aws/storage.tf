resource "aws_s3_bucket" "operations" {
  bucket_prefix = "coppersushi-forecast-ops-"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "operations" {
  bucket                  = aws_s3_bucket.operations.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "operations" {
  bucket = aws_s3_bucket.operations.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "operations" {
  bucket = aws_s3_bucket.operations.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "operations" {
  bucket = aws_s3_bucket.operations.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "operations" {
  bucket = aws_s3_bucket.operations.id

  rule {
    id     = "AbortIncompleteUploads"
    status = "Enabled"
    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

locals {
  retained_prefixes = ["fits", "issues", "receipts", "bundles", "attempts"]
  retained_objects = flatten([
    for prefix in local.retained_prefixes : [
      "${aws_s3_bucket.operations.arn}/${prefix}/*",
      "${aws_s3_bucket.operations.arn}/replays/*/${prefix}/*"
    ]
  ])
}

resource "aws_s3_bucket_policy" "operations" {
  bucket = aws_s3_bucket.operations.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "RequireTLS"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.operations.arn, "${aws_s3_bucket.operations.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "RequireCreateOnlyWrites"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = local.retained_objects
        Condition = { StringNotEquals = { "s3:if-none-match" = "*" } }
      },
      {
        Sid       = "KeepOperationalEvidence"
        Effect    = "Deny"
        Principal = "*"
        Action    = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
        Resource  = local.retained_objects
      }
    ]
  })
}
