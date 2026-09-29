locals {
  legacy_hosts = var.environment == "production" && local.custom_domains_enabled ? ["webbpulse.com", "www.webbpulse.com"] : []

  viewer_request_handler_js = templatefile("${path.module}/cloudfront_functions/app_handler.js.tftpl", {
    canonical_host = local.domain
    legacy_hosts   = local.legacy_hosts
  })
}

resource "aws_route53_record" "legacy_host" {
  for_each = toset(local.legacy_hosts)
  provider = aws.dns

  zone_id = local.records_zone_id
  name    = each.value
  type    = "A"

  alias {
    name                   = module.frontend.distribution_domain_name
    zone_id                = module.frontend.distribution_hosted_zone_id
    evaluate_target_health = false
  }
}

moved {
  from = aws_route53_record.apex_a[0]
  to   = aws_route53_record.legacy_host["webbpulse.com"]
}

moved {
  from = aws_route53_record.www[0]
  to   = aws_route53_record.legacy_host["www.webbpulse.com"]
}

resource "aws_cloudfront_function" "legacy_host_redirect" {
  count = local.custom_domain_count

  name    = "${local.prefix}-apex-redirect"
  runtime = "cloudfront-js-2.0"
  publish = true

  code = join("\n", [
    local.viewer_request_handler_js,
    "async function handler(event) { return appHandler(event); }",
  ])
}

moved {
  from = aws_cloudfront_function.apex_redirect
  to   = aws_cloudfront_function.legacy_host_redirect
}
