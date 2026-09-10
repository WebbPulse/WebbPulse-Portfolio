# ---------------------------------------------------------------------------
# Identity standard, milestone M1. The permanent thing, beside the M0 spike.
#
# M0 (identity_spike.tf) answered one question: does an API Gateway HTTP API JWT
# authorizer verify an RS256 token signed by a real KMS key, against a JWKS and
# a discovery document served by our own Lambda? It does, and that file records
# what it cost to find out. M0 is throwaway and stays gated behind
# var.identity_spike_enabled.
#
# This file is what replaces it. The scope is exactly section 9.1's M1 row and
# no more: a signing key, the grants the identity function needs to use it, and
# the configuration that lets the function serve the two `.well-known` documents
# through webbpulse.identity's own router.
#
# WHAT IS DELIBERATELY NOT HERE.
#
#  - No aws_apigatewayv2_authorizer. Attaching the JWT authorizer to a route is
#    M2 and later, and section 2.5 records why it is not merely the next line of
#    Terraform: an HTTP API route takes one authorizer, the staging access gate
#    already occupies that slot on every route, and which of the three answers
#    in 2.5 to take is question Q3 in section 11, still open. Nothing here
#    forces that decision.
#  - No DynamoDB tables. Section 4.2's nine tables belong to the flows, and the
#    flows are M2 and later. 0.9.0's stores are interfaces with no route calling
#    them, so a table created now would be an empty table with a backup policy.
#  - No symmetric data key. That is TOTP envelope encryption at M4.
#  - No SES wiring. Email is M3.
#
# The one thing M1 does that M0 did not, and the reason this file is not simply
# an edit of that one: the `.well-known` routes stop being conditional. Under
# the spike they exist only when var.identity_spike_enabled is true, which is
# staging only and off by default. Here they are permanent and unconditional in
# both environments, because from M1 on the discovery document and the JWKS are
# what this product publishes about itself rather than an experiment's exhaust.
# Section 3.4 is emphatic that both have to answer anonymously before an
# authorizer can be created at all, so having them already live and already
# outside the gate is precisely what makes M2's first apply an ordinary one.
# ---------------------------------------------------------------------------

locals {
  # The issuer, byte for byte, and the single definition of it.
  #
  # Section 3.4: this exact string is three things at once. It is the `iss`
  # claim the token service signs, the `issuer` member of the discovery
  # document, and, from M2, the `issuer` on the authorizer. A mismatch between
  # any two of them presents as every request being denied with nothing in any
  # log to say why, and a trailing slash is the classic way to produce one. So
  # it is derived once here and read from this local everywhere else.
  #
  # The `/api/auth` path is the standard's own shape (section 6.2:
  # `https://api.carmodpicker.com/api/auth`), and M0 confirmed API Gateway is
  # happy with a path on the issuer: it appends
  # `/.well-known/openid-configuration` to whatever it is given rather than
  # requiring the document at the origin root.
  #
  # Which means the path is not cosmetic. The documents answer under `/api/auth`
  # and not at the origin, because that is where API Gateway looks, and the
  # jwks_uri the discovery document advertises is built from this same string,
  # so it lands under the path too. apigateway.tf's route keys and the router's
  # mount point in app/composition/wiring.py both follow from this local, which
  # is what keeps the three of them from disagreeing.
  #
  # local.api_host rather than local.api_url. api_url is module.api.api_url,
  # which is the custom domain URL only when custom domains are on and the
  # execute-api endpoint otherwise; the issuer has to be a stable public
  # hostname that resolves and serves TLS from outside AWS, because API Gateway
  # fetches it from its own infrastructure. api_host is that hostname directly,
  # `api.webbpulse.com` or `api.staging.webbpulse.com`, and it does not change
  # shape with another flag.
  identity_issuer = "https://${local.api_host}/api/auth"

  # The audience, matched by the authorizer from M2 and carried as `aud` on
  # every token from now.
  #
  # Section 3.2's convention is `<product>-api`. The M0 spike used
  # `webbpulse-<env>` and its own comment says M1 settles the convention, so
  # this settles it on the standard's shape rather than on the spike's. The two
  # are separate values on separate resources and nothing compares them, so
  # both can be live at once while the spike is still switched on.
  #
  # It carries the environment because a staging token must not be accepted by
  # production. The audience is the only claim that distinguishes them once the
  # issuer differs by hostname anyway, and having both differ is cheap.
  identity_audience = "webbpulse-portfolio-${var.environment}-api"

  # The signing key ARNs, as the JSON array IDENTITY_SIGNING_KEY_ARNS expects.
  #
  # A list of one today. The list is the whole of section 3.5's rotation design:
  # the head signs, every element is published in the JWKS, and each step of a
  # rotation is an edit to this list plus a deploy. Writing it as a list now,
  # rather than a scalar that a later change has to widen, is what makes step 2
  # of that procedure a one line change rather than a refactor of this file,
  # the environment variable, and the settings that read it.
  #
  # Sorted through no function: the order is the design. aws_kms_key.identity_signing
  # is the active signer and belongs first.
  identity_signing_key_arns = [aws_kms_key.identity_signing.arn]

  # The cookie and WebAuthn scope: the registrable domain, not the API host.
  #
  # Section 6.1 is explicit that rp_id cannot be changed later, because the RP
  # ID is hashed into every credential by the authenticator and is immutable for
  # that credential's life. Choosing the registrable domain rather than a host
  # is therefore close to irreversible, and it is the right default because it
  # lets `www.` and any future subdomain share credentials.
  #
  # local.domain is already exactly that: `webbpulse.com` in production and
  # `staging.webbpulse.com` in staging. A passkey registered against staging
  # will not work in production, which is correct behaviour rather than a
  # problem, and the standard says so in the same paragraph.
  #
  # Neither value is used by a route in 0.9.0. They are set now because the
  # composition root reads the whole settings object at startup, and a value
  # that only appears at the milestone that first reads it is a value nobody
  # reviews when it is cheap to change.
  identity_registrable_domain = local.domain

  # The two M3 strings: where identity email comes from, and which SES
  # configuration set it is sent through. `terraform/ses.tf` creates both and
  # explains why this repository had no SES before M3.
  #
  # BOTH ARE EMPTY WHEN CUSTOM DOMAINS ARE OFF, AND THAT IS THE SWITCH RATHER
  # THAN AN ACCIDENT. A domain identity is verified by DKIM records, and without
  # a hosted zone there is nowhere to write them, so an SES identity created in
  # that configuration would stay permanently unverified and every send would
  # fail. Empty here means `IDENTITY_EMAIL_FROM` is empty on the function, which
  # means `build_email_sender` returns `None`, which means the package declares
  # none of the four email routes. A deployment that cannot send email serves
  # the M1 documents and the six M2 flows and promises nothing it cannot do.
  #
  # `no-reply@` because nothing reads replies to these two messages. The bodies
  # point a reader at `IDENTITY_SUPPORT_EMAIL` for a reply that a person will
  # see, which is the honest arrangement: a `From` that silently discards mail
  # and a stated address that does not is better than one address that looks
  # monitored and is not.
  identity_email_from            = local.custom_domains_enabled ? "no-reply@${local.domain}" : ""
  identity_ses_configuration_set = local.custom_domains_enabled ? "${local.prefix}-identity" : ""
}

# ---------------------------------------------------------------------------
# The signing key.
#
# RSA_2048 and SIGN_VERIFY. The HTTP API JWT authorizer's token validation
# workflow says "Currently, only RSA-based algorithms are supported", which is
# the single sentence that rules out the standard's preferred ES256 and forces
# RS256. Section 3.1 records the reasoning; M0 confirmed the outcome end to end.
#
# 2048 rather than 4096: a larger key means a larger signature and a slower,
# more expensive kms:Sign on the hot path of every login and every refresh, for
# no benefit any verifier can see. 2048 is what every OIDC provider in wide use
# serves.
#
# ROTATION IS OFF, AND THAT IS A DECISION RATHER THAN AN OMISSION. Section 3.5:
# `kid` is the base64url SHA-256 of the DER SubjectPublicKeyInfo, so it is a
# function of the key material itself. Rotating the material behind a single key
# id changes what GetPublicKey returns and the derived `kid` follows it, and
# every already-issued token then references a `kid` the JWKS no longer serves.
# Rotation in this design is by adding a second key and serving both through an
# overlap, never by mutating one, which is what local.identity_signing_key_arns
# being a list is for. aws_kms_key defaults enable_key_rotation to false; it is
# written out so the next reader does not have to know that.
#
# The deletion window is the 30 day default rather than the spike's 7. This is
# the opposite trade to the spike's: dropping a key that an already-issued token
# still references is the one mistake in this design with no recovery, and the
# waiting period is the last chance to notice. Section 3.5's step 5 says to
# schedule deletion no sooner than 30 days after a key leaves the list anyway.
# ---------------------------------------------------------------------------

resource "aws_kms_key" "identity_signing" {
  description = "RSA_2048 signing key for the Portfolio identity function's RS256 access tokens. The private half never leaves KMS; the public half is published in the JWKS at ${local.identity_issuer}/.well-known/jwks.json via the origin."

  key_usage                = "SIGN_VERIFY"
  customer_master_key_spec = "RSA_2048"
  enable_key_rotation      = false
  deletion_window_in_days  = 30

  policy = data.aws_iam_policy_document.identity_signing_key.json

  tags = {
    Name      = "${local.prefix}-identity-signing"
    Component = "identity"
    Milestone = "M1"
  }
}

# The alias is what the application is given, never the key id or the ARN of the
# key resource, and that avoids a dependency cycle rather than merely being
# tidier. The key policy below names module.lambda_domain["identity"].role_arn
# as a principal, so the key depends on the Lambda module; naming the key from
# inside that module's environment variables would make the module depend on the
# key, and Terraform refuses the graph. The alias name is a pure function of
# local.prefix, so it closes the loop with a string.
#
# KMS accepts an alias anywhere it accepts a key id for Sign and GetPublicKey.
#
# IDENTITY_SIGNING_KEY_ARNS is the exception and deliberately holds the real
# ARN: it is a list rendered as JSON, section 3.5's rotation works by adding a
# second entry, and two aliases would have to be created and swapped in lockstep
# to express the same thing. The ARN is set on the function through a separate
# statement in lambda_domains.tf whose comment explains why that one direction
# does not close a cycle.
resource "aws_kms_alias" "identity_signing" {
  name          = "alias/${local.prefix}-identity-signing"
  target_key_id = aws_kms_key.identity_signing.key_id
}

# The key policy.
#
# A KMS key policy is not optional the way most resource policies are: without a
# statement granting the account root, IAM policies in the account have no
# effect on the key at all and the key can become unmanageable. So the root
# statement is first, and then the identity function's role gets exactly two
# actions on exactly this key and nothing else.
#
# kms:Sign and kms:GetPublicKey, and no kms:Verify. Verification happens at the
# API Gateway authorizer against the public JWKS, and locally against a public
# key, never through KMS, so granting Verify would widen the grant for a call
# nothing makes. kms:DescribeKey is not granted either: the token service reads
# the key spec off the GetPublicKey response, which already carries it.
#
# The principal is the identity function's role and only that role. Section 5.8:
# the signing key is reachable from one function, which is the whole reason
# `identity` is a function of its own rather than a router in a larger one.
data "aws_iam_policy_document" "identity_signing_key" {
  statement {
    sid    = "EnableIAMPoliciesInThisAccount"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
    actions   = ["kms:*"]
    resources = ["*"]
  }

  statement {
    sid    = "AllowTheIdentityFunctionToSignAndPublish"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [module.lambda_domain["identity"].role_arn]
    }
    actions = [
      "kms:Sign",
      "kms:GetPublicKey",
    ]
    # A key policy statement's resource is the key the policy is attached to, so
    # "*" here is that key and not every key in the account. This is the one
    # place in this file where "*" is the correct value; the IAM policy below,
    # which is attached to a principal rather than to a key, names the ARN.
    resources = ["*"]
  }
}

# The matching identity-side grant.
#
# A KMS key policy allows; an IAM policy on the principal is the other half.
# Both are needed for a call in the same account unless the key policy delegates
# to IAM, which the root statement above does. Attaching it explicitly rather
# than relying on that delegation keeps the function's own policy an honest
# description of what it can reach, which is what a reader of lambda_domains.tf
# checks first.
#
# Scoped to this key's ARN. The two actions are the same two the key policy
# grants, so neither half of the pair is wider than the other, and a future key
# added for a rotation has to be added here as well, which is the intended
# friction: a second key is a deliberate step in a written procedure.
resource "aws_iam_role_policy" "identity_signing" {
  name = "identity-signing"
  role = module.lambda_domain["identity"].role_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SignAccessTokensAndPublishTheJwks"
        Effect = "Allow"
        Action = [
          "kms:Sign",
          "kms:GetPublicKey",
        ]
        Resource = [aws_kms_key.identity_signing.arn]
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# Outputs. The three strings a reviewer checks after an apply, and the two that
# M2's authorizer will be configured from.
# ---------------------------------------------------------------------------

output "identity_issuer" {
  description = "The identity issuer. Byte identical to the iss claim, to the issuer member of the discovery document, and from M2 to the JWT authorizer's configured issuer. Verify with: curl https://<api host>/.well-known/openid-configuration"
  value       = local.identity_issuer
}

output "identity_audience" {
  description = "The aud claim the identity function stamps on every access token, and the audience the M2 authorizer will require."
  value       = local.identity_audience
}

output "identity_signing_key_arns" {
  description = "The identity signing keys, active signer first. A single key today; a second entry is a rotation in progress per section 3.5 of the identity standard."
  value       = local.identity_signing_key_arns
}

output "identity_signing_key_alias" {
  description = "Alias of the active identity signing key. Points at the same key as the first entry of identity_signing_key_arns."
  value       = aws_kms_alias.identity_signing.name
}

# The M0 spike declared these three under `count = local.identity_spike_count`
# and M1 made them unconditional. In an environment where the spike was on
# (staging) the key already exists at the indexed address; without these blocks
# Terraform would destroy the signing key and create a new one under the same
# alias. Where the spike was off (production) nothing is at the old address and
# these are no-ops.
moved {
  from = aws_kms_key.identity_signing[0]
  to   = aws_kms_key.identity_signing
}

moved {
  from = aws_kms_alias.identity_signing[0]
  to   = aws_kms_alias.identity_signing
}

moved {
  from = aws_iam_role_policy.identity_spike_signing[0]
  to   = aws_iam_role_policy.identity_signing
}
