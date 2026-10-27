variable "custom_domain" {
  type    = string
  default = null
}

provider "aws" {
  alias   = "certificate"
  profile = var.profile
  region  = "us-east-1"
  default_tags { tags = { Project = "coppersushi-lambda-trial" } }
}

resource "aws_acm_certificate" "app" {
  count             = var.custom_domain == null ? 0 : 1
  provider          = aws.certificate
  domain_name       = var.custom_domain
  validation_method = "DNS"
  lifecycle { create_before_destroy = true }
}

# DNS is managed externally. Publish certificate_dns before completing the apply.
resource "aws_acm_certificate_validation" "app" {
  count                   = var.custom_domain == null ? 0 : 1
  provider                = aws.certificate
  certificate_arn         = aws_acm_certificate.app[0].arn
  validation_record_fqdns = [for option in aws_acm_certificate.app[0].domain_validation_options : option.resource_record_name]
}

data "aws_cloudfront_cache_policy" "disabled" { name = "Managed-CachingDisabled" }
data "aws_cloudfront_origin_request_policy" "lambda" { name = "Managed-AllViewerExceptHostHeader" }

resource "aws_cloudfront_distribution" "app" {
  count           = var.custom_domain == null ? 0 : 1
  enabled         = true
  is_ipv6_enabled = true
  aliases         = [var.custom_domain]
  comment         = "Copper Sushi Lambda trial"
  price_class     = "PriceClass_100"

  origin {
    domain_name = trimsuffix(trimprefix(aws_lambda_function_url.app[0].function_url, "https://"), "/")
    origin_id   = "lambda"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      origin_read_timeout    = 60
    }
  }

  default_cache_behavior {
    target_origin_id         = "lambda"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.lambda.id
    compress                 = true
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.app[0].certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

output "certificate_dns" {
  value = var.custom_domain == null ? [] : [for option in aws_acm_certificate.app[0].domain_validation_options : {
    name = option.resource_record_name, type = option.resource_record_type, value = option.resource_record_value
  }]
}
output "hostname_target" { value = try(aws_cloudfront_distribution.app[0].domain_name, null) }
output "custom_url" { value = var.custom_domain == null ? null : "https://${var.custom_domain}" }
