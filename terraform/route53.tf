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
  apprunner_api_dns_count           = local.legacy_enabled && local.custom_domains_enabled && var.api_dns_target == "apprunner" ? 1 : 0
  apigateway_api_dns_count          = local.custom_domains_enabled && var.api_dns_target == "apigateway" ? 1 : 0
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
  count    = local.apprunner_api_dns_count
  provider = aws.dns

  zone_id = var.route53_zone_id
  name    = "api.webbpulse.com"
  type    = "CNAME"
  ttl     = 300
  records = [aws_apprunner_custom_domain_association.api[0].dns_target]
}

resource "aws_route53_record" "api_apigateway" {
  count    = local.apigateway_api_dns_count
  provider = aws.dns

  zone_id = var.route53_zone_id
  name    = "api.webbpulse.com"
  type    = "A"

  alias {
    name                   = aws_apigatewayv2_domain_name.api[0].domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.api[0].domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}

check "api_dns_single_owner" {
  assert {
    condition     = !local.custom_domains_enabled || local.apprunner_api_dns_count + local.apigateway_api_dns_count == 1
    error_message = "api.webbpulse.com must be owned by exactly one backend when custom domains are enabled."
  }
}
