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
# ---------------------------------------------------------------------------

module "api" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/http-api"
  version = "~> 2.0"

  name = "${local.prefix}-api"

  integrations = {
    legacy = {
      lambda_function_name           = module.lambda_api.function_name
      lambda_invoke_arn              = module.lambda_api.invoke_arn
      lambda_permission_statement_id = "AllowAPIGatewayInvoke"
    }
  }

  # The monolith is reached through its two explicit route keys, not $default.
  # Keeping it that way is what makes the adoption plan zero add; $default
  # arrives on the first strangler step.
  default_integration = null

  routes = {
    "ANY /{proxy+}" = { integration = "legacy" }
    "ANY /"         = { integration = "legacy" }
  }

  throttling_burst_limit         = 200
  throttling_rate_limit          = 100
  access_log_retention_days      = 30
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
