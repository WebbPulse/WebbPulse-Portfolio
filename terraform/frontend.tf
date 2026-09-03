# ---------------------------------------------------------------------------
# Frontend — private S3 bucket served via CloudFront
#
# webbpulse.com and www.webbpulse.com both point at this distribution.
# A CloudFront Function 301-redirects the bare apex to www.
# 403/404 from S3 → index.html for client-side React Router.
#
# The frontend calls the API host directly — there is no proxying through
# CloudFront.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "frontend" {
  bucket = "${local.prefix}-frontend"
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${local.prefix}-frontend"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Allow CloudFront (and only CloudFront) to read from the bucket
resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontServicePrincipal"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
        }
      }
    }]
  })
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  aliases             = local.custom_domains_enabled ? ["www.webbpulse.com", "webbpulse.com"] : []
  price_class         = "PriceClass_100" # US + Europe + Canada — cheapest tier

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 31536000

    dynamic "function_association" {
      for_each = aws_cloudfront_function.apex_redirect
      content {
        event_type   = "viewer-request"
        function_arn = function_association.value.arn
      }
    }
  }

  # Serve index.html for all S3 misses (React Router handles the rest)
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  viewer_certificate {
    cloudfront_default_certificate = local.custom_domains_enabled ? null : true
    acm_certificate_arn            = local.custom_domains_enabled ? aws_acm_certificate_validation.www[0].certificate_arn : null
    ssl_support_method             = local.custom_domains_enabled ? "sni-only" : null
    minimum_protocol_version       = local.custom_domains_enabled ? "TLSv1.2_2021" : null
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
}

resource "aws_cloudfront_function" "apex_redirect" {
  count = local.custom_domain_count

  name    = "${local.prefix}-apex-redirect"
  runtime = "cloudfront-js-2.0"
  publish = true

  code = <<-EOT
    async function handler(event) {
      const host = event.request.headers.host
        ? event.request.headers.host.value
        : "";
      if (host === "webbpulse.com") {
        return {
          statusCode: 301,
          statusDescription: "Moved Permanently",
          headers: {
            location: {
              value: "https://www.webbpulse.com" + event.request.uri,
            },
          },
        };
      }
      return event.request;
    }
  EOT
}
