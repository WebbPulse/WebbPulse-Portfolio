# ---------------------------------------------------------------------------
# Staging access gate
#
# Puts the staging site and API behind a Cognito sign-in for a fixed list of
# email addresses. The module owns Cognito, the login Lambda, the CloudFront
# key group and function, the origin-verify secret and the HTTP API
# authorizer; the distribution and API wiring lives in frontend.tf and
# apigateway.tf, every piece gated on local.staging_gate_enabled so that
# production plans a no-op.
# ---------------------------------------------------------------------------

module "staging_access_gate" {
  count = local.staging_gate_count

  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/staging-access-gate"
  version = "~> 1.3"

  name             = local.prefix
  cookie_domain    = local.domain
  site_host        = local.www_host
  additional_hosts = [local.domain]
  allowed_emails   = var.staging_access_users

  # cloudfront_distribution_arn is left unset on purpose: module.frontend
  # consumes this module's outputs, so naming it here would be a dependency cycle.
  http_api_id      = module.api.api_id
  invite_login_url = "https://${local.www_host}/"

  viewer_request_handler_js = templatefile("${path.module}/cloudfront_functions/app_handler.js.tftpl", {
    domain   = local.domain
    www_host = local.www_host
  })
}
