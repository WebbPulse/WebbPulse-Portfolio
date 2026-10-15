locals {
  routed_lambda_domains = ["public"]
}

module "api" {
  source = "terraform.webbpulse.com/WebbPulse/platform-modules/aws//modules/http-api"

  version = "~> 2.39"

  name = "${local.prefix}-api"

  integrations = {
    for name in local.routed_lambda_domains : name => {
      lambda_function_name = module.lambda_domain[name].function_name
      lambda_invoke_arn    = module.lambda_domain[name].invoke_arn
    }
  }

  default_integration = null

  routes = {
    "GET /health"                = { integration = "public" }
    "GET /"                      = { integration = "public" }
    "GET /api/v1/public/figures" = { integration = "public" }
  }

  throttling_burst_limit = 200
  throttling_rate_limit  = 100

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

  cors_configuration = {
    allow_origins = split(",", local.cors_origins)
    allow_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allow_headers = [
      "Accept",
      "Accept-Language",
      "Authorization",
      "Content-Language",
      "Content-Type",
      "Origin",
      "X-Request-ID",
      "X-Retry-Attempt",
    ]
    allow_credentials = true
    max_age           = 86400
  }

  disable_execute_api_endpoint = local.staging_gate_enabled
  authorizer_id                = local.staging_gate_enabled ? one(module.staging_access_gate[*].http_api_authorizer_id) : null

  domain_name     = local.custom_domains_enabled ? local.api_host : null
  certificate_arn = module.api_certificate.certificate_arn
}
