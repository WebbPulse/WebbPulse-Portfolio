module "staging_access_gate" {
  count = local.staging_gate_count

  source = "app.terraform.io/WebbPulse/platform-modules/aws//modules/staging-access-gate"

  version = "~> 2.12"

  name             = local.prefix
  cookie_domain    = local.domain
  site_host        = local.www_host
  additional_hosts = [local.domain]
  allowed_emails   = var.staging_access_users

  http_api_id      = module.api.api_id
  invite_login_url = "https://${local.www_host}/"

  viewer_request_handler_js = templatefile("${path.module}/cloudfront_functions/app_handler.js.tftpl", {
    domain   = local.domain
    www_host = local.www_host
  })

  identity_jwt = local.identity_jwt_gate_enforced ? {
    issuer   = local.identity_issuer
    audience = local.identity_audience
  } : null

  identity_jwt_route_keys = local.identity_jwt_gate_enforced ? module.api.identity_jwt_route_keys : []
}
