# ---------------------------------------------------------------------------
# ACM certificate for CloudFront alternate domain names (www + apex).
# Must live in us-east-1 — CloudFront only accepts us-east-1 certs.
# ---------------------------------------------------------------------------

resource "aws_acm_certificate" "www" {
  count = local.custom_domain_count

  provider                  = aws.us_east_1
  domain_name               = local.www_host
  subject_alternative_names = [local.domain]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "www_cert_validation" {
  provider = aws.dns

  for_each = {
    for dvo in(local.custom_domains_enabled ? aws_acm_certificate.www[0].domain_validation_options : []) : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  zone_id         = local.records_zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 60
  records         = [each.value.record]
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "www" {
  count = local.custom_domain_count

  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.www[0].arn
  validation_record_fqdns = [for r in aws_route53_record.www_cert_validation : r.fqdn]

  depends_on = [aws_route53_record.staging_delegation]
}
