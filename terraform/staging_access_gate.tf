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

  source = "app.terraform.io/WebbPulse/platform-modules/aws//modules/staging-access-gate"

  # 2.9 added identity_jwt and identity_jwt_route_keys, which is how a gated
  # environment enforces the identity access token at all. 2.11 is what makes
  # that usable at scale: under 2.9 the enforced route key list travelled to the
  # authorizer Lambda in an environment variable, and a Lambda's whole
  # environment is capped at 4096 bytes, measured only at
  # UpdateFunctionConfiguration. CarModPicker staging hit that cap at 95 route
  # keys with a green plan and a failed apply. 2.11.0 renders the list and the
  # signing public key into the authorizer's deployment package instead, so the
  # environment no longer grows with the number of enforced routes.
  #
  # The inputs below are unchanged; how they reach the function was never part
  # of the module's interface. The bump plans one in-place update of the
  # authorizer function and nothing else.
  version = "~> 2.11"

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

  # Identity access token enforcement, staging's half of it.
  #
  # This is where the gate mode does its work. Every route on this API already
  # carries this module's REQUEST authorizer and an HTTP API route takes
  # exactly one authorizer, so the native JWT authorizer that production will
  # use has no slot here. The gate's own Lambda does both checks instead: the
  # signed cookie first, exactly as before, and then a valid Bearer access
  # token on the routes named below. The gate check still runs first and still
  # has to pass, so this only ever narrows access and can never open anything.
  #
  # The issuer and the audience are the same two locals module.identity is
  # configured with and module.api would be given in native mode, for the same
  # reason: byte identity with what the signer stamps is the entire
  # requirement, and a second spelling of either is a token that verifies
  # nowhere. jwks_url is left to the module, which derives
  # <issuer>/.well-known/jwks.json, and that is the URL this product actually
  # serves, because the discovery document builds jwks_uri the same way.
  identity_jwt = local.identity_jwt_gate_enforced ? {
    issuer   = local.identity_issuer
    audience = local.identity_audience
  } : null

  # THE ROUTE KEYS COME FROM module.api RATHER THAN BEING RESTATED HERE, and
  # that is the whole of the wiring. The output is the set of routes marked
  # require_identity_jwt in terraform/apigateway.tf, already sorted, and a
  # route key is the same string on both sides by construction: it is the map
  # key in that module's routes and it is requestContext.routeKey in this
  # authorizer's event. Listing the seven keys again here would be a second
  # place for the set to drift from the routes it is supposed to describe.
  #
  # Empty in every mode but gate, which is what leaves the authorizer checking
  # only the gate credentials. Both halves have to be set for anything to be
  # enforced: the module's identity_jwt_enforced output is the AND of them.
  identity_jwt_route_keys = local.identity_jwt_gate_enforced ? module.api.identity_jwt_route_keys : []
}
