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

  frontend_url = local.custom_domains_enabled ? "https://www.webbpulse.com" : "https://${aws_cloudfront_distribution.frontend.domain_name}"
  api_url      = local.custom_domains_enabled ? "https://api.webbpulse.com" : aws_apigatewayv2_api.backend.api_endpoint
  cors_origins = local.custom_domains_enabled ? "https://www.webbpulse.com,https://webbpulse.com" : local.frontend_url
}
