locals {
  identity_issuer = "https://${local.api_host}/api/auth"

  identity_audience = "webbpulse-portfolio-${var.environment}-api"

  identity_signing_key_arns = module.identity.signing_key_arns

  identity_registrable_domain = local.domain

  identity_email_from            = local.custom_domains_enabled ? "no-reply@${local.domain}" : ""
  identity_ses_configuration_set = local.custom_domains_enabled ? "${local.prefix}-identity" : ""
}

variable "oauth_google_client_id" {
  description = "Google OAuth client id for identity sign in. Empty turns Google sign in off. Not a secret; it travels in the authorization URL."
  type        = string
  default     = ""
}

variable "oauth_github_client_id" {
  description = "GitHub OAuth client id for identity sign in. Empty turns GitHub sign in off. Not a secret; it travels in the authorization URL."
  type        = string
  default     = ""
}

variable "oauth_google_client_secret" {
  description = "Google OAuth client secret matching oauth_google_client_id, delivered into the webbpulse-<env>/app secret. Set it in the same apply as the client id."
  type        = string
  sensitive   = true
  default     = ""
}

variable "oauth_github_client_secret" {
  description = "GitHub OAuth client secret matching oauth_github_client_id, delivered into the webbpulse-<env>/app secret. Set it in the same apply as the client id."
  type        = string
  sensitive   = true
  default     = ""
}

variable "passkeys_enabled" {
  description = "Whether the passkey routes are declared. Null derives it from the environment: true in staging, false in production."
  type        = bool
  default     = null
  nullable    = true
}

variable "passkeys_passwordless" {
  description = "Whether a passkey is a way in as well as a credential. Null derives it from the environment: true in staging, false in production."
  type        = bool
  default     = null
  nullable    = true
}

locals {
  passkeys_enabled = (
    var.passkeys_enabled != null
    ? var.passkeys_enabled
    : var.environment != "production"
  )

  passkeys_passwordless = (
    var.passkeys_passwordless != null
    ? var.passkeys_passwordless
    : var.environment != "production"
  )
}

variable "identity_rp_name" {
  description = "WebAuthn Relying Party display name shown during a passkey ceremony. A display string only, safe to change at any time."
  type        = string
  default     = "WebbPulse Portfolio"
}

locals {
  identity_oauth_redirect_uris = jsonencode(["${local.identity_issuer}/oauth/callback"])

  identity_webauthn_origins = jsonencode(["https://${local.domain}"])
}

module "identity" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/identity"
  version = "~> 2.8"

  name_prefix        = local.prefix
  issuer             = local.identity_issuer
  audience           = local.identity_audience
  registrable_domain = local.identity_registrable_domain

  identity_role_name = module.lambda_domain["identity"].role_id
  identity_role_arn  = module.lambda_domain["identity"].role_arn

  tags = {
    Component = "identity"
    Milestone = "M1"
  }
  name_tag = true

  point_in_time_recovery = true
  deletion_protection    = var.environment == "production"

  table_policy_actions = local.dynamodb_write_actions

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

    "totp-factors" = {
      attributes = [{ name = "user_id", type = "S" }]
      hash_key   = "user_id"
    }

    "recovery-codes" = {
      attributes = [
        { name = "user_id", type = "S" },
        { name = "code_hash", type = "S" },
      ]
      hash_key  = "user_id"
      range_key = "code_hash"
    }

    passkeys = {
      attributes = [
        { name = "user_id", type = "S" },
        { name = "credential_id", type = "S" },
      ]
      hash_key  = "user_id"
      range_key = "credential_id"
      global_secondary_indexes = [
        {
          name            = "credential_id-index"
          hash_key        = "credential_id"
          projection_type = "ALL"
        },
      ]
    }

    "webauthn-challenges" = {
      attributes    = [{ name = "challenge_id", type = "S" }]
      hash_key      = "challenge_id"
      ttl_attribute = "expires_at"
    }

    "oauth-states" = {
      attributes    = [{ name = "state", type = "S" }]
      hash_key      = "state"
      ttl_attribute = "expires_at"
    }

    "oauth-links" = {
      attributes = [
        { name = "provider_subject", type = "S" },
        { name = "user_id", type = "S" },
      ]
      hash_key = "provider_subject"
      global_secondary_indexes = [
        {
          name            = "user_id-index"
          hash_key        = "user_id"
          projection_type = "ALL"
        },
      ]
    }
  }
}

output "identity_issuer" {
  description = "Identity issuer, byte identical to the iss claim, the discovery document issuer, and the JWT authorizer issuer"
  value       = local.identity_issuer
}

output "identity_audience" {
  description = "The aud claim the identity function stamps on every access token, and the audience the authorizer requires"
  value       = local.identity_audience
}

output "identity_signing_key_arns" {
  description = "Identity signing key ARNs, active signer first. A second entry means a rotation is in progress."
  value       = local.identity_signing_key_arns
}

output "identity_signing_key_alias" {
  description = "Alias of the active identity signing key, pointing at the first entry of identity_signing_key_arns"
  value       = module.identity.signing_key_alias
}

output "identity_table_names" {
  description = "Logical name to physical name for the identity tables the module creates, for reviewing an apply"
  value       = module.identity.table_names
}

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
