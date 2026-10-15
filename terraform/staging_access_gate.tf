module "staging_access_gate" {
  count = local.staging_gate_count

  source = "terraform.webbpulse.com/WebbPulse/platform-modules/aws//modules/staging-access-gate"

  version = "~> 2.39"

  name           = local.prefix
  cookie_domain  = local.domain
  site_host      = local.domain
  allowed_emails = var.staging_access_users

  http_api_id      = module.api.api_id
  invite_login_url = "https://${local.domain}/"

  viewer_request_handler_js = module.frontend.viewer_request_handler_js
}
