# ---------------------------------------------------------------------------
# SES, for the identity standard's M3: the email verification and password
# reset links the identity function mails.
#
# THIS IS THE FIRST SES IN THIS REPOSITORY. Nothing here sent mail before M3,
# so there is no existing verified identity to reuse and no configuration set
# to borrow. Both are created here, following the same provider split and the
# same DNS conventions acm.tf and route53.tf already use, because a domain
# identity is verified by DNS records in exactly the way a certificate is.
#
# A DOMAIN IDENTITY RATHER THAN AN EMAIL ADDRESS IDENTITY. An email address
# identity is verified by a click in a mailbox, which is a manual step no apply
# can perform and no reviewer can reproduce. A domain identity is verified by
# records Terraform writes into a zone Terraform already manages, so the whole
# thing is in the plan. It also lets the from address change without a second
# verification, which matters because `no-reply@` today is a choice rather than
# a constraint.
#
# WHAT IS DELIBERATELY NOT HERE.
#
#  - No MAIL FROM domain. A custom MAIL FROM aligns SPF, which improves
#    deliverability, and it needs an MX record pointing at an SES endpoint plus
#    its own TXT. It is worth having and it is not what makes M3 work: DKIM
#    alignment alone satisfies DMARC, and the records below establish it. It is
#    a separate change with its own DNS to review.
#  - No bounce or complaint handling. The configuration set below publishes
#    events, and reacting to a bounce is a decision about a product's own user
#    record that belongs behind a hook the package does not yet have. The
#    package's own `email.py` says the same thing.
#  - No production sending quota request. Both accounts start in the SES
#    sandbox, where SES will only deliver to verified addresses. That is a
#    support case rather than Terraform, and it is called out in the PR body
#    rather than silently assumed away.
# ---------------------------------------------------------------------------

# The domain identity. `local.domain`, so `webbpulse.com` in production and
# `staging.webbpulse.com` in staging, which is the same registrable domain the
# frontend serves from and the same one the refresh cookie is scoped to. Mail
# from a domain the recipient already associates with the product is what makes
# the link in it credible.
#
# Gated on local.custom_domains_enabled for the same reason the certificates
# are: without a zone there is nowhere to write the DKIM records, so the
# identity would be created and stay permanently unverified. A staging profile
# without custom domains gets no SES and no email routes, which is correct: the
# package mounts the four routes only when a sender is supplied, and
# lambda_domains.tf supplies the from address only when this exists.
resource "aws_sesv2_email_identity" "primary" {
  count = local.custom_domain_count

  email_identity = local.domain

  dkim_signing_attributes {
    # Easy DKIM at 2048 bits. SES generates and rotates the private half and
    # publishes three CNAMEs; the alternative is bringing our own key, which
    # means a private key in state and a rotation nobody would remember to do.
    # RSA_2048_BIT rather than the 1024 bit default: 1024 bit DKIM keys are
    # what receiving domains are progressively derating, and the cost of the
    # larger key is borne by SES rather than by anything here.
    next_signing_key_length = "RSA_2048_BIT"
  }

  configuration_set_name = aws_sesv2_configuration_set.identity[0].configuration_set_name

  tags = {
    Name      = "${local.prefix}-identity"
    Component = "identity"
    Milestone = "M3"
  }
}

# The three DKIM CNAMEs, written through aws.dns like every other record in
# this configuration, because production's zone lives in the management account
# and is reached by assuming a role. `dkim_signing_attributes.tokens` is a list
# of three, and each becomes `<token>._domainkey.<domain>` pointing at
# `<token>.dkim.amazonses.com`.
#
# for_each over a toset of the tokens rather than count over an index: the
# tokens are opaque strings SES chose, and an index keyed address would move
# every record if SES ever returned them in a different order.
resource "aws_route53_record" "ses_dkim" {
  for_each = local.custom_domains_enabled ? toset(aws_sesv2_email_identity.primary[0].dkim_signing_attributes[0].tokens) : toset([])
  provider = aws.dns

  zone_id = local.records_zone_id
  name    = "${each.value}._domainkey.${local.domain}"
  type    = "CNAME"
  ttl     = 1800
  records = ["${each.value}.dkim.amazonses.com"]
}

# The configuration set. Section 5.8 of docs/identity-standard.md grants the
# identity function `ses:SendEmail` on the identity and the configuration set,
# which means the send names both and both have to exist.
#
# WHY THIS IS NOT OPTIONAL, EVEN THOUGH THE PACKAGE TREATS IT AS OPTIONAL.
# `SesV2EmailSender` omits `ConfigurationSetName` from the call when it is
# unset, and a configuration set that does not exist is a hard failure on every
# send rather than a degraded one. So the choice is between having one and
# passing it, or not having one and not passing it, and there is no third state
# where a name is set and wrong that fails quietly. Having one is worth it: it
# is the only way to know whether these emails are being delivered at all, and
# the reputation metrics are per configuration set rather than per account.
#
# The package tags every message with a `purpose`, which is what makes a bounce
# rate on verification separable from one on reset without a second set.
resource "aws_sesv2_configuration_set" "identity" {
  count = local.custom_domain_count

  # local.identity_ses_configuration_set rather than the literal, so the name on
  # the resource and the name on the function's environment are one string. They
  # have to match exactly: `SendEmail` names the set, and a set that does not
  # exist is a hard failure on every send rather than a degraded one.
  configuration_set_name = local.identity_ses_configuration_set

  delivery_options {
    # Require TLS on the hop to the receiving server rather than falling back to
    # plaintext. These messages carry a link that sets a password, and a link in
    # cleartext on the public internet is a link anybody on the path can use.
    # The cost is that a receiving server with no TLS gets no mail, which for
    # the mailbox providers a portfolio's administrator uses is not a real case.
    tls_policy = "REQUIRE"
  }

  reputation_options {
    # Bounce and complaint rates published to CloudWatch, which is what makes
    # them visible at all. Off by default, and a sending domain whose bounce
    # rate nobody can see is one that gets suspended without warning.
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

# ---------------------------------------------------------------------------
# The grant. Section 5.8: `ses:SendEmail` on the identity and the configuration
# set, and nothing else.
#
# BOTH ARNs ARE REQUIRED, NOT ONE OR THE OTHER. A `SendEmail` that names a
# configuration set is authorised against both resources, so a policy listing
# only the identity ARN denies every send this product makes. That is the
# specific mistake this comment exists to prevent, because the failure is an
# AccessDeniedException naming the configuration set on a policy that plainly
# grants SES.
#
# `ses:SendEmail` only. No `SendRawEmail`, which the v2 API does not use, and no
# `SendBulkEmail`: identity sends one message to one recipient and the package's
# `EmailSender` has exactly one method, so a bulk grant would be an action
# nothing can call.
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Outputs. What a reviewer checks after the apply, and the two strings
# lambda_domains.tf sets on the function.
# ---------------------------------------------------------------------------

output "identity_email_from" {
  description = "The From address the identity function sends verification and reset links from. Empty when custom domains are off, which is also when the four email routes do not mount."
  value       = local.identity_email_from
}

output "identity_ses_configuration_set" {
  description = "The SES configuration set every identity email is sent through. Bounce and complaint metrics are published per configuration set, so this is the name to look for in CloudWatch."
  value       = local.identity_ses_configuration_set
}

output "identity_ses_dkim_tokens" {
  description = "The three Easy DKIM tokens SES issued for the sending domain. Each has a CNAME at <token>._domainkey.<domain> written by this configuration. Verify with: aws sesv2 get-email-identity --email-identity <domain>"
  value       = local.custom_domains_enabled ? aws_sesv2_email_identity.primary[0].dkim_signing_attributes[0].tokens : []
}
