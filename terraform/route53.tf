# Registry DS records without Route53 hosted-zone DNSSEC signing cause
# validating resolvers to SERVFAIL (breaking TXT, e.g. DKIM). Enable signing
# in the zone before associating delegation signers at the registrar.

resource "aws_route53_record" "www" {
  count    = local.custom_domain_count
  provider = aws.dns

  zone_id = var.route53_zone_id
  name    = "www.webbpulse.com"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "apex_a" {
  count    = local.custom_domain_count
  provider = aws.dns

  zone_id = var.route53_zone_id
  name    = "webbpulse.com"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

locals {
  api_dns_apigateway                = var.api_dns_target == "apigateway"
  api_dns_count                     = local.custom_domains_enabled && (local.api_dns_apigateway || local.legacy_enabled) ? 1 : 0
  apprunner_cert_validation_records = local.legacy_enabled && local.custom_domains_enabled ? tolist(aws_apprunner_custom_domain_association.api[0].certificate_validation_records) : []
}

resource "aws_route53_record" "apprunner_cert_validation_0" {
  count    = local.legacy_enabled && local.custom_domains_enabled ? 1 : 0
  provider = aws.dns

  zone_id = var.route53_zone_id
  name    = local.apprunner_cert_validation_records[0].name
  type    = local.apprunner_cert_validation_records[0].type
  ttl     = 300
  records = [local.apprunner_cert_validation_records[0].value]
}

resource "aws_route53_record" "apprunner_cert_validation_1" {
  count    = local.legacy_enabled && local.custom_domains_enabled ? 1 : 0
  provider = aws.dns

  zone_id = var.route53_zone_id
  name    = local.apprunner_cert_validation_records[1].name
  type    = local.apprunner_cert_validation_records[1].type
  ttl     = 300
  records = [local.apprunner_cert_validation_records[1].value]
}

resource "aws_route53_record" "api" {
  count    = local.api_dns_count
  provider = aws.dns

  zone_id = var.route53_zone_id
  name    = "api.webbpulse.com"
  type    = local.api_dns_apigateway ? "A" : "CNAME"
  ttl     = local.api_dns_apigateway ? null : 300
  records = local.api_dns_apigateway ? null : [aws_apprunner_custom_domain_association.api[0].dns_target]

  dynamic "alias" {
    for_each = local.api_dns_apigateway ? [1] : []
    content {
      name                   = aws_apigatewayv2_domain_name.api[0].domain_name_configuration[0].target_domain_name
      zone_id                = aws_apigatewayv2_domain_name.api[0].domain_name_configuration[0].hosted_zone_id
      evaluate_target_health = false
    }
  }
}
