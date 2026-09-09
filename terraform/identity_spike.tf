# ---------------------------------------------------------------------------
# Identity standard, milestone M0. A throwaway spike, not the real thing.
#
# The whole question this file exists to answer: does an API Gateway HTTP API
# JWT authorizer verify an RS256 token signed by a real KMS asymmetric key,
# against a JWKS and an OIDC discovery document served by our own FastAPI
# Lambda? Every later milestone of docs/identity-standard.md assumes yes, and
# that assumption is cheap to test now and expensive to discover is wrong at M9.
#
# Two secondary questions it answers on the way, both recorded in the standard's
# section 10 as things that could not be confirmed by reading:
#
#  1. Whether the authorizer fetches <issuer>/.well-known/openid-configuration
#     and follows the jwks_uri out of it, or goes straight to a JWKS. The AWS
#     documentation says only "the public key that is fetched from the issuer's
#     jwks_uri" and the JWTConfiguration API reference calls `issuer` "The base
#     domain of the identity provider that issues JSON Web Tokens", neither of
#     which resolves the path. Serving both documents at the origin satisfies
#     either behaviour, and the access log tells us afterwards which one was
#     actually fetched.
#  2. Whether moto's kms:Sign is faithful enough to trust in a unit suite. The
#     package suite deliberately does not depend on the answer; this spike is
#     where real KMS settles it.
#
# EVERYTHING HERE IS GATED ON var.identity_spike_enabled, WHICH DEFAULTS TO
# false. Production is unaffected: with the variable unset every resource in
# this file has count 0 and the routes below are absent from the routes map, so
# a production plan is a no-op. Only the staging workspace sets it true, and
# only for as long as the spike is being exercised.
# ---------------------------------------------------------------------------

variable "identity_spike_enabled" {
  description = "Stand up the M0 identity spike: a KMS RSA_2048 signing key, a JWT authorizer on the HTTP API, and one protected route. A throwaway experiment for staging only, defaulting to false so production and any workspace that has not opted in plan a no-op. Turn it off and apply again to remove every resource in identity_spike.tf; the KMS key then enters its waiting period rather than being deleted immediately."
  type        = bool
  default     = false

  validation {
    condition     = !var.identity_spike_enabled || var.environment != "production"
    error_message = "identity_spike_enabled must stay false in production. It is a throwaway spike that exposes a route minting a signed token without authenticating anybody, and the standard's own milestone plan calls it throwaway."
  }
}

locals {
  # The spike needs custom domains, and not merely for tidiness. The authorizer
  # fetches the discovery and JWKS documents over the public internet from the
  # issuer URL, so the issuer has to be a hostname that resolves and serves TLS
  # from outside AWS. With custom domains off, local.api_url is the
  # execute-api endpoint, which would still work, but staging_gate_enabled also
  # sets disable_execute_api_endpoint, so that endpoint is switched off exactly
  # when the gate is on. Requiring custom domains keeps the issuer a single
  # stable value rather than one that changes shape with another flag.
  identity_spike_enabled = var.identity_spike_enabled && local.custom_domains_enabled
  identity_spike_count   = local.identity_spike_enabled ? 1 : 0

  # The issuer, byte for byte. This exact string is three things at once: the
  # `issuer` on the authorizer below, the `iss` claim the application signs, and
  # the `issuer` member of the discovery document. A mismatch between any two of
  # them, a trailing slash being the classic one, presents as every request
  # being denied with nothing in any log to say why, so it is derived once here
  # and read from this local everywhere else rather than written out three
  # times.
  #
  # local.api_url is the custom domain URL when custom domains are on, which the
  # guard above requires, so this is https://api.staging.webbpulse.com with no
  # path and no trailing slash.
  identity_spike_issuer = local.api_url

  # The audience. `aud` on the token has to match one entry in the authorizer's
  # audience list. The standard's section 3.2 uses `<product>-api`; this spike
  # follows the brief's `webbpulse-<env>` so the value is unambiguous while both
  # exist, and M1 settles the convention.
  identity_spike_audience = local.prefix
}

# ---------------------------------------------------------------------------
# The signing key.
#
# RSA_2048 and SIGN_VERIFY, because the HTTP API JWT authorizer's own token
# validation workflow says "Currently, only RSA-based algorithms are supported".
# That single sentence is what rules out the standard's preferred ES256 and
# forces RS256, and it is why this is an RSA key rather than an ECC one.
#
# 2048 rather than 4096: a larger key produces a larger signature and a slower,
# more expensive kms:Sign on the hot path of every login and every refresh, for
# no benefit the authorizer can see. 2048 is what every OIDC provider in wide
# use serves.
#
# Automatic rotation is left off, and that is a decision rather than an
# omission. Section 3.5 of the standard: `kid` is derived from the key material,
# so rotating the material behind a single key id changes what GetPublicKey
# returns while the derived `kid` follows it, and every already-issued token
# then references a `kid` the JWKS no longer serves. Rotation in this design is
# by adding a second key and serving both through an overlap, never by mutating
# one. aws_kms_key defaults enable_key_rotation to false; it is written out
# explicitly so the next reader does not have to know that.
# ---------------------------------------------------------------------------

resource "aws_kms_key" "identity_signing" {
  count = local.identity_spike_count

  description = "Identity standard M0 spike: RSA_2048 signing key for RS256 access tokens verified by the HTTP API JWT authorizer. Throwaway."

  key_usage                = "SIGN_VERIFY"
  customer_master_key_spec = "RSA_2048"
  enable_key_rotation      = false

  # Seven days rather than the 30 day default. This is a throwaway spike key,
  # and 7 is the shortest AWS allows, so tearing the spike down does not leave a
  # month of key charges behind. A real identity signing key would take the
  # default, because dropping a key an old token still references is the one
  # mistake with no recovery.
  deletion_window_in_days = 7

  policy = data.aws_iam_policy_document.identity_signing_key[0].json
}

resource "aws_kms_alias" "identity_signing" {
  count = local.identity_spike_count

  name          = "alias/${local.prefix}-identity-signing"
  target_key_id = aws_kms_key.identity_signing[0].key_id
}

# The key policy. A KMS key policy is not optional the way most resource
# policies are: without a statement granting the account root, IAM policies in
# the account have no effect on the key at all and the key can become
# unmanageable. So the root statement is first, and then the identity function's
# role gets exactly two actions and nothing else.
#
# kms:Sign and kms:GetPublicKey, and no kms:Verify. Verification happens at the
# API Gateway authorizer against the public JWKS, never through KMS, so granting
# Verify would widen the grant for a call nothing makes. kms:DescribeKey is not
# granted either: the application reads the key spec off the GetPublicKey
# response, which already carries it.
data "aws_iam_policy_document" "identity_signing_key" {
  count = local.identity_spike_count

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
    sid    = "AllowTheIdentityFunctionToSign"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [module.lambda_domain["identity"].role_arn]
    }
    actions = [
      "kms:Sign",
      "kms:GetPublicKey",
    ]
    resources = ["*"]
  }
}

# The matching identity-side grant. A KMS key policy allows; an IAM policy on
# the principal is the other half, and both are needed for a cross-service call
# in the same account unless the key policy delegates to IAM, which the root
# statement above does. Attaching it explicitly rather than relying on that
# delegation keeps the function's own policy an honest description of what it
# can reach, which is what a reader of lambda_domains.tf will check first.
resource "aws_iam_role_policy" "identity_spike_signing" {
  count = local.identity_spike_count

  name = "identity-spike-signing"
  role = module.lambda_domain["identity"].role_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SignAccessTokensWithTheIdentityKey"
        Effect = "Allow"
        Action = [
          "kms:Sign",
          "kms:GetPublicKey",
        ]
        Resource = aws_kms_key.identity_signing[0].arn
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# The authorizer.
#
# No identity_sources argument, so it takes the module default of
# `$request.header.Authorization`, which is where a bearer token belongs and
# what every client already sends.
#
# `issuer` and `audience` are the two things the authorizer validates beyond the
# signature, and both are derived from locals above so the application and the
# gateway cannot disagree about either.
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_authorizer" "identity_spike_jwt" {
  count = local.identity_spike_count

  api_id           = module.api.api_id
  name             = "${local.prefix}-identity-spike-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    issuer   = local.identity_spike_issuer
    audience = [local.identity_spike_audience]
  }
}

output "identity_spike_signing_key_id" {
  description = "Key id of the M0 spike's KMS signing key, null when the spike is off. The identity function reads the same value from IDENTITY_SIGNING_KEY_ID."
  value       = one(aws_kms_key.identity_signing[*].key_id)
}

output "identity_spike_issuer" {
  description = "Issuer the M0 spike's authorizer is configured with, null when the spike is off. Must be byte-identical to the iss claim the identity function signs and to the issuer member of its discovery document."
  value       = local.identity_spike_enabled ? local.identity_spike_issuer : null
}

output "identity_spike_audience" {
  description = "Audience the M0 spike's authorizer requires, null when the spike is off."
  value       = local.identity_spike_enabled ? local.identity_spike_audience : null
}
