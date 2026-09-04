# Registry DS records without Route53 hosted-zone DNSSEC signing cause
# validating resolvers to SERVFAIL (breaking TXT, e.g. DKIM). Enable signing
# in the zone before associating delegation signers at the registrar.

resource "aws_route53_zone" "staging" {
  count = var.environment != "production" && local.custom_domains_enabled ? 1 : 0

  name = local.domain
}

resource "aws_route53_record" "staging_delegation" {
  count    = var.environment != "production" && local.custom_domains_enabled ? 1 : 0
  provider = aws.parent_dns

  zone_id = var.route53_zone_id
  name    = local.domain
  type    = "NS"
  ttl     = 300
  records = aws_route53_zone.staging[0].name_servers
}

resource "aws_route53_record" "www" {
  count    = local.custom_domain_count
  provider = aws.dns

  zone_id = local.records_zone_id
  name    = local.www_host
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

  zone_id = local.records_zone_id
  name    = local.domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "api" {
  count    = local.custom_domain_count
  provider = aws.dns

  zone_id = local.records_zone_id
  name    = local.api_host
  type    = "A"

  alias {
    name                   = aws_apigatewayv2_domain_name.api[0].domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.api[0].domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}
