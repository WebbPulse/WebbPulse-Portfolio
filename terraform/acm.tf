# ---------------------------------------------------------------------------
# ACM certificate for CloudFront alternate domain names (www + apex).
# Must live in us-east-1 — CloudFront only accepts us-east-1 certs.
# api.webbpulse.com uses a certificate managed by App Runner (see frontend.tf).
# ---------------------------------------------------------------------------

resource "aws_acm_certificate" "www" {
  provider                  = aws.us_east_1
  domain_name               = "www.webbpulse.com"
  subject_alternative_names = ["webbpulse.com"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "www_cert_validation" {
  provider = aws.dns

  for_each = {
    for dvo in aws_acm_certificate.www.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  zone_id         = var.route53_zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 60
  records         = [each.value.record]
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "www" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.www.arn
  validation_record_fqdns = [for r in aws_route53_record.www_cert_validation : r.fqdn]
}
