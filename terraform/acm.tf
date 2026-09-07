# ---------------------------------------------------------------------------
# ACM certificates from the shared acm-certificate module. The CloudFront one
# must live in us-east-1, CloudFront accepts no other region; the API Gateway
# one lives in the deployment region.
#
# The module takes two providers: aws decides where the certificate is issued,
# aws.records decides where the DNS validation records are written. Production
# writes those records cross-account through aws.dns, which is why the split
# exists.
# ---------------------------------------------------------------------------

module "www_certificate" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/acm-certificate"
  version = "~> 1.6"

  providers = {
    aws         = aws.us_east_1
    aws.records = aws.dns
  }

  enabled                   = local.custom_domains_enabled
  domain_name               = local.www_host
  subject_alternative_names = [local.domain]
  zone_id                   = local.records_zone_id

  depends_on = [module.staging_dns]
}

module "api_certificate" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/acm-certificate"
  version = "~> 1.6"

  providers = {
    aws         = aws
    aws.records = aws.dns
  }

  enabled     = local.custom_domains_enabled
  domain_name = local.api_host
  zone_id     = local.records_zone_id

  depends_on = [module.staging_dns]
}

moved {
  from = aws_acm_certificate.www[0]
  to   = module.www_certificate.aws_acm_certificate.this[0]
}

moved {
  from = aws_route53_record.www_cert_validation
  to   = module.www_certificate.aws_route53_record.validation
}

moved {
  from = aws_acm_certificate_validation.www[0]
  to   = module.www_certificate.aws_acm_certificate_validation.this[0]
}

moved {
  from = aws_acm_certificate.api[0]
  to   = module.api_certificate.aws_acm_certificate.this[0]
}

moved {
  from = aws_route53_record.api_cert_validation
  to   = module.api_certificate.aws_route53_record.validation
}

moved {
  from = aws_acm_certificate_validation.api[0]
  to   = module.api_certificate.aws_acm_certificate_validation.this[0]
}
