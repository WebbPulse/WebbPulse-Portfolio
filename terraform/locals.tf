locals {
  project = "webbpulse"

  prefix = "${local.project}-${var.environment}"

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

  staging_gate_enabled = var.environment == "staging" && var.staging_access_gate && local.custom_domains_enabled
  staging_gate_count   = local.staging_gate_enabled ? 1 : 0

  frontend_api_url = local.api_url

  identity_jwt_gate_enforced   = var.identity_jwt_mode == "gate" && local.staging_gate_enabled
  identity_jwt_native_enforced = var.identity_jwt_mode == "native"
}
