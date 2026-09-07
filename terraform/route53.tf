# Registry DS records without Route53 hosted-zone DNSSEC signing cause
# validating resolvers to SERVFAIL (breaking TXT, e.g. DKIM). Enable signing
# in the zone before associating delegation signers at the registrar.

# The staging child zone and its NS delegation in the parent zone. Production
# serves the apex from a zone the management account owns, so the module is a
# no-op there.
module "staging_dns" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/staging-dns"
  version = "~> 1.3"

  providers = {
    aws        = aws
    aws.parent = aws.parent_dns
  }

  enabled        = var.environment != "production" && local.custom_domains_enabled
  zone_name      = local.domain
  parent_zone_id = var.route53_zone_id
}

# The api record stays here rather than inside http-api: production writes it
# cross-account through aws.dns, and a module has one aws provider.
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
    name                   = module.api.custom_domain_target_domain_name
    zone_id                = module.api.custom_domain_hosted_zone_id
    evaluate_target_health = false
  }
}
