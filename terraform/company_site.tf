locals {
  company_site_domains_enabled = var.staging_profile == "full" && var.route53_zone_id != null
  company_site_count           = local.company_site_domains_enabled ? 1 : 0

  company_site_domain    = var.environment == "production" ? "webbpulse.com" : "staging.webbpulse.com"
  company_site_www_host  = "www.${local.company_site_domain}"
  company_site_hosts     = local.company_site_domains_enabled ? [local.company_site_domain, local.company_site_www_host] : []
  company_site_zone_id   = var.environment == "production" ? var.route53_zone_id : module.company_site_dns.zone_id
  company_site_portfolio = var.environment == "production" ? "portfolio.webbpulse.com" : "staging.portfolio.webbpulse.com"

  company_site_gate_enabled = var.environment == "staging" && var.staging_access_gate && local.company_site_domains_enabled
  company_site_gate_count   = local.company_site_gate_enabled ? 1 : 0

  company_site_handler_js = templatefile("${path.module}/company_site_functions/app_handler.js.tftpl", {
    canonical_host  = local.company_site_domain
    www_host        = local.company_site_www_host
    portfolio_host  = local.company_site_portfolio
    portfolio_paths = ["/blog", "/privacy", "/admin", "/verify-email", "/reset-password"]
  })
}

module "company_site_dns" {
  source  = "terraform.webbpulse.com/WebbPulse/platform-modules/aws//modules/staging-dns"
  version = "~> 2.34"

  providers = {
    aws        = aws
    aws.parent = aws.parent_dns
  }

  enabled        = var.environment != "production" && local.company_site_domains_enabled
  zone_name      = local.company_site_domain
  parent_zone_id = var.route53_zone_id
}

module "company_site_certificate" {
  source  = "terraform.webbpulse.com/WebbPulse/platform-modules/aws//modules/acm-certificate"
  version = "~> 2.34"

  providers = {
    aws         = aws.us_east_1
    aws.records = aws.dns
  }

  enabled                   = local.company_site_domains_enabled
  domain_name               = local.company_site_domain
  subject_alternative_names = [local.company_site_www_host]
  zone_id                   = local.company_site_zone_id

  depends_on = [module.company_site_dns]
}

module "company_site_gate" {
  count = local.company_site_gate_count

  source  = "terraform.webbpulse.com/WebbPulse/platform-modules/aws//modules/staging-access-gate"
  version = "~> 2.34"

  name             = "${local.prefix}-site"
  cookie_domain    = local.company_site_domain
  site_host        = local.company_site_domain
  additional_hosts = [local.company_site_www_host]
  allowed_emails   = var.staging_access_users

  invite_login_url = "https://${local.company_site_domain}/"

  viewer_request_handler_js = local.company_site_handler_js
}

resource "aws_cloudfront_function" "company_site" {
  count = local.company_site_gate_enabled ? 0 : 1

  name    = "${local.prefix}-site-viewer-request"
  runtime = "cloudfront-js-2.0"
  comment = "Redirects www and old portfolio paths, returns 404 for unknown pages."
  publish = true

  code = join("\n", [
    local.company_site_handler_js,
    "function handler(event) { return appHandler(event); }",
  ])
}

module "company_site" {
  source  = "terraform.webbpulse.com/WebbPulse/platform-modules/aws//modules/spa-frontend"
  version = "~> 2.34"

  name    = "${local.prefix}-site"
  comment = "WebbPulse company site"

  aliases             = local.company_site_hosts
  acm_certificate_arn = module.company_site_certificate.certificate_arn

  viewer_request_function_arn = one(aws_cloudfront_function.company_site[*].arn)

  access_gate = local.company_site_gate_enabled ? {
    key_group_id                                           = module.company_site_gate[0].key_group_id
    viewer_request_function_arn                            = module.company_site_gate[0].viewer_request_function_arn
    login_origin_domain_name                               = module.company_site_gate[0].login_origin_domain_name
    login_origin_access_control_id                         = module.company_site_gate[0].login_origin_access_control_id
    auth_path_pattern                                      = module.company_site_gate[0].auth_path_pattern
    cache_policy_id_caching_disabled                       = module.company_site_gate[0].cache_policy_id_caching_disabled
    origin_request_policy_id_all_viewer_except_host_header = module.company_site_gate[0].origin_request_policy_id_all_viewer_except_host_header
  } : null

  create_dns_records = false

  depends_on = [module.frontend]
}

resource "aws_route53_record" "company_site" {
  for_each = toset(local.company_site_hosts)
  provider = aws.dns

  zone_id = local.company_site_zone_id
  name    = each.value
  type    = "A"

  alias {
    name                   = module.company_site.distribution_domain_name
    zone_id                = module.company_site.distribution_hosted_zone_id
    evaluate_target_health = false
  }
}

moved {
  from = aws_route53_record.legacy_host["webbpulse.com"]
  to   = aws_route53_record.company_site["webbpulse.com"]
}

moved {
  from = aws_route53_record.legacy_host["www.webbpulse.com"]
  to   = aws_route53_record.company_site["www.webbpulse.com"]
}

moved {
  from = module.site_certificate.aws_route53_record.validation["webbpulse.com"]
  to   = module.company_site_certificate.aws_route53_record.validation["webbpulse.com"]
}

moved {
  from = module.site_certificate.aws_route53_record.validation["www.webbpulse.com"]
  to   = module.company_site_certificate.aws_route53_record.validation["www.webbpulse.com"]
}

output "company_site_url" {
  description = "Public URL of the company site"
  value       = module.company_site.frontend_url
}

output "company_site_bucket" {
  description = "S3 bucket the company site deploy syncs into, set as the SITE_S3_BUCKET GitHub environment variable"
  value       = module.company_site.bucket_name
}

output "company_site_distribution_id" {
  description = "CloudFront distribution id of the company site, set as the SITE_CLOUDFRONT_DISTRIBUTION_ID GitHub environment variable"
  value       = module.company_site.distribution_id
}

output "company_site_staging_zone_name_servers" {
  description = "Name servers of the company site staging child zone, null in production or when custom domains are disabled"
  value       = module.company_site_dns.name_servers
}
