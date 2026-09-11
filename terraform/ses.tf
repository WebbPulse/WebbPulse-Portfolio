resource "aws_sesv2_email_identity" "primary" {
  count = local.custom_domain_count

  email_identity = local.domain

  dkim_signing_attributes {
    next_signing_key_length = "RSA_2048_BIT"
  }

  configuration_set_name = aws_sesv2_configuration_set.identity[0].configuration_set_name

  tags = {
    Name      = "${local.prefix}-identity"
    Component = "identity"
    Milestone = "M3"
  }
}

locals {
  ses_dkim_token_count = 3
}

resource "aws_route53_record" "ses_dkim" {
  count    = local.custom_domains_enabled ? local.ses_dkim_token_count : 0
  provider = aws.dns

  zone_id = local.records_zone_id
  name    = "${aws_sesv2_email_identity.primary[0].dkim_signing_attributes[0].tokens[count.index]}._domainkey.${local.domain}"
  type    = "CNAME"
  ttl     = 1800
  records = ["${aws_sesv2_email_identity.primary[0].dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}

resource "aws_sesv2_configuration_set" "identity" {
  count = local.custom_domain_count

  configuration_set_name = local.identity_ses_configuration_set

  delivery_options {
    tls_policy = "REQUIRE"
  }

  reputation_options {
    reputation_metrics_enabled = true
  }

  sending_options {
    sending_enabled = true
  }

  tags = {
    Name      = "${local.prefix}-identity"
    Component = "identity"
    Milestone = "M3"
  }
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
          aws_sesv2_email_identity.primary[0].arn,
          aws_sesv2_configuration_set.identity[0].arn,
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
  value       = local.custom_domains_enabled ? aws_sesv2_email_identity.primary[0].dkim_signing_attributes[0].tokens : []
}
