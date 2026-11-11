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


resource "aws_cloudfront_cache_policy" "static" {
  count       = var.custom_domain == null ? 0 : 1
  name        = "coppersushi-static-assets"
  min_ttl     = 300
  default_ttl = 300
  max_ttl     = 31536000
  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true
    cookies_config { cookie_behavior = "none" }
    headers_config { header_behavior = "none" }
    query_strings_config { query_string_behavior = "all" }
  }
}

resource "aws_cloudfront_distribution" "app" {
  count           = var.custom_domain == null ? 0 : 1
  enabled         = true
  is_ipv6_enabled = true
  aliases         = [var.custom_domain]
  comment         = "Copper Sushi production hosting"
  price_class     = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.cache.bucket_regional_domain_name
    origin_id                = "prepared-data"
    origin_access_control_id = aws_cloudfront_origin_access_control.prepared[0].id
  }

  dynamic "ordered_cache_behavior" {
    for_each = ["/data/cnec/*", "/data/opf/*"]
    content {
      path_pattern           = ordered_cache_behavior.value
      target_origin_id       = "prepared-data"
      viewer_protocol_policy = "redirect-to-https"
      allowed_methods        = ["GET", "HEAD", "OPTIONS"]
      cached_methods         = ["GET", "HEAD"]
      cache_policy_id        = aws_cloudfront_cache_policy.prepared[0].id
      compress               = true
    }
  }

  ordered_cache_behavior {
    path_pattern           = "/assets/*"
    target_origin_id       = "prepared-data"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = aws_cloudfront_cache_policy.static[0].id
    compress               = true
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.cnec_static[0].arn
    }
  }

  default_cache_behavior {
    target_origin_id       = "prepared-data"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = aws_cloudfront_cache_policy.prepared[0].id
    compress               = true
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.cnec_static[0].arn
    }
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

resource "aws_cloudfront_origin_access_control" "prepared" {
  count                             = var.custom_domain == null ? 0 : 1
  name                              = "coppersushi-prepared-data"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}
resource "aws_cloudfront_cache_policy" "prepared" {
  count       = var.custom_domain == null ? 0 : 1
  name        = "coppersushi-prepared-data"
  min_ttl     = 0
  default_ttl = 60
  max_ttl     = 31536000
  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true
    cookies_config { cookie_behavior = "none" }
    headers_config { header_behavior = "none" }
    query_strings_config { query_string_behavior = "none" }
  }
}

resource "aws_cloudfront_function" "cnec_static" {
  count   = var.custom_domain == null ? 0 : 1
  name    = "coppersushi-cnec-static"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-JS
    function handler(event) {
      var request = event.request;
      var path = request.uri;
      var prefix = '/data/cnec/v1/ui/';
      if (path.indexOf('/assets/') === 0) {
        request.uri = prefix + path.slice(1);
      } else if (/^\/(embed\/)?opf-2024\/?$/.test(path)) {
        request.uri = prefix + (path.indexOf('/embed/') === 0 ? 'opf-embed.html' : 'opf.html');
      } else if (path === '/' || /^\/(embed\/)?cnec(\/\d{4}-\d{2}-\d{2})?\/?$/.test(path)) {
        request.uri = prefix + (path.indexOf('/embed/') === 0 ? 'embed.html' : 'index.html');
      } else {
        return {statusCode: 404, statusDescription: 'Not Found',
          headers: {'content-type': {value: 'text/plain'}}, body: 'Not found'};
      }
      return request;
    }
  JS
}
