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
# COUNT RATHER THAN FOR_EACH, AND THIS IS NOT A STYLE CHOICE. Terraform requires
# every for_each key to be known at plan time, and these tokens are chosen by
# SES when the identity is created, so they are unknown on the very apply that
# needs them. `for_each = toset(...tokens)` therefore fails the plan outright
# with "Invalid for_each argument ... depends on resource attributes that cannot
# be determined until apply", which is a plan-time error rather than the kind
# that waits for an apply. count takes its length from a number, and Easy DKIM
# always returns exactly three tokens, so the length is known even though the
# values are not.
#
# The cost of count here is the usual one: the address is an index, so if SES
# ever returned the same three tokens in a different order Terraform would see
# three changed records rather than none. That is a re-write of three CNAMEs to
# the same values, not a loss of verification, and it is the cheaper of the two
# problems. The alternative does not plan at all.
locals {
  # Three, fixed by SES's Easy DKIM rather than by anything here. Written as a
  # length rather than as a literal 3 at the use site so the reason is attached
  # to the number.
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
# DMARC. The identity above is DKIM-verified, which means SES signs every
# message, but a signature nobody is told to check is a signature receivers are
# free to ignore. `_dmarc.<domain>` is that instruction: it tells a receiver
# what to do with mail claiming to be from this domain that fails both DKIM and
# SPF alignment, and it is what turns the DKIM records above into an actual
# anti-spoofing control rather than a deliverability nicety.
#
# WHY THIS IS NOT `p=none`. Production's own `_dmarc.webbpulse.com` is
# `p=none`, which is monitor-only: it asks for reports and tells receivers to
# deliver failing mail anyway. That is the correct first step for a domain that
# has carried real mail for years and whose every legitimate sender is not yet
# known, because a premature `p=reject` there silently drops invoices. Staging
# is the opposite case. It has exactly one sender, SES, created a day ago, and
# it has never carried mail from anything else, so there is no unknown
# legitimate sender for a policy to break. `quarantine` on a domain with one
# known sender costs nothing and makes a spoof land in spam rather than an
# inbox.
#
# STRICT ALIGNMENT, AND THIS IS SAFE ONLY BECAUSE OF WHAT IS ABOVE. `adkim=s`
# requires the DKIM `d=` to equal the From domain exactly rather than merely
# share an organisational domain. SES signs with `d=staging.webbpulse.com`
# (the identity is the full staging domain, not the parent), and
# `local.identity_email_from` is `no-reply@staging.webbpulse.com`, so the two
# match exactly and strict alignment passes. Were the identity ever narrowed to
# the parent domain, or the From moved to a subdomain, this would have to
# relax to `adkim=r` in the same change.
#
# `aspf=s` IS STRICT ON A CHECK THAT ALREADY FAILS, WHICH IS THE POINT. There
# is no custom MAIL FROM here (ses.tf says so above), so SES uses its own
# `amazonses.com` envelope sender. SPF therefore authenticates a domain that is
# not this one and SPF alignment fails no matter what `aspf` says. DMARC passes
# on DKIM alone, which is why this record is useful today, and setting `aspf=s`
# rather than `r` costs nothing now and prevents a lax SPF pass from being
# inherited if a MAIL FROM is ever added without revisiting this.
#
# NO `rua`. Aggregate reports go to a mailbox somebody reads, and the two
# addresses this repository knows are the CloudWatch alarm subscribers in
# monitoring.tf, which are a person's inboxes rather than a report endpoint.
# DMARC aggregate reports are daily XML from every receiver that handles the
# domain's mail, and pointing them at a human's inbox is how a person learns to
# filter DMARC reports to trash. Adding `rua` is worth doing behind a real
# report consumer and is a separate change; the policy below enforces without
# it, because enforcement is what `p=` does and `rua` only observes.
#
# Staging-only, and by construction rather than by a new condition: the whole
# file is gated on local.custom_domain_count, and in production `local.domain`
# is `webbpulse.com`, whose `_dmarc` is the `p=none` record the management
# account owns. This resource reuses the same gate as the DKIM records above,
# so production behaviour is untouched.
resource "aws_route53_record" "ses_dmarc" {
  count    = local.custom_domain_count
  provider = aws.dns

  zone_id = local.records_zone_id
  name    = "_dmarc.${local.domain}"
  type    = "TXT"
  ttl     = 1800
  records = ["v=DMARC1; p=quarantine; adkim=s; aspf=s"]
}

# SPF. SES needs `v=spf1 include:amazonses.com ~all` on whichever domain the
# envelope sender uses, and with no custom MAIL FROM that domain is
# `amazonses.com`, not this one: SES publishes the SPF record for it and the
# check passes against Amazon's own domain. An SPF record on
# `staging.webbpulse.com` would therefore authorise a sender that is never
# used, so it is deliberately absent rather than missing.
#
# This is also why production's apex SPF is `include:_spf.google.com`: that
# zone carries Google Workspace mail, an entirely different sender, and is not
# a template for this one. Adding `include:amazonses.com` here would not make
# SPF align (alignment needs the MAIL FROM domain to match the From domain,
# which is what a custom MAIL FROM is for), and DMARC above passes on DKIM
# alignment alone. The record to add, if SPF alignment is ever wanted, is a
# custom MAIL FROM subdomain with its own MX and TXT, which is the change
# ses.tf's header already scopes out.

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
