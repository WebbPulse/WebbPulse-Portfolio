# ---------------------------------------------------------------------------
# HTTP API in front of the Lambda backend.
#
# Behind the staging access gate the API is reachable only through its custom
# domain, where the gate's authorizer applies. The browser calls it directly at
# api.staging.webbpulse.com and the authorizer checks the gate's signed cookies,
# an origin-verify header (pipelines, health checks), or lets an OPTIONS
# preflight through. Both inputs are gated on local.staging_gate_enabled so
# production plans a no-op.
#
# The certificate lives in acm.tf and the api.<domain> alias record in
# route53.tf, because production writes DNS through aws.dns.
#
# Section 3.5 and section 6 of docs/migration/pilot-split-plan.md: the strangler
# runs through this file. Each cut adds route keys for one domain and the
# monolith keeps everything else through $default, so a cut is one map edit and
# a rollback is deleting it again. The cuts so far are recorded in
# docs/migration/cutover-log.md.
# ---------------------------------------------------------------------------

locals {
  # Domains that have been cut over, in cut order. A domain belongs here only
  # once apigateway.tf's routes map names it: the http-api module's
  # every_integration_is_routed check fails the plan on an integration no route
  # can reach, so this list and the routes map below move together.
  #
  # Cut 1 is `public`. Cuts 2 through 4 append resume, content and identity.
  routed_lambda_domains = ["public"]
}

module "api" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/http-api"
  version = "~> 2.0"

  name = "${local.prefix}-api"

  # The monolith plus the four per-domain functions from lambda_domains.tf. The
  # per-domain entries are generated from module.lambda_domain rather than
  # written out one at a time, so a domain added to local.lambda_domains cannot
  # be left without an integration here.
  #
  # Only the domains that have a route are reachable. The module's
  # every_integration_is_routed check refuses an integration nothing can reach,
  # so the three domains still waiting for their cut are deliberately not listed
  # yet: they arrive with their routes in cuts 2 through 4.
  integrations = merge(
    {
      legacy = {
        lambda_function_name           = module.lambda_api.function_name
        lambda_invoke_arn              = module.lambda_api.invoke_arn
        lambda_permission_statement_id = "AllowAPIGatewayInvoke"
      }
    },
    {
      for name in local.routed_lambda_domains : name => {
        lambda_function_name = module.lambda_domain[name].function_name
        lambda_invoke_arn    = module.lambda_domain[name].invoke_arn
      }
    },
  )

  # Cut 1. The monolith moves off its two explicit route keys and onto $default,
  # which is what lets a prefix be carved off it one cut at a time: API Gateway
  # matches a full route key first, then a greedy {proxy+}, then $default last,
  # so everything not named in routes keeps falling through to the monolith and
  # a rollback is deleting the routes entry again.
  default_integration = "legacy"

  # `public`'s four routes, all literal, all unauthenticated in the application
  # and none of them writing. No authorization_type is set on any of them, which
  # means the module's own choice, CUSTOM whenever authorizer_id is set, so each
  # one stays behind the staging access gate exactly as $default does. Setting
  # NONE here would punch a hole straight past the gate.
  routes = {
    "GET /health"      = { integration = "public" }
    "GET /"            = { integration = "public" }
    "GET /sitemap.xml" = { integration = "public" }
    "GET /robots.txt"  = { integration = "public" }
  }

  throttling_burst_limit = 200
  throttling_rate_limit  = 100

  # 7 days, matching the per-domain function log groups in lambda_domains.tf and
  # the retention the platform migration decision settled on. Section 3.5 puts
  # this change in the same file as the first cut, because the access log is
  # what a cut is verified against and both are now read the same way.
  access_log_retention_days = 7

  lambda_permission_statement_id = "AllowAPIGatewayInvoke"

  access_log_format = {
    requestId               = "$context.requestId"
    ip                      = "$context.identity.sourceIp"
    requestTime             = "$context.requestTime"
    httpMethod              = "$context.httpMethod"
    routeKey                = "$context.routeKey"
    path                    = "$context.path"
    status                  = "$context.status"
    responseLength          = "$context.responseLength"
    integrationErrorMessage = "$context.integrationErrorMessage"
    integrationLatency      = "$context.integrationLatency"
  }

  disable_execute_api_endpoint = local.staging_gate_enabled
  authorizer_id                = local.staging_gate_enabled ? one(module.staging_access_gate[*].http_api_authorizer_id) : null

  domain_name     = local.custom_domains_enabled ? local.api_host : null
  certificate_arn = module.api_certificate.certificate_arn
  # zone_id stays null: production writes api.webbpulse.com cross-account through aws.dns.
}
