# Registry DS records without Route53 hosted-zone DNSSEC signing cause
# validating resolvers to SERVFAIL (breaking TXT, e.g. DKIM). Enable signing
# in the zone before associating delegation signers at the registrar.

# ---------------------------------------------------------------------------
# www — CloudFront distribution
# ---------------------------------------------------------------------------

resource "aws_route53_record" "www" {
  zone_id = var.route53_zone_id
  name    = "www.webbpulse.com"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

# ---------------------------------------------------------------------------
# api.webbpulse.com — App Runner custom domain
#
# App Runner issues its own TLS cert; these CNAMEs prove domain ownership.
# The second record (api) routes traffic to the App Runner service endpoint.
# ---------------------------------------------------------------------------

locals {
  apprunner_cert_validation_records = tolist(aws_apprunner_custom_domain_association.api.certificate_validation_records)
}

resource "aws_route53_record" "apprunner_cert_validation_0" {
  zone_id = var.route53_zone_id
  name    = local.apprunner_cert_validation_records[0].name
  type    = local.apprunner_cert_validation_records[0].type
  ttl     = 300
  records = [local.apprunner_cert_validation_records[0].value]
}

resource "aws_route53_record" "apprunner_cert_validation_1" {
  zone_id = var.route53_zone_id
  name    = local.apprunner_cert_validation_records[1].name
  type    = local.apprunner_cert_validation_records[1].type
  ttl     = 300
  records = [local.apprunner_cert_validation_records[1].value]
}

resource "aws_route53_record" "api" {
  zone_id = var.route53_zone_id
  name    = "api.webbpulse.com"
  type    = "CNAME"
  ttl     = 300
  records = [aws_apprunner_custom_domain_association.api.dns_target]
}

# ---------------------------------------------------------------------------
# Apex: webbpulse.com → same CloudFront distribution as www
# A CloudFront Function on the distribution redirects to www.webbpulse.com.
# ---------------------------------------------------------------------------
resource "aws_route53_record" "apex_a" {
  zone_id = var.route53_zone_id
  name    = "webbpulse.com"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}
