variable "static_assets_enabled" {
  type        = bool
  default     = false
  description = "Route static requests to S3 after publishing the image's assets."
}

resource "aws_s3_bucket" "static" {
  count         = var.custom_domain == null ? 0 : 1
  bucket_prefix = "coppersushi-static-"
}
resource "aws_s3_bucket_public_access_block" "static" {
  count                   = var.custom_domain == null ? 0 : 1
  bucket                  = aws_s3_bucket.static[0].id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "static" {
  count  = var.custom_domain == null ? 0 : 1
  bucket = aws_s3_bucket.static[0].id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_cloudfront_origin_access_control" "static" {
  count                             = var.custom_domain == null ? 0 : 1
  name                              = "coppersushi-static"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}
resource "aws_s3_bucket_policy" "static" {
  count  = var.custom_domain == null ? 0 : 1
  bucket = aws_s3_bucket.static[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    {
      Effect    = "Allow", Principal = { Service = "cloudfront.amazonaws.com" },
      Action    = "s3:GetObject", Resource = "${aws_s3_bucket.static[0].arn}/*",
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.app[0].arn } }
    },
    {
      Effect    = "Deny", Principal = "*", Action = "s3:*",
      Resource  = [aws_s3_bucket.static[0].arn, "${aws_s3_bucket.static[0].arn}/*"],
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }
  ] })
}
output "static_bucket" { value = try(aws_s3_bucket.static[0].id, null) }
