module "ses" {
  source  = "terraform.webbpulse.com/WebbPulse/platform-modules/aws//modules/ses-identity"
  version = "~> 2.39"
  count   = local.custom_domain_count

  configuration_set_name  = local.identity_ses_configuration_set
  domain                  = local.domain
  tls_policy              = "REQUIRE"
  set_feedback_attributes = false
  verified_recipients     = try(module.config.values.ses_verified_recipients, [])

  tags = {
    Name      = "${local.prefix}-identity"
    Component = "identity"
    Milestone = "M3"
  }

  recipient_tags = { Name = "${local.prefix}-ses-recipient" }
}

moved {
  from = aws_sesv2_configuration_set.identity[0]
  to   = module.ses[0].aws_sesv2_configuration_set.this
}

moved {
  from = aws_sesv2_email_identity.primary[0]
  to   = module.ses[0].aws_sesv2_email_identity.domain[0]
}

moved {
  from = aws_sesv2_email_identity.recipient
  to   = module.ses[0].aws_sesv2_email_identity.recipient
}

locals {
  ses_dkim_token_count = 3
}

resource "aws_route53_record" "ses_dkim" {
  count    = local.custom_domains_enabled ? local.ses_dkim_token_count : 0
  provider = aws.dns

  zone_id = local.records_zone_id
  name    = "${module.ses[0].dkim_tokens[count.index]}._domainkey.${local.domain}"
  type    = "CNAME"
  ttl     = 1800
  records = ["${module.ses[0].dkim_tokens[count.index]}.dkim.amazonses.com"]
}

resource "aws_iam_role_policy" "identity_ses" {
  count = local.custom_domain_count

  name = "identity-ses"
  role = module.lambda_domain["identity"].role_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SendIdentityEmailThroughTheIdentityConfigurationSet"
        Effect = "Allow"
        Action = ["ses:SendEmail"]
        Resource = [
          module.ses[0].identity_arn,
          module.ses[0].configuration_set_arn,
        ]
      },
    ]
  })
}

resource "aws_route53_record" "ses_dmarc" {
  count    = var.environment == "staging" ? local.custom_domain_count : 0
  provider = aws.dns

  zone_id = local.records_zone_id
  name    = "_dmarc.${local.domain}"
  type    = "TXT"
  ttl     = 1800
  records = ["v=DMARC1; p=quarantine; adkim=s; aspf=s; rua=mailto:tyler@webbpulse.com"]
}

output "identity_email_from" {
  description = "From address the identity function sends verification and reset links from, empty when custom domains are off"
  value       = local.identity_email_from
}

output "identity_ses_configuration_set" {
  description = "SES configuration set every identity email is sent through, and the name bounce and complaint metrics are published under"
  value       = local.identity_ses_configuration_set
}

output "identity_ses_dkim_tokens" {
  description = "Easy DKIM tokens SES issued for the sending domain, each published as a CNAME at <token>._domainkey.<domain>"
  value       = local.custom_domains_enabled ? module.ses[0].dkim_tokens : []
}
