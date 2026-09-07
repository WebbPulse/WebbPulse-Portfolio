# ---------------------------------------------------------------------------
# Frontend — private S3 bucket served via CloudFront
#
# The apex and www hostnames both point at this distribution.
# A CloudFront Function 301-redirects the bare apex to www.
# 403/404 from S3 → index.html for client-side React Router.
#
# The frontend calls the API host directly — there is no proxying through
# CloudFront. The one exception is the staging access gate: when it is on,
# /api/* is proxied to the API host with an origin-verify header, /_auth/* goes
# to the gate's login Lambda, and every behavior requires signed cookies. All
# of that is gated on local.staging_gate_enabled (see staging_access_gate.tf).
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
  aliases             = local.custom_domains_enabled ? [local.www_host, local.domain] : []
  price_class         = "PriceClass_100" # US + Europe + Canada — cheapest tier

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # Staging access gate: login Lambda function URL, SigV4-signed through an OAC.
  dynamic "origin" {
    for_each = local.staging_gate_enabled ? ["access-gate-login"] : []
    content {
      domain_name              = module.staging_access_gate[0].login_origin_domain_name
      origin_id                = origin.value
      origin_access_control_id = module.staging_access_gate[0].login_origin_access_control_id

      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
      }
    }
  }

  # Staging access gate: the API host, reached only with the origin-verify header
  # the HTTP API authorizer checks.
  dynamic "origin" {
    for_each = local.staging_gate_enabled ? ["api"] : []
    content {
      domain_name = local.api_host
      origin_id   = origin.value

      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
      }

      custom_header {
        name  = module.staging_access_gate[0].origin_verify_header_name
        value = module.staging_access_gate[0].origin_verify_header_value
      }
    }
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

    # Staging access gate: require the gate's signed cookies on every page.
    trusted_key_groups = local.staging_gate_enabled ? module.staging_access_gate[*].key_group_id : null

    dynamic "function_association" {
      for_each = local.default_viewer_request_function_arns
      content {
        event_type   = "viewer-request"
        function_arn = function_association.value
      }
    }
  }

  # Staging access gate: /_auth/* goes to the login Lambda (hosted UI redirect,
  # code exchange, cookie issue, logout).
  dynamic "ordered_cache_behavior" {
    for_each = local.staging_gate_enabled ? ["access-gate-login"] : []
    content {
      path_pattern             = module.staging_access_gate[0].auth_path_pattern
      target_origin_id         = ordered_cache_behavior.value
      viewer_protocol_policy   = "https-only"
      allowed_methods          = ["GET", "HEAD", "OPTIONS"]
      cached_methods           = ["GET", "HEAD"]
      cache_policy_id          = module.staging_access_gate[0].cache_policy_id_caching_disabled
      origin_request_policy_id = module.staging_access_gate[0].origin_request_policy_id_all_viewer_except_host_header

      function_association {
        event_type   = "viewer-request"
        function_arn = module.staging_access_gate[0].viewer_request_function_arn
      }
    }
  }

  # Staging access gate: /api/* is proxied to the API host behind the signed
  # cookies, so the browser calls the API on the site origin.
  dynamic "ordered_cache_behavior" {
    for_each = local.staging_gate_enabled ? ["api"] : []
    content {
      path_pattern             = module.staging_access_gate[0].api_path_pattern
      target_origin_id         = ordered_cache_behavior.value
      viewer_protocol_policy   = "https-only"
      allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods           = ["GET", "HEAD"]
      cache_policy_id          = module.staging_access_gate[0].cache_policy_id_caching_disabled
      origin_request_policy_id = module.staging_access_gate[0].origin_request_policy_id_all_viewer_except_host_header
      trusted_key_groups       = module.staging_access_gate[*].key_group_id

      function_association {
        event_type   = "viewer-request"
        function_arn = module.staging_access_gate[0].viewer_request_function_arn
      }
    }
  }

  # Staging access gate: the SPA shell must stay reachable without cookies so
  # CloudFront's own custom_error_response fetch (403/404 -> /index.html) still
  # works. The gate function still turns away browsers asking for it directly.
  dynamic "ordered_cache_behavior" {
    for_each = local.staging_gate_enabled ? ["s3-frontend"] : []
    content {
      path_pattern           = "/index.html"
      target_origin_id       = ordered_cache_behavior.value
      viewer_protocol_policy = "redirect-to-https"
      allowed_methods        = ["GET", "HEAD"]
      cached_methods         = ["GET", "HEAD"]
      cache_policy_id        = "658327ea-f89d-4fab-a63d-7e88639e58f6" # AWS managed CachingOptimized
      compress               = true

      function_association {
        event_type   = "viewer-request"
        function_arn = module.staging_access_gate[0].viewer_request_function_arn
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

# Apex to www redirect. The logic lives in cloudfront_functions/app_handler.js.tftpl
# so the staging access gate can run the same appHandler before its own check;
# without the gate this function wraps it directly as the viewer-request handler.
resource "aws_cloudfront_function" "apex_redirect" {
  count = local.custom_domain_count

  name    = "${local.prefix}-apex-redirect"
  runtime = "cloudfront-js-2.0"
  publish = true

  code = join("\n", [
    templatefile("${path.module}/cloudfront_functions/app_handler.js.tftpl", {
      domain   = local.domain
      www_host = local.www_host
    }),
    "async function handler(event) { return appHandler(event); }",
  ])
}
