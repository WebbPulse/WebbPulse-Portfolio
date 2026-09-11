locals {
  project = "webbpulse"

  # Use as a prefix for all resource names: "${local.prefix}-bucket", etc.
  prefix = "${local.project}-${var.environment}"

  # Applied to every resource via provider default_tags.
  # Add resource-specific tags inline where needed.
  common_tags = {
    Project     = local.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  custom_domains_enabled = var.staging_profile == "full" && var.route53_zone_id != null
  custom_domain_count    = local.custom_domains_enabled ? 1 : 0

  domain   = var.environment == "production" ? "webbpulse.com" : "staging.webbpulse.com"
  www_host = "www.${local.domain}"
  api_host = "api.${local.domain}"

  workload_dns_role_arn = var.environment == "production" ? var.route53_write_role_arn : ""
  records_zone_id       = var.environment == "production" ? var.route53_zone_id : module.staging_dns.zone_id

  frontend_url = module.frontend.frontend_url
  api_url      = module.api.api_url
  cors_origins = local.custom_domains_enabled ? "https://${local.www_host},https://${local.domain}" : local.frontend_url

  # Staging access gate. Only a fully provisioned staging environment with custom domains can be
  # gated: the gate scopes its cookies to the staging apex, which has to cover the API host too.
  staging_gate_enabled = var.environment == "staging" && var.staging_access_gate && local.custom_domains_enabled
  staging_gate_count   = local.staging_gate_enabled ? 1 : 0

  # Base URL the frontend build must call. Always the API host, gate or no gate: behind the gate
  # the browser sends the signed cookies to https://api.staging.webbpulse.com itself, because they
  # are scoped to the staging apex, and the API's own authorizer checks them.
  frontend_api_url = local.api_url

  # Gateway level enforcement of the identity access token, split into the two booleans the two
  # modules actually read. var.identity_jwt_mode is the one place the choice is written; these
  # exist so neither module block has to repeat the string comparison, and so the mode and the
  # environment's actual shape are reconciled in one place rather than two.
  #
  # The gate branch is additionally conditioned on local.staging_gate_enabled. "gate" names a
  # mechanism that only exists when the gate module is instantiated, so a workspace left on "gate"
  # while the gate is off would otherwise index a module with count 0 and fail the plan. Resolving
  # to false instead means an environment without a gate enforces nothing rather than failing,
  # which is the same relationship every other staging_gate_enabled consumer in this configuration
  # has.
  identity_jwt_gate_enforced   = var.identity_jwt_mode == "gate" && local.staging_gate_enabled
  identity_jwt_native_enforced = var.identity_jwt_mode == "native"
}
