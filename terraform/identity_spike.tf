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
#
#     ANSWERED, and earlier than expected. API Gateway fetches the discovery
#     document, and it does so at CreateAuthorizer time rather than only at
#     request time: the first apply of this file (run-Yj1PJz22kVW7NM4p) failed
#     with "BadRequestException: Caught exception when connecting to
#     https://api.staging.webbpulse.com/.well-known/openid-configuration for
#     issuer https://api.staging.webbpulse.com ... Issuer must have a valid
#     discovery endpoint ended with '/.well-known/openid-configuration'". So the
#     path is derived from the issuer, the document has to be a real discovery
#     document, and jwks_uri is read out of it in the ordinary OIDC way. The
#     JWKS fetch itself has still not been observed; the access log settles that
#     once a request actually reaches whoami.
#
#     The consequence is the ordering this file is now written around, and the
#     ORDERING note on the authorizer below has it in full: the two `.well-known`
#     routes and the function behind them have to exist and answer before the
#     authorizer can be created, and whoami has to be created after it.
#
#     Nothing about that ordering applies to the mint route. `POST
#     /api/identity/spike/token` names no authorizer of its own, so it is an
#     ordinary entry in apigateway.tf's routes map behind the staging access
#     gate, alongside the two `.well-known` keys. It was missing from that map
#     when the spike first went live, which made the mint endpoint a gateway 404
#     and left no way to obtain a token to point at whoami; the routes-map entry
#     is the fix.
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
  description = "Stand up the M0 identity spike: a KMS RSA_2048 signing key, a JWT authorizer on the HTTP API, one route protected by that authorizer, and three routes in apigateway.tf's routes map (the two anonymous .well-known documents and the gated mint route). A throwaway experiment for staging only, defaulting to false so production and any workspace that has not opted in plan a no-op. Turn it off and apply again to remove every resource in identity_spike.tf; the KMS key then enters its waiting period rather than being deleted immediately."
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
#
# ORDERING. This resource has to be created after the discovery document is
# already being served, and that is not a preference. CreateAuthorizer on an
# HTTP API validates the issuer synchronously: API Gateway fetches
# <issuer>/.well-known/openid-configuration during the create call and rejects
# it with BadRequestException, "Issuer must have a valid discovery endpoint
# ended with '/.well-known/openid-configuration'", when it does not get a
# discovery document back. The AWS documentation does not say so anywhere; the
# first apply of this file (run-Yj1PJz22kVW7NM4p) is where it was learned, and
# the error above is quoted from it.
#
# So two things must already exist when this resource is created:
#
#  1. The identity function carrying IDENTITY_SPIKE_ENABLED, which is what makes
#     it mount webbpulse.identity's router and serve the two documents at all.
#     Without the environment variable the function is up but answers 404.
#  2. The two `.well-known` routes in apigateway.tf, which are what let a
#     request from outside AWS reach that function.
#
# Neither is implied by anything this resource references. It reads
# module.api.api_id, which is the API itself and is created long before the
# routes on it, and it reads nothing at all from module.lambda_domain. So the
# ordering is written out with depends_on, on both whole modules rather than on
# the individual resources inside them: the route the authorizer needs lives in
# a for_each inside module.api whose key exists only when the spike is on, and
# an address that conditional cannot be named in depends_on. Whole-module
# dependencies are coarser than necessary and cost nothing here, since both
# modules are upstream of this file in every other respect already.
#
# depends_on alone is still not quite enough, because it orders Terraform's API
# calls and not their effects. terraform_data.identity_spike_discovery_ready
# below closes that gap by polling the real URL; its own comment has the three
# lags it exists for.
#
# This is also why `GET /api/identity/spike/whoami` is a standalone route below
# rather than an entry in module.api's routes map. An entry there would name
# this authorizer's id, module.api would then depend on this resource, and this
# resource depends on module.api, which is a cycle Terraform refuses. Before the
# depends_on existed the graph had no cycle and no ordering either, and the
# whole route set simply waited on the authorizer that needed two of those
# routes to already answer.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The wait, between the routes and the authorizer.
#
# depends_on above orders the API calls Terraform makes. It does not order the
# world those calls change, and three separate lags sit between "CreateRoute
# returned 201" and "a request from API Gateway's own validator gets a discovery
# document back":
#
#  1. The stage is auto_deploy, so a new route is deployed asynchronously after
#     the route is created. AWS documents the deployment as automatic, not as
#     synchronous, and puts no number on it.
#  2. UpdateFunctionConfiguration, which is what setting IDENTITY_SPIKE_ENABLED
#     is, returns while LastUpdateStatus is still InProgress. Until it reaches
#     Successful an invoke can still reach the old configuration, which is a
#     function that does not serve either document.
#  3. The identity function is a container image under the Lambda Web Adapter,
#     and this is the coldest a cold start gets: the first request after a
#     configuration update pulls a new execution environment, starts Python,
#     imports FastAPI and builds the app before the adapter will answer. Seconds,
#     not milliseconds.
#
# Any one of those makes CreateAuthorizer fetch a 404 or time out, and the
# failure is the same BadRequestException as having no route at all, with
# nothing to say which of the two it was. That ambiguity is the argument for
# this resource: without it a spurious failure and a real misconfiguration are
# indistinguishable, and the recovery for the spurious one is to run the apply
# again and hope.
#
# So this polls the real URL, from outside AWS, until it answers 200, and fails
# the apply if it never does. It is a poll rather than a sleep because a sleep
# long enough to be safe is longer than the wait usually needs to be, and a
# sleep short enough to be quick is not safe. Sixty attempts a second apart is a
# minute of patience, which is far longer than a cold start and still bounded.
#
# curl is on the HCP Terraform worker image. `-fsS` makes a non-2xx an exit
# code, so the 404 case is a failed attempt rather than a successful fetch of an
# error document, and the loop's own message is what gets printed if the minute
# runs out.
#
# The trigger is the issuer, so the poll runs again if the issuer ever changes,
# and is skipped on an apply that changes neither. That is the honest trigger:
# what this resource asserts is that this exact URL answers.
# ---------------------------------------------------------------------------

resource "terraform_data" "identity_spike_discovery_ready" {
  count = local.identity_spike_count

  triggers_replace = {
    issuer = local.identity_spike_issuer
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      url="${local.identity_spike_issuer}/.well-known/openid-configuration"
      for attempt in $(seq 1 60); do
        if curl -fsS --max-time 10 "$url" > /dev/null; then
          echo "discovery document served after $attempt attempt(s): $url"
          exit 0
        fi
        echo "attempt $attempt: no discovery document yet at $url"
        sleep 1
      done
      echo "gave up after 60 attempts: $url never returned 2xx." >&2
      echo "API Gateway CreateAuthorizer fetches this URL and will fail without it." >&2
      exit 1
    EOT
  }

  depends_on = [
    module.api,
    module.lambda_domain,
  ]
}

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

  depends_on = [
    # The two `.well-known` routes, the integration behind them and the stage
    # that serves them. See the ORDERING note above.
    module.api,
    # The identity function with IDENTITY_SPIKE_ENABLED set. Without it the
    # function serves neither document and the create call fails.
    module.lambda_domain,
    # And the proof that both of those have actually taken effect, rather than
    # merely having been created. The two above order the API calls; this one
    # orders the outcome.
    terraform_data.identity_spike_discovery_ready,
  ]
}

# ---------------------------------------------------------------------------
# The protected route, and the actual experiment.
#
# One route, JWT authorization, this API's own authorizer. It returns the claims
# API Gateway put in the request context, so a 200 from it is proof the
# authorizer fetched the JWKS, verified an RS256 signature made by KMS, and
# matched issuer and audience. A 401 with no token is the other half of the
# proof.
#
# It is a standalone resource rather than a routes entry in apigateway.tf for
# the reason the ORDERING note gives: a route that names the authorizer has to
# be created after it, and the only way to express "after" for one route while
# the rest of the route set is created before is for that one route to live
# outside the module. Referencing aws_apigatewayv2_authorizer.identity_spike_jwt
# below is the whole ordering; no depends_on is needed here.
#
# The route key is literal and single-segment, GET, and outside `/api/v1` so a
# throwaway experiment stays out of the published contract in
# backend/tests/fixtures/route_contract.json.
#
# The target is built the same way the module builds its own, from the module's
# integration_ids output, so this route reaches the identity function through
# the one AWS_PROXY integration that already exists rather than through a second
# one pointing at the same function. The invoke permission the module attaches
# to that integration is scoped to `<execution_arn>/*/*`, every stage and every
# route, so this route is covered by it and needs no permission of its own.
#
# There is no authorization_type override to write: JWT is not a module default
# being overridden here, it is stated directly, and there is no gate authorizer
# in the way because this resource does not go through var.authorizer_id.
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_route" "identity_spike_whoami" {
  count = local.identity_spike_count

  api_id    = module.api.api_id
  route_key = "GET /api/identity/spike/whoami"
  target    = "integrations/${module.api.integration_ids["identity"]}"

  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.identity_spike_jwt[0].id
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
