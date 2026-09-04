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

  legacy_enabled         = var.legacy_stack_enabled && var.environment == "production"
  legacy_count           = local.legacy_enabled ? 1 : 0
  custom_domains_enabled = var.staging_profile == "full" && var.route53_zone_id != null
  custom_domain_count    = local.custom_domains_enabled ? 1 : 0

  domain   = var.environment == "production" ? "webbpulse.com" : "staging.webbpulse.com"
  www_host = "www.${local.domain}"
  api_host = "api.${local.domain}"

  workload_dns_role_arn = var.environment == "production" ? var.route53_write_role_arn : ""
  records_zone_id       = var.environment == "production" ? var.route53_zone_id : one(aws_route53_zone.staging[*].zone_id)

  frontend_url = local.custom_domains_enabled ? "https://${local.www_host}" : "https://${aws_cloudfront_distribution.frontend.domain_name}"
  api_url      = local.custom_domains_enabled ? "https://${local.api_host}" : aws_apigatewayv2_api.backend.api_endpoint
  cors_origins = local.custom_domains_enabled ? "https://${local.www_host},https://${local.domain}" : local.frontend_url
}
