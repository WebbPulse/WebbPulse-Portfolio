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
  # Read from the module rather than built here. The module owns the keys now,
  # and `signing_key_arns` is ordered by its `active_signing_key` input and
  # never sorted, which is the same contract this local carried: the head signs
  # and every element is published in the JWKS. Section 3.5's rotation is two
  # applies against `signing_key_count` and `active_signing_key` rather than an
  # edit to a list here.
  identity_signing_key_arns = module.identity.signing_key_arns

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
# The identity layer, from the shared platform module.
#
# This replaced three hand-written resources and four table definitions that
# lived in two files. What the module owns now:
#
#  - The RSA_2048 SIGN_VERIFY signing key, its alias, and the key policy that
#    grants the identity Lambda role kms:Sign and kms:GetPublicKey.
#  - The four identity tables, credentials, refresh-tokens, login-attempts and
#    identity-tokens, which moved out of module.dynamodb.
#  - The two IAM role policies, identity-signing and identity-tables, on the
#    identity function's role.
#
# Every one of those is a `moved` block below rather than a create, so adopting
# the module changes no resource in AWS beyond the two metadata differences the
# PR body lists.
#
# The pin is 2.7, which also brings the M4 resources the module added in that
# release: the symmetric TOTP envelope key, its alias, the identity-mfa role
# policy granting kms:GenerateDataKey and kms:Decrypt on it, and the
# IDENTITY_DATA_KEY_ARN environment variable. Those are plain creates. The
# identity Lambda ignores the variable until the backend adopts webbpulse 0.12
# and the M4 routes, which is the next PR.
#
# WHAT IS DELIBERATELY NOT PASSED.
#
# `http_api_id` stays unset, so no aws_apigatewayv2_authorizer is created here.
# The M0 spike in identity_spike.tf still owns the only JWT authorizer on this
# API and its behaviour is untouched by this change. An HTTP API route takes one
# authorizer and in staging the access gate already occupies that slot on every
# route, so which of section 2.5's three answers to take is still open and
# nothing here forces it. Leaving http_api_id null also leaves
# terraform_data.discovery_document_ready uncreated, which is what we want: the
# spike has its own poll and a second one would wait on the same URL twice.
#
# The rotation inputs are left at their defaults, one key at index zero, which
# is exactly the single key state this environment is in. Section 3.5's rotation
# becomes two applies against signing_key_count and active_signing_key rather
# than an edit to a list of ARNs.
#
# ON TAGS, WHICH IS THE ONE PLACE THE MODULE'S SHAPE COSTS SOMETHING.
#
# `tags` and `name_tag` are module wide: they reach the signing key and the four
# tables alike, and there is no per-resource tag input. The hand-written key
# carries Name, Component and Milestone; the four tables carry none, because
# module.dynamodb was called with neither `tags` nor `name_tag`. No setting of
# these two inputs keeps both. Reproducing the key's tags is the option taken,
# because it keeps the key, the one resource whose tags exist today, byte
# identical, and the cost is three tags added to four tables. A tag addition is
# metadata: it is an in-place update, it replaces nothing, and it loses no data.
# The PR body lists all four addresses.
# ---------------------------------------------------------------------------

module "identity" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/identity"
  version = "~> 2.7"

  name_prefix        = local.prefix
  issuer             = local.identity_issuer
  audience           = local.identity_audience
  registrable_domain = local.identity_registrable_domain

  identity_role_name = module.lambda_domain["identity"].role_id
  identity_role_arn  = module.lambda_domain["identity"].role_arn

  # Reproduces the tags the hand-written key carries so the key itself is a pure
  # move. See the tag note above for what this costs the four tables.
  tags = {
    Component = "identity"
    Milestone = "M1"
  }
  name_tag = true

  # The same pair module.dynamodb is called with, so the three tables that had
  # continuous backups keep them and login-attempts, which the module's own
  # default map already sets to false, keeps not having them. identity-tokens
  # overrides it to false below for the reason dynamodb.tf gave: restoring a
  # consumed single-use link to its unconsumed state is the one thing the
  # single-use guarantee exists to prevent.
  point_in_time_recovery = true
  deletion_protection    = var.environment == "production"

  # The actions the identity role gets on the four tables, matched to what
  # aws_iam_role_policy.lambda_domain["identity"] granted them before this
  # change rather than left at the module's shorter default.
  #
  # The module's default drops Scan, DescribeTable and ConditionCheckItem, and
  # dropping a permission is a behaviour change rather than a refactor. This is
  # the one part of the adoption that is not a state move: the grant was one
  # statement inside the `identity-runtime` policy and becomes its own
  # `identity-tables` policy on the same role, so it is an add here and a
  # narrowing of the existing policy there. Matching the action list keeps the
  # role's effective permissions on these four tables identical across that
  # split, which is what makes the split safe to make in one change. Narrowing
  # to the module's default is a separate decision with its own review.
  table_policy_actions = local.dynamodb_write_actions

  # The module's default map already carries the package's key schemas for all
  # four tables, and they are byte identical to what dynamodb.tf declared. Only
  # identity-tokens is restated, and only to turn point in time recovery off:
  # the module's default leaves it null, which takes the module wide `true`
  # above, and the table that exists today has it off.
  tables = {
    credentials = {
      attributes = [
        { name = "user_id", type = "S" },
        { name = "credential_type", type = "S" },
      ]
      hash_key  = "user_id"
      range_key = "credential_type"
    }

    "refresh-tokens" = {
      attributes = [
        { name = "token_hash", type = "S" },
        { name = "family_id", type = "S" },
        { name = "generation", type = "N" },
      ]
      hash_key = "token_hash"
      global_secondary_indexes = [
        {
          name            = "family_id-generation-index"
          hash_key        = "family_id"
          range_key       = "generation"
          projection_type = "ALL"
        },
      ]
      ttl_attribute = "expires_at"
    }

    "login-attempts" = {
      attributes = [
        { name = "identity_key", type = "S" },
        { name = "attempted_at", type = "S" },
      ]
      hash_key               = "identity_key"
      range_key              = "attempted_at"
      ttl_attribute          = "expires_at"
      point_in_time_recovery = false
    }

    "identity-tokens" = {
      attributes             = [{ name = "token_hash", type = "S" }]
      hash_key               = "token_hash"
      ttl_attribute          = "expires_at"
      point_in_time_recovery = false
    }
  }
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
  value       = module.identity.signing_key_alias
}

output "identity_table_names" {
  description = "Logical name to physical name for the four identity tables the module creates. The application derives the same strings from DYNAMODB_TABLE_PREFIX rather than reading this, so it is here for a reviewer checking an apply rather than for a consumer."
  value       = module.identity.table_names
}

# ---------------------------------------------------------------------------
# Adoption of the platform identity module. Every block below is a state move
# and none of them changes a resource in AWS.
#
# THE FIRST THREE ARE CHAINS, and the chaining is the point. The M0 spike
# declared the key, the alias and the signing policy under
# `count = local.identity_spike_count`, M1 made them unconditional, and the
# three `moved` blocks that expressed that are still needed: a workspace that
# has never applied since M1 still has state at the indexed spike address.
# Terraform follows a chain of moves in one plan, so `[0]` to the bare address
# to the module address resolves in a single step, and dropping the first hop
# would destroy the signing key and create a new one under the same alias. That
# is the one mistake in this design with no recovery.
#
# The module's own resources use `count`, so each destination carries `[0]`.
# ---------------------------------------------------------------------------

moved {
  from = aws_kms_key.identity_signing[0]
  to   = aws_kms_key.identity_signing
}

moved {
  from = aws_kms_key.identity_signing
  to   = module.identity.aws_kms_key.identity_signing[0]
}

moved {
  from = aws_kms_alias.identity_signing[0]
  to   = aws_kms_alias.identity_signing
}

moved {
  from = aws_kms_alias.identity_signing
  to   = module.identity.aws_kms_alias.identity_signing[0]
}

moved {
  from = aws_iam_role_policy.identity_spike_signing[0]
  to   = aws_iam_role_policy.identity_signing
}

moved {
  from = aws_iam_role_policy.identity_signing
  to   = module.identity.aws_iam_role_policy.identity_signing[0]
}

# The four tables, out of module.dynamodb and into module.identity. Both calls
# build the physical name as "<name_prefix>-<key>" from the same local.prefix
# and both key their resource on the same logical name, so the name does not
# change and neither does anything DynamoDB stores.
#
# The two modules' table resources take the same arguments in the same shape,
# which is what makes this a move rather than a replace: `aws_dynamodb_table`
# forces a new resource only on `name`, `hash_key`, `range_key` and the
# attribute set, and all four are identical on both sides. The dynamodb-tables
# module also renders `stream_enabled`, `read_capacity` and `write_capacity`
# where the identity module does not, and every one of those is false or null on
# these four tables today, so none of them appears in the diff.

moved {
  from = module.dynamodb.aws_dynamodb_table.this["credentials"]
  to   = module.identity.aws_dynamodb_table.this["credentials"]
}

moved {
  from = module.dynamodb.aws_dynamodb_table.this["refresh-tokens"]
  to   = module.identity.aws_dynamodb_table.this["refresh-tokens"]
}

moved {
  from = module.dynamodb.aws_dynamodb_table.this["login-attempts"]
  to   = module.identity.aws_dynamodb_table.this["login-attempts"]
}

moved {
  from = module.dynamodb.aws_dynamodb_table.this["identity-tokens"]
  to   = module.identity.aws_dynamodb_table.this["identity-tokens"]
}
